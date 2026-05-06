from __future__ import annotations

import time

from app.cell.ctx import RobotTask
from app.cell.enums import CmdStatus, PostProcStage, LogType
from app.cell.modbus_protocol import ModbusHandshakeClient
from app.cell.sequence import Sequence
from app.core.config import get_settings

# Module role:
# - consume robot tasks requested by printer/washing/curing sequences
# - choose which robot task can run now based on equipment availability
# - send the task to either ST-TCP or Modbus
# - after a successful robot move, update RuntimeCtx and publish ACK


class RobotSequence(Sequence):
    STEP0000 = 0
    STEP0010 = 10
    STEP0020 = 20
    STEP0030 = 30
    STEP0040 = 40
    STEP0050 = 50
    STEP0060 = 60
    STEP0070 = 70
    STEP0080 = 80
    STEP0090 = 90
    STEP10000 = 10000

    def __init__(self, runtime_ctx) -> None:
        super().__init__('RobotSequence')
        self.ctx = runtime_ctx
        self._settings = get_settings()
        self._current_task: RobotTask | None = None
        self._busy_until: float = 0.0
        self._next_tcp_retry_ts: float = 0.0
        self._next_comm_config_sync_ts: float = 0.0
        self._pc_ready_off_due_ts: float = 0.0
        self._idle_reset_done: bool = False
        self._robot_modbus = ModbusHandshakeClient(
            host=self._settings.ROBOT_TCP_HOST,
            port=self._settings.ROBOT_TCP_PORT,
            timeout_seconds=self._settings.ROBOT_TCP_TIMEOUT_SECONDS,
            slave_id=self._settings.ROBOT_MODBUS_SLAVE_ID,
        )

    @property
    def _use_real_io(self) -> bool:
        return bool(self._settings.ENABLE_TCP_IO) and not self.ctx.simul_mode

    def _log_job(self, cmd_id: str, msg: str, allocated_data: dict | None = None) -> None:
        # Keep robot-origin logs grouped in the common command log table.
        fields: dict = {
            "message": msg,
            "_log_type": int(LogType.ROBOT),
            "_log_source": "robot",
        }
        if allocated_data is not None:
            fields["allocated_data"] = allocated_data
        self.ctx.repo.update_command(cmd_id, **fields)

    def _normalize_task_type(self, task_type: str) -> str:
        # Backward compatibility for legacy task names from earlier revisions.
        mapping = {
            'W': 'FW',
            'R': 'SC',
            'C': 'FC',
        }
        return mapping.get(task_type, task_type)

    def _select_executable_task(self) -> RobotTask | None:
        # Pick one runnable robot task from robot_queue.
        #
        # Priority order:
        # FC > SC > FW > SW/P
        #
        # The reason is:
        # - finish-cure/output should not block
        # - start-cure depends on reserved cure slots
        # - finish-washing needs an empty printer + cure slot
        # - printer offload to washing can wait slightly longer
        if not self.ctx.robot_queue:
            return None

        def _priority(task_type: str) -> int:
            task_type = self._normalize_task_type(task_type)
            # Required execution order: FC > SC > FW > SW > P
            if task_type == 'FC':
                return 0
            if task_type == 'SC':
                return 1
            if task_type == 'FW':
                return 2
            if task_type == 'SW':
                return 3
            if task_type == 'P':
                return 4
            return 5

        def _find_free_wash() -> int | None:
            return next((wid for wid, c in self.ctx.wash_active_cmd.items() if c is None), None)

        def _find_free_printer_without_plate() -> int | None:
            return next(
                (
                    pid
                    for pid in sorted(self.ctx.printer_has_plate.keys())
                    if (not self.ctx.printer_has_plate.get(pid, False))
                    and self.ctx.printer_active_cmd.get(pid) is None
                    and len(self.ctx.printer_queues.get(pid, [])) == 0
                ),
                None,
            )

        def _find_free_cure() -> int | None:
            return next((cid for cid, c in self.ctx.cure_active_cmd.items() if c is None), None)

        def _all_busy(active_map: dict[int, str | None]) -> bool:
            return all(v is not None for v in active_map.values())

        candidates = list(self.ctx.robot_queue)
        candidates.sort(key=lambda t: _priority(t.task_type))

        for task in candidates:
            task.task_type = self._normalize_task_type(task.task_type)
            job = self.ctx.active_jobs.get(task.cmd_id)
            if job is None:
                try:
                    self.ctx.robot_queue.remove(task)
                except ValueError:
                    pass
                continue

            if task.task_type in {'SW', 'P'}:
                # SW/P = printer -> washing.
                # Limit how many printers can sit without a plate at the same time.
                waiting_plate_printers = sum(1 for has_plate in self.ctx.printer_has_plate.values() if not has_plate)
                if waiting_plate_printers >= 2:
                    continue
                # A washing destination must exist before the move is allowed.
                if _all_busy(self.ctx.wash_active_cmd):
                    continue
                free_wash = _find_free_wash()
                if free_wash is None:
                    continue
                job.allocated_data['wash_id'] = free_wash
                self._log_job(
                    job.cmd_id,
                    f'ROBOT PLAN P: assign wash={free_wash} (printer={job.allocated_data.get("printer_id") or job.target_printer})',
                    job.allocated_data,
                )

            elif task.task_type == 'FW':
                # FW = wash -> empty printer, and the workflow reserves a cure slot too.
                if _all_busy(self.ctx.cure_active_cmd):
                    continue
                free_printer = _find_free_printer_without_plate()
                free_cure = _find_free_cure()
                if free_printer is None or free_cure is None:
                    continue
                job.allocated_data['parking_printer_id'] = free_printer
                job.allocated_data['cure_id'] = free_cure
                task.to_unit = f'printer-{free_printer}'
                # Reserve the cure slot immediately so another job cannot steal it.
                self.ctx.cure_active_cmd[free_cure] = job.cmd_id
                self._log_job(
                    job.cmd_id,
                    f'ROBOT PLAN FW: reserve printer={free_printer}, cure={free_cure}, wash={job.allocated_data.get("wash_id")}',
                    job.allocated_data,
                )
            elif task.task_type == 'SC':
                # SC exists in the sequence model for compatibility.
                # In the current preferred flow, FW already includes the cure handoff.
                cure_id = int(job.allocated_data.get('cure_id') or 0)
                if cure_id <= 0:
                    continue
                holder = self.ctx.cure_active_cmd.get(cure_id)
                if holder not in (None, job.cmd_id):
                    continue
                task.to_unit = f'cure-{cure_id}'
                self._log_job(
                    job.cmd_id,
                    f'ROBOT PLAN SC: cure={cure_id} holder={holder}',
                    job.allocated_data,
                )
            elif task.task_type == 'FC':
                # FC = cure -> output. No printer-state gating is needed here.
                task.to_unit = 'output'
                self._log_job(
                    job.cmd_id,
                    f'ROBOT PLAN FC: cure={job.allocated_data.get("cure_id")}',
                    job.allocated_data,
                )

            try:
                self.ctx.robot_queue.remove(task)
            except ValueError:
                return None
            return task

        return None

    def _complete_task(self, task: RobotTask) -> None:
        # Update RuntimeCtx after the physical robot move has succeeded.
        # This is where printer/wash/cure ownership and downstream queues are advanced.
        job = self.ctx.active_jobs.get(task.cmd_id)
        if job is None:
            self.ctx.robot_acks[task.ack_key] = True
            return

        if task.task_type in {'SW', 'P'}:
            # SW/P: printing finished -> move plate from printer to washing machine.
            printer_id = int(job.allocated_data.get('printer_id') or job.target_printer or 0)
            wash_id = int(job.allocated_data.get('wash_id') or 0)
            if printer_id in self.ctx.printer_has_plate:
                self.ctx.printer_has_plate[printer_id] = False
                self.ctx.printer_use[printer_id] = 'N'

            job.cmd_status = CmdStatus.POST_PROCESSING
            job.post_proc_stage = PostProcStage.WASHING
            job.allocated_data['plate_in_printer'] = False
            job.allocated_data['plate_state'] = 'IN_WASHER_WITH_PLATE'
            self.ctx.wash_waiting.append(job.cmd_id)
            self.ctx.repo.update_command(
                job.cmd_id,
                cmd_status=int(CmdStatus.POST_PROCESSING),
                post_proc_stage=int(PostProcStage.WASHING),
                allocated_data=job.allocated_data,
                message=f'ROBOT SW done: printer->{wash_id}',
                _log_type=int(LogType.ROBOT),
                _log_source='robot',
            )
        elif task.task_type == 'FW':
            # FW: take the plate out of washing, drop it on an empty printer,
            # and continue the overall job toward curing.
            printer_id = int(
                job.allocated_data.get('parking_printer_id')
                or job.allocated_data.get('printer_id')
                or job.target_printer
                or 0
            )
            if printer_id <= 0 and isinstance(task.to_unit, str) and task.to_unit.startswith('printer-'):
                try:
                    printer_id = int(task.to_unit.split('-', 1)[1])
                except Exception:
                    printer_id = 0
            cure_id = int(job.allocated_data.get('cure_id') or 0)
            if printer_id in self.ctx.printer_has_plate:
                # Plate has been parked back on a printer, so that printer becomes populated again.
                self.ctx.printer_has_plate[printer_id] = True
                self.ctx.printer_use[printer_id] = 'Y'
            if printer_id > 0:
                job.target_printer = printer_id
                job.allocated_data['parking_printer_id'] = printer_id
                job.allocated_data['printer_id'] = printer_id
            job.post_proc_stage = PostProcStage.CURE_WAITING
            job.allocated_data['plate_in_printer'] = True
            job.allocated_data['plate_state'] = 'PARKED_ON_EMPTY_PRINTER_AFTER_WASH'
            job.allocated_data['fw_started_cure'] = True
            self.ctx.cure_waiting.append(job.cmd_id)
            self.ctx.repo.update_command(
                job.cmd_id,
                target_printer=printer_id if printer_id > 0 else job.target_printer,
                post_proc_stage=int(PostProcStage.CURE_WAITING),
                allocated_data=job.allocated_data,
                message=f'ROBOT FW done: wash->{printer_id}->cure-{cure_id}, printer plate/use ON',
                _log_type=int(LogType.ROBOT),
                _log_source='robot',
            )
            if printer_id <= 0:
                self._log_job(
                    job.cmd_id,
                    'ROBOT FW warning: printer_id unresolved, could not force printer plate/use ON',
                    job.allocated_data,
                )
        elif task.task_type == 'SC':
            # SC: modeled separately, but today this is often skipped because FW already
            # implies the handoff into the cure flow.
            cure_id = int(job.allocated_data.get('cure_id') or 0)
            # SC must not toggle printer plate/use flags.
            job.allocated_data['plate_state'] = 'IN_CURE_WAITING'
            self.ctx.repo.update_command(
                job.cmd_id,
                allocated_data=job.allocated_data,
                message=f'ROBOT SC done: move->cure-{cure_id}',
                _log_type=int(LogType.ROBOT),
                _log_source='robot',
            )
        elif task.task_type == 'FC':
            # FC: curing finished -> discharge the part to output.
            # No printer ownership changes are required here.
            job.allocated_data['plate_state'] = 'OUTPUT_DISCHARGED'
            self.ctx.repo.update_command(
                job.cmd_id,
                allocated_data=job.allocated_data,
                message='ROBOT FC done: cure->output discharged',
                _log_type=int(LogType.ROBOT),
                _log_source='robot',
            )

        self._log_job(task.cmd_id, f'ROBOT ACK SET: {task.ack_key}')
        self.ctx.robot_acks[task.ack_key] = True

    def _modbus_command_value(self, task_type: str) -> int:
        # IO map command values written into register 130.
        t = self._normalize_task_type(task_type)
        if t in {'SW', 'P'}:
            return int(self._settings.ROBOT_MODBUS_CMD_PRINTING_VALUE)
        if t == 'FW':
            return int(self._settings.ROBOT_MODBUS_CMD_FW_VALUE)
        if t == 'FC':
            return int(self._settings.ROBOT_MODBUS_CMD_FC_VALUE)
        raise ValueError(f'unsupported modbus task_type: {t}')

    def _modbus_params(self, task: RobotTask) -> list[int]:
        # IO map parameter layout written into 131..135.
        #
        # P  => [printer_id, wash_id, 0, 0, 0]
        # FW => [wash_id, parking_printer_id, cure_id, wait_minutes, 0]
        # FC => [cure_id, 0, 0, 0, 0]
        job = self.ctx.active_jobs.get(task.cmd_id)
        if job is None:
            return [0, 0, 0, 0, 0]

        t = self._normalize_task_type(task.task_type)
        printer_id = int((job.allocated_data.get('printer_id') or job.target_printer or 0) or 0)
        wash_id = int((job.allocated_data.get('wash_id') or 0) or 0)
        cure_id = int((job.allocated_data.get('cure_id') or 0) or 0)
        wait_minutes = int(round(float(job.washing_time or 0))) # max(0, int(round(float(job.washing_time or 0) / 60.0)))

        if t in {'SW', 'P'}:
            return [printer_id, wash_id, 0, 0, 0]
        if t == 'FW':
            parking_printer_id = int(
                (job.allocated_data.get('parking_printer_id') or job.allocated_data.get('printer_id') or job.target_printer or 0) or 0
            )
            return [wash_id, parking_printer_id, cure_id, wait_minutes, 0]
        if t == 'FC':
            return [cure_id, 0, 0, 0, 0]

        raise ValueError(f'unsupported modbus task_type: {t}')

    def _modbus_trace(self, message: str) -> None:
        if self._current_task is None:
            return
        self._log_job(self._current_task.cmd_id, message)

    def _modbus_read(self, address: int) -> tuple[bool, int | str]:
        self._sync_comm_targets()
        self._robot_modbus.timeout_seconds = max(1.0, float(self._settings.ROBOT_TCP_TIMEOUT_SECONDS))
        self._robot_modbus.slave_id = int(self._settings.ROBOT_MODBUS_SLAVE_ID)
        return self._robot_modbus.read_single(int(address), trace=self._modbus_trace)

    def _modbus_write(self, address: int, value: int) -> tuple[bool, int | str]:
        self._sync_comm_targets()
        self._robot_modbus.timeout_seconds = max(1.0, float(self._settings.ROBOT_TCP_TIMEOUT_SECONDS))
        self._robot_modbus.slave_id = int(self._settings.ROBOT_MODBUS_SLAVE_ID)
        self._modbus_trace(f'MODBUS WRITE: reg={int(address)} value={int(value)}')
        return self._robot_modbus.write_single(int(address), int(value))

    def _modbus_retry_wait(self, detail: str) -> None:
        retry_in = max(0.2, float(self._settings.ROBOT_MODBUS_RETRY_SECONDS))
        self._next_tcp_retry_ts = time.time() + retry_in
        if self._current_task is not None:
            job = self.ctx.active_jobs.get(self._current_task.cmd_id)
            self._log_job(
                self._current_task.cmd_id,
                f'ROBOT WAIT MODBUS STEP: {detail}, retry_in={retry_in:.1f}s',
                job.allocated_data if job is not None else None,
            )

    def _reset_idle_registers(self) -> bool:
        # When robot sequence is idle at STEP0000, keep the command-facing registers
        # in the same safe state used by STOP.
        if not self._use_real_io:
            return True
        if time.time() < self._next_tcp_retry_ts:
            return False

        self.ctx.repo.add_log(int(LogType.ROBOT), 'robot', 'ROBOT IDLE RESET START')
        writes = (
            (int(self._settings.ROBOT_MODBUS_COMMAND_REG), 100),
            (int(self._settings.ROBOT_MODBUS_SEND_REG), 0),
            (int(self._settings.ROBOT_MODBUS_PC_READY_REG), 0),
        )
        for reg, value in writes:
            ok, result = self._modbus_write(reg, value)
            if not ok:
                self.ctx.repo.add_log(
                    int(LogType.ROBOT),
                    'robot',
                    f'ROBOT IDLE RESET WRITE FAILED: reg={reg} value={value} detail={result}',
                )
                self._modbus_retry_wait(f'idle reset failed: reg={reg} value={value} detail={result}')
                return False
            self.ctx.repo.add_log(int(LogType.ROBOT), 'robot', f'ROBOT IDLE RESET WRITE: reg={reg} value={value}')
        self.ctx.repo.add_log(int(LogType.ROBOT), 'robot', 'ROBOT IDLE RESET DONE')
        self._next_tcp_retry_ts = 0.0
        return True

    def sequence_logic(self, step: int) -> None:
        if step == self.STEP0000:
            # Recovery:
            # if the sequence returned to idle while still holding a task reference,
            # drop that stale reference and pick again cleanly.
            if self._current_task is not None:
                stale = self.ctx.active_jobs.get(self._current_task.cmd_id)
                if stale is not None and stale.cmd_status != CmdStatus.CANCELED:
                    self.ctx.repo.update_command(
                        stale.cmd_id,
                        message=f'{self.sequence_name}: dropped stale task at STEP0000',
                    )
                self._current_task = None
                self.ctx.robot_active_cmd = None

            if not self._idle_reset_done:
                if not self._reset_idle_registers():
                    return
                self._idle_reset_done = True

            # Idle state: pick the next executable robot task.
            if self.ctx.paused or self._current_task is not None:
                return
            task = self._select_executable_task()
            if task is None:
                return
            self._idle_reset_done = False
            self._current_task = task
            self.ctx.robot_active_cmd = task.cmd_id
            self._log_job(task.cmd_id, f'ROBOT PICK: type={task.task_type}, from={task.from_unit}, to={task.to_unit}')
            self._busy_until = time.time() + max(1, self._settings.ROBOT_SIM_SECONDS)
            self._pc_ready_off_due_ts = 0.0
            self.now_step = self.STEP0010
            return

        if step == self.STEP0010:
            # Step 1:
            # 200 == 1 Check
            if self._current_task is None:
                self.now_step = self.STEP10000
                return

            if self._use_real_io:
                if time.time() < self._next_tcp_retry_ts:
                    return
                reg = int(self._settings.ROBOT_MODBUS_ROBOT_READY_REG)
                self._modbus_trace(f'MODBUS CHECK: reg={reg} expected=1')
                ok, value = self._modbus_read(reg)
                if not ok:
                    self._modbus_retry_wait(str(value))
                    return
                if int(value) != 1:
                    self._modbus_retry_wait(f'reg={reg} current={value} expected=1')
                    return
                self._modbus_trace(f'MODBUS CHECK OK: reg={reg} value=1')
                self._next_tcp_retry_ts = 0.0
                self.now_step = self.STEP0020
                return

            if time.time() < self._busy_until:
                return
            self.now_step = self.STEP0090
            return

        if step == self.STEP0020:
            # Step 2:
            # 151 = 1
            if self._current_task is None:
                self.now_step = self.STEP10000
                return
            if time.time() < self._next_tcp_retry_ts:
                return
            reg = int(self._settings.ROBOT_MODBUS_PC_READY_REG)
            ok, result = self._modbus_write(reg, 1)
            if not ok:
                self._modbus_retry_wait(str(result))
                return
            self._next_tcp_retry_ts = 0.0
            self.now_step = self.STEP0030
            return

        if step == self.STEP0030:
            # Step 3:
            # 206 == 0 Check
            if self._current_task is None:
                self.now_step = self.STEP10000
                return
            if time.time() < self._next_tcp_retry_ts:
                return
            reg = int(self._settings.ROBOT_MODBUS_ROBOT_MOVED_REG)
            self._modbus_trace(f'MODBUS CHECK: reg={reg} expected=0')
            ok, value = self._modbus_read(reg)
            if not ok:
                self._modbus_retry_wait(str(value))
                return
            if int(value) != 0:
                self._modbus_retry_wait(f'reg={reg} current={value} expected=0')
                return
            self._modbus_trace(f'MODBUS CHECK OK: reg={reg} value=0')
            self._pc_ready_off_due_ts = time.time() + max(
                0.0,
                float(self._settings.ROBOT_MODBUS_PC_READY_OFF_DELAY_SECONDS),
            )
            self._next_tcp_retry_ts = 0.0
            self.now_step = self.STEP0040
            return

        if step == self.STEP0040:
            # Step 4:
            # wait 4s, then 151 = 0
            if self._current_task is None:
                self.now_step = self.STEP10000
                return
            if time.time() < self._pc_ready_off_due_ts:
                return
            if time.time() < self._next_tcp_retry_ts:
                return
            reg = int(self._settings.ROBOT_MODBUS_PC_READY_REG)
            ok, result = self._modbus_write(reg, 0)
            if not ok:
                self._modbus_retry_wait(str(result))
                return
            self._next_tcp_retry_ts = 0.0
            self.now_step = self.STEP0050
            return

        if step == self.STEP0050:
            # Step 5:
            # 130 = command, 131..135 = params
            if self._current_task is None:
                self.now_step = self.STEP10000
                return
            if time.time() < self._next_tcp_retry_ts:
                return
            try:
                command_value = self._modbus_command_value(self._current_task.task_type)
                params = self._modbus_params(self._current_task)
            except ValueError as e:
                self._modbus_retry_wait(str(e))
                return
            cmd_reg = int(self._settings.ROBOT_MODBUS_COMMAND_REG)
            ok, result = self._modbus_write(cmd_reg, command_value)
            if not ok:
                self._modbus_retry_wait(str(result))
                return
            param_start = int(self._settings.ROBOT_MODBUS_PARAM_START_REG)
            param_count = int(self._settings.ROBOT_MODBUS_PARAM_COUNT)
            normalized_params = [int(v) for v in list(params)[: max(0, param_count)]]
            while len(normalized_params) < param_count:
                normalized_params.append(0)
            for idx, value in enumerate(normalized_params):
                ok, result = self._modbus_write(param_start + idx, value)
                if not ok:
                    self._modbus_retry_wait(str(result))
                    return
            self._next_tcp_retry_ts = 0.0
            self.now_step = self.STEP0060
            return

        if step == self.STEP0060:
            # Step 6:
            # 150 = 1
            if self._current_task is None:
                self.now_step = self.STEP10000
                return
            if time.time() < self._next_tcp_retry_ts:
                return
            reg = int(self._settings.ROBOT_MODBUS_SEND_REG)
            ok, result = self._modbus_write(reg, 1)
            if not ok:
                self._modbus_retry_wait(str(result))
                return
            self._next_tcp_retry_ts = 0.0
            self.now_step = self.STEP0070
            return

        if step == self.STEP0070:
            # Step 7:
            # 206 == 1 Check
            if self._current_task is None:
                self.now_step = self.STEP10000
                return
            if time.time() < self._next_tcp_retry_ts:
                return
            reg = int(self._settings.ROBOT_MODBUS_ROBOT_MOVED_REG)
            self._modbus_trace(f'MODBUS CHECK: reg={reg} expected=1')
            ok, value = self._modbus_read(reg)
            if not ok:
                self._modbus_retry_wait(str(value))
                return
            if int(value) != 1:
                self._modbus_retry_wait(f'reg={reg} current={value} expected=1')
                return
            self._modbus_trace(f'MODBUS CHECK OK: reg={reg} value=1')
            self._next_tcp_retry_ts = 0.0
            self.now_step = self.STEP0080
            return

        if step == self.STEP0080:
            # Step 8:
            # 150 = 0
            if self._current_task is None:
                self.now_step = self.STEP10000
                return
            if time.time() < self._next_tcp_retry_ts:
                return
            reg = int(self._settings.ROBOT_MODBUS_SEND_REG)
            ok, result = self._modbus_write(reg, 0)
            if not ok:
                self._modbus_retry_wait(str(result))
                return
            self._next_tcp_retry_ts = 0.0
            self.now_step = self.STEP0090
            return

        if step == self.STEP0090:
            # Final step:
            # physical move succeeded, so commit logical state transition
            if self._current_task is not None:
                self._complete_task(self._current_task)
            self._current_task = None
            self.ctx.robot_active_cmd = None
            self._pc_ready_off_due_ts = 0.0
            self._idle_reset_done = False
            self.now_step = self.STEP10000
            return

        if step == self.STEP10000:
            self.now_step = self.STEP0000
            return

    def machine_stop_logic(self) -> None:
        self._current_task = None
        self.ctx.robot_active_cmd = None
        self._busy_until = 0.0
        self._next_tcp_retry_ts = 0.0
        self._next_comm_config_sync_ts = 0.0
        self._pc_ready_off_due_ts = 0.0
        self._idle_reset_done = False

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

    def _sync_comm_targets(self) -> None:
        # Pull robot/vision endpoints from DB-backed manual communication config.
        # This lets the manual screen and sequence thread use the same target settings.
        now = time.time()
        if now < self._next_comm_config_sync_ts:
            return
        self._next_comm_config_sync_ts = now + 2.0
        try:
            cfg = self.ctx.repo.get_comm_targets()
            robot_host = str(cfg.get('robot_host') or self._settings.ROBOT_TCP_HOST)
            robot_port = int(cfg.get('robot_port') or self._settings.ROBOT_TCP_PORT)
            self._robot_modbus.host = robot_host
            self._robot_modbus.port = robot_port
        except Exception:
            # Keep last known endpoints when DB sync fails.
            return
