"""MCP server exposing OffPeak to any MCP-compatible agent.

Run with: ``python -m offpeak.mcp_server``
Install the MCP SDK first: ``pip install 'offpeak[mcp]'``
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "OffPeak's MCP server needs the MCP SDK."
        " Install with: pip install 'offpeak[mcp]'"
    ) from exc

from offpeak.harness import OffPeakHarness

DB_PATH = os.environ.get("OFFPEAK_DB", str(Path.home() / ".offpeak" / "harness.db"))
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
harness = OffPeakHarness(db_path=DB_PATH)
mcp = FastMCP("offpeak")


@mcp.tool()
def get_price_forecast(hours: int = 24) -> str:
    """Current + forecasted inference prices ($/Mtok), the cheapest upcoming
    window, and the daily peak. Use this to decide when to run work."""
    return json.dumps(harness.forecast_summary(hours), indent=2)


@mcp.tool()
def submit_task(
    prompt: str,
    category: str = "general",
    est_tokens: int = 10000,
    deadline_hours: float = 24.0,
    duration_min: int = 5,
) -> str:
    """Submit a task for price-aware scheduling. Returns the decision and,
    when deferral would save money, an offer message to relay to the user."""
    deadline = datetime.now() + timedelta(hours=deadline_hours)
    decision = harness.submit(
        prompt,
        category=category,
        est_tokens=est_tokens,
        deadline=deadline,
        duration_min=duration_min,
    )
    return json.dumps(
        {
            "task_id": decision.task_id,
            "action": decision.action,
            "scheduled_at": (
                decision.scheduled_at.isoformat() if decision.scheduled_at else None
            ),
            "savings_frac": decision.savings_frac,
            "savings_usd": decision.savings_usd,
            "message": decision.message,
        },
        indent=2,
    )


@mcp.tool()
def respond_to_offer(task_id: str, accept: bool) -> str:
    """Record the user's answer to a deferral offer. The harness learns the
    user's flexibility from accept/reject decisions, per task category."""
    return harness.respond_to_offer(task_id, accept)


@mcp.tool()
def get_ready_tasks() -> str:
    """Deferred tasks whose cheap window has arrived. Execute their prompts,
    then report back with complete_task."""
    tasks = harness.ready_tasks()
    return json.dumps(
        [
            {
                "task_id": task.id,
                "prompt": task.prompt,
                "category": task.category,
                "scheduled_at": (
                    task.scheduled_at.isoformat() if task.scheduled_at else None
                ),
            }
            for task in tasks
        ],
        indent=2,
    )


@mcp.tool()
def complete_task(task_id: str, actual_tokens: Optional[int] = None) -> str:
    """Report a task's completion; records actual cost and savings."""
    return json.dumps(
        harness.complete_task(task_id, actual_tokens=actual_tokens), indent=2
    )


@mcp.tool()
def get_savings_report() -> str:
    """Savings and spend totals, plus the user's learned flexibility profile."""
    return harness.savings_report()


if __name__ == "__main__":
    mcp.run()

