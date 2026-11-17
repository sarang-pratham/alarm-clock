import unittest
from datetime import date, datetime, time

from alarm_clock.models import Alarm, Recurrence, RecurrenceKind


class RecurrenceTests(unittest.TestCase):
    def test_custom_recurrence_accepts_unique_weekdays(self) -> None:
        recurrence = Recurrence(RecurrenceKind.CUSTOM, (0, 2, 6))

        self.assertEqual(recurrence.days, (0, 2, 6))

    def test_custom_recurrence_requires_days(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one weekday"):
            Recurrence(RecurrenceKind.CUSTOM)

    def test_weekdays_are_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "from 0 to 6"):
            Recurrence(RecurrenceKind.CUSTOM, (7,))
        with self.assertRaisesRegex(ValueError, "duplicates"):
            Recurrence(RecurrenceKind.CUSTOM, (1, 1))

    def test_only_custom_recurrence_accepts_weekday_selections(self) -> None:
        with self.assertRaisesRegex(ValueError, "only valid for custom"):
            Recurrence(RecurrenceKind.DAILY, (1,))


class AlarmTests(unittest.TestCase):
    def test_one_time_alarm_has_defaults_and_unique_identity(self) -> None:
        first = Alarm(scheduled_time=time(7, 30), scheduled_date=date(2026, 11, 18))
        second = Alarm(scheduled_time=time(7, 30), scheduled_date=date(2026, 11, 18))

        self.assertTrue(first.enabled)
        self.assertEqual(first.snooze_minutes, 5)
        self.assertNotEqual(first.id, second.id)
        self.assertIsInstance(first.created_at, datetime)

    def test_recurring_alarm_does_not_require_a_date(self) -> None:
        alarm = Alarm(
            scheduled_time=time(8, 0),
            recurrence=Recurrence(RecurrenceKind.DAILY),
        )

        self.assertIsNone(alarm.scheduled_date)

    def test_one_time_alarm_requires_a_date(self) -> None:
        with self.assertRaisesRegex(ValueError, "require a scheduled_date"):
            Alarm(scheduled_time=time(8, 0))

    def test_rejects_timezone_aware_or_subminute_alarm_times(self) -> None:
        with self.assertRaisesRegex(ValueError, "without a timezone"):
            Alarm(
                scheduled_time=time(8, 0, tzinfo=datetime.now().astimezone().tzinfo),
                scheduled_date=date(2026, 11, 18),
            )
        with self.assertRaisesRegex(ValueError, "minute precision"):
            Alarm(scheduled_time=time(8, 0, 1), scheduled_date=date(2026, 11, 18))

    def test_normalizes_blank_labels_and_rejects_bad_snooze(self) -> None:
        alarm = Alarm(scheduled_time=time(8, 0), scheduled_date=date(2026, 11, 18), label="  ")
        self.assertIsNone(alarm.label)

        with self.assertRaisesRegex(ValueError, "from 1 to 1440"):
            Alarm(
                scheduled_time=time(8, 0),
                scheduled_date=date(2026, 11, 18),
                snooze_minutes=0,
            )


if __name__ == "__main__":
    unittest.main()
