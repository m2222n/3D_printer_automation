from __future__ import annotations

"""
DB access layer for sequence service.

This script handles schema bootstrap, command creation/claiming,
and per-step status updates used by all sequences.
"""

from datetime import datetime
import uuid

from sqlalchemy import select, text, update

from app.cell.ctx import JobCtx
from app.cell.enums import CmdStatus, PostProcStage, LogType
from app.core.config import get_settings
from app.db.models import Base, CellState, PrintCommand, AutomationLog
from app.db.session import engine


class PrintCommandRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def init_db(self) -> None:
        # Bootstrap DB objects used by sequence runtime.
        Base.metadata.create_all(bind=engine)
        self.ensure_print_command_columns()
        self.ensure_cell_state_columns()
        self.ensure_automation_log_table()
        self.ensure_automation_comm_config_table()
        self.ensure_cell_state()

    def ensure_print_command_columns(self) -> None:
        # Add migration-safe duration columns if missing.
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE print_command "
                    "ADD COLUMN IF NOT EXISTS washing_time INT NOT NULL DEFAULT 6"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE print_command "
                    "ADD COLUMN IF NOT EXISTS curing_time INT NOT NULL DEFAULT 120"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE print_command "
                    "ADD COLUMN IF NOT EXISTS use_yn CHAR(1) NOT NULL DEFAULT 'Y'"
                )
            )
            conn.execute(
                text(
                    "UPDATE print_command "
                    "SET washing_time = COALESCE(NULLIF(washing_time, 0), 360) "
                    "WHERE washing_time IS NULL OR washing_time = 0"
                )
            )
            conn.execute(
                text(
                    "UPDATE print_command "
                    "SET use_yn = 'Y' "
                    "WHERE use_yn IS NULL OR use_yn = ''"
                )
            )

    def ensure_cell_state(self) -> None:
        # Ensure singleton row(id=1) for run/pause state.
        settings = get_settings()
        with self.session_factory() as s:
            row = s.execute(select(CellState).where(CellState.id == 1)).scalar_one_or_none()
            if row is None:
                s.add(CellState(
                    id=1,
                    running=0,
                    paused=0,
                    simul_mode=1 if settings.SIMUL_MODE else 0,
                    queue_state=None,
                    updated_at=datetime.now()
                ))
                s.commit()

    def ensure_cell_state_columns(self) -> None:
        # Add runtime queue snapshot column for automation UI.
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE cell_state "
                    "ADD COLUMN IF NOT EXISTS queue_state JSON NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE cell_state "
                    "ADD COLUMN IF NOT EXISTS simul_mode INT NOT NULL DEFAULT 0"
                )
            )

    def ensure_automation_log_table(self) -> None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS automation_log (
                        id BIGINT PRIMARY KEY AUTO_INCREMENT,
                        log_type INT NOT NULL,
                        source VARCHAR(64) NOT NULL,
                        cmd_id VARCHAR(36) NULL,
                        message VARCHAR(2048) NOT NULL,
                        created_at DATETIME NOT NULL,
                        INDEX idx_automation_log_created (created_at),
                        INDEX idx_automation_log_type_created (log_type, created_at)
                    )
                    """
                )
            )

    def ensure_automation_comm_config_table(self) -> None:
        settings = get_settings()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS automation_comm_config (
                        id INT PRIMARY KEY,
                        robot_host VARCHAR(255) NOT NULL,
                        robot_port INT NOT NULL,
                        vision_host VARCHAR(255) NOT NULL,
                        vision_port INT NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )
            )
            row = conn.execute(
                text("SELECT id FROM automation_comm_config WHERE id = 1 LIMIT 1")
            ).mappings().first()
            if not row:
                conn.execute(
                    text(
                        """
                        INSERT INTO automation_comm_config
                        (id, robot_host, robot_port, vision_host, vision_port, updated_at)
                        VALUES (1, :robot_host, :robot_port, :vision_host, :vision_port, :updated_at)
                        """
                    ),
                    {
                        "robot_host": settings.ROBOT_TCP_HOST,
                        "robot_port": int(settings.ROBOT_TCP_PORT),
                        "vision_host": settings.VISION_TCP_HOST,
                        "vision_port": int(settings.VISION_TCP_PORT),
                        "updated_at": datetime.now(),
                    },
                )

    def get_comm_targets(self) -> dict[str, object]:
        settings = get_settings()
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT robot_host, robot_port, vision_host, vision_port, updated_at
                    FROM automation_comm_config
                    WHERE id = 1
                    LIMIT 1
                    """
                )
            ).mappings().first()
        if not row:
            return {
                "robot_host": settings.ROBOT_TCP_HOST,
                "robot_port": int(settings.ROBOT_TCP_PORT),
                "vision_host": settings.VISION_TCP_HOST,
                "vision_port": int(settings.VISION_TCP_PORT),
                "updated_at": datetime.now(),
            }
        return dict(row)

    def get_cell_state(self) -> tuple[bool, bool, bool]:
        with self.session_factory() as s:
            row = s.execute(select(CellState).where(CellState.id == 1)).scalar_one_or_none()
            if row is None:
                return False, False, False
            return bool(row.running), bool(row.paused), bool(row.simul_mode)

    def set_cell_state(self, running: bool | None = None, paused: bool | None = None, simul_mode: bool | None = None) -> None:
        values = {'updated_at': datetime.now()}
        if running is not None:
            values['running'] = 1 if running else 0
        if paused is not None:
            values['paused'] = 1 if paused else 0
        if simul_mode is not None:
            values['simul_mode'] = 1 if simul_mode else 0
        with self.session_factory() as s:
            s.execute(update(CellState).where(CellState.id == 1).values(**values))
            s.commit()

    def update_queue_state(self, queue_state: dict) -> None:
        with self.session_factory() as s:
            s.execute(
                update(CellState)
                .where(CellState.id == 1)
                .values(queue_state=queue_state, updated_at=datetime.now())
            )
            s.commit()

    def create_command(
        self,
        file_path: str,
        file_name: str,
        washing_time: int | None = None,
        curing_time: int | None = None,
        target_printer: int | None = None,
    ) -> str:
        # Insert one QUEUED command row and return generated cmd_id.
        settings = get_settings()
        if washing_time is None:
            washing_time = settings.DEFAULT_WASHING_TIME
        if curing_time is None:
            curing_time = settings.DEFAULT_CURING_TIME

        now = datetime.now()
        cmd_id = str(uuid.uuid4())
        row = PrintCommand(
            cmd_id=cmd_id,
            file_path=file_path,
            file_name=file_name,
            cmd_status=int(CmdStatus.QUEUED),
            post_proc_stage=int(PostProcStage.NONE),
            washing_time=washing_time,
            curing_time=curing_time,
            use_yn='Y',
            target_printer=target_printer,
            allocated_data=None,
            progress=0,
            message='QUEUED',
            claimed_by=None,
            locked_at=None,
            created_at=now,
            updated_at=now,
        )
        with self.session_factory() as s:
            s.add(row)
            s.commit()
        self.add_log(
            log_type=int(LogType.PROGRAM),
            source='program',
            cmd_id=cmd_id,
            message='CMD created (QUEUED)',
        )
        return cmd_id

    def list_queued_commands(self, limit: int = 32) -> list[dict]:
        # Read queued jobs for inprocess allocation.
        with self.session_factory() as s:
            rows = (
                s.execute(
                    select(PrintCommand)
                    .where(PrintCommand.cmd_status == int(CmdStatus.QUEUED))
                    .where(PrintCommand.use_yn == 'Y')
                    .order_by(PrintCommand.created_at.asc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )

            return [
                {
                    "cmd_id": r.cmd_id,
                    "file_path": r.file_path,
                    "file_name": r.file_name,
                    "target_printer": r.target_printer,
                    "washing_time": r.washing_time,
                    "curing_time": r.curing_time,
                }
                for r in rows
            ]

    def allocate_to_printer(self, cmd_id: str, printer_id: int, claimed_by: str) -> JobCtx | None:
        # Safe claim/update of one queued command for a target printer.
        with self.session_factory() as s:
            row = s.execute(
                select(PrintCommand).where(PrintCommand.cmd_id == cmd_id).limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None

            alloc = dict(row.allocated_data or {})
            alloc["printer_id"] = printer_id
            alloc.setdefault("plate_state", "ON_PRINTER")
            alloc.setdefault("plate_in_printer", True)

            now = datetime.now()
            res = s.execute(
                update(PrintCommand)
                .where(PrintCommand.cmd_id == cmd_id)
                .where(PrintCommand.cmd_status == int(CmdStatus.QUEUED))
                .where(PrintCommand.use_yn == 'Y')
                .values(
                    cmd_status=int(CmdStatus.CLAIMED),
                    claimed_by=claimed_by,
                    locked_at=now,
                    target_printer=printer_id,
                    allocated_data=alloc,
                    updated_at=now,
                    message=f"ALLOCATED to printer-{printer_id}",
                )
            )
            if res.rowcount != 1:
                s.rollback()
                return None
            s.commit()

            return JobCtx(
                cmd_id=row.cmd_id,
                file_path=row.file_path,
                file_name=row.file_name,
                washing_time=row.washing_time or get_settings().DEFAULT_WASHING_TIME,
                curing_time=row.curing_time,
                target_printer=printer_id,
                cmd_status=CmdStatus.CLAIMED,
                post_proc_stage=PostProcStage(row.post_proc_stage),
                allocated_data=alloc,
                progress=row.progress,
                message=row.message or "",
            )

    def claim_next_queued(self, claimed_by: str) -> JobCtx | None:
        # generic claim
        return self.claim_next_queued_for_printer(claimed_by=claimed_by, printer_id=None)

    def claim_next_queued_for_printer(self, claimed_by: str, printer_id: int | None) -> JobCtx | None:
        # Generic claim path with optional printer filter.
        with self.session_factory() as s:
            q = (
                select(PrintCommand)
                .where(PrintCommand.cmd_status == int(CmdStatus.QUEUED))
                .where(PrintCommand.use_yn == 'Y')
                .order_by(PrintCommand.created_at.asc())
                .limit(1)
            )
            if printer_id is not None:
                q = (
                    select(PrintCommand)
                    .where(PrintCommand.cmd_status == int(CmdStatus.QUEUED))
                    .where(PrintCommand.use_yn == 'Y')
                    .where((PrintCommand.target_printer.is_(None)) | (PrintCommand.target_printer == printer_id))
                    .order_by(PrintCommand.created_at.asc())
                    .limit(1)
                )

            candidate = s.execute(q).scalar_one_or_none()
            if candidate is None:
                return None

            now = datetime.now()
            alloc = dict(candidate.allocated_data or {})
            if printer_id is not None:
                alloc["printer_id"] = printer_id
                alloc.setdefault("plate_state", "ON_PRINTER")

            res = s.execute(
                update(PrintCommand)
                .where(PrintCommand.cmd_id == candidate.cmd_id)
                .where(PrintCommand.cmd_status == int(CmdStatus.QUEUED))
                .where(PrintCommand.use_yn == 'Y')
                .values(
                    cmd_status=int(CmdStatus.CLAIMED),
                    claimed_by=claimed_by,
                    locked_at=now,
                    allocated_data=alloc,
                    updated_at=now,
                    message='CLAIMED',
                )
            )

            if res.rowcount != 1:
                s.rollback()
                return None

            s.commit()

            return JobCtx(
                cmd_id=candidate.cmd_id,
                file_path=candidate.file_path,
                file_name=candidate.file_name,
                washing_time=candidate.washing_time or get_settings().DEFAULT_WASHING_TIME,
                curing_time=candidate.curing_time,
                target_printer=printer_id if printer_id is not None else candidate.target_printer,
                cmd_status=CmdStatus.CLAIMED,
                post_proc_stage=PostProcStage(candidate.post_proc_stage),
                allocated_data=alloc,
                progress=candidate.progress,
                message=candidate.message or '',
            )

    def update_command(self, cmd_id: str, **fields) -> None:
        # Generic update helper used by all sequence steps.
        log_type_val = int(fields.pop('_log_type', int(LogType.SEQUENCE)))
        log_source = str(fields.pop('_log_source', 'sequence'))
        log_enabled = bool(fields.pop('_log', True))
        msg_for_log = fields.get('message')
        fields['updated_at'] = datetime.now()
        with self.session_factory() as s:
            s.execute(update(PrintCommand).where(PrintCommand.cmd_id == cmd_id).values(**fields))
            s.commit()
        if log_enabled and isinstance(msg_for_log, str) and msg_for_log.strip():
            self.add_log(
                log_type=log_type_val,
                source=log_source,
                cmd_id=cmd_id,
                message=msg_for_log,
            )

    def append_log(self, cmd_id: str, msg: str) -> None:
        self.update_command(
            cmd_id,
            message=msg,
            _log_type=int(LogType.SEQUENCE),
            _log_source='sequence',
        )

    def add_log(self, log_type: int, source: str, message: str, cmd_id: str | None = None) -> None:
        if not message:
            return
        row = AutomationLog(
            log_type=int(log_type),
            source=source[:64],
            cmd_id=cmd_id,
            message=message[:2048],
            created_at=datetime.now(),
        )
        with self.session_factory() as s:
            s.add(row)
            s.commit()

    def mark_error(self, cmd_id: str, message: str) -> None:
        self.update_command(cmd_id, cmd_status=int(CmdStatus.ERROR), message=message)

    def cancel_inflight_commands(self, reason: str = "STOP requested") -> int:
        """
        Cancel all non-terminal commands when machine STOP is requested.
        This includes QUEUED rows so runtime queues are effectively drained.
        """
        with self.session_factory() as s:
            res = s.execute(
                update(PrintCommand)
                .where(
                    PrintCommand.cmd_status.in_(
                        [
                            int(CmdStatus.QUEUED),
                            int(CmdStatus.CLAIMED),
                            int(CmdStatus.PRINTING),
                            int(CmdStatus.PRINT_FINISHED),
                            int(CmdStatus.POST_PROCESSING),
                        ]
                    )
                )
                .values(
                    cmd_status=int(CmdStatus.CANCELED),
                    message=reason,
                    locked_at=None,
                    updated_at=datetime.now(),
                )
            )
            s.commit()
            return int(res.rowcount or 0)
