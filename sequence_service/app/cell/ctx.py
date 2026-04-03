from collections import deque
from dataclasses import dataclass, field
from typing import Any

from app.cell.enums import CmdStatus, PostProcStage

# Shared runtime context models for the sequence thread and all sequences.


@dataclass
class JobCtx:
    # Immutable identity for a single print command/job
    cmd_id: str
    file_path: str
    file_name: str
    # Effective stage durations used by washing/curing sequences (seconds)
    washing_time: int = 6
    curing_time: int = 120
    # Allocated/target printer index (1..4)
    target_printer: int | None = None

    # High-level process state and post-process sub-state
    cmd_status: CmdStatus = CmdStatus.QUEUED
    post_proc_stage: PostProcStage = PostProcStage.NONE

    # Dynamic runtime payload shared across sequences
    allocated_data: dict[str, Any] = field(default_factory=dict)
    progress: int = 0
    message: str = ''


@dataclass
class RobotTask:
    # Job id and task code:
    # SW = StartWashing (printer -> wash)
    # FW = FinishWashing (wash -> empty printer, and reserve cure)
    # SC = StartCure (printer -> cure)
    # FC = FinishCure (cure -> output)
    cmd_id: str    # 어떤 작업인지
    task_type: str
    from_unit: str # 이동 출발
    to_unit: str   # 도착장비
    requested_by: str # 어떤 시퀀스가 요청했는지
    status: str = 'WAIT' #  task 상태

    @property
    def ack_key(self) -> str:
        return f'{self.cmd_id}:{self.task_type}'


@dataclass
class RuntimeCtx:
    # Repository handle and machine-level control state
    repo: Any
    running: bool = False
    paused: bool = False

    # All active jobs currently managed in-memory by sequence runtime
    active_jobs: dict[str, JobCtx] = field(default_factory=dict)

    # Printer runtime states
    printer_has_plate: dict[int, bool] = field(default_factory=lambda: {1: True, 2: True, 3: True, 4: True})
    # Use flag consumed by InprocessSequence (Y = can accept next job)
    printer_use: dict[int, str] = field(default_factory=lambda: {1: 'Y', 2: 'Y', 3: 'Y', 4: 'Y'})
    printer_active_cmd: dict[int, str | None] = field(default_factory=lambda: {1: None, 2: None, 3: None, 4: None})
    printer_queues: dict[int, deque[str]] = field(
        default_factory=lambda: {1: deque(), 2: deque(), 3: deque(), 4: deque()}
    )

    # Equipment occupancy states
    wash_active_cmd: dict[int, str | None] = field(default_factory=lambda: {1: None, 2: None})
    cure_active_cmd: dict[int, str | None] = field(default_factory=lambda: {1: None, 2: None})
    robot_active_cmd: str | None = None

    # Stage waiting queues
    wash_waiting: deque[str] = field(default_factory=deque)
    cure_waiting: deque[str] = field(default_factory=deque)
    # Robot task inbox + ACK map used for sequence handshake
    robot_queue: deque[RobotTask] = field(default_factory=deque)
    robot_acks: dict[str, bool] = field(default_factory=dict)
