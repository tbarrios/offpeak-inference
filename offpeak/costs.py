"""Cost and savings ledger: every completed task's actual spend and savings."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime

from offpeak.tasks import Task

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    category TEXT NOT NULL,
    est_tokens INTEGER NOT NULL,
    actual_tokens INTEGER NOT NULL,
    submit_price REAL NOT NULL,
    paid_price REAL NOT NULL,
    peak_price REAL NOT NULL,
    cost_usd REAL NOT NULL,
    savings_vs_now REAL NOT NULL,
    savings_vs_peak REAL NOT NULL,
    deferred INTEGER NOT NULL,
    completed_at TEXT NOT NULL
)
"""


class CostTracker:
    """Records actual spend and honest arbitrage savings per completed task."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.executescript(_SCHEMA)

    def record(
        self,
        task: Task,
        price_paid: float,
        completed_at: datetime,
        actual_tokens: int | None = None,
        deferred: bool = False,
    ) -> dict:
        tokens = actual_tokens if actual_tokens is not None else task.est_tokens
        cost = tokens / 1e6 * price_paid
        # Deferred tasks only count savings vs the price at submit time — the
        # honest arbitrage number. Immediate runs record zero deferral savings.
        savings_now = (
            max(0.0, tokens / 1e6 * (task.submit_price - price_paid))
            if deferred else 0.0
        )
        savings_peak = max(0.0, tokens / 1e6 * (task.peak_price - price_paid))
        entry = {
            "task_id": task.id,
            "category": task.category,
            "est_tokens": task.est_tokens,
            "actual_tokens": tokens,
            "submit_price": task.submit_price,
            "paid_price": price_paid,
            "peak_price": task.peak_price,
            "cost_usd": cost,
            "savings_vs_now": savings_now,
            "savings_vs_peak": savings_peak,
            "deferred": deferred,
            "completed_at": completed_at.isoformat(),
        }
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                "INSERT INTO ledger (task_id, category, est_tokens, actual_tokens,"
                " submit_price, paid_price, peak_price, cost_usd,"
                " savings_vs_now, savings_vs_peak, deferred, completed_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (entry["task_id"], entry["category"], entry["est_tokens"],
                 entry["actual_tokens"], entry["submit_price"], entry["paid_price"],
                 entry["peak_price"], entry["cost_usd"], entry["savings_vs_now"],
                 entry["savings_vs_peak"], int(entry["deferred"]),
                 entry["completed_at"]),
            )
        return entry

    def totals(self) -> dict:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT COUNT(*) AS tasks, COALESCE(SUM(deferred),0) AS deferred,"
                " COALESCE(SUM(cost_usd),0) AS spend,"
                " COALESCE(SUM(savings_vs_now),0) AS saved_now,"
                " COALESCE(SUM(savings_vs_peak),0) AS saved_peak FROM ledger"
            ).fetchone()
        spend = float(row["spend"])
        saved_now = float(row["saved_now"])
        baseline = spend + saved_now
        return {
            "tasks": row["tasks"],
            "deferred": row["deferred"],
            "spend_usd": spend,
            "savings_vs_now_usd": saved_now,
            "savings_vs_peak_usd": float(row["saved_peak"]),
            "avg_discount_pct": (saved_now / baseline * 100) if baseline > 0 else 0.0,
        }

    def recent(self, limit: int = 20) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ledger ORDER BY completed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

