"""Quickstart: a full simulated day with OffPeak — no LLM required.

Run: python examples/quickstart.py
"""

import os
import tempfile
from datetime import datetime, timedelta

from offpeak.clock import SimClock
from offpeak.harness import OffPeakHarness

clock = SimClock(datetime(2026, 11, 8, 18, 0))  # 6:00 PM — evening peak
with tempfile.TemporaryDirectory() as tmp:
    harness = OffPeakHarness(db_path=os.path.join(tmp, "quickstart.db"), clock=clock)

    decision = harness.submit(
        "Research the state of grid-aware inference scheduling",
        category="research",
        est_tokens=2_000_000,
        deadline=clock.now() + timedelta(hours=12),
    )
    print(decision.message)

    print(harness.respond_to_offer(decision.task_id, True))

    clock.advance(hours=9)  # 3:00 AM — the cheap window
    for task in harness.ready_tasks():
        print(harness.complete_task(task.id)["message"])

    print(harness.savings_report())

