import json
import os
import tempfile
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterable

from .models import Alarm, Recurrence, RecurrenceKind


class StorageError(Exception):
    pass


class JsonAlarmStore:
    version = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> list[Alarm]:
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
        except FileNotFoundError:
            return []
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StorageError(f"could not read alarm storage at {self.path}: {error}") from error

        if not isinstance(payload, dict) or payload.get("version") != self.version:
            raise StorageError(f"alarm storage at {self.path} has an unsupported format")
        records = payload.get("alarms")
        if not isinstance(records, list):
            raise StorageError(f"alarm storage at {self.path} must contain an alarms list")

        alarms: list[Alarm] = []
        ids: set[str] = set()
        for index, record in enumerate(records):
            try:
                alarm = self._deserialize_alarm(record)
            except (KeyError, TypeError, ValueError) as error:
                raise StorageError(f"invalid alarm at index {index} in {self.path}: {error}") from error
            if alarm.id in ids:
                raise StorageError(f"duplicate alarm id {alarm.id!r} in {self.path}")
            ids.add(alarm.id)
            alarms.append(alarm)
        return alarms

    def save(self, alarms: Iterable[Alarm]) -> None:
        alarm_list = list(alarms)
        ids: set[str] = set()
        for alarm in alarm_list:
            if not isinstance(alarm, Alarm):
                raise StorageError("only Alarm values can be saved")
            if alarm.id in ids:
                raise StorageError(f"duplicate alarm id {alarm.id!r}")
            ids.add(alarm.id)

        self.load()
        payload = {
            "version": self.version,
            "alarms": [self._serialize_alarm(alarm) for alarm in alarm_list],
        }

        temporary_path: str | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = stream.name
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
        except (OSError, TypeError, ValueError) as error:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
            raise StorageError(f"could not write alarm storage at {self.path}: {error}") from error

    @staticmethod
    def _serialize_alarm(alarm: Alarm) -> dict[str, object]:
        return {
            "id": alarm.id,
            "scheduled_time": alarm.scheduled_time.isoformat(),
            "label": alarm.label,
            "enabled": alarm.enabled,
            "recurrence": {
                "kind": alarm.recurrence.kind.value,
                "days": list(alarm.recurrence.days),
            },
            "snooze_minutes": alarm.snooze_minutes,
            "scheduled_date": alarm.scheduled_date.isoformat() if alarm.scheduled_date else None,
            "created_at": alarm.created_at.isoformat(),
        }

    @staticmethod
    def _deserialize_alarm(record: object) -> Alarm:
        if not isinstance(record, dict):
            raise ValueError("alarm value must be an object")
        recurrence_data = record["recurrence"]
        if not isinstance(recurrence_data, dict):
            raise ValueError("recurrence value must be an object")
        days = recurrence_data["days"]
        if not isinstance(days, list):
            raise ValueError("recurrence days must be a list")
        scheduled_date_value = record["scheduled_date"]
        scheduled_date = date.fromisoformat(scheduled_date_value) if scheduled_date_value is not None else None
        return Alarm(
            id=record["id"],
            scheduled_time=time.fromisoformat(record["scheduled_time"]),
            label=record["label"],
            enabled=record["enabled"],
            recurrence=Recurrence(RecurrenceKind(recurrence_data["kind"]), tuple(days)),
            snooze_minutes=record["snooze_minutes"],
            scheduled_date=scheduled_date,
            created_at=datetime.fromisoformat(record["created_at"]),
        )
