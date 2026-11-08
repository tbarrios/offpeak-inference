"""Synthetic users and a closed-loop simulation of conversations."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .learner import (
    evaluate_temporal_choice,
    learn_from_ask,
    learn_from_defer,
    learn_from_immediate,
)
from .policy import Action, decide
from .pricing import cost_usd
from .reporting import (
    LEVEL_INDEX,
    TOO_LITTLE,
    TOO_MUCH,
    RIGHT,
    choose_report_level,
    evaluate_report_calibration,
    learn_from_report_feedback,
)
from .state import UserState


TASK_TYPES = ["deep_research", "code_review", "email_draft", "summarize"]
MATERIAL_SAVINGS = 0.25


@dataclass
class SyntheticUser:
    """A simulated user with hidden true flexibility per task type."""

    user_id: str
    true_flexibility: dict[str, float]
    true_detail: dict[str, str] | None = None
    honesty: float = 0.9

    def __post_init__(self) -> None:
        if self.true_detail is None:
            self.true_detail = {
                "deep_research": "detailed",
                "code_review": "standard",
                "email_draft": "standard",
                "summarize": "standard",
            }

    def accepts_defer(self, task_type: str, rng: random.Random) -> bool:
        return rng.random() < self.true_flexibility.get(task_type, 0.3)

    def answers_ask(self, task_type: str, rng: random.Random) -> bool:
        truth = self.true_flexibility.get(task_type, 0.3) >= 0.5
        if rng.random() < self.honesty:
            return truth
        return not truth

    def report_feedback(self, task_type: str, level: str, rng: random.Random) -> str:
        desired = self.true_detail.get(task_type, "standard")
        if level == desired:
            return RIGHT if rng.random() < self.honesty else rng.choice([TOO_MUCH, TOO_LITTLE])
        if LEVEL_INDEX[level] > LEVEL_INDEX[desired]:
            return TOO_MUCH if rng.random() < self.honesty else rng.choice([RIGHT, TOO_LITTLE])
        return TOO_LITTLE if rng.random() < self.honesty else rng.choice([RIGHT, TOO_MUCH])


@dataclass
class SimulationResult:
    records: list[dict] = field(default_factory=list)
    savings_usd: float = 0.0
    baseline_savings_usd: float = 0.0
    asks: int = 0
    defers: int = 0
    defers_accepted: int = 0
    defers_overridden: int = 0
    run_now: int = 0
    autonomous_correct: int = 0
    autonomous_total: int = 0
    report_correct: int = 0
    report_total: int = 0
    level_error: int = 0

    @property
    def override_rate(self) -> float:
        return self.defers_overridden / self.defers if self.defers else 0.0

    @property
    def correctness_rate(self) -> float:
        return self.autonomous_correct / self.autonomous_total if self.autonomous_total else 0.0

    @property
    def report_calibration_rate(self) -> float:
        return self.report_correct / self.report_total if self.report_total else 0.0


def _arrival_hour(rng: random.Random) -> int:
    hour = rng.triangular(7, 23, 17)
    return int(hour) % 24


def _tokens_for(task_type: str, rng: random.Random) -> float:
    base = {"deep_research": 250_000, "code_review": 90_000, "email_draft": 25_000, "summarize": 40_000}
    return base[task_type] * rng.uniform(0.7, 1.3)


def simulate_conversations(
    user: SyntheticUser,
    state: UserState,
    schedule: list[float],
    n_conversations: int,
    seed: int = 0,
    log_prefix: str | None = None,
    verbose: bool = False,
) -> SimulationResult:
    """Run the full closed loop: decide, observe, learn, evaluate."""

    rng = random.Random(seed)
    result = SimulationResult()

    for conversation in range(1, n_conversations + 1):
        task_type = rng.choice(TASK_TYPES)
        hour = _arrival_hour(rng)
        tokens = _tokens_for(task_type, rng)

        decision = decide(task_type, hour, state, schedule)

        if decision.action is Action.ASK:
            result.asks += 1
            flexible = user.answers_ask(task_type, rng)
            learn_from_ask(state, task_type, flexible)
            revealed = "flexible" if flexible else "immediate"
            if flexible:
                run_hour = decision.best_hour
                run_price = decision.best_price
            else:
                run_hour = hour
                run_price = decision.price_now
            autonomous = False
        else:
            run_hour = hour
            run_price = decision.price_now
            revealed = None
            autonomous = True

        if decision.action is Action.DEFER:
            result.defers += 1
            accepted = user.accepts_defer(task_type, rng)
            accepted_revealed = learn_from_defer(state, task_type, accepted)
            revealed = "flexible" if accepted_revealed else "immediate"
            if accepted:
                result.defers_accepted += 1
                run_hour = decision.best_hour
                run_price = decision.best_price
            else:
                result.defers_overridden += 1
                run_hour = hour
                run_price = decision.price_now
        elif decision.action is Action.RUN_NOW:
            result.run_now += 1
            would_have_waited = user.accepts_defer(task_type, rng)
            material = decision.savings_ratio >= MATERIAL_SAVINGS
            waited_revealed = learn_from_immediate(state, task_type, would_have_waited, material=material)
            revealed = "flexible" if waited_revealed else "immediate"

        correct = evaluate_temporal_choice(
            state,
            task_type,
            decision.action.value,
            revealed or "immediate",
            savings_ratio=decision.savings_ratio,
            material_savings=MATERIAL_SAVINGS,
        )
        if autonomous:
            result.autonomous_total += 1
            if correct:
                result.autonomous_correct += 1

        report_level = choose_report_level(state, task_type)
        feedback = user.report_feedback(task_type, report_level, rng)
        learn_from_report_feedback(state, task_type, report_level, feedback)
        desired_level = user.true_detail.get(task_type, "standard")
        report_correct = evaluate_report_calibration(report_level, desired_level)
        result.report_total += 1
        if report_correct:
            result.report_correct += 1
        result.level_error += abs(LEVEL_INDEX[report_level] - LEVEL_INDEX[desired_level])

        actual_savings = cost_usd(tokens, decision.price_now) - cost_usd(tokens, run_price)
        result.savings_usd += max(0.0, actual_savings)
        result.baseline_savings_usd += max(0.0, cost_usd(tokens, decision.price_now) - cost_usd(tokens, decision.best_price))

        record = {
            "conversation": conversation,
            "task_type": task_type,
            "hour": hour,
            "action": decision.action.value,
            "revealed": revealed,
            "correct": correct,
            "savings_usd": max(0.0, actual_savings),
            "tokens": tokens,
            "report_level": report_level,
            "report_feedback": feedback,
            "report_correct": report_correct,
        }
        result.records.append(record)
        state.record_decision(record)

        if verbose and log_prefix:
            print(f"{log_prefix} conv={conversation:02d} task={task_type:<12} hour={hour:02d} action={decision.action.value:<7} revealed={revealed:<9} correct={correct} saved=${record['savings_usd']:.4f}")

    return result


def window_metrics(records: list[dict]) -> dict:
    """Aggregate metrics for a slice of conversation records."""

    asks = sum(r["action"] == "ask" for r in records)
    defers = sum(r["action"] == "defer" for r in records)
    overrides = sum(r["action"] == "defer" and r["revealed"] == "immediate" for r in records)
    autonomous = [r for r in records if r["action"] in ("defer", "run_now")]
    return {
        "asks": asks,
        "defers": defers,
    "overrides": overrides,
        "ask_rate": asks / len(records) if records else 0.0,
        "override_rate": overrides / defers if defers else 0.0,
        "autonomous_correctness": (
            sum(r["correct"] for r in autonomous) / len(autonomous) if autonomous else None
        ),
        "report_calibration": (
            sum(r["report_correct"] for r in records) / len(records) if records else None
        ),
    }
