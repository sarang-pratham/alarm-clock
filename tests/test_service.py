import tempfile
import unittest
from datetime import date, datetime, time
from pathlib import Path

from alarm_clock.models import Alarm, Recurrence, RecurrenceKind
from alarm_clock.service import (
    AlarmAlreadyExistsError,
    AlarmNotFoundError,
    AlarmService,
    OccurrenceState,
)
from alarm_clock.storage import JsonAlarmStore, StorageError


class AlarmServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = JsonAlarmStore(Path(self.temporary_directory.name) / "alarms.json")
        self.changes: list[list[Alarm]] = []

        def changed() -> None:
            self.changes.append(self.store.load())

        self.service = AlarmService(self.store, on_change=changed)
        self.alarm = Alarm(
            id="wake-up",
            scheduled_time=time(7, 30),
            scheduled_date=date(2026, 11, 18),
            label="Wake up",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_create_persists_before_notifying_and_lists_alarm(self) -> None:
        created = self.service.create(self.alarm)

        self.assertEqual(created, self.alarm)
        self.assertEqual(self.service.list_alarms(), [self.alarm])
        self.assertEqual(self.changes, [[self.alarm]])

    def test_create_rejects_duplicate_id(self) -> None:
        self.service.create(self.alarm)

        with self.assertRaises(AlarmAlreadyExistsError):
            self.service.create(self.alarm)
        self.assertEqual(len(self.changes), 1)

    def test_update_persists_supported_fields(self) -> None:
        self.service.create(self.alarm)

        updated = self.service.update(
            self.alarm.id,
            scheduled_time=time(8, 15),
            label="Later",
            snooze_minutes=10,
        )

        self.assertEqual(updated.scheduled_time, time(8, 15))
        self.assertEqual(updated.label, "Later")
        self.assertEqual(updated.snooze_minutes, 10)
        self.assertEqual(self.store.load(), [updated])
        self.assertEqual(self.changes[-1], [updated])

    def test_update_can_change_recurrence_and_date_together(self) -> None:
        self.service.create(self.alarm)

        updated = self.service.update(
            self.alarm.id,
            recurrence=Recurrence(RecurrenceKind.WEEKDAYS),
            scheduled_date=None,
        )

        self.assertIsNone(updated.scheduled_date)
        self.assertEqual(updated.recurrence.kind, RecurrenceKind.WEEKDAYS)

    def test_invalid_update_keeps_persisted_alarm_unchanged(self) -> None:
        self.service.create(self.alarm)
        change_count = len(self.changes)

        with self.assertRaisesRegex(ValueError, "minute precision"):
            self.service.update(self.alarm.id, scheduled_time=time(8, 0, 1))
        with self.assertRaisesRegex(ValueError, "unsupported alarm field"):
            self.service.update(self.alarm.id, id="different")

        self.assertEqual(self.service.get(self.alarm.id), self.alarm)
        self.assertEqual(self.store.load(), [self.alarm])
        self.assertEqual(len(self.changes), change_count)

    def test_storage_failure_does_not_change_service_state_or_notify(self) -> None:
        self.service.create(self.alarm)
        self.store.path.write_text("broken", encoding="utf-8")
        change_count = len(self.changes)

        with self.assertRaises(StorageError):
            self.service.disable(self.alarm.id)

        self.assertTrue(self.service.get(self.alarm.id).enabled)
        self.assertEqual(len(self.changes), change_count)

    def test_enable_disable_and_delete(self) -> None:
        self.service.create(self.alarm)

        disabled = self.service.disable(self.alarm.id)
        enabled = self.service.enable(self.alarm.id)
        deleted = self.service.delete(self.alarm.id)

        self.assertFalse(disabled.enabled)
        self.assertTrue(enabled.enabled)
        self.assertEqual(deleted, self.alarm)
        self.assertEqual(self.service.list_alarms(), [])
        self.assertEqual(self.store.load(), [])

    def test_unknown_ids_raise_for_get_update_and_delete(self) -> None:
        for operation in (
            lambda: self.service.get("unknown"),
            lambda: self.service.update("unknown", label="x"),
            lambda: self.service.delete("unknown"),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(AlarmNotFoundError):
                    operation()

    def test_list_is_sorted_by_time(self) -> None:
        later = Alarm(id="later", scheduled_time=time(9, 0), scheduled_date=date(2026, 11, 18))
        self.service.create(later)
        self.service.create(self.alarm)

        self.assertEqual([alarm.id for alarm in self.service.list_alarms()], ["wake-up", "later"])

    def test_snooze_preserves_alarm_identity_and_can_be_repeated(self) -> None:
        self.service.create(self.alarm)
        occurrence = datetime(2026, 11, 18, 7, 30)
        self.service.mark_ringing(self.alarm.id, occurrence)

        first = self.service.snooze(self.alarm.id, datetime(2026, 11, 18, 7, 31))
        runtime = self.service.runtime_for(self.alarm.id)
        self.assertEqual(first, datetime(2026, 11, 18, 7, 36))
        self.assertEqual(runtime.state, OccurrenceState.SNOOZED)
        self.assertEqual(runtime.scheduled_at, occurrence)

        second = self.service.snooze(self.alarm.id, datetime(2026, 11, 18, 7, 35))
        runtime = self.service.runtime_for(self.alarm.id)
        self.assertEqual(second, datetime(2026, 11, 18, 7, 40))
        self.assertEqual(runtime.scheduled_at, occurrence)

    def test_snooze_requires_a_ringing_alarm(self) -> None:
        self.service.create(self.alarm)

        with self.assertRaisesRegex(ValueError, "not ringing"):
            self.service.snooze(self.alarm.id, datetime(2026, 11, 18, 7, 31))

    def test_dismiss_disables_one_time_and_keeps_recurring_alarms_configured(self) -> None:
        self.service.create(self.alarm)
        self.service.mark_ringing(self.alarm.id, datetime(2026, 11, 18, 7, 30))

        dismissed_once = self.service.dismiss(self.alarm.id)

        self.assertFalse(dismissed_once.enabled)
        self.assertIsNone(self.service.runtime_for(self.alarm.id))
        self.assertEqual(self.store.load(), [dismissed_once])

        recurring = Alarm(
            id="daily",
            scheduled_time=time(8, 0),
            recurrence=Recurrence(RecurrenceKind.DAILY),
        )
        self.service.create(recurring)
        self.service.mark_ringing(recurring.id, datetime(2026, 11, 18, 8, 0))
        dismissed_recurring = self.service.dismiss(recurring.id)

        self.assertTrue(dismissed_recurring.enabled)
        self.assertEqual(self.service.get(recurring.id), recurring)
        self.assertIsNone(self.service.runtime_for(recurring.id))


if __name__ == "__main__":
    unittest.main()
