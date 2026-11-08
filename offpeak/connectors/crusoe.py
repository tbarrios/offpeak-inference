"""Crusoe Cloud temporal pricing connector (stub).

Crusoe's inference API is OpenAI-compatible. When Crusoe exposes a temporal
pricing schedule (time-varying $/Mtok), implement ``price_at``/``forecast``
here by fetching and caching the schedule. Until then this connector raises
``NotImplementedError`` with a pointer to where the integration goes.
"""

from __future__ import annotations

from datetime import datetime

from offpeak.pricing import PricePoint, PricingSource


class CrusoePricing(PricingSource):
    """Temporal pricing from Crusoe's inference API (to be wired up)."""

    def __init__(
        self, api_key: str | None = None, schedule_url: str | None = None
    ) -> None:
        self.api_key = api_key
        self.schedule_url = schedule_url

    def price_at(self, at: datetime) -> float:
        raise NotImplementedError(
            "Fetch Crusoe's temporal pricing schedule here and return the "
            "$/Mtok effective at the given time. The default CAISO "
            "connector covers the harness until this is wired."
        )

    def forecast(self, start: datetime, hours: int = 24) -> list[PricePoint]:
        raise NotImplementedError("See price_at(); fetch and cache the schedule.")
