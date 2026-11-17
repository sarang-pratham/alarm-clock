from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Event
from typing import Callable

from .models import Alarm, RecurrenceKind
from .service import AlarmNotFoundError, AlarmService


@dataclass(frozen=True, slots=True)
class ScheduledOccurrence:
    alarm: Alarm
    at: datetime


def next_occurrence(alarm: Alarm, after: datetime) -> datetime | None:
    if after.tzinfo is not None:
        raise ValueError("scheduler clock must return a local datetime without a timezone")

    if alarm.recurrence.kind is RecurrenceKind.ONCE:
        if alarm.scheduled_date is None:
            return None
        occurrence = datetime.combine(alarm.scheduled_date, alarm.scheduled_time)
        return occurrence if occurrence >= after else None

    for offset in range(8):
        day = after.date() + timedelta(days=offset)
        if alarm.recurrence.kind is RecurrenceKind.DAILY:
            matches = True
        elif alarm.recurrence.kind is RecurrenceKind.WEEKDAYS:
            matches = day.weekday() < 5
        else:
            matches = day.weekday() in alarm.recurrence.days
        if not matches:
            continue
        occurrence = datetime.combine(day, alarm.scheduled_time)
        if occurrence >= after:
            return occurrence
    return None


class Scheduler:
    def __init__(
        self,
        service: AlarmService,
        on_trigger: Callable[[Alarm], None],
        clock: Callable[[], datetime] = datetime.now,
        clock_check_interval: float = 60.0,
    ) -> None:
        if clock_check_interval <= 0:
            raise ValueError("clock_check_interval must be positive")
        self._service = service
        self._on_trigger = on_trigger
        self._clock = clock
        self._clock_check_interval = clock_check_interval
        self._wake_event = Event()
        self._stop_event = Event()
        self._occurrences: dict[str, ScheduledOccurrence] = {}
        self._fired: set[tuple[str, datetime]] = set()
        service.set_change_callback(self.wake)
        self.refresh()

    def wake(self) -> None:
        self._wake_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self.wake()

    def refresh(self) -> None:
        now = self._clock()
        if now.tzinfo is not None:
            raise ValueError("scheduler clock must return a local datetime without a timezone")
        occurrences: dict[str, ScheduledOccurrence] = {}
        for alarm in self._service.list_alarms():
            if not alarm.enabled:
                continue
            previous = self._occurrences.get(alarm.id)
            if previous is not None and previous.alarm == alarm and previous.at <= now:
                occurrences[alarm.id] = previous
                continue
            occurrence = self._next_unfired_occurrence(alarm, now)
            if occurrence is not None:
                occurrences[alarm.id] = ScheduledOccurrence(alarm, occurrence)
        self._occurrences = occurrences

    def next_upcoming(self) -> ScheduledOccurrence | None:
        now = self._clock()
        candidates = [
            ScheduledOccurrence(alarm, occurrence)
            for alarm in self._service.list_alarms()
            if alarm.enabled
            if (occurrence := self._next_unfired_occurrence(alarm, now)) is not None
        ]
        return min(candidates, key=lambda item: item.at) if candidates else None

    def run_pending(self) -> list[Alarm]:
        now = self._clock()
        due = sorted(
            (item for item in self._occurrences.values() if item.at <= now),
            key=lambda item: (item.at, item.alarm.id),
        )
        triggered: list[Alarm] = []
        for item in due:
            planned = self._occurrences.get(item.alarm.id)
            if planned != item:
                continue
            try:
                current = self._service.get(item.alarm.id)
            except AlarmNotFoundError:
                self._occurrences.pop(item.alarm.id, None)
                continue
            if current != item.alarm or not current.enabled:
                continue

            self._occurrences.pop(item.alarm.id, None)
            self._fired.add((item.alarm.id, item.at))
            try:
                self._on_trigger(current)
            except Exception:
                pass
            triggered.append(current)

            if current.recurrence.kind is not RecurrenceKind.ONCE:
                try:
                    latest = self._service.get(current.id)
                except AlarmNotFoundError:
                    continue
                if latest == current and latest.enabled:
                    after = max(now, self._clock()) + timedelta(microseconds=1)
                    upcoming = self._next_unfired_occurrence(latest, after)
                    if upcoming is not None:
                        self._occurrences[latest.id] = ScheduledOccurrence(latest, upcoming)
        return triggered

    def _next_unfired_occurrence(self, alarm: Alarm, after: datetime) -> datetime | None:
        occurrence = next_occurrence(alarm, after)
        while occurrence is not None and (alarm.id, occurrence) in self._fired:
            occurrence = next_occurrence(alarm, occurrence + timedelta(microseconds=1))
        return occurrence

    def run_forever(self) -> None:
        self._stop_event.clear()
        self.refresh()
        while not self._stop_event.is_set():
            self.run_pending()
            if self._stop_event.is_set():
                break
            timeout = self._wait_timeout()
            if self._wake_event.wait(timeout):
                self._wake_event.clear()
                if not self._stop_event.is_set():
                    self.refresh()

    def _wait_timeout(self) -> float:
        now = self._clock()
        upcoming = min((item.at for item in self._occurrences.values()), default=None)
        if upcoming is None:
            return self._clock_check_interval
        seconds = max(0.0, (upcoming - now).total_seconds())
        return min(seconds, self._clock_check_interval)
