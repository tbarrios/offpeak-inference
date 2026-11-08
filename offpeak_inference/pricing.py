"""Placeholder time-varying price schedule for the Manage Loads MVP.

The harness consumes any hourly price schedule in $/MWh. For the MVP we use a
24-hour "duck curve" with a midday solar dip and an evening peak. A real
deployment would replace `build_schedule` with live signals such as CAISO
day-ahead prices or Electricity Maps carbon intensity.
"""

from __future__ import annotations


def price_at_hour(hour: int) -> float:
    """Grid price in $/MWh for a given hour of the day."""

    h = hour % 24
    if 1 <= h <= 5:
        return 30.0
    if 6 <= h <= 8:
        return 45.0
    if 9 <= h <= 15:
        return 35.0
    if 16 <= h <= 18:
        return 70.0
    if 19 <= h <= 21:
        return 105.0
    if h == 22:
        return 80.0
    return 55.0


def build_schedule(days: int = 1) -> list[float]:
    """Hour-by-hour price schedule (length 24 * days)."""

    return [price_at_hour(h) for h in range(24 * days)]


def best_future(
    schedule: list[float], from_index: int, horizon_hours: int
) -> tuple[float, int]:
    """Cheapest (price, index) reachable within the deferral horizon."""

    end = min(from_index + horizon_hours, len(schedule))
    candidates = range(from_index + 1, end)
    if not candidates:
        return schedule[from_index], from_index
    best_index = min(candidates, key=lambda i: schedule[i])
    return schedule[best_index], best_index


def cost_usd(tokens: float, price_per_mwh: float) -> float:
    """Map tokens to modeled energy cost using a placeholder efficiency.

    Placeholder: 1M tokens requires 0.0006 MWh of grid electricity. Swap this
    constant for a measured value (or a per-model energy profile) in a real
    deployment.
    """

    mwh = (tokens / 1_000_000.0) * 0.0006
    return mwh * price_per_mwh
