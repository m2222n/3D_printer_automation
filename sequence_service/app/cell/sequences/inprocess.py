from __future__ import annotations

from app.cell.printer_interface import WebApiPrinterClient
from app.cell.sequence import Sequence
from app.core.config import get_settings

# Module role: fetch queued jobs and place them into per-printer queues.


class InprocessSequence(Sequence):
    """
    C# InProcsssSequence pattern:
    - polling DB
    - check available printers
    - allocate command and enqueue to printer queue
    """

    STEP0000 = 0
    STEP0010 = 10
    STEP0020 = 20
    STEP0030 = 30
    STEP0040 = 40
    STEP10000 = 10000

    def __init__(self, runtime_ctx) -> None:
        super().__init__('InprocessSequence')
        self.ctx = runtime_ctx
        self._settings = get_settings()
        self._client = WebApiPrinterClient(
            base_url=self._settings.WEB_API_BASE_URL,
            timeout_seconds=self._settings.WEB_API_TIMEOUT_SECONDS,
        )
        self._available_printers: list[int] = []
        self._candidates: list[dict] = []

    def sequence_logic(self, step: int) -> None:
        if step == self.STEP0000:
            # Start a new polling cycle
            self.now_step = self.STEP0010
            return

        if step == self.STEP0010:
            # Poll DB/availability at 1s interval
            if self.elapsed_ms() < 1000:
                return

            self._available_printers = []
            for pid in sorted(self.ctx.printer_queues.keys()):
                if (
                    self._is_printer_available(pid)
                    and self.ctx.printer_has_plate.get(pid, False)
                    and self.ctx.printer_active_cmd.get(pid) is None
                    and len(self.ctx.printer_queues[pid]) == 0
                ):
                    self._available_printers.append(pid)
            self.now_step = self.STEP0020
            return

        if step == self.STEP0020:
            # Nothing to allocate in this cycle
            if not self._available_printers or self.ctx.paused:
                self.now_step = self.STEP0040
                return

            # Pull latest queued commands
            self._candidates = self.ctx.repo.list_queued_commands(limit=32)
            self.now_step = self.STEP0030
            return

        if step == self.STEP0030:
            if not self._candidates:
                self.now_step = self.STEP0040
                return

            # Try allocating one job per available printer
            for pid in list(self._available_printers):
                selected = None
                for row in self._candidates:
                    target = row.get('target_printer')
                    if target is None or int(target) == pid:
                        selected = row
                        break

                if not selected:
                    continue

                job = self.ctx.repo.allocate_to_printer(
                    cmd_id=selected['cmd_id'],
                    printer_id=pid,
                    claimed_by='inprocess',
                )
                if job is None:
                    continue

                self.ctx.active_jobs[job.cmd_id] = job
                self.ctx.printer_queues[pid].append(job.cmd_id)
                self._candidates = [c for c in self._candidates if c['cmd_id'] != job.cmd_id]

            self.now_step = self.STEP0040
            return

        if step == self.STEP0040:
            self.now_step = self.STEP10000
            return

        if step == self.STEP10000:
            self.now_step = self.STEP0000
            return

    def machine_stop_logic(self) -> None:
        self._available_printers.clear()
        self._candidates.clear()

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

    def _is_printer_available(self, pid: int) -> bool:
        if self.ctx.printer_use.get(pid, 'N') != 'Y':
            return False
        if self._settings.SIMUL_MODE or self._settings.PRINTER_SERVER_SIMUL:
            return True

        serial = str(self._settings.PRINTER_SERIAL_MAP.get(pid) or '').strip()
        if not serial:
            return False

        resp = self._client.get_printer_summary(serial)
        if not resp.get('ok'):
            return False

        data = resp.get('data') or {}
        status = str(data.get('status') or '').upper()
        is_online = bool(data.get('is_online', False))
        has_error = bool(data.get('has_error', False))
        is_ready = bool(data.get('is_ready', False))
        ready_to_print = str(data.get('ready_to_print') or '').upper()

        if not is_online or has_error:
            return False

        # Exclude printer summaries that explicitly say the printer is not ready,
        # even if the outer status still looks idle/finished.
        if ready_to_print in {'NOT_READY', 'READY_TO_PRINT_NOT_READY'}:
            return False

        # A printer can receive a new job only when it is in a non-printing state
        # and the Formlabs readiness flags also say it is ready to print.
        return status in {'IDLE', 'READY', 'FINISHED'} and (
            is_ready or ready_to_print in {'READY', 'READY_TO_PRINT_READY'}
        )
