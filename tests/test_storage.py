import json
import tempfile
import unittest
from datetime import date, datetime, time
from pathlib import Path

from alarm_clock.models import Alarm, Recurrence, RecurrenceKind
from alarm_clock.storage import JsonAlarmStore, StorageError
from alarm_clock.service import AlarmRuntime, OccurrenceState


class JsonAlarmStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "nested" / "alarms.json"
        self.store = JsonAlarmStore(self.path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_missing_file_loads_as_empty(self) -> None:
        self.assertEqual(self.store.load(), [])

    def test_save_and_load_round_trip_alarm_configuration(self) -> None:
        alarm = Alarm(
            id="alarm-1",
            scheduled_time=time(6, 45),
            label="Morning",
            enabled=False,
            recurrence=Recurrence(RecurrenceKind.CUSTOM, (0, 2, 4)),
            snooze_minutes=12,
            created_at=datetime(2026, 11, 17, 9, 30, 45, 123456),
        )

        self.store.save([alarm])

        self.assertEqual(self.store.load(), [alarm])

    def test_one_time_alarm_round_trips_its_date(self) -> None:
        alarm = Alarm(
            id="alarm-2",
            scheduled_time=time(7, 0),
            scheduled_date=date(2026, 11, 20),
        )

        self.store.save([alarm])

        self.assertEqual(self.store.load(), [alarm])

    def test_malformed_json_is_reported_and_preserved_on_save(self) -> None:
        self.path.parent.mkdir(parents=True)
        original = "{not valid json"
        self.path.write_text(original, encoding="utf-8")

        with self.assertRaisesRegex(StorageError, "could not read"):
            self.store.load()
        with self.assertRaises(StorageError):
            self.store.save([])

        self.assertEqual(self.path.read_text(encoding="utf-8"), original)

    def test_invalid_alarm_data_is_rejected(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"version": 1, "alarms": [{"id": "missing"}]}), encoding="utf-8")

        with self.assertRaisesRegex(StorageError, "invalid alarm at index 0"):
            self.store.load()

    def test_duplicate_ids_are_rejected_before_writing(self) -> None:
        first = Alarm(id="same", scheduled_time=time(7, 0), scheduled_date=date(2026, 11, 20))
        second = Alarm(id="same", scheduled_time=time(8, 0), scheduled_date=date(2026, 11, 20))

        with self.assertRaisesRegex(StorageError, "duplicate alarm id"):
            self.store.save([first, second])
        self.assertFalse(self.path.exists())

    def test_runtime_state_survives_store_reload(self) -> None:
        alarm = Alarm(id="active", scheduled_time=time(7, 0), scheduled_date=date(2026, 11, 20))
        runtime = AlarmRuntime(
            OccurrenceState.SNOOZED,
            datetime(2026, 11, 20, 7, 0),
            datetime(2026, 11, 20, 7, 5),
        )

        self.store.save([alarm], {alarm.id: runtime})

        self.assertEqual(self.store.load_runtime(), {alarm.id: runtime})

    def test_corrupt_runtime_state_is_rejected_and_not_overwritten(self) -> None:
        alarm = Alarm(id="active", scheduled_time=time(7, 0), scheduled_date=date(2026, 11, 20))
        self.store.save([alarm])
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload["runtime"] = {alarm.id: {"state": "not-a-state"}}
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        original = self.path.read_text(encoding="utf-8")

        with self.assertRaisesRegex(StorageError, "invalid runtime state"):
            self.store.load_runtime()
        with self.assertRaises(StorageError):
            self.store.save([alarm])

        self.assertEqual(self.path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
