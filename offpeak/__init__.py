"""OffPeak: temporal inference cost arbitrage for AI agents."""

__version__ = "0.1.0"

from offpeak.clock import Clock, RealClock, SimClock
from offpeak.connectors import CrusoePricing, TimeOfDayPricing
from offpeak.costs import CostTracker
from offpeak.flexibility import FlexibilityLearner
from offpeak.harness import OffPeakHarness
from offpeak.policy import ASK_USER, DEFER, RUN_NOW, Decision, Policy
from offpeak.pricing import (
    PricePoint,
    PricingSource,
    StaticPricing,
    cheapest_start,
    peak_price,
)
from offpeak.tasks import Task, TaskQueue

__all__ = [
    "ASK_USER",
    "Clock",
    "CostTracker",
    "CrusoePricing",
    "DEFER",
    "Decision",
    "FlexibilityLearner",
    "OffPeakHarness",
    "Policy",
    "PricePoint",
    "PricingSource",
    "RealClock",
    "RUN_NOW",
    "SimClock",
    "StaticPricing",
    "Task",
    "TaskQueue",
    "TimeOfDayPricing",
    "cheapest_start",
    "peak_price",
]

