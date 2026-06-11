from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.constants import EventType, SessionStatus
from app.core.logger import get_logger
from app.models.admin import Admin
from app.repositories.daily_attendance_repo import DailyAttendanceRepository
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.event_repo import EventRepository
from app.services.settings_service import get_settings_service
from app.utils.time_utils import local_day_bounds, local_tz, to_local

log = get_logger(__name__)


@dataclass
class ComputedDay:
    in_time: datetime | None
    out_time: datetime | None
    first_break_out: datetime | None
    first_break_in: datetime | None
    break_count: int
    total_work_seconds: int
    total_break_seconds: int
    late_minutes: int
    early_exit_minutes: int
    any_manual: bool


@dataclass
class CloseDayResult:
    closed: int
    already_closed: int
    no_activity: int


class DailyAttendanceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.event_repo = EventRepository(db)
        self.daily_repo = DailyAttendanceRepository(db)
        self.employee_repo = EmployeeRepository(db)

    # ------------------------------------------------------------------
    # Pure computation — no DB writes here
    # ------------------------------------------------------------------

    def _compute(self, events: list, work_date: date) -> ComputedDay:
        """Walk the ordered event list and derive the day's summary.

        Handles arbitrary numbers of BREAK_OUT/BREAK_IN pairs. OUT finalizes
        the day. A trailing BREAK_OUT without a matching BREAK_IN and no OUT
        is treated as an open break (session stays INCOMPLETE).
        """
        in_time: datetime | None = None
        out_time: datetime | None = None
        first_break_out: datetime | None = None
        first_break_in: datetime | None = None
        break_count = 0
        total_work = 0
        total_break = 0
        any_manual = False

        current_state: str | None = None  # "WORKING", "ON_BREAK", or None
        last_boundary: datetime | None = None

        for ev in events:
            if ev.is_manual:
                any_manual = True

            et = ev.event_type
            if et == EventType.IN:
                if in_time is None:
                    in_time = ev.event_time
                    current_state = "WORKING"
                    last_boundary = ev.event_time
            elif et == EventType.BREAK_OUT:
                if current_state == "WORKING" and last_boundary is not None:
                    total_work += int((ev.event_time - last_boundary).total_seconds())
                current_state = "ON_BREAK"
                last_boundary = ev.event_time
                if first_break_out is None:
                    first_break_out = ev.event_time
                break_count += 1
            elif et == EventType.BREAK_IN:
                if current_state == "ON_BREAK" and last_boundary is not None:
                    total_break += int((ev.event_time - last_boundary).total_seconds())
                current_state = "WORKING"
                last_boundary = ev.event_time
                if first_break_in is None:
                    first_break_in = ev.event_time
            elif et == EventType.OUT:
                if current_state == "WORKING" and last_boundary is not None:
                    total_work += int((ev.event_time - last_boundary).total_seconds())
                elif current_state == "ON_BREAK" and last_boundary is not None:
                    total_break += int((ev.event_time - last_boundary).total_seconds())
                out_time = ev.event_time
                current_state = None
                last_boundary = ev.event_time

        total_work = max(0, total_work)
        total_break = max(0, total_break)

        late_minutes, early_exit_minutes = self._late_early(
            in_time, out_time, work_date
        )

        return ComputedDay(
            in_time=in_time,
            out_time=out_time,
            first_break_out=first_break_out,
            first_break_in=first_break_in,
            break_count=break_count,
            total_work_seconds=total_work,
            total_break_seconds=total_break,
            late_minutes=late_minutes,
            early_exit_minutes=early_exit_minutes,
            any_manual=any_manual,
        )

    @staticmethod
    def _late_early(
        in_time: datetime | None, out_time: datetime | None, work_date: date
    ) -> tuple[int, int]:
        s = get_settings_service().get()
        tz = local_tz()
        late = 0
        early = 0
        if s.work_start_time is not None and in_time is not None:
            expected_in = datetime.combine(work_date, s.work_start_time, tzinfo=tz)
            delta_min = int((to_local(in_time) - expected_in).total_seconds() // 60)
            late = max(0, delta_min - int(s.grace_minutes))
        if s.work_end_time is not None and out_time is not None:
            expected_out = datetime.combine(work_date, s.work_end_time, tzinfo=tz)
            delta_min = int((expected_out - to_local(out_time)).total_seconds() // 60)
            early = max(0, delta_min - int(s.early_exit_grace_minutes))
        return late, early

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recompute(self, employee_id: int, work_date: date) -> None:
        start, end = local_day_bounds(work_date)
        events = self.event_repo.list_for_employee_between(employee_id, start, end)
        computed = self._compute(events, work_date)

        if computed.out_time is not None and computed.in_time is not None:
            status = SessionStatus.PRESENT
        elif computed.in_time is not None:
            status = SessionStatus.INCOMPLETE
        else:
            status = SessionStatus.ABSENT

        row = self.daily_repo.upsert_for_day(employee_id, work_date)
        row.in_time = computed.in_time
        row.break_out_time = computed.first_break_out
        row.break_in_time = computed.first_break_in
        row.out_time = computed.out_time
        row.total_work_seconds = computed.total_work_seconds
        row.total_break_seconds = computed.total_break_seconds
        row.break_count = computed.break_count
        row.late_minutes = computed.late_minutes
        row.early_exit_minutes = computed.early_exit_minutes
        row.status = status
        row.is_manually_adjusted = computed.any_manual
        self.db.flush()
        log.debug(
            "Daily recomputed emp=%s date=%s status=%s work=%ds break=%ds breaks=%d late=%dm early=%dm",
            employee_id,
            work_date,
            status.value,
            computed.total_work_seconds,
            computed.total_break_seconds,
            computed.break_count,
            computed.late_minutes,
            computed.early_exit_minutes,
        )

    def close_day(self, work_date: date, admin: Admin | None = None) -> CloseDayResult:
        """Reclassify trailing BREAK_OUT → OUT for the given day.

        For every employee who had at least one event that day:
          - If the last event is BREAK_OUT (they never came back), convert it to OUT
            in place (`is_manual=True`, `corrected_by=admin.id` if provided).
          - If the last event is already OUT or BREAK_IN/IN, leave as-is; the
            session remains INCOMPLETE until an OUT is entered manually.
        Recomputes the daily rollup for each affected employee and marks
        `is_day_closed=True`.
        """
        start, end = local_day_bounds(work_date)

        from sqlalchemy import distinct, select

        from app.models.attendance_event import AttendanceEvent

        stmt = select(distinct(AttendanceEvent.employee_id)).where(
            AttendanceEvent.event_time >= start,
            AttendanceEvent.event_time < end,
        )
        employee_ids = [int(r) for r in self.db.execute(stmt).scalars().all()]

        closed = 0
        already_closed = 0
        no_activity = 0

        for emp_id in employee_ids:
            existing = self.daily_repo.get_for_day(emp_id, work_date)
            if existing is not None and existing.is_day_closed:
                already_closed += 1
                continue

            events = self.event_repo.list_for_employee_between(emp_id, start, end)
            if not events:
                no_activity += 1
                continue

            last_event = events[-1]
            if last_event.event_type == EventType.BREAK_OUT:
                last_event.event_type = EventType.OUT
                last_event.is_manual = True
                if admin is not None:
                    last_event.corrected_by = admin.id
                last_event.note = (
                    (last_event.note or "") + " [auto-closed: trailing BREAK_OUT → OUT]"
                ).strip()
                self.db.flush()

            self.recompute(emp_id, work_date)
            row = self.daily_repo.get_for_day(emp_id, work_date)
            if row is not None:
                row.is_day_closed = True
            closed += 1

        self.db.flush()
        log.info(
            "Day close %s: closed=%d already_closed=%d no_activity=%d",
            work_date,
            closed,
            already_closed,
            no_activity,
        )
        return CloseDayResult(
            closed=closed,
            already_closed=already_closed,
            no_activity=no_activity,
        )

    def recompute_range(
        self,
        *,
        employee_id: int | None,
        start: date,
        end: date,
        chunk_commit_every: int = 200,
    ) -> int:
        """Force-recompute the daily rollup for every (employee, date) in the range.

        H6 fix — was previously N×M queries inside one transaction. For a
        quarter range × 100 employees that was 30,000+ round-trips holding
        locks the entire time, which drained the pool and stalled camera
        attendance INSERTs.

        Now:
          - ONE query loads every event in the range (server-side ordered).
          - Pure-Python bucketing by (employee_id, local_date).
          - Per-day _compute() is the same pure function as recompute().
          - Upserts happen in chunks, committing every N rows so locks do
            not span the whole job.

        If `employee_id` is None, recomputes every employee who had at least
        one event in the range. Returns the number of (employee, date)
        combinations touched.
        """
        if end < start:
            start, end = end, start

        from sqlalchemy import asc, select

        from app.models.attendance_event import AttendanceEvent
        from app.utils.time_utils import local_date_of

        range_start, _ = local_day_bounds(start)
        _, range_end = local_day_bounds(end)

        stmt = (
            select(AttendanceEvent)
            .where(
                AttendanceEvent.event_time >= range_start,
                AttendanceEvent.event_time < range_end,
            )
            .order_by(
                asc(AttendanceEvent.employee_id),
                asc(AttendanceEvent.event_time),
            )
        )
        if employee_id is not None:
            stmt = stmt.where(AttendanceEvent.employee_id == employee_id)

        all_events = list(self.db.execute(stmt).scalars().all())

        # Bucket events into (employee_id, local_date) -> ordered events.
        buckets: dict[tuple[int, date], list[AttendanceEvent]] = {}
        seen_employees: set[int] = set()
        for ev in all_events:
            key = (ev.employee_id, local_date_of(ev.event_time))
            buckets.setdefault(key, []).append(ev)
            seen_employees.add(ev.employee_id)

        # Build the full date range so absent days also get an ABSENT rollup.
        dates: list[date] = []
        cur = start
        while cur <= end:
            dates.append(cur)
            cur += timedelta(days=1)

        if employee_id is not None:
            employees = [employee_id]
        else:
            employees = sorted(seen_employees)

        touched = 0
        chunked_since_commit = 0
        for emp_id in employees:
            for d in dates:
                events = buckets.get((emp_id, d), [])
                self._apply_rollup(emp_id, d, events)
                touched += 1
                chunked_since_commit += 1
                if chunked_since_commit >= chunk_commit_every:
                    self.db.flush()
                    self.db.commit()
                    chunked_since_commit = 0

        self.db.flush()
        # Caller's session_scope will commit; an explicit commit here would
        # double-flush some sessions. Last chunk lands at scope exit.
        log.info(
            "recompute_range employees=%d dates=%d touched=%d",
            len(employees),
            len(dates),
            touched,
        )
        return touched

    def _apply_rollup(
        self, employee_id: int, work_date: date, events: list
    ) -> None:
        """Compute + upsert one (employee, date). No DB read for events —
        the caller supplies them pre-loaded. Used by recompute_range."""
        computed = self._compute(events, work_date)
        if computed.out_time is not None and computed.in_time is not None:
            status = SessionStatus.PRESENT
        elif computed.in_time is not None:
            status = SessionStatus.INCOMPLETE
        else:
            status = SessionStatus.ABSENT
        row = self.daily_repo.upsert_for_day(employee_id, work_date)
        row.in_time = computed.in_time
        row.break_out_time = computed.first_break_out
        row.break_in_time = computed.first_break_in
        row.out_time = computed.out_time
        row.total_work_seconds = computed.total_work_seconds
        row.total_break_seconds = computed.total_break_seconds
        row.break_count = computed.break_count
        row.late_minutes = computed.late_minutes
        row.early_exit_minutes = computed.early_exit_minutes
        row.status = status
        row.is_manually_adjusted = computed.any_manual

    def reopen_day(self, work_date: date) -> int:
        """Clear the is_day_closed flag for all employees on this date.

        Does NOT revert any OUT events that were created during close_day —
        use the manual event API to undo specific events.
        """
        rows = self.daily_repo.list_by_date(work_date)
        count = 0
        for row in rows:
            if row.is_day_closed:
                row.is_day_closed = False
                count += 1
        self.db.flush()
        return count
