"""Temporal inference pricing: cost curves that drive deferral decisions.

Prices are expressed as USD per 1M tokens ($/Mtok) at a point in time. Real
inference prices vary with grid load (overnight baseload is cheap, evening
peak is expensive); the bundled placeholder connector models a realistic
24-hour "duck curve" over a base rate.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta

# Illustrative 24-hour multiplier curve over a base $/Mtok rate, loosely
# modeled on real grid load: cheap overnight, a solar-driven midday dip,
# and a steep evening peak.
DEFAULT_TIME_OF_DAY_CURVE: dict[int, float] = {
    0: 0.60, 1: 0.52, 2: 0.45, 3: 0.42, 4: 0.44, 5: 0.55,
    6: 0.75, 7: 0.95, 8: 1.05, 9: 0.98, 10: 0.85, 11: 0.76,
    12: 0.70, 13: 0.67, 14: 0.70, 15: 0.80, 16: 0.95,
    17: 1.20, 18: 1.45, 19: 1.55, 20: 1.45, 21: 1.20, 22: 0.95, 23: 0.75,
}


@dataclass(frozen=True)
class PricePoint:
    at: datetime
    price_per_mtok: float


class PricingSource(ABC):
    """Connector interface for a provider's temporal pricing schedule."""

    @abstractmethod
    def price_at(self, at: datetime) -> float:
        """Return the USD price per 1M tokens at a point in time."""

    @abstractmethod
    def forecast(self, start: datetime, hours: int = 24) -> list[PricePoint]:
        """Return hourly price points starting at ``start``."""


class StaticPricing(PricingSource):
    """Flat pricing with no temporal spread (baseline / tests)."""

    def __init__(self, price_per_mtok: float = 0.60) -> None:
        self.price_per_mtok = float(price_per_mtok)

    def price_at(self, at: datetime) -> float:
        return self.price_per_mtok

    def forecast(self, start: datetime, hours: int = 24) -> list[PricePoint]:
        return [
            PricePoint(at=start + timedelta(hours=i), price_per_mtok=self.price_per_mtok)
            for i in range(hours)
        ]


def cheapest_start(
    source: PricingSource,
    earliest: datetime,
    latest_start: datetime,
    duration: timedelta = timedelta(0),
    step_minutes: int = 30,
) -> tuple[datetime, float] | None:
    """Find the cheapest start time in ``[earliest, latest_start]`` for a task
    taking ``duration``. Returns ``(start, avg_price_per_mtok)`` or None."""
    if latest_start < earliest:
        return None
    step = timedelta(minutes=step_minutes)
    best_start: datetime | None = None
    best_price = float("inf")
    t = earliest
    while t <= latest_start:
        price = _window_average(source, t, duration)
        if price < best_price - 1e-12:
            best_start, best_price = t, price
        t += step
    return None if best_start is None else (best_start, best_price)


def peak_price(source: PricingSource, start: datetime, hours: int = 24) -> float:
    """Highest price per Mtok in the next ``hours`` from ``start``."""
    points = source.forecast(start, hours)
    return max(p.price_per_mtok for p in points) if points else source.price_at(start)


def _window_average(
    source: PricingSource, start: datetime, duration: timedelta, samples: int = 12
) -> float:
    if duration <= timedelta(0):
        return source.price_at(start)
    step = duration / samples
    return sum(source.price_at(start + step * i) for i in range(samples)) / samples

