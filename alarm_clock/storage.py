from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, time
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Mapping

from .models import Alarm, Recurrence, RecurrenceKind

if TYPE_CHECKING:
    from .service import AlarmRuntime


class StorageError(Exception):
    pass


class JsonAlarmStore:
    version = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> list[Alarm]:
        payload = self._read_payload()
        if payload is None:
            return []
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

    def load_runtime(self) -> dict[str, AlarmRuntime]:
        payload = self._read_payload()
        if payload is None:
            return {}
        records = payload.get("runtime", {})
        if not isinstance(records, dict):
            raise StorageError(f"alarm storage at {self.path} must contain an object for runtime state")
        alarm_ids = {alarm.id for alarm in self.load()}
        runtime: dict[str, AlarmRuntime] = {}
        for alarm_id, record in records.items():
            if not isinstance(alarm_id, str) or alarm_id not in alarm_ids:
                raise StorageError(f"runtime state references unknown alarm id {alarm_id!r} in {self.path}")
            try:
                runtime[alarm_id] = self._deserialize_runtime(record)
            except (KeyError, TypeError, ValueError) as error:
                raise StorageError(f"invalid runtime state for alarm {alarm_id!r} in {self.path}: {error}") from error
        return runtime

    def save(
        self,
        alarms: Iterable[Alarm],
        runtime: Mapping[str, AlarmRuntime] | None = None,
    ) -> None:
        alarm_list = list(alarms)
        ids: set[str] = set()
        for alarm in alarm_list:
            if not isinstance(alarm, Alarm):
                raise StorageError("only Alarm values can be saved")
            if alarm.id in ids:
                raise StorageError(f"duplicate alarm id {alarm.id!r}")
            ids.add(alarm.id)

        self.load()
        existing_runtime = self.load_runtime()
        if runtime is None:
            runtime_records = {alarm_id: state for alarm_id, state in existing_runtime.items() if alarm_id in ids}
        else:
            runtime_records = dict(runtime)
        for alarm_id, state in runtime_records.items():
            if alarm_id not in ids:
                raise StorageError(f"runtime state references unknown alarm id {alarm_id!r}")
            if not isinstance(state, self._runtime_type()):
                raise StorageError("runtime values must be AlarmRuntime instances")
        payload = {
            "version": self.version,
            "alarms": [self._serialize_alarm(alarm) for alarm in alarm_list],
            "runtime": {
                alarm_id: self._serialize_runtime(state)
                for alarm_id, state in runtime_records.items()
            },
        }
        self._write_payload(payload)

    def save_runtime(self, runtime: Mapping[str, AlarmRuntime]) -> None:
        self.save(self.load(), runtime)

    def _read_payload(self) -> dict[str, object] | None:
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StorageError(f"could not read alarm storage at {self.path}: {error}") from error

        if not isinstance(payload, dict) or payload.get("version") != self.version:
            raise StorageError(f"alarm storage at {self.path} has an unsupported format")
        return payload

    def _write_payload(self, payload: dict[str, object]) -> None:
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

    @staticmethod
    def _runtime_type() -> type[AlarmRuntime]:
        from .service import AlarmRuntime

        return AlarmRuntime

    @staticmethod
    def _serialize_runtime(runtime: AlarmRuntime) -> dict[str, str | None]:
        return {
            "state": runtime.state.value,
            "scheduled_at": runtime.scheduled_at.isoformat(),
            "snoozed_until": runtime.snoozed_until.isoformat() if runtime.snoozed_until else None,
        }

    @staticmethod
    def _deserialize_runtime(record: object) -> AlarmRuntime:
        if not isinstance(record, dict):
            raise ValueError("runtime value must be an object")
        from .service import AlarmRuntime, OccurrenceState

        snoozed_until_value = record["snoozed_until"]
        return AlarmRuntime(
            state=OccurrenceState(record["state"]),
            scheduled_at=datetime.fromisoformat(record["scheduled_at"]),
            snoozed_until=(
                datetime.fromisoformat(snoozed_until_value)
                if snoozed_until_value is not None
                else None
            ),
        )
