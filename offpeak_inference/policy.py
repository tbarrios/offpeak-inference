"""Decision policy: run now, defer, or ask the user."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .pricing import best_future
from .state import UserState


class Action(str, Enum):
    RUN_NOW = "run_now"
    DEFER = "defer"
    ASK = "ask"


@dataclass
class Decision:
    action: Action
    task_type: str
    hour: int
    price_now: float
    best_price: float
    best_hour: int
    savings_ratio: float
    p_flexible: float
    rationale: str


def decide(
    task_type: str,
    hour: int,
    state: UserState,
    schedule: list[float],
    horizon_hours: int = 12,
    min_savings: float = 0.15,
    material_savings: float = 0.25,
    dissat_penalty: float = 0.45,
    ask_variance: float = 0.055,
    min_observations: float = 2.0,
) -> Decision:
    """Choose an action balancing price savings against user preference risk.

    The expected utility of deferring is p * savings - (1 - p) * penalty,
    where p is the learned probability this user accepts deferral for this
    task type. The agent only asks when its belief is still uncertain and the
    stakes are material; as evidence accumulates it stops asking and decides
    autonomously.
    """

    price_now = schedule[hour]
    best_price, best_hour = best_future(schedule, hour, horizon_hours)
    savings_ratio = max(0.0, (price_now - best_price) / price_now)

    belief = state.get_task_belief(task_type)
    p_flexible = belief.belief.mean
    variance = belief.belief.variance
    observations = belief.observations

    penalty = dissat_penalty
    correctness = belief.correctness_rate
    if correctness is not None and correctness < 0.6 and belief.decision_total >= 3:
        penalty *= min(3.0, 0.6 / max(correctness, 0.2))

    if savings_ratio < min_savings or best_price >= price_now:
        return Decision(
            Action.RUN_NOW, task_type, hour, price_now, best_price, best_hour,
            savings_ratio, p_flexible,
            "savings below threshold; run immediately",
        )

    eu_defer = p_flexible * savings_ratio - (1.0 - p_flexible) * penalty
    uncertain = variance > ask_variance or observations < min_observations

    if uncertain and savings_ratio >= material_savings:
        return Decision(
            Action.ASK, task_type, hour, price_now, best_price, best_hour,
            savings_ratio, p_flexible,
            "belief still uncertain; ask the user before deferring",
        )

    if eu_defer > 0:
        return Decision(
            Action.DEFER, task_type, hour, price_now, best_price, best_hour,
            savings_ratio, p_flexible,
            f"expected deferral utility {eu_defer:.3f} > 0 at p_flexible={p_flexible:.2f}",
        )

    return Decision(
        Action.RUN_NOW, task_type, hour, price_now, best_price, best_hour,
        savings_ratio, p_flexible,
        f"expected deferral utility {eu_defer:.3f} <= 0; keep the answer immediate",
    )
