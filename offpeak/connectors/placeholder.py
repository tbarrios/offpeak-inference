"""Placeholder pricing connector: a time-of-day curve over a base rate.

This stands in for a real provider's temporal pricing schedule. The default
curve loosely follows grid load: cheap overnight, a solar-driven midday dip,
and a steep evening peak. Swap in a real connector (see ``crusoe.py``) once a
provider exposes time-varying inference prices.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from offpeak.pricing import (
    DEFAULT_TIME_OF_DAY_CURVE,
    PricePoint,
    PricingSource,
)


class TimeOfDayPricing(PricingSource):
    """Placeholder temporal pricing: ``base_rate * curve[hour]`` $/Mtok."""

    def __init__(
        self,
        base_rate_per_mtok: float = 0.60,
        curve: dict[int, float] | None = None,
    ) -> None:
        self.base_rate_per_mtok = float(base_rate_per_mtok)
        self.curve = dict(curve or DEFAULT_TIME_OF_DAY_CURVE)
        if sorted(self.curve) != list(range(24)):
            raise ValueError("curve must define a multiplier for each hour 0..23")

    def price_at(self, at: datetime) -> float:
        return self.base_rate_per_mtok * self.curve[at.hour]

    def forecast(self, start: datetime, hours: int = 24) -> list[PricePoint]:
        return [
            PricePoint(
                at=start + timedelta(hours=i),
                price_per_mtok=self.price_at(start + timedelta(hours=i)),
            )
            for i in range(hours)
        ]

