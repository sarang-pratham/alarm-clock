from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Callable

from .models import Alarm, RecurrenceKind
from .storage import JsonAlarmStore


class AlarmNotFoundError(LookupError):
    pass


class AlarmAlreadyExistsError(ValueError):
    pass


class OccurrenceState(StrEnum):
    RINGING = "ringing"
    SNOOZED = "snoozed"


@dataclass(frozen=True, slots=True)
class AlarmRuntime:
    state: OccurrenceState
    scheduled_at: datetime
    snoozed_until: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", OccurrenceState(self.state))
        if self.scheduled_at.tzinfo is not None:
            raise ValueError("scheduled_at must use local time without a timezone")
        if self.state is OccurrenceState.SNOOZED:
            if self.snoozed_until is None or self.snoozed_until.tzinfo is not None:
                raise ValueError("snoozed occurrences require a local snoozed_until time")
        elif self.snoozed_until is not None:
            raise ValueError("snoozed_until is only valid for snoozed occurrences")


class AlarmService:
    mutable_fields = {
        "scheduled_time",
        "label",
        "enabled",
        "recurrence",
        "snooze_minutes",
        "scheduled_date",
    }

    def __init__(self, store: JsonAlarmStore, on_change: Callable[[], None] | None = None) -> None:
        self._store = store
        self._on_change = on_change
        self._alarms = {alarm.id: alarm for alarm in store.load()}
        self._runtime: dict[str, AlarmRuntime] = {}

    def list_alarms(self) -> list[Alarm]:
        return sorted(
            self._alarms.values(),
            key=lambda alarm: (alarm.scheduled_time, alarm.scheduled_date or date.min, alarm.id),
        )

    def get(self, alarm_id: str) -> Alarm:
        try:
            return self._alarms[alarm_id]
        except KeyError as error:
            raise AlarmNotFoundError(f"alarm {alarm_id!r} does not exist") from error

    def create(self, alarm: Alarm) -> Alarm:
        if not isinstance(alarm, Alarm):
            raise ValueError("alarm must be an Alarm value")
        if alarm.id in self._alarms:
            raise AlarmAlreadyExistsError(f"alarm {alarm.id!r} already exists")
        updated = dict(self._alarms)
        updated[alarm.id] = alarm
        self._save_and_replace(updated)
        self._notify_change()
        return alarm

    def update(self, alarm_id: str, **changes: object) -> Alarm:
        current = self.get(alarm_id)
        if not changes:
            raise ValueError("at least one alarm field must be updated")
        invalid_fields = set(changes) - self.mutable_fields
        if invalid_fields:
            fields = ", ".join(sorted(invalid_fields))
            raise ValueError(f"unsupported alarm field(s): {fields}")
        updated_alarm = replace(current, **changes)
        updated = dict(self._alarms)
        updated[alarm_id] = updated_alarm
        runtime = dict(self._runtime)
        if changes.get("enabled") is False:
            runtime.pop(alarm_id, None)
        self._save_and_replace(updated, runtime)
        self._notify_change()
        return updated_alarm

    def delete(self, alarm_id: str) -> Alarm:
        deleted = self.get(alarm_id)
        updated = dict(self._alarms)
        del updated[alarm_id]
        runtime = dict(self._runtime)
        runtime.pop(alarm_id, None)
        self._save_and_replace(updated, runtime)
        self._notify_change()
        return deleted

    def enable(self, alarm_id: str) -> Alarm:
        return self.update(alarm_id, enabled=True)

    def disable(self, alarm_id: str) -> Alarm:
        return self.update(alarm_id, enabled=False)

    def set_change_callback(self, callback: Callable[[], None] | None) -> None:
        self._on_change = callback

    def runtime_for(self, alarm_id: str) -> AlarmRuntime | None:
        self.get(alarm_id)
        return self._runtime.get(alarm_id)

    def mark_ringing(self, alarm_id: str, scheduled_at: datetime) -> None:
        self.get(alarm_id)
        self._runtime[alarm_id] = AlarmRuntime(OccurrenceState.RINGING, scheduled_at)

    def snooze(self, alarm_id: str, now: datetime | None = None) -> datetime:
        alarm = self.get(alarm_id)
        runtime = self._runtime.get(alarm_id)
        if runtime is None:
            raise ValueError(f"alarm {alarm_id!r} is not ringing")
        if now is None:
            now = datetime.now()
        if now.tzinfo is not None:
            raise ValueError("snooze clock must return a local datetime without a timezone")
        snoozed_until = now + timedelta(minutes=alarm.snooze_minutes)
        self._runtime[alarm_id] = AlarmRuntime(
            OccurrenceState.SNOOZED,
            runtime.scheduled_at,
            snoozed_until,
        )
        self._notify_change()
        return snoozed_until

    def dismiss(self, alarm_id: str) -> Alarm:
        alarm = self.get(alarm_id)
        if alarm_id not in self._runtime:
            raise ValueError(f"alarm {alarm_id!r} is not ringing")
        if alarm.recurrence.kind is RecurrenceKind.ONCE:
            self.update(alarm_id, enabled=False)
            return self.get(alarm_id)
        self._runtime.pop(alarm_id, None)
        self._notify_change()
        return alarm

    def _save_and_replace(
        self,
        updated: dict[str, Alarm],
        runtime: dict[str, AlarmRuntime] | None = None,
    ) -> None:
        self._store.save(updated.values())
        self._alarms = updated
        if runtime is not None:
            self._runtime = runtime

    def _notify_change(self) -> None:
        if self._on_change is not None:
            self._on_change()
