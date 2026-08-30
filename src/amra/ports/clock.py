"""Clock port keeps wall time outside workflow definitions."""

from datetime import datetime
from typing import Protocol


class ClockPort(Protocol):
    def now(self) -> datetime: ...
