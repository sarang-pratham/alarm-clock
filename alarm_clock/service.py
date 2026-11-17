from dataclasses import replace
from datetime import date
from typing import Callable

from .models import Alarm
from .storage import JsonAlarmStore


class AlarmNotFoundError(LookupError):
    pass


class AlarmAlreadyExistsError(ValueError):
    pass


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
        self._save_and_replace(updated)
        self._notify_change()
        return updated_alarm

    def delete(self, alarm_id: str) -> Alarm:
        deleted = self.get(alarm_id)
        updated = dict(self._alarms)
        del updated[alarm_id]
        self._save_and_replace(updated)
        self._notify_change()
        return deleted

    def enable(self, alarm_id: str) -> Alarm:
        return self.update(alarm_id, enabled=True)

    def disable(self, alarm_id: str) -> Alarm:
        return self.update(alarm_id, enabled=False)

    def set_change_callback(self, callback: Callable[[], None] | None) -> None:
        self._on_change = callback

    def _save_and_replace(self, updated: dict[str, Alarm]) -> None:
        self._store.save(updated.values())
        self._alarms = updated

    def _notify_change(self) -> None:
        if self._on_change is not None:
            self._on_change()
