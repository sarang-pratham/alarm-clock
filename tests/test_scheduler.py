import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path

from alarm_clock.models import Alarm, Recurrence, RecurrenceKind
from alarm_clock.scheduler import Scheduler, next_occurrence
from alarm_clock.service import AlarmService
from alarm_clock.storage import JsonAlarmStore


class NextOccurrenceTests(unittest.TestCase):
    def test_one_time_alarm_is_returned_only_if_not_missed(self) -> None:
        alarm = Alarm(scheduled_time=time(8, 0), scheduled_date=date(2026, 11, 18))

        self.assertEqual(
            next_occurrence(alarm, datetime(2026, 11, 18, 7, 59)),
            datetime(2026, 11, 18, 8, 0),
        )
        self.assertIsNone(next_occurrence(alarm, datetime(2026, 11, 18, 8, 1)))

    def test_daily_alarm_selects_today_or_tomorrow(self) -> None:
        alarm = Alarm(scheduled_time=time(8, 0), recurrence=Recurrence(RecurrenceKind.DAILY))

        self.assertEqual(
            next_occurrence(alarm, datetime(2026, 11, 18, 7, 0)),
            datetime(2026, 11, 18, 8, 0),
        )
        self.assertEqual(
            next_occurrence(alarm, datetime(2026, 11, 18, 8, 1)),
            datetime(2026, 11, 19, 8, 0),
        )

    def test_weekday_and_custom_day_recurrence(self) -> None:
        weekdays = Alarm(scheduled_time=time(8, 0), recurrence=Recurrence(RecurrenceKind.WEEKDAYS))
        custom = Alarm(
            scheduled_time=time(8, 0),
            recurrence=Recurrence(RecurrenceKind.CUSTOM, (0, 2)),
        )
        sunday = datetime(2026, 11, 22, 9, 0)

        self.assertEqual(next_occurrence(weekdays, sunday), datetime(2026, 11, 23, 8, 0))
        self.assertEqual(next_occurrence(custom, sunday), datetime(2026, 11, 23, 8, 0))


class SchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        store = JsonAlarmStore(Path(self.temporary_directory.name) / "alarms.json")
        self.service = AlarmService(store)
        self.now = [datetime(2026, 11, 18, 7, 0)]
        self.triggered: list[Alarm] = []

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def make_scheduler(self, callback=None) -> Scheduler:
        return Scheduler(
            self.service,
            callback or self.triggered.append,
            clock=lambda: self.now[0],
            clock_check_interval=15,
        )

    def make_alarm(self, alarm_id: str, at: time, enabled: bool = True) -> Alarm:
        return Alarm(
            id=alarm_id,
            scheduled_time=at,
            scheduled_date=self.now[0].date(),
            enabled=enabled,
        )

    def test_triggers_alarm_when_clock_reaches_scheduled_time_once(self) -> None:
        alarm = self.make_alarm("wake", time(7, 1))
        self.service.create(alarm)
        scheduler = self.make_scheduler()

        self.assertEqual(scheduler.run_pending(), [])
        self.now[0] = datetime(2026, 11, 18, 7, 1)
        self.assertEqual(scheduler.run_pending(), [alarm])
        self.assertEqual(scheduler.run_pending(), [])
        self.assertEqual(self.triggered, [alarm])

    def test_same_time_alarms_all_trigger(self) -> None:
        first = self.make_alarm("first", time(7, 0))
        second = self.make_alarm("second", time(7, 0))
        self.service.create(first)
        self.service.create(second)
        scheduler = self.make_scheduler()

        self.assertEqual(scheduler.run_pending(), [first, second])

    def test_disabled_alarm_is_excluded_and_service_changes_wake_schedule(self) -> None:
        disabled = self.make_alarm("disabled", time(7, 5), enabled=False)
        self.service.create(disabled)
        scheduler = self.make_scheduler()
        self.assertIsNone(scheduler.next_upcoming())

        enabled = self.service.enable(disabled.id)
        self.assertEqual(scheduler.next_upcoming().alarm, enabled)
        self.assertTrue(scheduler._wake_event.is_set())

    def test_configuration_change_rebuilds_schedule(self) -> None:
        alarm = self.make_alarm("wake", time(7, 10))
        self.service.create(alarm)
        scheduler = self.make_scheduler()
        earlier = self.service.update(alarm.id, scheduled_time=time(7, 2))
        scheduler.refresh()

        self.now[0] = datetime(2026, 11, 18, 7, 2)
        self.assertEqual(scheduler.run_pending(), [earlier])

    def test_clock_jump_forward_triggers_due_alarm_and_refresh_handles_backward_jump(self) -> None:
        alarm = self.make_alarm("wake", time(7, 5))
        self.service.create(alarm)
        scheduler = self.make_scheduler()

        self.now[0] = datetime(2026, 11, 18, 7, 20)
        self.assertEqual(scheduler.run_pending(), [alarm])

        recurring = Alarm(
            id="daily",
            scheduled_time=time(8, 0),
            recurrence=Recurrence(RecurrenceKind.DAILY),
        )
        self.service.create(recurring)
        self.now[0] = datetime(2026, 11, 18, 7, 30)
        scheduler.refresh()
        self.now[0] = datetime(2026, 11, 18, 6, 30)
        scheduler.refresh()
        self.assertEqual(scheduler.next_upcoming().at, datetime(2026, 11, 18, 8, 0))
        self.assertEqual(scheduler.run_pending(), [])

    def test_refresh_keeps_an_already_due_occurrence_until_it_triggers(self) -> None:
        alarm = self.make_alarm("wake", time(7, 5))
        self.service.create(alarm)
        scheduler = self.make_scheduler()
        self.now[0] = datetime(2026, 11, 18, 7, 20)

        scheduler.refresh()

        self.assertEqual(scheduler.run_pending(), [alarm])

    def test_notification_failure_does_not_stop_other_due_alarms(self) -> None:
        first = self.make_alarm("first", time(7, 0))
        second = self.make_alarm("second", time(7, 0))
        self.service.create(first)
        self.service.create(second)

        def failing_callback(alarm: Alarm) -> None:
            if alarm.id == "first":
                raise RuntimeError("notification failed")
            self.triggered.append(alarm)

        scheduler = self.make_scheduler(failing_callback)

        self.assertEqual(scheduler.run_pending(), [first, second])
        self.assertEqual(self.triggered, [second])

    def test_stop_from_trigger_callback_shuts_down_run_loop(self) -> None:
        alarm = self.make_alarm("now", time(7, 0))
        self.service.create(alarm)
        scheduler_holder: list[Scheduler] = []

        def stop_after_trigger(triggered: Alarm) -> None:
            self.triggered.append(triggered)
            scheduler_holder[0].stop()

        scheduler = self.make_scheduler(stop_after_trigger)
        scheduler_holder.append(scheduler)

        scheduler.run_forever()

        self.assertTrue(scheduler._stop_event.is_set())
        self.assertEqual(self.triggered, [alarm])

    def test_wait_timeout_is_bounded_for_clock_change_checks(self) -> None:
        alarm = self.make_alarm("later", time(8, 0))
        self.service.create(alarm)
        scheduler = self.make_scheduler()

        self.assertEqual(scheduler._wait_timeout(), 15)
        self.now[0] += timedelta(minutes=90)
        self.assertEqual(scheduler._wait_timeout(), 0)


if __name__ == "__main__":
    unittest.main()
