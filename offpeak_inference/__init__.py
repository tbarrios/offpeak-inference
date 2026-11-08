"""Off-Peak Inference: a demand-side inference flexibility harness."""

from .state import PRIOR_ALPHA, PRIOR_BETA, BetaBelief, TaskBelief, UserState
from .policy import Action, Decision, decide
from .learner import (
    learn_from_ask,
    learn_from_defer,
    learn_from_immediate,
    evaluate_temporal_choice,
)
from .simulate import SyntheticUser, simulate_conversations
from .reporting import (
    BRIEF,
    DETAILED,
    STANDARD,
    RIGHT,
    TOO_MUCH,
    TOO_LITTLE,
    choose_report_level,
    learn_from_report_feedback,
    evaluate_report_calibration,
)

__all__ = [
    "PRIOR_ALPHA",
    "PRIOR_BETA",
    "BetaBelief",
    "TaskBelief",
    "UserState",
    "Action",
    "Decision",
    "decide",
    "learn_from_ask",
    "learn_from_defer",
    "learn_from_immediate",
    "evaluate_temporal_choice",
    "SyntheticUser",
    "simulate_conversations",
    "BRIEF",
    "DETAILED",
    "STANDARD",
    "RIGHT",
    "TOO_MUCH",
    "TOO_LITTLE",
    "choose_report_level",
    "learn_from_report_feedback",
    "evaluate_report_calibration",
]
