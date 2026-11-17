import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from alarm_clock.cli import main


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_file = Path(self.temporary_directory.name) / "alarms.json"
        self.now = lambda: datetime(2026, 11, 17, 7, 30)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        output = io.StringIO()
        errors = io.StringIO()
        result = main(
            ["--data-file", str(self.data_file), *args],
            stdout=output,
            stderr=errors,
            clock=self.now,
        )
        return result, output.getvalue(), errors.getvalue()

    def test_add_and_list_alarm(self) -> None:
        code, output, errors = self.run_cli("add", "08:00", "--label", "Morning")
        self.assertEqual(code, 0)
        self.assertIn("Created alarm", output)
        self.assertEqual(errors, "")

        code, output, errors = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("Morning", output)
        self.assertIn("enabled", output)
        self.assertIn("2026-11-17 08:00", output)
        self.assertEqual(errors, "")

    def test_add_recurring_custom_alarm(self) -> None:
        code, output, errors = self.run_cli(
            "add",
            "06:30",
            "--repeat",
            "custom",
            "--days",
            "mon,wed,fri",
        )

        self.assertEqual(code, 0)
        self.assertIn("Created alarm", output)
        self.assertEqual(errors, "")

        code, output, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("custom (mon,wed,fri)", output)

    def test_update_enable_disable_and_delete(self) -> None:
        self.run_cli("add", "08:00")
        alarm_id = json.loads(self.data_file.read_text(encoding="utf-8"))["alarms"][0]["id"]

        self.assertEqual(self.run_cli("update", alarm_id, "--time", "09:15", "--label", "Later")[0], 0)
        self.assertEqual(self.run_cli("disable", alarm_id)[0], 0)
        self.assertEqual(self.run_cli("enable", alarm_id)[0], 0)
        code, output, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("09:15", output)
        self.assertIn("Later", output)
        self.assertEqual(self.run_cli("delete", alarm_id)[0], 0)
        self.assertEqual(self.run_cli("list")[1], "No alarms configured.\n")

    def test_invalid_time_and_missing_alarm_return_error_code(self) -> None:
        code, output, errors = self.run_cli("add", "7am")
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("HH:MM", errors)

        code, _, errors = self.run_cli("delete", "unknown")
        self.assertEqual(code, 1)
        self.assertIn("does not exist", errors)

    def test_help_lists_commands(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            main(["--help"])

        self.assertEqual(raised.exception.code, 0)
        for command in ("add", "list", "update", "delete", "enable", "disable", "run"):
            self.assertIn(command, output.getvalue())


if __name__ == "__main__":
    unittest.main()
