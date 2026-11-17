# Alarm Clock

A local alarm clock that runs in the terminal. It uses Python 3.12 or newer and the standard library; alarms are stored in a JSON file.

## Run from a checkout

Create and activate a virtual environment if desired, then run the module from the repository root:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m alarm_clock --help
```

The default data file is `~/.alarm-clock/alarms.json`. Pass `--data-file PATH` before the command to use a different file.

## Commands

Create one-time and recurring alarms:

```sh
python -m alarm_clock add 07:30 --label "Wake up"
python -m alarm_clock add 08:00 --date 2026-11-20 --label "Appointment"
python -m alarm_clock add 06:45 --repeat weekdays
python -m alarm_clock add 09:00 --repeat custom --days mon,wed,fri --snooze 10
```

One-time alarms without `--date` use the next local calendar date at that time. Recurring options are `daily`, `weekdays`, and `custom`; custom days use three-letter weekday names. Times use 24-hour `HH:MM` format.

Manage alarms with `list`, `update ID`, `enable ID`, `disable ID`, and `delete ID`:

```sh
python -m alarm_clock list
python -m alarm_clock update ALARM_ID --time 07:45 --label "Earlier"
python -m alarm_clock update ALARM_ID --repeat custom --days tue,thu
python -m alarm_clock disable ALARM_ID
python -m alarm_clock delete ALARM_ID
```

Run the scheduler in the foreground:

```sh
python -m alarm_clock run
```

When an alarm rings, enter `snooze ID` or `dismiss ID`. Snooze uses the alarm's configured duration. Enter `quit` or press Ctrl-C to stop monitoring. The scheduler reports missed alarms when it starts and does not play them overdue.

To use a separate data file:

```sh
python -m alarm_clock --data-file ./data/alarms.json add 07:30 --label "Wake up"
```

## Architecture

- `models.py` defines validated alarm configuration and recurrence rules.
- `service.py` handles alarm changes and occurrence lifecycle operations.
- `storage.py` validates and atomically saves configuration and runtime state as JSON.
- `schedule.py` calculates local calendar occurrences.
- `scheduler.py` watches the wall clock, responds to configuration changes, and dispatches alarms.
- `notifier.py` prints a terminal message and sends the terminal bell.
- `cli.py` parses commands and connects the application components.

## Time and notification limits

The scheduler uses the operating system's local calendar clock. It checks the wall clock at least once a minute while waiting, so clock changes are picked up without a long uninterrupted sleep. Recurrence is based on local calendar dates. If a scheduled local time does not exist during a daylight-saving transition, the alarm is detected after the clock advances past that time; repeated local times are treated as one occurrence per calendar day.

The terminal bell depends on terminal and system settings. There is no audio-file playback, background service, or wake-from-sleep support. The process must remain running in the foreground for alarms to trigger.

## Tests

Run the standard-library test suite with:

```sh
python -m unittest discover -s tests -v
```
