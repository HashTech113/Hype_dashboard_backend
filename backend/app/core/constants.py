from enum import Enum


class EventType(str, Enum):
    IN = "IN"
    BREAK_OUT = "BREAK_OUT"
    BREAK_IN = "BREAK_IN"
    OUT = "OUT"


class CameraType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class Role(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    VIEWER = "VIEWER"


class SessionStatus(str, Enum):
    PRESENT = "PRESENT"
    INCOMPLETE = "INCOMPLETE"
    ABSENT = "ABSENT"


class UnknownClusterStatus(str, Enum):
    PENDING = "PENDING"      # awaiting admin review
    PROMOTED = "PROMOTED"    # converted to an Employee
    IGNORED = "IGNORED"      # admin discarded the cluster
    MERGED = "MERGED"        # consolidated into another cluster


class UnknownCaptureStatus(str, Enum):
    KEEP = "KEEP"            # active capture, counts toward cluster centroid
    DISCARDED = "DISCARDED"  # excluded from centroid (manually removed or post-hoc rejected)


# Multi-break state machine:
#   None       ──ENTRY──▶ IN
#   IN         ──EXIT──▶  BREAK_OUT
#   BREAK_OUT  ──ENTRY──▶ BREAK_IN
#   BREAK_IN   ──EXIT──▶  BREAK_OUT   (repeats — arbitrarily many breaks)
# OUT is produced only by (a) manual admin entry, or
# (b) day-close job that reclassifies the trailing BREAK_OUT as OUT.
STATE_TRANSITIONS: dict[tuple[EventType | None, CameraType], EventType] = {
    (None, CameraType.ENTRY): EventType.IN,
    (EventType.IN, CameraType.EXIT): EventType.BREAK_OUT,
    (EventType.BREAK_OUT, CameraType.ENTRY): EventType.BREAK_IN,
    (EventType.BREAK_IN, CameraType.EXIT): EventType.BREAK_OUT,
}

# OUT is the only terminal state; once set, no further auto-events for the day.
TERMINAL_STATES: frozenset[EventType] = frozenset({EventType.OUT})
