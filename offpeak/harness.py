"""The OffPeak harness: pricing-aware scheduling and savings accounting.

The harness never calls your LLM itself — your agent (or any MCP client)
executes tasks and reports token usage back, so the accounting stays honest.
Attach a handler to ``submit()`` if you want the harness to execute work
itself when the cheap window arrives.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from offpeak import voice
from offpeak.clock import Clock, RealClock
from offpeak.connectors.caiso import CaisoDayAheadPricing
from offpeak.costs import CostTracker
from offpeak.flexibility import FlexibilityLearner
from offpeak.policy import ASK_USER, DEFER, Decision, Policy
from offpeak.pricing import PricingSource, cheapest_start, peak_price
from offpeak.tasks import Task, TaskQueue

DEFAULT_HORIZON = timedelta(hours=24)


class OffPeakHarness:
    """Schedules tasks into cheap windows and keeps an honest savings ledger."""

    def __init__(
        self,
        db_path: str = "offpeak.db",
        *,
        pricing: PricingSource | None = None,
        clock: Clock | None = None,
        policy: Policy | None = None,
    ) -> None:
        self.clock = clock or RealClock()
        self.pricing = pricing or CaisoDayAheadPricing()
        self.policy = policy or Policy()
        self.queue = TaskQueue(db_path)
        self.costs = CostTracker(db_path)
        self.flex = FlexibilityLearner(db_path)
        self._handlers: dict[str, object] = {}

    # ---------------------------------------------------------------- pricing
    def price_now(self) -> float:
        return self.pricing.price_at(self.clock.now())

    def forecast_summary(self, hours: int = 24) -> dict:
        now = self.clock.now()
        now_price = self.pricing.price_at(now)
        points = self.pricing.forecast(now, hours)
        found = cheapest_start(self.pricing, now, now + timedelta(hours=hours))
        best = None
        if found:
            best_start, best_price = found
            best = {
                "start": best_start.isoformat(),
                "price_per_mtok": best_price,
                "savings_frac_vs_now": (
                    (now_price - best_price) / now_price if now_price else 0.0
                ),
            }
        return {
            "now": now.isoformat(),
            "price_now_per_mtok": now_price,
            "peak_per_mtok": max(p.price_per_mtok for p in points),
            "best_window": best,
            "points": [
                {"at": p.at.isoformat(), "price_per_mtok": p.price_per_mtok}
                for p in points
            ],
        }

    # ----------------------------------------------------------- task lifecycle
    def submit(
        self,
        prompt: str,
        *,
        category: str = "general",
        est_tokens: int = 10_000,
        deadline: datetime | None = None,
        duration_min: int = 5,
        handler=None,
    ) -> Decision:
        """Submit a task for price-aware scheduling and get a Decision back."""
        now = self.clock.now()
        deadline = deadline or (now + DEFAULT_HORIZON)
        now_price = self.pricing.price_at(now)
        task = Task(
            id=uuid.uuid4().hex[:12],
            prompt=prompt,
            category=category,
            est_tokens=int(est_tokens),
            duration_min=int(duration_min),
            status="now",
            created_at=now,
            deadline=deadline,
            submit_price=now_price,
            peak_price=peak_price(self.pricing, now),
        )
        latest_start = deadline - timedelta(minutes=task.duration_min)
        found = cheapest_start(
            self.pricing, now, latest_start, timedelta(minutes=task.duration_min)
        )
        best_start, best_price = found if found else (None, None)
        if best_price is not None:
            task.best_price = best_price
        decision = self.policy.decide(
            task, now_price, best_start, best_price,
            self.flex.acceptance_rate(category),
        )
        decision.task_id = task.id
        if decision.action == DEFER:
            task.status = "deferred"
            task.scheduled_at = best_start
        elif decision.action == ASK_USER:
            task.status = "offer"
            task.scheduled_at = best_start
        self.queue.add(task)
        if handler is not None:
            self._handlers[task.id] = handler
        return decision

    def respond_to_offer(self, task_id: str, accept: bool) -> str:
        """Record the user's answer to a deferral offer (this is how the
        harness learns the user's flexibility per task category)."""
        task = self.queue.get(task_id)
        if task is None or task.status != "offer":
            return f"No pending offer for task {task_id}."
        now_price = self.price_now()
        savings_frac = (
            (task.submit_price - task.best_price) / task.submit_price
            if task.submit_price
            else 0.0
        )
        if accept and task.scheduled_at is not None:
            task.status = "deferred"
            self.flex.record_offer(task.id, task.category, savings_frac, accepted=True)
            message = voice.deferred(
                task, task.scheduled_at, task.best_price,
                task.submit_price, savings_frac, auto=False,
            )
        else:
            task.status = "now"
            self.flex.record_offer(task.id, task.category, savings_frac, accepted=False)
            message = voice.rejected(now_price)
        self.queue.update(task)
        return message

    def ready_tasks(self) -> list[Task]:
        """Deferred tasks whose cheap window has arrived (marks them ready)."""
        now = self.clock.now()
        ready = self.queue.due(now)
        for task in ready:
            task.status = "ready"
            self.queue.update(task)
        return ready

    def complete_task(
        self,
        task_id: str,
        *,
        actual_tokens: int | None = None,
        result: str | None = None,
    ) -> dict:
        """Report a task's completion; records actual cost and savings."""
        task = self.queue.get(task_id)
        if task is None:
            return {"error": f"Unknown task {task_id}."}
        if task.status not in ("ready", "now"):
            return {"error": f"Task {task_id} is '{task.status}', not awaiting completion."}
        now = self.clock.now()
        price_paid = self.pricing.price_at(now)
        deferred = task.status == "ready"
        entry = self.costs.record(
            task, price_paid, now, actual_tokens, deferred=deferred
        )
        task.status = "done"
        task.actual_tokens = (
            actual_tokens if actual_tokens is not None else task.est_tokens
        )
        task.result = result
        self.queue.update(task)
        self._handlers.pop(task_id, None)
        entry["message"] = voice.completion(entry, now)
        return entry

    def run_due(self) -> list[dict]:
        """Execute ready tasks that have attached handlers."""
        results = []
        for task in self.ready_tasks():
            handler = self._handlers.get(task.id)
            if handler is None:
                continue
            try:
                outcome = handler(task) or {}
                usage = outcome.get("usage") or {}
                results.append(
                    self.complete_task(
                        task.id,
                        actual_tokens=usage.get("total_tokens"),
                        result=outcome.get("output"),
                    )
                )
            except Exception as exc:  # record failures, keep scheduling
                task.status = "failed"
                task.result = f"handler error: {exc}"
                self.queue.update(task)
                self._handlers.pop(task.id, None)
                results.append({"task_id": task.id, "error": str(exc)})
        return results

    # -------------------------------------------------------------- reporting
    def savings_report(self) -> str:
        return voice.savings_report(self.costs.totals(), self.flex.summary())

    def tasks(self, status: str | None = None) -> list[Task]:
        return self.queue.list(status)

