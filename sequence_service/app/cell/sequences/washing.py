from __future__ import annotations

import time

from app.cell.ctx import RobotTask
from app.cell.enums import CmdStatus, PostProcStage
from app.cell.sequence import Sequence

# Module role:
# - run washing timer after StartWashing(SW) move has finished
# - request FinishWashing(FW): wash -> empty printer (and cure reservation)


class WashingSequence(Sequence):
    STEP0000 = 0
    STEP0010 = 10
    STEP0020 = 20  # request robot FW
    STEP0030 = 30  # wait robot FW ack
    STEP10000 = 10000

    def __init__(self, runtime_ctx, wash_id: int) -> None:
        super().__init__(f'WashingSequence-{wash_id}')
        self.ctx = runtime_ctx
        self.wash_id = wash_id
        self._end_ts = 0.0
        self._current_cmd: str | None = None
        self._robot_req_sent = False

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
                self.ctx.wash_active_cmd[self.wash_id] = None
                self._current_cmd = None
                self._end_ts = 0.0
                self._robot_req_sent = False

            # IDLE: take one waiting job assigned to this wash unit
            if self._current_cmd is None and not self.ctx.paused:
                for _ in range(len(self.ctx.wash_waiting)):
                    cmd_id = self.ctx.wash_waiting.popleft()
                    job = self.ctx.active_jobs.get(cmd_id)
                    if job is None:
                        continue
                    if int(job.allocated_data.get('wash_id') or 0) != self.wash_id:
                        self.ctx.wash_waiting.append(cmd_id)
                        continue
                    self._current_cmd = cmd_id
                    self._robot_req_sent = False
                    self.ctx.wash_active_cmd[self.wash_id] = cmd_id
                    self._end_ts = time.time() + max(1, int(job.washing_time or 0))
                    self.now_step = self.STEP0010
                    return
            return

        if step == self.STEP0010:
            # WASHING timer
            if time.time() < self._end_ts:
                return
            self.now_step = self.STEP0020
            return

        if step == self.STEP0020:
            # WASH DONE: request robot FW (wash -> empty printer)
            if self._current_cmd is None:
                self.now_step = self.STEP10000
                return

            job = self.ctx.active_jobs.get(self._current_cmd)
            if job is None:
                self.ctx.wash_active_cmd[self.wash_id] = None
                self._current_cmd = None
                self._end_ts = 0.0
                self.now_step = self.STEP10000
                return

            if not self._robot_req_sent:
                job.post_proc_stage = PostProcStage.WASH_DONE
                job.allocated_data['plate_state'] = 'WASH_DONE_WITH_PLATE'
                self.ctx.robot_queue.append(
                    RobotTask(
                        cmd_id=job.cmd_id,
                        task_type='FW',
                        from_unit=f'wash-{self.wash_id}',
                        to_unit='printer',
                        requested_by=self.sequence_name,
                    )
                )
                self._robot_req_sent = True
                self.ctx.repo.update_command(
                    job.cmd_id,
                    post_proc_stage=int(PostProcStage.WASH_DONE),
                    allocated_data=job.allocated_data,
                    message=f'WASH_DONE on wash-{self.wash_id}, ROBOT_REQ FW queued (need empty printer+cure)',
                )
            self.now_step = self.STEP0030
            return

        if step == self.STEP0030:
            # Wait for robot completion ACK(FW)
            if self._current_cmd is None:
                self.now_step = self.STEP10000
                return
            ack_key = f'{self._current_cmd}:FW'
            if not self.ctx.robot_acks.get(ack_key, False):
                return
            self.ctx.robot_acks.pop(ack_key, None)

            self.ctx.wash_active_cmd[self.wash_id] = None
            self._current_cmd = None
            self._end_ts = 0.0
            self._robot_req_sent = False
            self.now_step = self.STEP10000
            return

        if step == self.STEP10000:
            self.now_step = self.STEP0000

    def machine_stop_logic(self) -> None:
        self.ctx.wash_active_cmd[self.wash_id] = None
        self._current_cmd = None
        self._end_ts = 0.0
        self._robot_req_sent = False

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
