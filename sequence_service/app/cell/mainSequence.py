from __future__ import annotations

from app.cell.sequences.curing import CuringSequence
from app.cell.sequences.inprocess import InprocessSequence
from app.cell.sequences.printer import PrinterSequence
from app.cell.sequences.robot import RobotSequence
from app.cell.sequences.washing import WashingSequence

# Sequence list composition point.
# This file decides which sequence instances run and in what order.


def build_main_sequences(runtime_ctx):
    """
    Build the main sequence list used by SequenceThread.
    Order is execution priority in every tick.
    """
    return [
        # 1) Pull queued DB jobs and assign to available printers
        InprocessSequence(runtime_ctx),
        # 2) Run printer units (4 instances)
        PrinterSequence(runtime_ctx, 1),
        PrinterSequence(runtime_ctx, 2),
        PrinterSequence(runtime_ctx, 3),
        PrinterSequence(runtime_ctx, 4),
        # 3) Shared robot dispatcher for P/W/C transport tasks
        RobotSequence(runtime_ctx),
        # 4) Wash units (2 instances)
        WashingSequence(runtime_ctx, 1),
        WashingSequence(runtime_ctx, 2),
        # 5) Cure units (2 instances)
        CuringSequence(runtime_ctx, 1),
        CuringSequence(runtime_ctx, 2),
    ]
