from __future__ import annotations

import time

from app.cell.ctx import RobotTask
from app.cell.enums import CmdStatus, PostProcStage
from app.cell.sequence import Sequence
from app.core.config import get_settings

# Module role:
# - request StartCure(SC): parking-printer -> cure
# - run curing timer
# - request FinishCure(FC): cure -> output and finalize DONE


class CuringSequence(Sequence):
    STEP0000 = 0
    STEP0010 = 10  # request robot SC (printer -> cure)
    STEP0020 = 20  # wait robot SC ack and start curing timer
    STEP0030 = 30  # curing timer
    STEP0040 = 40  # request robot FC (cure -> output)
    STEP0050 = 50  # wait robot FC ack
    STEP10000 = 10000

    def __init__(self, runtime_ctx, cure_id: int) -> None:
        super().__init__(f'CuringSequence-{cure_id}')
        self.ctx = runtime_ctx
        self.cure_id = cure_id
        self._settings = get_settings()
        self._end_ts = 0.0
        self._current_cmd: str | None = None
        self._robot_req_to_cure_sent = False
        self._robot_req_to_return_sent = False

    def sequence_logic(self, step: int) -> None:
        if step == self.STEP0000:
            # Recovery rule: if STEP0000 still holds a non-canceled cmd, drop it and re-pick.
            if self._current_cmd is not None:
                stale = self.ctx.active_jobs.get(self._current_cmd)
                if stale is not None and stale.cmd_status != CmdStatus.CANCELED:
                    self.ctx.repo.update_command(
                        stale.cmd_id,
                        message=f'{self.sequence_name}: dropped stale cmd at STEP0000',
                    )
                self.ctx.cure_active_cmd[self.cure_id] = None
                self._current_cmd = None
                self._end_ts = 0.0
                self._robot_req_to_cure_sent = False
                self._robot_req_to_return_sent = False

            # IDLE: take one waiting job assigned to this cure unit
            if self._current_cmd is None and not self.ctx.paused:
                for _ in range(len(self.ctx.cure_waiting)):
                    cmd_id = self.ctx.cure_waiting.popleft()
                    job = self.ctx.active_jobs.get(cmd_id)
                    if job is None:
                        continue
                    if int(job.allocated_data.get('cure_id') or 0) != self.cure_id:
                        self.ctx.cure_waiting.append(cmd_id)
                        continue

                    self._current_cmd = cmd_id
                    self._robot_req_to_cure_sent = False
                    self._robot_req_to_return_sent = False
                    self.ctx.cure_active_cmd[self.cure_id] = cmd_id
                    job.allocated_data['cure_id'] = self.cure_id
                    self.ctx.repo.update_command(
                        cmd_id,
                        post_proc_stage=int(PostProcStage.CURE_WAITING),
                        allocated_data=job.allocated_data,
                        message=f'CURE_WAITING on cure-{self.cure_id}',
                    )
                    self.now_step = self.STEP0010
                    return
            return

        if step == self.STEP0010:
            # Request robot SC: move plate from parking-printer to cure
            if self._current_cmd is None:
                self.now_step = self.STEP10000
                return
            job = self.ctx.active_jobs.get(self._current_cmd)
            if job is None:
                self.ctx.cure_active_cmd[self.cure_id] = None
                self._current_cmd = None
                self.now_step = self.STEP10000
                return
            # FW can include SC transport. If so, skip SC command and continue timer step.
            if bool(job.allocated_data.get('fw_started_cure', False)):
                self.ctx.robot_acks[f'{self._current_cmd}:SC'] = True
                self.now_step = self.STEP0020
                return
            if not self._robot_req_to_cure_sent:
                printer_id = int(job.allocated_data.get('printer_id') or job.target_printer or 0)
                self.ctx.robot_queue.append(
                    RobotTask(
                        cmd_id=job.cmd_id,
                        task_type='SC',
                        from_unit=f'printer-{printer_id}',
                        to_unit=f'cure-{self.cure_id}',
                        requested_by=self.sequence_name,
                    )
                )
                self._robot_req_to_cure_sent = True
                self.ctx.repo.update_command(
                    job.cmd_id,
                    allocated_data=job.allocated_data,
                    message=f'ROBOT_REQ SC queued: printer-{printer_id}->cure-{self.cure_id}',
                )
            self.now_step = self.STEP0020
            return

        if step == self.STEP0020:
            # Wait robot ACK(SC), then start curing timer
            if self._current_cmd is None:
                self.now_step = self.STEP10000
                return
            ack_key = f'{self._current_cmd}:SC'
            if not self.ctx.robot_acks.get(ack_key, False):
                return
            self.ctx.robot_acks.pop(ack_key, None)

            job = self.ctx.active_jobs.get(self._current_cmd)
            if job is None:
                self.ctx.cure_active_cmd[self.cure_id] = None
                self._current_cmd = None
                self.now_step = self.STEP10000
                return

            job.post_proc_stage = PostProcStage.CURING
            job.allocated_data['plate_state'] = 'CURING_WITH_PLATE'
            cure_seconds = max(1, job.curing_time or self._settings.CURE_SIM_SECONDS)
            self._end_ts = time.time() + cure_seconds
            self.ctx.repo.update_command(
                job.cmd_id,
                post_proc_stage=int(PostProcStage.CURING),
                allocated_data=job.allocated_data,
                message=f'CURING start on cure-{self.cure_id}',
            )
            self.now_step = self.STEP0030
            return

        if step == self.STEP0030:
            # CURING timer
            if time.time() < self._end_ts:
                return
            self.now_step = self.STEP0040
            return

        if step == self.STEP0040:
            # CURE DONE: request robot FC (cure -> output)
            if self._current_cmd is None:
                self.now_step = self.STEP10000
                return
            job = self.ctx.active_jobs.get(self._current_cmd)
            if job is None:
                self.ctx.cure_active_cmd[self.cure_id] = None
                self._current_cmd = None
                self._end_ts = 0.0
                self.now_step = self.STEP10000
                return

            if not self._robot_req_to_return_sent:
                job.post_proc_stage = PostProcStage.CURE_DONE
                self.ctx.robot_queue.append(
                    RobotTask(
                        cmd_id=job.cmd_id,
                        task_type='FC',
                        from_unit=f'cure-{self.cure_id}',
                        to_unit='output',
                        requested_by=self.sequence_name,
                    )
                )
                self._robot_req_to_return_sent = True
                self.ctx.repo.update_command(
                    job.cmd_id,
                    post_proc_stage=int(PostProcStage.CURE_DONE),
                    allocated_data=job.allocated_data,
                    message=f'CURE_DONE on cure-{self.cure_id}, ROBOT_REQ FC(output) queued',
                )
            self.now_step = self.STEP0050
            return

        if step == self.STEP0050:
            # Wait for robot completion ACK(FC), then finalize DONE
            if self._current_cmd is None:
                self.now_step = self.STEP10000
                return
            ack_key = f'{self._current_cmd}:FC'
            if not self.ctx.robot_acks.get(ack_key, False):
                return
            self.ctx.robot_acks.pop(ack_key, None)

            job = self.ctx.active_jobs.get(self._current_cmd)
            if job:
                printer_id = int(job.allocated_data.get('printer_id') or job.target_printer or 0)
                job.post_proc_stage = PostProcStage.OUTPUT_DONE
                job.cmd_status = CmdStatus.DONE
                job.allocated_data['plate_state'] = 'OUTPUT_DONE'
                job.allocated_data['plate_in_printer'] = False
                self.ctx.repo.update_command(
                    job.cmd_id,
                    cmd_status=int(CmdStatus.DONE),
                    post_proc_stage=int(PostProcStage.OUTPUT_DONE),
                    allocated_data=job.allocated_data,
                    message=f'DONE after cure-{self.cure_id}, output discharged',
                )
                self.ctx.active_jobs.pop(job.cmd_id, None)

            self.ctx.cure_active_cmd[self.cure_id] = None
            self._current_cmd = None
            self._end_ts = 0.0
            self._robot_req_to_cure_sent = False
            self._robot_req_to_return_sent = False
            self.now_step = self.STEP10000
            return

        if step == self.STEP10000:
            self.now_step = self.STEP0000

    def machine_stop_logic(self) -> None:
        self.ctx.cure_active_cmd[self.cure_id] = None
        self._current_cmd = None
        self._end_ts = 0.0
        self._robot_req_to_cure_sent = False
        self._robot_req_to_return_sent = False

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
