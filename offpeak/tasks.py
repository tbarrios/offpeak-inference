"""Persistent task queue for deferred and immediate work."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    category TEXT NOT NULL,
    est_tokens INTEGER NOT NULL,
    duration_min INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    deadline TEXT,
    scheduled_at TEXT,
    submit_price REAL NOT NULL,
    best_price REAL NOT NULL,
    peak_price REAL NOT NULL,
    actual_tokens INTEGER,
    result TEXT
)
"""


@dataclass
class Task:
    id: str
    prompt: str
    category: str = "general"
    est_tokens: int = 10_000
    duration_min: int = 5
    status: str = "now"  # offer | deferred | ready | now | done | failed
    created_at: datetime | None = None
    deadline: datetime | None = None
    scheduled_at: datetime | None = None
    submit_price: float = 0.0
    best_price: float = 0.0
    peak_price: float = 0.0
    actual_tokens: int | None = None
    result: str | None = None


def new_task_id() -> str:
    return uuid.uuid4().hex[:12]


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


def _task_values(task: Task) -> tuple:
    return (
        task.id, task.prompt, task.category, task.est_tokens, task.duration_min,
        task.status, _iso(task.created_at), _iso(task.deadline),
        _iso(task.scheduled_at), task.submit_price, task.best_price,
        task.peak_price, task.actual_tokens, task.result,
    )


def _task_from_row(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"], prompt=row["prompt"], category=row["category"],
        est_tokens=row["est_tokens"], duration_min=row["duration_min"],
        status=row["status"], created_at=_parse(row["created_at"]),
        deadline=_parse(row["deadline"]), scheduled_at=_parse(row["scheduled_at"]),
        submit_price=row["submit_price"], best_price=row["best_price"],
        peak_price=row["peak_price"], actual_tokens=row["actual_tokens"],
        result=row["result"],
    )


class TaskQueue:
    """SQLite-backed task store (naive local datetimes, ISO-serialized)."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, task: Task) -> None:
        query = (
            "INSERT INTO tasks (id, prompt, category, est_tokens, duration_min,"
            " status, created_at, deadline, scheduled_at, submit_price,"
            " best_price, peak_price, actual_tokens, result)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )
        with closing(self._connect()) as conn, conn:
            conn.execute(query, _task_values(task))

    def update(self, task: Task) -> None:
        query = (
            "UPDATE tasks SET status=?, deadline=?, scheduled_at=?,"
            " actual_tokens=?, result=? WHERE id=?"
        )
        with closing(self._connect()) as conn, conn:
            conn.execute(
                query,
                (task.status, _iso(task.deadline), _iso(task.scheduled_at),
                 task.actual_tokens, task.result, task.id),
            )

    def get(self, task_id: str) -> Task | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return _task_from_row(row) if row else None

    def list(self, status: str | None = None) -> list[Task]:
        query = "SELECT * FROM tasks"
        params: tuple = ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        query += " ORDER BY created_at"
        with closing(self._connect()) as conn:
            rows = conn.execute(query, params).fetchall()
        return [_task_from_row(row) for row in rows]

    def due(self, now: datetime) -> list[Task]:
        return [
            task
            for task in self.list(status="deferred")
            if task.scheduled_at is not None and task.scheduled_at <= now
        ]

