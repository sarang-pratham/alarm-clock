import sys
from datetime import datetime
from typing import TextIO

from .models import Alarm


class TerminalNotifier:
    def __init__(self, stream: TextIO | None = None, clock=datetime.now) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._clock = clock

    def notify(self, alarm: Alarm) -> None:
        label = f" — {alarm.label}" if alarm.label else ""
        current = self._clock().strftime("%Y-%m-%d %H:%M:%S")
        self._stream.write(f"\aAlarm {alarm.id}{label} is ringing at {current}.\n")
        self._stream.flush()
