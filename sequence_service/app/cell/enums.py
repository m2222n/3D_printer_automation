from enum import IntEnum

# Central status enums used across DB/Repository/Sequences.


class CmdStatus(IntEnum):
    # Command lifecycle status (stored as INT in DB)
    UPLOADING = 0
    QUEUED = 10
    CLAIMED = 20
    PRINTING = 30
    PRINT_FINISHED = 40
    POST_PROCESSING = 50
    DONE = 90
    CANCELED = 98
    ERROR = 99


class PostProcStage(IntEnum):
    # Post-process detailed status (stored as INT in DB)
    NONE = 0
    CURE_WAITING = 10
    CURING = 20
    CURE_DONE = 30
    WASH_WAITING = 40
    WASHING = 50
    WASH_DONE = 60
    OUTPUT_DONE = 70


class LogType(IntEnum):
    # Automation log type (stored as INT)
    PROGRAM = 10
    SEQUENCE = 20
    ROBOT = 30
    SYSTEM = 40
