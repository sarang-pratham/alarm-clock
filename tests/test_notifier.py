import io
import unittest
from datetime import date, datetime, time

from alarm_clock.models import Alarm
from alarm_clock.notifier import TerminalNotifier


class TerminalNotifierTests(unittest.TestCase):
    def test_prints_labeled_alarm_and_emits_terminal_bell(self) -> None:
        output = io.StringIO()
        alarm = Alarm(
            id="morning",
            scheduled_time=time(7, 0),
            scheduled_date=date(2026, 11, 18),
            label="Wake up",
        )
        notifier = TerminalNotifier(output, clock=lambda: datetime(2026, 11, 18, 7, 0, 1))

        notifier.notify(alarm)

        self.assertEqual(output.getvalue(), "\aAlarm morning — Wake up is ringing at 2026-11-18 07:00:01.\n")

    def test_unlabeled_alarm_omits_label_separator(self) -> None:
        output = io.StringIO()
        alarm = Alarm(
            id="later",
            scheduled_time=time(8, 0),
            scheduled_date=date(2026, 11, 19),
        )
        notifier = TerminalNotifier(output, clock=lambda: datetime(2026, 11, 19, 8, 0))

        notifier.notify(alarm)

        self.assertIn("Alarm later is ringing", output.getvalue())
        self.assertNotIn(" — ", output.getvalue())

    def test_output_errors_are_propagated_to_scheduler_boundary(self) -> None:
        class BrokenOutput(io.StringIO):
            def write(self, value: str) -> int:
                raise OSError("terminal unavailable")

        alarm = Alarm(
            id="later",
            scheduled_time=time(8, 0),
            scheduled_date=date(2026, 11, 19),
        )
        notifier = TerminalNotifier(BrokenOutput(), clock=lambda: datetime(2026, 11, 19, 8, 0))

        with self.assertRaisesRegex(OSError, "terminal unavailable"):
            notifier.notify(alarm)


if __name__ == "__main__":
    unittest.main()
