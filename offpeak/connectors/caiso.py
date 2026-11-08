"""CAISO day-ahead pricing connector.

The bundled schedule is an official CAISO OASIS day-ahead snapshot: the hourly
average of NP15, SP15, and ZP26 trading-hub LMPs for the 2026-11-08 operating
day. `caiso_pricing_for_date()` can refresh it from OASIS; the bundled values
keep tests and offline demos deterministic.
"""

from __future__ import annotations

import csv
import io
import ssl
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

try:
    import certifi
except ImportError:
    certifi = None

from offpeak.pricing import PricePoint, PricingSource


CAISO_TRADING_HUBS = (
    "TH_NP15_GEN-APND",
    "TH_SP15_GEN-APND",
    "TH_ZP26_GEN-APND",
)
SNAPSHOT_TRADING_DATE = date(2026, 11, 8)

# CAISO OASIS PRC_LMP day-ahead hourly LMPs, averaged across the three
# California trading hubs. Values are $/MWh.
CAISO_DAY_AHEAD_HUB_AVERAGE_USD_PER_MWH = (
    48.28281,
    47.29598,
    44.94818,
    46.32724,
    46.54057,
    46.99047,
    48.05339,
    27.08720,
    14.81303,
    11.72642,
    12.23355,
    12.43572,
    12.33628,
    13.15697,
    14.62582,
    35.91151,
    54.68872,
    54.57319,
    54.94372,
    54.87468,
    55.15630,
    55.52838,
    54.81575,
    52.51726,
)

# Placeholder end-to-end efficiency and provider overhead. A production
# deployment should replace both with measured values or a provider price feed.
MWH_PER_MTOK = 0.0006
DEFAULT_INFERENCE_MARKUP = 50.0


@dataclass(frozen=True)
class CaisoDayAheadPricing(PricingSource):
    """Grid-cost-based temporal inference pricing.

    Inference price is: CAISO LMP ($/MWh) × energy per Mtok (MWh/Mtok) ×
    markup. The markup converts grid energy cost into modeled inference cost;
    it is configurable rather than presented as a market quote.
    """

    grid_prices_per_mwh: tuple[float, ...] = CAISO_DAY_AHEAD_HUB_AVERAGE_USD_PER_MWH
    trading_date: date = SNAPSHOT_TRADING_DATE
    mwh_per_mtok: float = MWH_PER_MTOK
    markup: float = DEFAULT_INFERENCE_MARKUP

    def __post_init__(self) -> None:
        if len(self.grid_prices_per_mwh) != 24:
            raise ValueError("grid_prices_per_mwh must contain 24 hourly values")
        if self.mwh_per_mtok <= 0 or self.markup < 1.0:
            raise ValueError("mwh_per_mtok must be positive and markup must be >= 1")

    def grid_price_at(self, at: datetime) -> float:
        return self.grid_prices_per_mwh[at.hour % 24]

    def price_at(self, at: datetime) -> float:
        return self.grid_price_at(at) * self.mwh_per_mtok * self.markup

    def forecast(self, start: datetime, hours: int = 24) -> list[PricePoint]:
        return [
            PricePoint(
                at=start + timedelta(hours=offset),
                price_per_mtok=self.price_at(start + timedelta(hours=offset)),
            )
            for offset in range(hours)
        ]


def fetch_caiso_day_ahead_hub_average(trading_date: date) -> tuple[float, ...]:
    """Fetch and average CAISO trading-hub LMPs from the official OASIS API."""

    timezone = ZoneInfo("America/Los_Angeles")
    start_local = datetime(
        trading_date.year, trading_date.month, trading_date.day, tzinfo=timezone
    )
    end_local = start_local + timedelta(days=1)
    start = start_local.strftime("%Y%m%dT%H:%M%z")
    end = end_local.strftime("%Y%m%dT%H:%M%z")
    url = (
        "https://oasis.caiso.com/oasisapi/SingleZip"
        "?resultformat=6&queryname=PRC_LMP&version=12&market_run_id=DAM"
        f"&grp_type=ALL_APNODES&startdatetime={start}&enddatetime={end}"
    )
    context = ssl.create_default_context(cafile=certifi.where()) if certifi else None
    with urllib.request.urlopen(url, timeout=60, context=context) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    csv_name = archive.namelist()[0]
    prices_by_hour: dict[int, list[float]] = {}
    with archive.open(csv_name) as raw_csv:
        csv_file = io.TextIOWrapper(raw_csv, newline="")
        for row in csv.DictReader(csv_file):
            if row["LMP_TYPE"] == "LMP" and row["NODE_ID"] in CAISO_TRADING_HUBS:
                prices_by_hour.setdefault(int(row["OPR_HR"]), []).append(float(row["MW"]))
    if sorted(prices_by_hour) != list(range(1, 25)):
        raise ValueError(f"CAISO response did not contain all 24 hours for {trading_date}")
    return tuple(
        sum(prices_by_hour[hour]) / len(prices_by_hour[hour]) for hour in range(1, 25)
    )


def caiso_pricing_for_date(trading_date: date, **kwargs) -> CaisoDayAheadPricing:
    """Build a connector from live CAISO OASIS data."""

    return CaisoDayAheadPricing(
        grid_prices_per_mwh=fetch_caiso_day_ahead_hub_average(trading_date),
        trading_date=trading_date,
        **kwargs,
    )
