from __future__ import annotations

import json
import time

from app.cell.ctx import RobotTask
from app.cell.enums import CmdStatus
from app.cell.printer_interface import WebApiPrinterClient
from app.cell.sequence import Sequence
from app.core.config import get_settings

# Module role:
# - take one queued job assigned to this printer
# - optionally talk to the real web-api print server
# - or, when PRINTER_SERVER_SIMUL=true, fake only the printer-server part
# - after print completion, request robot transfer to washing


class PrinterSequence(Sequence):
    STEP0000 = 0
    STEP0010 = 10  # receive one queued command and occupy the printer
    STEP0020 = 20  # upload file to printer server
    STEP0030 = 30  # upload complete handling / start-print preparation
    STEP0040 = 40  # send start-print request
    STEP0050 = 50  # wait print complete (poll printer status)
    STEP0060 = 60  # request robot SW
    STEP0070 = 70  # wait robot SW ack
    STEP10000 = 10000

    def __init__(self, runtime_ctx, printer_id: int) -> None:
        super().__init__(f'PrinterSequence-{printer_id}')
        self.ctx = runtime_ctx
        self.printer_id = printer_id
        self._settings = get_settings()
        self._client = WebApiPrinterClient(
            base_url=self._settings.WEB_API_BASE_URL,
            timeout_seconds=self._settings.WEB_API_TIMEOUT_SECONDS,
        )
        # Full SIMUL_MODE means the whole cell runs in simulation style.
        # PRINTER_SERVER_SIMUL means only the printer server/API part is faked,
        # while the rest of the cell flow can still use real robot communication.
        self._printer_server_simul = bool(self._settings.PRINTER_SERVER_SIMUL)
        self._robot_req_sent = False
        self._next_status_poll_ts: float = 0.0
        self._sim_finish_ts: float = 0.0
        self._sim_wait_seconds: int = 15
        self._uploaded_filename: str = ''
        self._step_wait_until: float = 0.0
        self._last_api_log_by_label: dict[str, str] = {}

    def sequence_logic(self, step: int) -> None:
        if self._step_wait_until and time.time() < self._step_wait_until:
            return
        if self._step_wait_until and time.time() >= self._step_wait_until:
            self._step_wait_until = 0.0

        # Command currently occupying this printer (if any)
        current_cmd = self.ctx.printer_active_cmd[self.printer_id]

        if step == self.STEP0000:
            # Recovery rule: if STEP0000 still holds a non-canceled cmd, drop it and re-pick.
            if current_cmd is not None:
                stale = self.ctx.active_jobs.get(current_cmd)
                if stale is not None and stale.cmd_status != CmdStatus.CANCELED:
                    self.ctx.repo.update_command(
                        stale.cmd_id,
                        message=f'{self.sequence_name}: dropped stale cmd at STEP0000',
                    )
                self.ctx.printer_active_cmd[self.printer_id] = None
                self.ctx.printer_use[self.printer_id] = 'Y'
                self._robot_req_sent = False
                self._next_status_poll_ts = 0.0
                self._sim_finish_ts = 0.0
                self._uploaded_filename = ''
                self._last_api_log_by_label.clear()
                current_cmd = None

            # IDLE:
            # - if command exists, continue current flow
            # - else start next command from printer queue
            if current_cmd is not None:
                job = self.ctx.active_jobs.get(current_cmd)
                if job and job.cmd_status == CmdStatus.PRINT_FINISHED:
                    self.now_step = self.STEP0060
                elif job:
                    self.now_step = self.STEP0050
                else:
                    self.now_step = self.STEP10000
            elif self.ctx.printer_queues[self.printer_id]:
                self.now_step = self.STEP0010
            return

        if step == self.STEP0010:
            # RECEIVE COMMAND:
            # 1) take one queued cmd for this printer
            # 2) occupy the printer
            # 3) prepare local state for upload/start sequence
            if self.ctx.paused:
                return
            if not self.ctx.printer_has_plate[self.printer_id]:
                self.now_step = self.STEP10000
                return
            if current_cmd is None and not self.ctx.printer_queues[self.printer_id]:
                self.now_step = self.STEP10000
                return

            if current_cmd is None:
                cmd_id = self.ctx.printer_queues[self.printer_id].popleft()
                job = self.ctx.active_jobs.get(cmd_id)
                if job is None:
                    self.now_step = self.STEP10000
                    return

                self.ctx.printer_active_cmd[self.printer_id] = cmd_id
                self.ctx.printer_use[self.printer_id] = 'N'
                self._next_status_poll_ts = 0.0
                self._uploaded_filename = ''
            else:
                cmd_id = current_cmd
                job = self.ctx.active_jobs.get(cmd_id)

            if job is None:
                self.ctx.printer_active_cmd[self.printer_id] = None
                self.now_step = self.STEP10000
                return

            if self.ctx.simul_mode or self._printer_server_simul:
                # In simulation modes, skip upload/start entirely and move directly
                # to the print-complete wait phase with a short timer.
                job.cmd_status = CmdStatus.PRINTING
                job.progress = max(1, job.progress)
                job.target_printer = self.printer_id
                job.allocated_data['printer_id'] = self.printer_id
                job.allocated_data['plate_state'] = 'ON_PRINTER'
                job.allocated_data['plate_in_printer'] = True
                job.allocated_data['simul_mode'] = bool(self.ctx.simul_mode)
                job.allocated_data['printer_server_simul'] = bool(self._printer_server_simul)
                # In simulation modes, never call the real printer API.
                # We mark PRINTING first, then finish after a short fixed timer.
                self._sim_finish_ts = time.time() + self._sim_wait_seconds
                self.ctx.repo.update_command(
                    cmd_id,
                    cmd_status=int(CmdStatus.PRINTING),
                    target_printer=self.printer_id,
                    progress=job.progress,
                    allocated_data=job.allocated_data,
                    message=(
                        f'PRINTING({"full-sim" if self.ctx.simul_mode else "printer-server-sim"} '
                        f'{self._sim_wait_seconds}s) on printer-{self.printer_id}'
                    ),
                )
                self._go_next(self.STEP0050)
                return

            self.ctx.repo.update_command(
                cmd_id,
                message=f'PRINTER_CMD_ACCEPTED printer-{self.printer_id}',
            )
            self._go_next(self.STEP0020)
            return

        if step == self.STEP0020:
            # UPLOAD FILE:
            # 1) precheck printer readiness
            # 2) upload file to web-api
            cmd_id = self.ctx.printer_active_cmd[self.printer_id]
            if cmd_id is None:
                self.now_step = self.STEP10000
                return

            job = self.ctx.active_jobs.get(cmd_id)
            if job is None:
                self.ctx.printer_active_cmd[self.printer_id] = None
                self.now_step = self.STEP10000
                return

            upload_ok, uploaded_filename, upload_error = self._upload_print_file(job)
            if not upload_ok:
                self._mark_aborted_and_release(job, f'ABORT: upload failed after retries: {upload_error}')
                return

            self._uploaded_filename = uploaded_filename
            job.allocated_data['printer_serial'] = self._resolve_printer_serial()
            job.allocated_data['uploaded_filename'] = uploaded_filename
            self.ctx.repo.update_command(
                cmd_id,
                allocated_data=job.allocated_data,
                message=f'UPLOAD_FINISHED file={uploaded_filename}',
            )
            self._go_next(self.STEP0030)
            return

        if step == self.STEP0030:
            # UPLOAD COMPLETE CHECK / PRINT START PREP:
            # keep this as a dedicated step so the sequence visibly pauses here
            # before sending the actual start-print request.
            cmd_id = self.ctx.printer_active_cmd[self.printer_id]
            if cmd_id is None:
                self.now_step = self.STEP10000
                return
            job = self.ctx.active_jobs.get(cmd_id)
            if job is None:
                self.ctx.printer_active_cmd[self.printer_id] = None
                self.now_step = self.STEP10000
                return

            if not self._uploaded_filename:
                self._mark_aborted_and_release(job, 'ABORT: uploaded filename missing before start-print')
                return
            self.ctx.repo.update_command(
                cmd_id,
                allocated_data=job.allocated_data,
                message=f'UPLOAD_CONFIRMED ready_to_start file={self._uploaded_filename}',
            )
            self._go_next(self.STEP0040)
            return

        if step == self.STEP0040:
            # START PRINT:
            # request actual print start after upload has completed.
            cmd_id = self.ctx.printer_active_cmd[self.printer_id]
            if cmd_id is None:
                self.now_step = self.STEP10000
                return
            job = self.ctx.active_jobs.get(cmd_id)
            if job is None:
                self.ctx.printer_active_cmd[self.printer_id] = None
                self.now_step = self.STEP10000
                return

            start_ok, start_error = self._start_uploaded_print(job, self._uploaded_filename)
            if not start_ok:
                self._mark_aborted_and_release(job, f'ABORT: start print failed after retries: {start_error}')
                return

            job.cmd_status = CmdStatus.PRINTING
            job.progress = max(1, job.progress)
            job.target_printer = self.printer_id
            job.allocated_data['printer_id'] = self.printer_id
            job.allocated_data['plate_state'] = 'ON_PRINTER'
            job.allocated_data['plate_in_printer'] = True
            job.allocated_data['seen_printing'] = False
            self._next_status_poll_ts = 0.0
            self._last_api_log_by_label.clear()

            self.ctx.repo.update_command(
                cmd_id,
                cmd_status=int(CmdStatus.PRINTING),
                target_printer=self.printer_id,
                progress=job.progress,
                allocated_data=job.allocated_data,
                message=f'PRINT_REQUEST_ACCEPTED on printer-{self.printer_id}',
            )
            self._go_next(self.STEP0050)
            return

        if step == self.STEP0050:
            # WAIT PRINT COMPLETE:
            # poll web-api /api/v1/printers/{serial} and detect FINISHED/ERROR
            cmd_id = self.ctx.printer_active_cmd[self.printer_id]
            if cmd_id is None:
                self.now_step = self.STEP10000
                return

            job = self.ctx.active_jobs.get(cmd_id)
            if job is None:
                self.ctx.printer_active_cmd[self.printer_id] = None
                self.now_step = self.STEP10000
                return

            if self.ctx.simul_mode or self._printer_server_simul:
                if time.time() < self._sim_finish_ts:
                    return
                job.cmd_status = CmdStatus.PRINT_FINISHED
                job.progress = 100
                job.allocated_data['plate_state'] = 'PRINT_DONE_ON_PRINTER'
                self.ctx.repo.update_command(
                    cmd_id,
                    cmd_status=int(CmdStatus.PRINT_FINISHED),
                    progress=job.progress,
                    allocated_data=job.allocated_data,
                    message=(
                        f'PRINT_FINISHED({"full-sim" if self.ctx.simul_mode else "printer-server-sim"}) '
                        f'on printer-{self.printer_id}'
                    ),
                )
                self._robot_req_sent = False
                self._go_next(self.STEP0060)
                return

            if time.time() < self._next_status_poll_ts:
                return

            self._next_status_poll_ts = time.time() + max(1.0, self._settings.PRINTER_STATUS_POLL_SECONDS)

            local_job_id = str(job.allocated_data.get('local_print_job_id') or '').strip()
            if local_job_id:
                local_job_resp = self._client.get_local_print_job(local_job_id)
                self._log_api_response(job, 'LOCAL_PRINT_JOB_API', local_job_resp)
                if not local_job_resp.get('ok'):
                    self.ctx.repo.update_command(
                        job.cmd_id,
                        allocated_data=job.allocated_data,
                        message=f'local print job poll failed: {local_job_resp.get("error", "unknown error")}',
                    )
                    return

                local_job = local_job_resp.get('data') or {}
                local_status = str(local_job.get('status') or '').lower()
                job.allocated_data['local_print_status'] = local_status
                scene_id = local_job.get('scene_id')
                if scene_id:
                    job.allocated_data['scene_id'] = scene_id

                if local_status == 'failed':
                    error_message = str(local_job.get('error_message') or 'local print job failed')
                    self._mark_error_and_release(job, error_message, block_printer=False)
                    self.now_step = self.STEP10000
                    return

                if local_status not in {'sent'}:
                    self.ctx.repo.update_command(
                        job.cmd_id,
                        progress=job.progress,
                        allocated_data=job.allocated_data,
                        message=f'local print job status={local_status or "pending"}',
                    )
                    return

            serial = str(job.allocated_data.get('printer_serial') or self._resolve_printer_serial())
            if not serial:
                self._mark_error_and_release(job, 'printer serial not configured', block_printer=False)
                self.now_step = self.STEP10000
                return

            status_resp = self._client.get_printer_summary(serial)
            self._log_api_response(job, 'PRINTER_STATUS_API', status_resp)
            if not status_resp.get('ok'):
                self.ctx.repo.update_command(
                    job.cmd_id,
                    message=f'printer status poll failed: {status_resp.get("error", "unknown error")}',
                )
                return

            summary = status_resp.get('data') or {}
            status = str(summary.get('status') or '').upper()
            progress_percent = summary.get('progress_percent')
            if isinstance(progress_percent, (int, float)):
                job.progress = max(job.progress, min(100, int(progress_percent)))
            job.allocated_data['printer_status'] = status

            if status in {'ERROR', 'ABORTED'}:
                self._mark_error_and_release(job, f'printer reported {status}', block_printer=True)
                self.now_step = self.STEP10000
                return

            if status in {'PRINTING', 'PREHEAT', 'PREPRINT', 'PRECOAT', 'POSTCOAT', 'PAUSING', 'PAUSED'}:
                job.allocated_data['seen_printing'] = True
                last_logged_status = str(job.allocated_data.get('last_logged_printer_status') or '').upper()
                if last_logged_status != status:
                    job.allocated_data['last_logged_printer_status'] = status
                    self.ctx.repo.update_command(
                        job.cmd_id,
                        progress=job.progress,
                        allocated_data=job.allocated_data,
                        message=f'printer-{self.printer_id} status={status}',
                    )
                return

            if job.allocated_data.get('seen_printing') and status in {'FINISHED', 'IDLE'}:
                job.cmd_status = CmdStatus.PRINT_FINISHED
                job.progress = 100
                job.allocated_data['plate_state'] = 'PRINT_DONE_ON_PRINTER'
                job.allocated_data.pop('last_logged_printer_status', None)

                self.ctx.repo.update_command(
                    cmd_id,
                    cmd_status=int(CmdStatus.PRINT_FINISHED),
                    progress=job.progress,
                    allocated_data=job.allocated_data,
                    message=f'PRINT_FINISHED on printer-{self.printer_id}',
                )
                self._robot_req_sent = False
                self._go_next(self.STEP0060)
                return

        if step == self.STEP0060:
            # REQUEST ROBOT(SW): StartWashing (printer -> wash transfer)
            cmd_id = self.ctx.printer_active_cmd[self.printer_id]
            if cmd_id is None:
                self.now_step = self.STEP10000
                return
            job = self.ctx.active_jobs.get(cmd_id)
            if job is None:
                self.ctx.printer_active_cmd[self.printer_id] = None
                self.now_step = self.STEP10000
                return

            if not self._robot_req_sent:
                task = RobotTask(
                    cmd_id=cmd_id,
                    task_type='SW',
                    from_unit=f'printer-{self.printer_id}',
                    to_unit='wash',
                    requested_by=self.sequence_name,
                )
                self.ctx.robot_queue.append(task)
                self._robot_req_sent = True
                self.ctx.repo.update_command(
                    cmd_id,
                    allocated_data=job.allocated_data,
                    message=f'ROBOT_REQ SW queued by printer-{self.printer_id}',
                )
            self._go_next(self.STEP0070)
            return

        if step == self.STEP0070:
            # WAIT ROBOT ACK(SW)
            cmd_id = self.ctx.printer_active_cmd[self.printer_id]
            if cmd_id is None:
                self.now_step = self.STEP10000
                return
            ack_key = f'{cmd_id}:SW'
            if not self.ctx.robot_acks.get(ack_key, False):
                return
            self.ctx.robot_acks.pop(ack_key, None)
            self.ctx.printer_active_cmd[self.printer_id] = None
            self._robot_req_sent = False
            self._next_status_poll_ts = 0.0
            self._uploaded_filename = ''
            self._go_next(self.STEP10000)
            return

        if step == self.STEP10000:
            self.now_step = self.STEP0000
            return

    def machine_stop_logic(self) -> None:
        self.ctx.printer_active_cmd[self.printer_id] = None
        self.ctx.printer_use[self.printer_id] = 'Y'
        self._robot_req_sent = False
        self._next_status_poll_ts = 0.0
        self._sim_finish_ts = 0.0
        self._uploaded_filename = ''
        self._step_wait_until = 0.0
        self._last_api_log_by_label.clear()

    def machine_pause_logic(self) -> None:
        pass

    def origin_logic(self) -> bool:
        return True

    def get_db_info(self) -> None:
        pass

    def save_data(self) -> None:
        pass

    def init(self) -> None:
        pass

    def step_update_to_db(self, cmd_id: str, now_step: str, is_complete: bool, remark: str) -> None:
        if cmd_id:
            self.ctx.repo.update_command(cmd_id, message=f'{self.sequence_name}:{now_step}:{remark}')

    def _resolve_printer_serial(self) -> str:
        serial = self._settings.PRINTER_SERIAL_MAP.get(self.printer_id)
        return str(serial or '').strip()

    def _go_next(self, next_step: int) -> None:
        self.now_step = next_step
        delay = max(0.0, float(getattr(self._settings, 'PRINTER_STEP_DELAY_SECONDS', 0.0)))
        if delay > 0:
            self._step_wait_until = time.time() + delay

    def _upload_print_file(self, job) -> tuple[bool, str, str]:
        # Real printer-server mode:
        # 1) precheck printer readiness
        # 2) upload the file to web-api
        serial = self._resolve_printer_serial()
        if not serial:
            return False, '', f'no serial configured for printer-{self.printer_id}'
        precheck_retries = max(1, int(getattr(self._settings, 'PRINT_PRECHECK_RETRIES', 3)))
        upload_retries = max(1, int(getattr(self._settings, 'PRINT_UPLOAD_RETRIES', 3)))

        last_precheck_error = 'unknown error'
        for attempt in range(1, precheck_retries + 1):
            ready, detail = self._precheck_printer_ready(serial)
            if ready:
                self.ctx.repo.update_command(
                    job.cmd_id,
                    message=f'printer precheck success ({attempt}/{precheck_retries})',
                )
                break
            last_precheck_error = detail
            self.ctx.repo.update_command(
                job.cmd_id,
                message=f'printer precheck retry {attempt}/{precheck_retries} failed: {detail}',
            )
        else:
            return False, '', f'printer precheck failed: {last_precheck_error}'

        upload_resp: dict = {}
        uploaded_filename = str(job.file_name or '')
        last_upload_error = 'unknown error'
        for attempt in range(1, upload_retries + 1):
            upload_resp = self._client.upload_file(job.file_path)
            self._log_api_response(job, f'UPLOAD_API attempt={attempt}', upload_resp)
            if upload_resp.get('ok'):
                upload_data = upload_resp.get('data') or {}
                uploaded_filename = str(upload_data.get('filename') or job.file_name)
                self.ctx.repo.update_command(
                    job.cmd_id,
                    message=f'upload success ({attempt}/{upload_retries})',
                )
                break
            last_upload_error = str(upload_resp.get("error", "unknown error"))
            self.ctx.repo.update_command(
                job.cmd_id,
                message=f'upload retry {attempt}/{upload_retries} failed: {last_upload_error}',
            )
        else:
            return False, '', f'upload failed: {last_upload_error}'

        return True, uploaded_filename, ''

    def _start_uploaded_print(self, job, uploaded_filename: str) -> tuple[bool, str]:
        serial = self._resolve_printer_serial()
        if not serial:
            return False, f'no serial configured for printer-{self.printer_id}'

        print_settings = self._build_print_settings(job)
        preset_id = str((getattr(job, 'allocated_data', {}) or {}).get('preset_id') or '').strip() or None
        start_retries = max(1, int(getattr(self._settings, 'PRINT_START_RETRIES', 3)))
        print_resp: dict = {}
        last_start_error = 'unknown error'
        for attempt in range(1, start_retries + 1):
            print_resp = self._client.start_print(
                stl_file=uploaded_filename,
                printer_serial=serial,
                simul_mode=bool(self.ctx.simul_mode),
                preset_id=preset_id,
                settings=print_settings,
            )
            self._log_api_response(job, f'START_PRINT_API attempt={attempt}', print_resp)
            if print_resp.get('ok'):
                self.ctx.repo.update_command(
                    job.cmd_id,
                    message=f'start print success ({attempt}/{start_retries})',
                )
                break
            last_start_error = str(print_resp.get("error", "unknown error"))
            self.ctx.repo.update_command(
                job.cmd_id,
                message=f'start print retry {attempt}/{start_retries} failed: {last_start_error}',
            )
        else:
            return False, f'start print failed: {last_start_error}'

        print_data = print_resp.get('data') or {}
        job.allocated_data['printer_serial'] = serial
        job.allocated_data['uploaded_filename'] = uploaded_filename
        job.allocated_data['local_print_job_id'] = print_data.get('id')
        job.allocated_data['print_settings'] = print_settings
        job.allocated_data['seen_printing'] = False
        return True, ''

    def _build_print_settings(self, job) -> dict:
        preset_settings = (getattr(job, 'allocated_data', {}) or {}).get('print_settings')
        if isinstance(preset_settings, dict):
            return preset_settings
        return {
            'machine_type': str(self._settings.PRINT_MACHINE_TYPE),
            'material_code': str(self._settings.PRINT_MATERIAL_CODE),
            'layer_thickness_mm': float(self._settings.PRINT_LAYER_THICKNESS_MM),
            'orientation': {
                'x_rotation': 0.0,
                'y_rotation': 0.0,
                'z_rotation': 0.0,
            },
            'support': {
                'density': str(self._settings.PRINT_SUPPORT_DENSITY),
                'touchpoint_size': float(self._settings.PRINT_SUPPORT_TOUCHPOINT_SIZE),
                'internal_supports': bool(self._settings.PRINT_SUPPORT_INTERNALS),
            },
        }

    def _precheck_printer_ready(self, serial: str) -> tuple[bool, str]:
        # Ready means the printer can accept a new print request now.
        status_resp = self._client.get_printer_summary(serial)
        cmd_id = self.ctx.printer_active_cmd.get(self.printer_id)
        if cmd_id:
            job = self.ctx.active_jobs.get(cmd_id)
            if job is not None:
                self._log_api_response(job, 'PRINTER_PRECHECK_API', status_resp)
        if not status_resp.get('ok'):
            return False, str(status_resp.get("error", "status read failed"))
        summary = status_resp.get('data') or {}
        status = str(summary.get('status') or '').upper()
        if status in {'IDLE', 'READY', 'FINISHED'}:
            return True, status or 'IDLE'
        return False, f'not ready status={status or "UNKNOWN"}'


    def _log_api_response(self, job, label: str, resp: dict) -> None:
        try:
            payload = {
                'ok': bool(resp.get('ok')),
                'status_code': resp.get('status_code'),
            }
            if resp.get('ok'):
                payload['data'] = resp.get('data')
            else:
                payload['error'] = resp.get('error')
            raw = json.dumps(payload, ensure_ascii=False, default=str, separators=(',', ':'))
        except Exception:
            raw = str(resp)
        if len(raw) > 900:
            raw = raw[:900] + '...'
        last_raw = self._last_api_log_by_label.get(label)
        if last_raw == raw:
            return
        self._last_api_log_by_label[label] = raw
        self.ctx.repo.update_command(
            job.cmd_id,
            allocated_data=job.allocated_data,
            message=f'{label}: {raw}',
        )
    def _mark_aborted_and_release(self, job, message: str) -> None:
        job.cmd_status = CmdStatus.CANCELED
        job.message = message
        job.allocated_data['abort_reason'] = message
        self.ctx.repo.update_command(
            job.cmd_id,
            cmd_status=int(CmdStatus.CANCELED),
            allocated_data=job.allocated_data,
            message=message,
        )
        self.ctx.active_jobs.pop(job.cmd_id, None)
        self.ctx.printer_active_cmd[self.printer_id] = None
        self.ctx.printer_use[self.printer_id] = 'Y'
        self._uploaded_filename = ''
        self._last_api_log_by_label.clear()
        self.now_step = self.STEP10000

    def _mark_error_and_release(self, job, message: str, block_printer: bool) -> None:
        job.cmd_status = CmdStatus.ERROR
        job.message = message
        job.allocated_data['error'] = message
        job.allocated_data['plate_state'] = 'ERROR_ON_PRINTER' if block_printer else 'ON_PRINTER'
        self.ctx.repo.update_command(
            job.cmd_id,
            cmd_status=int(CmdStatus.ERROR),
            allocated_data=job.allocated_data,
            message=message,
        )
        self.ctx.active_jobs.pop(job.cmd_id, None)
        self.ctx.printer_active_cmd[self.printer_id] = None
        self.ctx.printer_use[self.printer_id] = 'N' if block_printer else 'Y'
        self._uploaded_filename = ''
        self._last_api_log_by_label.clear()


