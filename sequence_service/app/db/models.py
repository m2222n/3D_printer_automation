from datetime import datetime

from sqlalchemy import DateTime, Integer, String, JSON, Index, BigInteger
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PrintCommand(Base):
    __tablename__ = 'print_command'

    cmd_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)

    cmd_status: Mapped[int] = mapped_column(Integer, nullable=False)
    post_proc_stage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    washing_time: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    curing_time: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    use_yn: Mapped[str] = mapped_column(String(1), nullable=False, default='Y')
    target_printer: Mapped[int | None] = mapped_column(Integer, nullable=True)

    allocated_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    claimed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index('idx_status_created', 'cmd_status', 'created_at'),
        Index('idx_locked', 'locked_at'),
    )


class CellState(Base):
    __tablename__ = 'cell_state'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    running: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paused: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    simul_mode: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queue_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AutomationLog(Base):
    __tablename__ = 'automation_log'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    log_type: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    cmd_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    message: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index('idx_automation_log_created', 'created_at'),
        Index('idx_automation_log_type_created', 'log_type', 'created_at'),
    )
