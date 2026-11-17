from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum
from uuid import uuid4


class RecurrenceKind(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class Recurrence:
    kind: RecurrenceKind = RecurrenceKind.ONCE
    days: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        try:
            kind = RecurrenceKind(self.kind)
        except ValueError as error:
            allowed = ", ".join(item.value for item in RecurrenceKind)
            raise ValueError(f"recurrence must be one of: {allowed}") from error
        object.__setattr__(self, "kind", kind)

        if not isinstance(self.days, tuple):
            object.__setattr__(self, "days", tuple(self.days))

        if any(type(day) is not int or day not in range(7) for day in self.days):
            raise ValueError("recurrence days must be weekday numbers from 0 to 6")
        if len(set(self.days)) != len(self.days):
            raise ValueError("recurrence days must not contain duplicates")

        if kind is RecurrenceKind.CUSTOM and not self.days:
            raise ValueError("custom recurrence requires at least one weekday")
        if kind is not RecurrenceKind.CUSTOM and self.days:
            raise ValueError("weekday selections are only valid for custom recurrence")


@dataclass(frozen=True, slots=True)
class Alarm:
    scheduled_time: time
    label: str | None = None
    enabled: bool = True
    recurrence: Recurrence = field(default_factory=Recurrence)
    snooze_minutes: int = 5
    scheduled_date: date | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if not isinstance(self.scheduled_time, time) or self.scheduled_time.tzinfo is not None:
            raise ValueError("scheduled_time must be a local time without a timezone")
        if self.scheduled_time.second or self.scheduled_time.microsecond:
            raise ValueError("scheduled_time must have minute precision")
        if not isinstance(self.recurrence, Recurrence):
            raise ValueError("recurrence must be a Recurrence value")
        if type(self.enabled) is not bool:
            raise ValueError("enabled must be true or false")
        if type(self.snooze_minutes) is not int or not 1 <= self.snooze_minutes <= 1440:
            raise ValueError("snooze_minutes must be an integer from 1 to 1440")
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("id must be a non-empty string")
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be a datetime")
        if self.created_at.tzinfo is not None:
            raise ValueError("created_at must use local time without a timezone")
        if self.label is not None and not isinstance(self.label, str):
            raise ValueError("label must be text")
        if self.label is not None:
            normalized_label = self.label.strip()
            object.__setattr__(self, "label", normalized_label or None)

        if self.recurrence.kind is RecurrenceKind.ONCE:
            if not isinstance(self.scheduled_date, date):
                raise ValueError("one-time alarms require a scheduled_date")
        elif self.scheduled_date is not None:
            raise ValueError("scheduled_date is only valid for one-time alarms")

