from datetime import datetime, timedelta

from .models import Alarm, RecurrenceKind


def _matches_day(alarm: Alarm, weekday: int) -> bool:
    if alarm.recurrence.kind is RecurrenceKind.DAILY:
        return True
    if alarm.recurrence.kind is RecurrenceKind.WEEKDAYS:
        return weekday < 5
    return weekday in alarm.recurrence.days


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
        if not _matches_day(alarm, day.weekday()):
            continue
        occurrence = datetime.combine(day, alarm.scheduled_time)
        if occurrence >= after:
            return occurrence
    return None


def previous_occurrence(alarm: Alarm, before: datetime) -> datetime | None:
    if before.tzinfo is not None:
        raise ValueError("scheduler clock must return a local datetime without a timezone")
    if alarm.recurrence.kind is RecurrenceKind.ONCE:
        if alarm.scheduled_date is None:
            return None
        occurrence = datetime.combine(alarm.scheduled_date, alarm.scheduled_time)
        return occurrence if occurrence < before else None

    for offset in range(8):
        day = before.date() - timedelta(days=offset)
        if not _matches_day(alarm, day.weekday()):
            continue
        occurrence = datetime.combine(day, alarm.scheduled_time)
        if occurrence < before:
            return occurrence
    return None
