import argparse
import re
import sys
from threading import Thread
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Sequence, TextIO

from .models import Alarm, Recurrence, RecurrenceKind
from .notifier import TerminalNotifier
from .scheduler import Scheduler, next_occurrence
from .service import AlarmService
from .storage import JsonAlarmStore, StorageError


WEEKDAYS = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alarm-clock", description="Manage local command-line alarms.")
    parser.add_argument(
        "--data-file",
        type=Path,
        default=Path.home() / ".alarm-clock" / "alarms.json",
        help="alarm JSON file (default: ~/.alarm-clock/alarms.json)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="create an alarm")
    add.add_argument("time", help="local time in HH:MM format")
    add.add_argument("--date", help="date for a one-time alarm (YYYY-MM-DD)")
    add.add_argument("--label")
    add.add_argument("--repeat", choices=[kind.value for kind in RecurrenceKind], default="once")
    add.add_argument("--days", help="comma-separated weekdays for custom recurrence")
    add.add_argument("--snooze", type=int, default=5, help="snooze duration in minutes (1-1440)")

    commands.add_parser("list", help="list configured alarms")

    update = commands.add_parser("update", help="modify an alarm")
    update.add_argument("id")
    update.add_argument("--time", dest="scheduled_time")
    update.add_argument("--date")
    label = update.add_mutually_exclusive_group()
    label.add_argument("--label")
    label.add_argument("--clear-label", action="store_true")
    update.add_argument("--repeat", choices=[kind.value for kind in RecurrenceKind])
    update.add_argument("--days")
    update.add_argument("--snooze", type=int)

    delete = commands.add_parser("delete", help="delete an alarm")
    delete.add_argument("id")
    enable = commands.add_parser("enable", help="enable an alarm")
    enable.add_argument("id")
    disable = commands.add_parser("disable", help="disable an alarm")
    disable.add_argument("id")
    commands.add_parser("run", help="monitor alarms until interrupted")
    return parser


def parse_time(value: str) -> time:
    if re.fullmatch(r"\d{2}:\d{2}", value) is None:
        raise ValueError("time must use HH:MM format")
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"invalid alarm time {value!r}; use HH:MM") from error


def parse_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"invalid date {value!r}; use YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise ValueError(f"invalid date {value!r}; use YYYY-MM-DD")
    return parsed


def parse_recurrence(kind: str, days: str | None) -> Recurrence:
    recurrence_kind = RecurrenceKind(kind)
    if recurrence_kind is not RecurrenceKind.CUSTOM:
        if days is not None:
            raise ValueError("--days can only be used with --repeat custom")
        return Recurrence(recurrence_kind)
    if not days:
        raise ValueError("custom recurrence requires --days")
    try:
        selected = tuple(WEEKDAYS[item.strip().lower()] for item in days.split(","))
    except KeyError as error:
        raise ValueError("--days must be comma-separated weekday names: mon,tue,wed,thu,fri,sat,sun") from error
    return Recurrence(recurrence_kind, selected)


def _next_one_time_date(scheduled_time: time, now: datetime) -> date:
    return now.date() if scheduled_time > now.time().replace(second=0, microsecond=0) else now.date() + timedelta(days=1)


def _format_recurrence(alarm: Alarm) -> str:
    if alarm.recurrence.kind is RecurrenceKind.CUSTOM:
        days = ",".join(name for name, day in WEEKDAYS.items() if day in alarm.recurrence.days)
        return f"custom ({days})"
    return alarm.recurrence.kind.value


def _format_next(alarm: Alarm, now: datetime) -> str:
    if not alarm.enabled:
        return "—"
    occurrence = next_occurrence(alarm, now)
    if occurrence is None:
        return "missed"
    return occurrence.strftime("%Y-%m-%d %H:%M")


def _list_alarms(service: AlarmService, now: datetime, stream: TextIO) -> None:
    alarms = service.list_alarms()
    if not alarms:
        print("No alarms configured.", file=stream)
        return
    headings = ("ID", "TIME", "LABEL", "STATUS", "REPEAT", "NEXT")
    rows = [
        (
            alarm.id,
            alarm.scheduled_time.strftime("%H:%M"),
            alarm.label or "—",
            "enabled" if alarm.enabled else "disabled",
            _format_recurrence(alarm),
            _format_next(alarm, now),
        )
        for alarm in alarms
    ]
    widths = [max(len(headings[index]), *(len(row[index]) for row in rows)) for index in range(len(headings))]
    print("  ".join(value.ljust(widths[index]) for index, value in enumerate(headings)), file=stream)
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)), file=stream)


def _update_alarm(service: AlarmService, args: argparse.Namespace, now: datetime) -> Alarm:
    current = service.get(args.id)
    changes: dict[str, object] = {}
    scheduled_time = parse_time(args.scheduled_time) if args.scheduled_time is not None else current.scheduled_time
    if args.scheduled_time is not None:
        changes["scheduled_time"] = scheduled_time
    if args.label is not None:
        changes["label"] = args.label
    elif args.clear_label:
        changes["label"] = None
    if args.snooze is not None:
        changes["snooze_minutes"] = args.snooze

    if args.repeat is not None:
        recurrence = parse_recurrence(args.repeat, args.days)
        changes["recurrence"] = recurrence
        if recurrence.kind is RecurrenceKind.ONCE:
            if args.date is not None:
                changes["scheduled_date"] = parse_date(args.date)
            elif current.recurrence.kind is RecurrenceKind.ONCE and current.scheduled_date is not None:
                changes["scheduled_date"] = current.scheduled_date
            else:
                changes["scheduled_date"] = _next_one_time_date(scheduled_time, now)
        else:
            changes["scheduled_date"] = None
    else:
        if args.days is not None:
            raise ValueError("--days requires --repeat custom")
        if args.date is not None:
            changes["scheduled_date"] = parse_date(args.date)

    if not changes:
        raise ValueError("provide at least one field to update")
    return service.update(args.id, **changes)


def _run_monitoring(
    service: AlarmService,
    output: TextIO,
    errors: TextIO,
    input_stream: TextIO,
    clock,
) -> None:
    notifier = TerminalNotifier(output, clock)
    scheduler = Scheduler(service, notifier.notify, clock=clock)
    worker = Thread(target=scheduler.run_forever, name="alarm-scheduler")
    print("Monitoring alarms. Enter 'dismiss <id>', 'snooze <id>', or 'quit'.", file=output, flush=True)
    worker.start()
    try:
        while True:
            line = input_stream.readline()
            if not line:
                break
            parts = line.strip().split()
            if not parts:
                continue
            command = parts[0].lower()
            if command in {"quit", "exit"}:
                break
            if command not in {"dismiss", "snooze"} or len(parts) != 2:
                print("Use 'dismiss <id>', 'snooze <id>', or 'quit'.", file=errors)
                continue
            alarm_id = parts[1]
            try:
                if command == "dismiss":
                    alarm = service.dismiss(alarm_id)
                    print(f"Dismissed alarm {alarm_id}.", file=output)
                else:
                    snoozed_until = service.snooze(alarm_id, now=clock())
                    print(f"Snoozed alarm {alarm_id} until {snoozed_until:%Y-%m-%d %H:%M}.", file=output)
            except (ValueError, LookupError) as error:
                print(f"error: {error}", file=errors)
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.stop()
        worker.join()
    print("Alarm monitoring stopped.", file=output)


def main(
    argv: Sequence[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    stdin: TextIO | None = None,
    clock=datetime.now,
) -> int:
    output = stdout if stdout is not None else sys.stdout
    errors = stderr if stderr is not None else sys.stderr
    input_stream = stdin if stdin is not None else sys.stdin
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        service = AlarmService(JsonAlarmStore(args.data_file))
        now = clock()
        if args.command == "add":
            scheduled_time = parse_time(args.time)
            recurrence = parse_recurrence(args.repeat, args.days)
            scheduled_date = parse_date(args.date) if args.date else None
            if recurrence.kind is RecurrenceKind.ONCE:
                if scheduled_date is None:
                    scheduled_date = _next_one_time_date(scheduled_time, now)
            elif scheduled_date is not None:
                raise ValueError("--date can only be used with a one-time alarm")
            alarm = Alarm(
                scheduled_time=scheduled_time,
                label=args.label,
                recurrence=recurrence,
                snooze_minutes=args.snooze,
                scheduled_date=scheduled_date,
            )
            service.create(alarm)
            print(f"Created alarm {alarm.id} for {alarm.scheduled_time:%H:%M}.", file=output)
        elif args.command == "list":
            _list_alarms(service, now, output)
        elif args.command == "update":
            alarm = _update_alarm(service, args, now)
            print(f"Updated alarm {alarm.id}.", file=output)
        elif args.command == "delete":
            service.delete(args.id)
            print(f"Deleted alarm {args.id}.", file=output)
        elif args.command == "enable":
            service.enable(args.id)
            print(f"Enabled alarm {args.id}.", file=output)
        elif args.command == "disable":
            service.disable(args.id)
            print(f"Disabled alarm {args.id}.", file=output)
        elif args.command == "run":
            _run_monitoring(service, output, errors, input_stream, clock)
        return 0
    except (ValueError, LookupError, StorageError, OSError) as error:
        print(f"error: {error}", file=errors)
        return 1
