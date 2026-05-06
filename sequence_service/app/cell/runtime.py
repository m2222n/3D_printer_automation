from __future__ import annotations

import queue
import threading
import time
from collections import deque

from app.cell.ctx import RuntimeCtx
from app.cell.enums import CmdStatus, LogType
from app.cell.mainSequence import build_main_sequences
from app.cell.modbus_protocol import ModbusHandshakeClient
from app.cell.printer_interface import WebApiPrinterClient
from app.core.config import get_settings

# Runtime thread that repeatedly executes ordered sequences.
# Also handles start/stop/pause/resume control commands.


class SeqCommand:
    # External control commands for sequence runtime
    START = 'START'
    STOP = 'STOP'
    PAUSE = 'PAUSE'
    RESUME = 'RESUME'


class SequenceThread(threading.Thread):
    def __init__(self, repo, tick_sec: float | None = None):
        super().__init__(daemon=True)
        settings = get_settings()
        self._settings = settings
        self.repo = repo
        self.tick_sec = tick_sec if tick_sec is not None else settings.TICK_SECONDS
        self.enable_cell_state = settings.ENABLE_CELL_STATE
        self._robot_modbus = ModbusHandshakeClient(
            host=settings.ROBOT_TCP_HOST,
            port=settings.ROBOT_TCP_PORT,
            timeout_seconds=settings.ROBOT_TCP_TIMEOUT_SECONDS,
            slave_id=settings.ROBOT_MODBUS_SLAVE_ID,
        )
        self._printer_client = WebApiPrinterClient(
            base_url=settings.WEB_API_BASE_URL,
            timeout_seconds=settings.WEB_API_TIMEOUT_SECONDS,
        )

        self.cmd_queue: queue.Queue[str] = queue.Queue()
        self._stop_evt = threading.Event()

        self.ctx = RuntimeCtx(repo=repo, running=False, paused=False)
        self._next_queue_publish_ts: float = 0.0
        self._next_printer_health_sync_ts: float = 0.0
        self._startup_robot_reset_done: bool = False

        # Main ordered sequence chain
        self.sequences = build_main_sequences(self.ctx)
        self._last_synced_running: bool = False

    def _write_robot_stop_registers(self) -> None:
        # Force robot-facing control registers to a safe reset state.
        # Requirement:
        # - 130 = 100
        # - 150 = 0
        # - 151 = 0
        if not self._settings.ENABLE_TCP_IO:
            return
        try:
            self.repo.add_log(int(LogType.PROGRAM), 'program', 'Robot STOP reset start')
            cfg = self.repo.get_comm_targets()
            self._robot_modbus.host = str(cfg.get('robot_host') or self._settings.ROBOT_TCP_HOST)
            self._robot_modbus.port = int(cfg.get('robot_port') or self._settings.ROBOT_TCP_PORT)
            self._robot_modbus.timeout_seconds = float(self._settings.ROBOT_TCP_TIMEOUT_SECONDS)
            self._robot_modbus.slave_id = int(self._settings.ROBOT_MODBUS_SLAVE_ID)

            for reg, value in (
                (int(self._settings.ROBOT_MODBUS_COMMAND_REG), 100),
                (int(self._settings.ROBOT_MODBUS_SEND_REG), 0),
                (int(self._settings.ROBOT_MODBUS_PC_READY_REG), 0),
            ):
                ok, result = self._robot_modbus.write_single(reg, value)
                if ok:
                    self.repo.add_log(int(LogType.PROGRAM), 'program', f'Robot STOP write: reg={reg} value={value}')
                else:
                    self.repo.add_log(
                        int(LogType.PROGRAM),
                        'program',
                        f'Robot STOP write failed: reg={reg} value={value} detail={result}',
                    )
            self.repo.add_log(int(LogType.PROGRAM), 'program', 'Robot STOP reset done')
        except Exception as exc:
            self.repo.add_log(int(LogType.PROGRAM), 'program', f'Robot STOP register cleanup exception: {exc}')

    def _has_residual_runtime_work(self) -> bool:
        if self.ctx.active_jobs:
            return True
        if any(self.ctx.printer_active_cmd.values()):
            return True
        if any(len(q) > 0 for q in self.ctx.printer_queues.values()):
            return True
        if any(self.ctx.wash_active_cmd.values()) or any(self.ctx.cure_active_cmd.values()):
            return True
        if self.ctx.robot_active_cmd is not None:
            return True
        if self.ctx.wash_waiting or self.ctx.cure_waiting or self.ctx.robot_queue:
            return True
        return False

    def push(self, cmd: str) -> None:
        self.cmd_queue.put(cmd)

    def stop_thread(self) -> None:
        self._stop_evt.set()

    def _reset_runtime(self) -> None:
        # Reset all in-memory states when STOP is requested
        self.ctx.active_jobs.clear()
        self.ctx.printer_has_plate = {1: True, 2: True, 3: True, 4: True}
        self.ctx.printer_use = {1: 'Y', 2: 'Y', 3: 'Y', 4: 'Y'}
        self.ctx.printer_active_cmd = {1: None, 2: None, 3: None, 4: None}
        self.ctx.printer_queues = {1: deque(), 2: deque(), 3: deque(), 4: deque()}
        self.ctx.wash_active_cmd = {1: None, 2: None}
        self.ctx.cure_active_cmd = {1: None}
        self.ctx.robot_active_cmd = None
        self.ctx.wash_waiting = deque()
        self.ctx.cure_waiting = deque()
        self.ctx.robot_queue = deque()
        self.ctx.robot_acks.clear()
        for seq in self.sequences:
            seq.machine_stop()

    def _apply_control(self) -> None:
        # Apply all pending START/STOP/PAUSE/RESUME commands
        while True:
            try:
                c = self.cmd_queue.get_nowait()
            except queue.Empty:
                break

            if c == SeqCommand.START:
                self.ctx.running = True
                self.ctx.paused = False
                self.repo.add_log(int(LogType.PROGRAM), 'program', 'Sequence START')
                if self.enable_cell_state:
                    self.repo.set_cell_state(running=True, paused=False)
            elif c == SeqCommand.STOP:
                self.ctx.running = False
                self.ctx.paused = False
                self._write_robot_stop_registers()
                self.repo.cancel_inflight_commands(reason='CANCELED by STOP')
                self._reset_runtime()
                self._publish_queue_state(force=True)
                self.repo.add_log(int(LogType.PROGRAM), 'program', 'Sequence STOP')
                if self.enable_cell_state:
                    self.repo.set_cell_state(running=False, paused=False)
            elif c == SeqCommand.PAUSE:
                self.ctx.paused = True
                self.repo.add_log(int(LogType.PROGRAM), 'program', 'Sequence PAUSE')
                if self.enable_cell_state:
                    self.repo.set_cell_state(paused=True)
            elif c == SeqCommand.RESUME:
                self.ctx.paused = False
                self.repo.add_log(int(LogType.PROGRAM), 'program', 'Sequence RESUME')
                if self.enable_cell_state:
                    self.repo.set_cell_state(paused=False)

        if self.enable_cell_state:
            # Optional DB-backed run/pause state synchronization
            running, paused, simul_mode = self.repo.get_cell_state()
            # If DB-driven control changed RUNNING -> STOPPED, enforce same cleanup as STOP command.
            if self._last_synced_running and not running:
                self._write_robot_stop_registers()
                self.repo.cancel_inflight_commands(reason='CANCELED by STOP(DB sync)')
                self._reset_runtime()
                self._publish_queue_state(force=True)
            # Safety net: if already STOPPED but stale runtime queues remain, clear them.
            elif not running and self._has_residual_runtime_work():
                self._write_robot_stop_registers()
                self._reset_runtime()
                self._publish_queue_state(force=True)
            self.ctx.running = running
            self.ctx.paused = paused
            self.ctx.simul_mode = simul_mode
            self._last_synced_running = running

    def _cleanup_canceled_jobs(self) -> None:
        # Remove canceled jobs from all active maps/queues
        canceled_ids = [
            cmd_id for cmd_id, job in self.ctx.active_jobs.items() if job.cmd_status == CmdStatus.CANCELED
        ]
        for cmd_id in canceled_ids:
            self.ctx.active_jobs.pop(cmd_id, None)
            for rid, val in self.ctx.printer_active_cmd.items():
                if val == cmd_id:
                    self.ctx.printer_active_cmd[rid] = None
            for q in self.ctx.printer_queues.values():
                try:
                    q.remove(cmd_id)
                except ValueError:
                    pass
            for rid, val in self.ctx.wash_active_cmd.items():
                if val == cmd_id:
                    self.ctx.wash_active_cmd[rid] = None
            for rid, val in self.ctx.cure_active_cmd.items():
                if val == cmd_id:
                    self.ctx.cure_active_cmd[rid] = None
            if self.ctx.robot_active_cmd == cmd_id:
                self.ctx.robot_active_cmd = None
            try:
                self.ctx.wash_waiting.remove(cmd_id)
            except ValueError:
                pass
            try:
                self.ctx.cure_waiting.remove(cmd_id)
            except ValueError:
                pass
            self.ctx.robot_queue = deque([t for t in self.ctx.robot_queue if t.cmd_id != cmd_id])
            # Legacy + current robot ack keys cleanup
            self.ctx.robot_acks.pop(f'{cmd_id}:P', None)
            self.ctx.robot_acks.pop(f'{cmd_id}:W', None)
            self.ctx.robot_acks.pop(f'{cmd_id}:R', None)
            self.ctx.robot_acks.pop(f'{cmd_id}:C', None)
            self.ctx.robot_acks.pop(f'{cmd_id}:SW', None)
            self.ctx.robot_acks.pop(f'{cmd_id}:FW', None)
            self.ctx.robot_acks.pop(f'{cmd_id}:SC', None)
            self.ctx.robot_acks.pop(f'{cmd_id}:FC', None)

    def _build_queue_state_snapshot(self) -> dict:
        return {
            "running": self.ctx.running,
            "paused": self.ctx.paused,
            "runtime_ctx": {
                "active_job_count": len(self.ctx.active_jobs),
                "robot_ack_count": len(self.ctx.robot_acks),
            },
            "printer_queues": {str(k): list(v) for k, v in self.ctx.printer_queues.items()},
            "printer_active_cmd": {str(k): v for k, v in self.ctx.printer_active_cmd.items()},
            "printer_has_plate": {str(k): bool(v) for k, v in self.ctx.printer_has_plate.items()},
            "printer_use": {str(k): v for k, v in self.ctx.printer_use.items()},
            "wash_waiting": list(self.ctx.wash_waiting),
            "wash_active_cmd": {str(k): v for k, v in self.ctx.wash_active_cmd.items()},
            "cure_waiting": list(self.ctx.cure_waiting),
            "cure_active_cmd": {str(k): v for k, v in self.ctx.cure_active_cmd.items()},
            "robot_active_cmd": self.ctx.robot_active_cmd,
            "robot_queue": [
                {
                    "cmd_id": t.cmd_id,
                    "task_type": t.task_type,
                    "from_unit": t.from_unit,
                    "to_unit": t.to_unit,
                    "requested_by": t.requested_by,
                    "status": t.status,
                }
                for t in self.ctx.robot_queue
            ],
            "active_jobs": {
                cmd_id: {
                    "cmd_id": job.cmd_id,
                    "file_path": job.file_path,
                    "file_name": job.file_name,
                    "cmd_status": int(job.cmd_status),
                    "post_proc_stage": int(job.post_proc_stage),
                    "washing_time": job.washing_time,
                    "curing_time": job.curing_time,
                    "target_printer": job.target_printer,
                    "allocated_data": job.allocated_data,
                    "progress": job.progress,
                    "message": job.message,
                }
                for cmd_id, job in self.ctx.active_jobs.items()
            },
        }

    def _publish_queue_state(self, force: bool = False) -> None:
        if not self.enable_cell_state:
            return
        now = time.time()
        if not force and now < self._next_queue_publish_ts:
            return
        self._next_queue_publish_ts = now + 1.0
        self.repo.update_queue_state(self._build_queue_state_snapshot())

    def _sync_printer_use_from_status(self) -> None:
        """
        Keep printer_use synchronized with the real printer server state.

        Skip this check when:
        - full cell simulation is enabled, or
        - only printer server simulation is enabled.
        """
        if self.ctx.simul_mode or self._settings.PRINTER_SERVER_SIMUL:
            return
        now = time.time()
        if now < self._next_printer_health_sync_ts:
            return
        self._next_printer_health_sync_ts = now + max(1.0, float(self._settings.PRINTER_STATUS_POLL_SECONDS))

        ready_statuses = {'IDLE', 'READY', 'FINISHED'}
        for pid in sorted(self.ctx.printer_use.keys()):
            serial = str(self._settings.PRINTER_SERIAL_MAP.get(pid) or '').strip()
            if not serial:
                prev = self.ctx.printer_use.get(pid, 'N')
                self.ctx.printer_use[pid] = 'N'
                if prev != 'N':
                    self.repo.add_log(
                        int(LogType.PROGRAM),
                        'program',
                        f'Printer-{pid} use->N (serial not configured)',
                    )
                continue

            resp = self._printer_client.get_printer_summary(serial)
            if not resp.get('ok'):
                prev = self.ctx.printer_use.get(pid, 'N')
                self.ctx.printer_use[pid] = 'N'
                if prev != 'N':
                    err_msg = str(resp.get("error", "unknown"))
                    code = resp.get("status_code")
                    code_text = f"HTTP {code}" if code is not None else "no-status"
                    self.repo.add_log(
                        int(LogType.PROGRAM),
                        'program',
                        f'Printer-{pid} [{serial}] use->N (status check failed: {code_text}, {err_msg})',
                    )
                continue

            status = str((resp.get('data') or {}).get('status') or '').upper()
            is_ready = (
                status in ready_statuses
                and self.ctx.printer_has_plate.get(pid, False)
                and self.ctx.printer_active_cmd.get(pid) is None
            )
            next_use = 'Y' if is_ready else 'N'
            prev_use = self.ctx.printer_use.get(pid, 'N')
            self.ctx.printer_use[pid] = next_use
            if prev_use != next_use:
                self.repo.add_log(
                    int(LogType.PROGRAM),
                    'program',
                    f'Printer-{pid} use->{next_use} (status={status or "UNKNOWN"})',
                )

    def run(self) -> None:
        # Single-thread tick loop:
        # control -> run gate -> cleanup -> execute each sequence
        while not self._stop_evt.is_set():
            if not self._startup_robot_reset_done:
                self._write_robot_stop_registers()
                self._startup_robot_reset_done = True
            self._apply_control()
            self._sync_printer_use_from_status()
            self._publish_queue_state()

            if not self.ctx.running:
                time.sleep(0.2)
                continue

            self._cleanup_canceled_jobs()

            for seq in self.sequences:
                try:
                    seq.sequence_run_void()
                except Exception as exc:
                    # Keep thread alive even if one sequence failed on a tick
                    continue

            time.sleep(self.tick_sec)
