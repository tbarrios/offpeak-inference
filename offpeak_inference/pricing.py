"""CAISO day-ahead schedule for the learning simulation.

The schedule is the hourly average of CAISO's NP15, SP15, and ZP26 trading-hub
day-ahead LMPs for the 2026-11-08 operating day. A production deployment can
replace this with a live OASIS or another grid-price feed.
"""

from __future__ import annotations

from offpeak.connectors.caiso import (
    CAISO_DAY_AHEAD_HUB_AVERAGE_USD_PER_MWH,
    DEFAULT_INFERENCE_MARKUP,
    MWH_PER_MTOK,
)


def price_at_hour(hour: int) -> float:
    """Grid price in $/MWh for a given hour of the day."""

    return CAISO_DAY_AHEAD_HUB_AVERAGE_USD_PER_MWH[hour % 24]


def build_schedule(days: int = 1) -> list[float]:
    """Hour-by-hour CAISO grid-price schedule (length 24 * days)."""

    return [price_at_hour(hour) for hour in range(24 * days)]


def best_future(
    schedule: list[float], from_index: int, horizon_hours: int
) -> tuple[float, int]:
    """Cheapest (price, index) reachable within the deferral horizon."""

    end = min(from_index + horizon_hours, len(schedule))
    candidates = range(from_index + 1, end)
    if not candidates:
        return schedule[from_index], from_index
    best_index = min(candidates, key=lambda index: schedule[index])
    return schedule[best_index], best_index


def cost_usd(
    tokens: float,
    price_per_mwh: float,
    markup: float = DEFAULT_INFERENCE_MARKUP,
) -> float:
    """Map tokens to modeled inference cost from CAISO grid prices.

    Formula: tokens/Mtok × MWh/Mtok × CAISO LMP ($/MWh) × markup.
    """

    mwh = (tokens / 1_000_000.0) * MWH_PER_MTOK
    return mwh * price_per_mwh * markup
