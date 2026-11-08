"""Clock abstraction so the scheduler is testable and demoable offline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime:
        """Return the current local time."""


class RealClock(Clock):
    def now(self) -> datetime:
        return datetime.now()


class SimClock(Clock):
    """A controllable clock for deterministic tests and offline demos."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta | float = 0, *, hours: float | None = None) -> None:
        """Advance time by a timedelta, by hours (number), or via hours=..."""
        if hours is not None:
            self._now += timedelta(hours=hours)
        elif isinstance(delta, timedelta):
            self._now += delta
        else:
            self._now += timedelta(hours=delta)

