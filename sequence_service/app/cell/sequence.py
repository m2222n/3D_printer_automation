from __future__ import annotations

import time
from abc import ABC, abstractmethod

# Abstract C#-style sequence base.
# All concrete sequences inherit this and implement step-driven logic.


class Sequence(ABC):
    """
    C# Sequence.cs style base (adapted for Python).
    - now_step / before_step tracking
    - sequence_run() guards working flag
    - init/get_db_info hooks at step 0
    """

    def __init__(self, sequence_name: str) -> None:
        # Sequence identifier (used in logs/messages)
        self.sequence_name = sequence_name
        # Re-entrancy guard for one-tick execution
        self._sequence_is_working = False
        # Step bookkeeping
        self.before_step = 0
        self._now_step = 0

        # Origin-related flags (kept for C# compatibility)
        self._origin_step = 0
        self.is_origin = False
        # Master enable/disable switch for this sequence
        self.enable_sequence = True

        # Timestamp for elapsed_ms() helper
        self._step_started_at = time.monotonic()

    @property
    def sequence_is_working(self) -> bool:
        return self._sequence_is_working

    @property
    def now_step(self) -> int:
        return self._now_step

    @now_step.setter
    def now_step(self, value: int) -> None:
        # Any step change updates before_step and step timer
        self.before_step = self._now_step
        self._now_step = int(value)
        self._step_started_at = time.monotonic()

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._step_started_at) * 1000)

    def sequence_run(self) -> bool:
        # Full run mode: when step=0, call get_db_info + init once
        if self._sequence_is_working or not self.enable_sequence:
            return self._sequence_is_working

        if self.now_step == 0:
            self.get_db_info()
            self.init()

        self._sequence_is_working = True
        self.before_step = self.now_step
        try:
            self.sequence_logic(self.now_step)
        finally:
            self._sequence_is_working = False
        return self._sequence_is_working

    def sequence_run_void(self) -> None:
        # Tick mode: lightweight runner called by SequenceThread loop
        if self._sequence_is_working or not self.enable_sequence:
            return

        if self.now_step == 0:
            self.get_db_info()

        self._sequence_is_working = True
        self.before_step = self.now_step
        try:
            self.sequence_logic(self.now_step)
        finally:
            self._sequence_is_working = False

    def machine_stop(self) -> None:
        # Global stop hook + step reset
        self.machine_stop_logic()
        self.now_step = 0
        self.before_step = 0
        self._sequence_is_working = False

    def machine_pause(self) -> None:
        # Per-sequence pause hook
        self.machine_pause_logic()
        self._sequence_is_working = False

    def origin(self) -> bool:
        return self.origin_logic()

    @abstractmethod
    def sequence_logic(self, step: int) -> None:
        ...

    @abstractmethod
    def machine_stop_logic(self) -> None:
        ...

    @abstractmethod
    def machine_pause_logic(self) -> None:
        ...

    @abstractmethod
    def origin_logic(self) -> bool:
        ...

    @abstractmethod
    def get_db_info(self) -> None:
        ...

    @abstractmethod
    def save_data(self) -> None:
        ...

    @abstractmethod
    def init(self) -> None:
        ...

    @abstractmethod
    def step_update_to_db(self, cmd_id: str, now_step: str, is_complete: bool, remark: str) -> None:
        ...
