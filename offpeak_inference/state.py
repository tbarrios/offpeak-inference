"""Per-user belief state for the Off-Peak Inference harness.

The harness maintains Bayesian beliefs about each user's willingness to let
tasks run later ("flexibility"), tracked per task type. New task types inherit
a hierarchical prior from everything already learned about the user, so the
agent learns people, not just categories.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path


PRIOR_ALPHA = 1.0
PRIOR_BETA = 2.0
PRIOR_WEIGHT = PRIOR_ALPHA + PRIOR_BETA

BRIEF = "brief"
STANDARD = "standard"
DETAILED = "detailed"
REPORT_LEVELS = (BRIEF, STANDARD, DETAILED)
DEFAULT_DETAIL_PRIOR = {BRIEF: 1.0, STANDARD: 2.0, DETAILED: 1.0}
PRIOR_DETAIL_WEIGHT = sum(DEFAULT_DETAIL_PRIOR.values())


@dataclass
class BetaBelief:
    """Posterior belief over the probability a user is flexible."""

    alpha: float = PRIOR_ALPHA
    beta: float = PRIOR_BETA

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        n = self.alpha + self.beta
        return (self.alpha * self.beta) / ((n * n) * (n + 1.0))

    @property
    def observations(self) -> float:
        return (self.alpha + self.beta) - PRIOR_WEIGHT


@dataclass
class TaskBelief:
    """Beliefs and outcome counters for one task type for one user."""

    alpha: float = PRIOR_ALPHA
    beta: float = PRIOR_BETA
    defer_accepted: int = 0
    defer_overridden: int = 0
    immediate_engaged: int = 0
    immediate_waste: int = 0
    asked_flexible: int = 0
    asked_inflexible: int = 0
    decision_correct: int = 0
    decision_total: int = 0
    detail_counts: dict = field(default_factory=lambda: dict(DEFAULT_DETAIL_PRIOR))
    report_right: int = 0
    report_total: int = 0

    @property
    def belief(self) -> BetaBelief:
        return BetaBelief(self.alpha, self.beta)

    @property
    def correctness_rate(self) -> float | None:
        if self.decision_total == 0:
            return None
        return self.decision_correct / self.decision_total

    @property
    def observations(self) -> float:
        return self.belief.observations

    @property
    def detail_posterior(self) -> dict:
        total = sum(self.detail_counts.values()) or 1.0
        return {level: count / total for level, count in self.detail_counts.items()}

    @property
    def detail_map(self) -> str:
        posterior = self.detail_posterior
        return max(posterior, key=posterior.get)

    @property
    def detail_observations(self) -> float:
        return sum(self.detail_counts.values()) - PRIOR_DETAIL_WEIGHT

    @property
    def right_feedback_rate(self) -> float | None:
        if self.report_total == 0:
            return None
        return self.report_right / self.report_total


@dataclass
class UserState:
    """Everything the harness remembers about one user."""

    user_id: str
    task_types: dict[str, TaskBelief] = field(default_factory=dict)
    overall_alpha: float = PRIOR_ALPHA
    overall_beta: float = PRIOR_BETA
    pooled_detail: dict = field(default_factory=lambda: dict(DEFAULT_DETAIL_PRIOR))
    decisions: list[dict] = field(default_factory=list)

    @property
    def overall(self) -> BetaBelief:
        return BetaBelief(self.overall_alpha, self.overall_beta)

    def get_task_belief(self, task_type: str) -> TaskBelief:
        """Return the task belief, creating it from the user prior if new."""

        if task_type not in self.task_types:
            alpha, beta = self._hierarchical_prior()
            self.task_types[task_type] = TaskBelief(
                alpha, beta, detail_counts=self._hierarchical_detail_prior()
            )
        return self.task_types[task_type]

    def _hierarchical_prior(self) -> tuple[float, float]:
        """Blend the base prior with the pooled user belief for new tasks."""

        pooled = self.overall.mean
        blended = 0.5 * (PRIOR_ALPHA / PRIOR_WEIGHT) + 0.5 * pooled
        alpha = blended * PRIOR_WEIGHT
        beta = PRIOR_WEIGHT - alpha
        return alpha, beta

    def _hierarchical_detail_prior(self) -> dict:
        """Blend the base detail prior with everything learned about this user."""

        pooled_total = sum(self.pooled_detail.values()) or 1.0
        return {
            level: 0.5 * DEFAULT_DETAIL_PRIOR[level]
            + 0.5 * (self.pooled_detail.get(level, 0.0) / pooled_total) * PRIOR_DETAIL_WEIGHT
            for level in REPORT_LEVELS
        }

    def record_decision(self, entry: dict) -> None:
        self.decisions.append(entry)

    def save(self, directory: str | Path) -> Path:
        path = Path(directory) / f"{self.user_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))
        return path

    @classmethod
    def load(cls, user_id: str, directory: str | Path) -> "UserState":
        path = Path(directory) / f"{user_id}.json"
        data = json.loads(path.read_text())
        state = cls(
            user_id=data["user_id"],
            task_types={
                name: TaskBelief(**fields)
                for name, fields in data["task_types"].items()
            },
            overall_alpha=data["overall_alpha"],
            overall_beta=data["overall_beta"],
            pooled_detail=data.get("pooled_detail", dict(DEFAULT_DETAIL_PRIOR)),
            decisions=data["decisions"],
        )
        return state
