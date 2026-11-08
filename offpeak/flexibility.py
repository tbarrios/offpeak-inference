"""Learns the user's scheduling flexibility, per task category.

Every time the harness offers a deferral, the user's accept/reject decision is
recorded. A Laplace-smoothed acceptance rate per category drives auto-defer:
once the user accepts enough offers in a category (and savings are
meaningful), OffPeak starts deferring those tasks automatically.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime

_SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    category TEXT NOT NULL,
    savings_frac REAL NOT NULL,
    accepted INTEGER NOT NULL,
    offered_at TEXT NOT NULL
)
"""


class FlexibilityLearner:
    """Tracks how often the user accepts deferral offers, by category."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.executescript(_SCHEMA)

    def record_offer(
        self,
        task_id: str,
        category: str,
        savings_frac: float,
        *,
        accepted: bool,
        at: datetime | None = None,
    ) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                "INSERT INTO offers (task_id, category, savings_frac, accepted, offered_at)"
                " VALUES (?,?,?,?,?)",
                (task_id, category, float(savings_frac), int(accepted),
                 (at or datetime.now()).isoformat()),
            )

    def acceptance_rate(self, category: str) -> float:
        """Laplace-smoothed acceptance rate; unseen categories start at 0.5."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT COUNT(*) AS offers, COALESCE(SUM(accepted),0) AS accepted"
                " FROM offers WHERE category=?",
                (category,),
            ).fetchone()
        return (row["accepted"] + 1) / (row["offers"] + 2)

    def summary(self) -> dict[str, dict[str, int]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT category, COUNT(*) AS offers,"
                " COALESCE(SUM(accepted),0) AS accepted"
                " FROM offers GROUP BY category ORDER BY offers DESC"
            ).fetchall()
        return {
            row["category"]: {"offers": row["offers"], "accepted": row["accepted"]}
            for row in rows
        }

