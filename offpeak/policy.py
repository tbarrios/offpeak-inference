"""Deferral policy: run now, defer automatically, or ask the user."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from offpeak.tasks import Task
from offpeak.voice import deferred, offer, run_now

RUN_NOW = "run_now"
DEFER = "defer"
ASK_USER = "ask_user"


@dataclass
class Decision:
    action: str
    task_id: str = ""
    message: str = ""
    scheduled_at: datetime | None = None
    savings_frac: float = 0.0
    savings_usd: float = 0.0
    now_price: float = 0.0
    best_price: float = 0.0
    best_start: datetime | None = None


class Policy:
    """Decides between running now, deferring, or asking the user.

    - Below ``min_savings`` (5%), deferring isn't worth the friction.
    - Once the user's learned acceptance rate for a category reaches
      ``auto_defer_acceptance`` and savings are at least
      ``auto_defer_savings``, defer automatically.
    - Otherwise, surface the savings and ask — this is how the harness
      learns each user's flexibility.
    """

    def __init__(
        self,
        min_savings: float = 0.05,
        auto_defer_savings: float = 0.15,
        auto_defer_acceptance: float = 0.75,
    ) -> None:
        self.min_savings = min_savings
        self.auto_defer_savings = auto_defer_savings
        self.auto_defer_acceptance = auto_defer_acceptance

    def decide(
        self,
        task: Task,
        now_price: float,
        best_start: datetime | None,
        best_price: float | None,
        acceptance_rate: float,
    ) -> Decision:
        if best_start is None or best_price is None:
            return Decision(
                action=RUN_NOW,
                now_price=now_price,
                message=run_now(
                    now_price, reason="no cheaper window before the deadline"
                ),
            )
        savings_frac = (
            (now_price - best_price) / now_price if now_price else 0.0
        )
        savings_usd = task.est_tokens / 1e6 * (now_price - best_price)
        if savings_frac < self.min_savings:
            return Decision(
                action=RUN_NOW,
                now_price=now_price,
                message=run_now(now_price),
            )
        if (
            savings_frac >= self.auto_defer_savings
            and acceptance_rate >= self.auto_defer_acceptance
        ):
            return Decision(
                action=DEFER,
                scheduled_at=best_start,
                savings_frac=savings_frac,
                savings_usd=savings_usd,
                now_price=now_price,
                best_price=best_price,
                best_start=best_start,
                message=deferred(
                    task, best_start, best_price, now_price, savings_frac, auto=True
                ),
            )
        return Decision(
            action=ASK_USER,
            scheduled_at=best_start,
            savings_frac=savings_frac,
            savings_usd=savings_usd,
            now_price=now_price,
            best_price=best_price,
            best_start=best_start,
            message=offer(
                task, best_start, now_price, best_price, savings_frac, savings_usd
            ),
        )
