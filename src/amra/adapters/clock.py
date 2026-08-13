"""UTC system and deterministic test clocks."""

from dataclasses import dataclass
from datetime import UTC, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    instant: datetime

    def __post_init__(self) -> None:
        if self.instant.tzinfo is None:
            raise ValueError("fixed instant must be timezone-aware")

    def now(self) -> datetime:
        return self.instant
