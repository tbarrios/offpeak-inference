"""Tests for pricing, policy, learning, costs, and the end-to-end harness."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from io import StringIO
from contextlib import redirect_stdout

from offpeak.clock import SimClock
from offpeak.connectors.placeholder import TimeOfDayPricing
from offpeak.costs import CostTracker
from offpeak.flexibility import FlexibilityLearner
from offpeak.harness import OffPeakHarness
from offpeak.policy import ASK_USER, DEFER, RUN_NOW, Policy
from offpeak.pricing import cheapest_start
from offpeak.tasks import Task


def make_task(**kwargs) -> Task:
    defaults = dict(
        id="t1", prompt="p", category="research", est_tokens=100_000,
        duration_min=5, submit_price=1.0, best_price=0.3, peak_price=1.6,
    )
    defaults.update(kwargs)
    return Task(**defaults)


class PricingTests(unittest.TestCase):
    def test_placeholder_duck_curve(self) -> None:
        pricing = TimeOfDayPricing()
        self.assertAlmostEqual(pricing.price_at(datetime(2026, 1, 1, 3)), 0.60 * 0.42)
        self.assertAlmostEqual(pricing.price_at(datetime(2026, 1, 1, 19)), 0.60 * 1.55)

    def test_cheapest_start_finds_overnight_window(self) -> None:
        pricing = TimeOfDayPricing()
        earliest = datetime(2026, 1, 1, 18)
        found = cheapest_start(
            pricing, earliest, earliest + timedelta(hours=11), timedelta(minutes=5)
        )
        self.assertIsNotNone(found)
        start, price = found
        self.assertEqual((start.hour, start.minute), (3, 0))
        self.assertAlmostEqual(price, 0.60 * 0.42)

    def test_no_window_when_deadline_too_tight(self) -> None:
        pricing = TimeOfDayPricing()
        at = datetime(2026, 1, 1, 18)
        self.assertIsNone(cheapest_start(pricing, at, at - timedelta(minutes=1)))


class PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = Policy()
        self.best_start = datetime(2026, 1, 2, 3)

    def test_asks_user_when_flexibility_unknown(self) -> None:
        decision = self.policy.decide(
            make_task(), now_price=1.0, best_start=self.best_start,
            best_price=0.3, acceptance_rate=0.5,
        )
        self.assertEqual(decision.action, ASK_USER)
        self.assertIn("3:00 AM", decision.message)
        self.assertIn("Want me to defer it?", decision.message)

    def test_auto_defers_when_user_flexibility_learned(self) -> None:
        decision = self.policy.decide(
            make_task(), now_price=1.0, best_start=self.best_start,
            best_price=0.3, acceptance_rate=0.8,
        )
        self.assertEqual(decision.action, DEFER)
        self.assertIn("Auto-scheduled", decision.message)

    def test_runs_now_when_savings_small(self) -> None:
        decision = self.policy.decide(
            make_task(), now_price=1.0, best_start=self.best_start,
            best_price=0.97, acceptance_rate=0.9,
        )
        self.assertEqual(decision.action, RUN_NOW)

    def test_runs_now_without_window(self) -> None:
        decision = self.policy.decide(
            make_task(), now_price=1.0, best_start=None,
            best_price=None, acceptance_rate=0.9,
        )
        self.assertEqual(decision.action, RUN_NOW)
        self.assertIn("deadline", decision.message)


class FlexibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "flex.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_laplace_smoothing_and_learning(self) -> None:
        learner = FlexibilityLearner(self.db)
        self.assertAlmostEqual(learner.acceptance_rate("research"), 0.5)
        for i in range(3):
            learner.record_offer(f"t{i}", "research", 0.7, accepted=True)
        self.assertAlmostEqual(learner.acceptance_rate("research"), 0.8)
        summary = learner.summary()
        self.assertEqual(summary["research"], {"offers": 3, "accepted": 3})


class CostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "costs.db")
        self.tracker = CostTracker(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_deferred_savings_math(self) -> None:
        entry = self.tracker.record(
            make_task(), price_paid=0.3,
            completed_at=datetime(2026, 1, 2, 3), deferred=True,
        )
        self.assertAlmostEqual(entry["cost_usd"], 0.03)
        self.assertAlmostEqual(entry["savings_vs_now"], 0.07)
        self.assertAlmostEqual(entry["savings_vs_peak"], 0.13)

    def test_immediate_runs_record_zero_deferral_savings(self) -> None:
        entry = self.tracker.record(
            make_task(), price_paid=0.9,
            completed_at=datetime(2026, 1, 1, 19), deferred=False,
        )
        self.assertEqual(entry["savings_vs_now"], 0.0)
        self.assertAlmostEqual(entry["savings_vs_peak"], 0.07)

    def test_totals(self) -> None:
        task = make_task()
        self.tracker.record(task, 0.3, datetime(2026, 1, 2, 3), deferred=True)
        self.tracker.record(make_task(id="t2"), 0.9, datetime(2026, 1, 1, 19), deferred=False)
        totals = self.tracker.totals()
        self.assertEqual(totals["tasks"], 2)
        self.assertEqual(totals["deferred"], 1)
        self.assertAlmostEqual(totals["savings_vs_now_usd"], 0.07)


class HarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "harness.db")
        self.clock = SimClock(datetime(2026, 11, 8, 18, 0))
        self.harness = OffPeakHarness(db_path=self.db, clock=self.clock)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_end_to_end_offer_accept_defer_complete(self) -> None:
        decision = self.harness.submit(
            "Deep research on inference pricing",
            category="research",
            est_tokens=2_000_000,
            deadline=self.clock.now() + timedelta(hours=12),
        )
        self.assertEqual(decision.action, ASK_USER)
        self.assertAlmostEqual(decision.savings_frac, (0.87 - 0.252) / 0.87, places=3)
        self.assertAlmostEqual(decision.savings_usd, 2_000_000 / 1e6 * 0.618, places=5)
        self.assertIn("Want me to defer it?", decision.message)

        message = self.harness.respond_to_offer(decision.task_id, True)
        self.assertIn("Scheduled", message)
        task = self.harness.tasks("deferred")[0]
        self.assertEqual(task.scheduled_at.hour, 3)

        self.clock.advance(hours=9)  # 3:00 AM — the cheap window
        ready = self.harness.ready_tasks()
        self.assertEqual(len(ready), 1)
        entry = self.harness.complete_task(decision.task_id)
        self.assertTrue(entry["deferred"])
        self.assertAlmostEqual(entry["savings_vs_now"], 1.236, places=5)
        self.assertIn("saved", entry["message"])

        report = self.harness.savings_report()
        self.assertIn("OffPeak savings", report)
        self.assertIn("research 1/1", report)

    def test_reject_offer_runs_now(self) -> None:
        decision = self.harness.submit(
            "Quick analysis", category="analysis", est_tokens=20_000,
            deadline=self.clock.now() + timedelta(hours=12),
        )
        self.assertEqual(decision.action, ASK_USER)
        message = self.harness.respond_to_offer(decision.task_id, False)
        self.assertIn("running now", message)
        entry = self.harness.complete_task(decision.task_id)
        self.assertFalse(entry["deferred"])
        self.assertEqual(entry["savings_vs_now"], 0.0)

    def test_low_savings_runs_now(self) -> None:
        self.clock.advance(hours=9)  # 3:00 AM — already cheap
        decision = self.harness.submit(
            "Quick question", est_tokens=1_000,
            deadline=self.clock.now() + timedelta(hours=6),
        )
        self.assertEqual(decision.action, RUN_NOW)
        task = self.harness.tasks("now")[0]
        self.assertEqual(task.id, decision.task_id)

    def test_auto_defer_after_learning(self) -> None:
        for i in range(2):
            decision = self.harness.submit(
                f"Research task {i}", category="research", est_tokens=50_000,
                deadline=self.clock.now() + timedelta(hours=12),
            )
            self.harness.respond_to_offer(decision.task_id, True)
        self.assertAlmostEqual(self.harness.flex.acceptance_rate("research"), 0.75)

        decision = self.harness.submit(
            "Third research task", category="research", est_tokens=50_000,
            deadline=self.clock.now() + timedelta(hours=12),
        )
        self.assertEqual(decision.action, DEFER)
        self.assertIn("Auto-scheduled", decision.message)
        self.assertEqual(self.harness.tasks("deferred")[0].scheduled_at.hour, 3)

    def test_run_due_executes_handlers(self) -> None:
        def handler(task):
            return {"output": "done", "usage": {"total_tokens": 123}}

        decision = self.harness.submit(
            "Handled task", category="research", est_tokens=10_000,
            deadline=self.clock.now() + timedelta(hours=12), handler=handler,
        )
        self.harness.respond_to_offer(decision.task_id, True)
        self.clock.advance(hours=9)
        results = self.harness.run_due()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["actual_tokens"], 123)
        self.assertEqual(self.harness.tasks("done")[0].id, decision.task_id)

    def test_persistence_across_instances(self) -> None:
        decision = self.harness.submit(
            "Persisted task", category="research", est_tokens=40_000,
            deadline=self.clock.now() + timedelta(hours=12),
        )
        self.harness.respond_to_offer(decision.task_id, True)
        self.clock.advance(hours=9)
        for task in self.harness.ready_tasks():
            self.harness.complete_task(task.id)
        reopened = OffPeakHarness(db_path=self.db, clock=self.clock)
        self.assertEqual(reopened.costs.totals()["tasks"], 1)
        self.assertAlmostEqual(reopened.costs.totals()["savings_vs_now_usd"], 0.02472, places=5)

    def test_cli_demo_smoke(self) -> None:
        from offpeak.cli import main

        buffer = StringIO()
        with redirect_stdout(buffer):
            main(["demo"])
        output = buffer.getvalue()
        self.assertIn("OffPeak demo", output)
        self.assertIn("Auto-scheduled", output)

