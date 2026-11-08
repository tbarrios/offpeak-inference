"""Report calibration: learn how much detail each user wants.

The harness treats report length as a learned preference. After every report
the user's signal -- too much, too little, or right -- updates a per-task-type
belief over three levels (brief, standard, detailed). Reports then default to
the user's learned level with no extra questions, so calibration fades into
the background.
"""

from __future__ import annotations

from .state import (
    BRIEF,
    DETAILED,
    REPORT_LEVELS,
    STANDARD,
    UserState,
)


RIGHT = "right"
TOO_MUCH = "too_much"
TOO_LITTLE = "too_little"
FEEDBACKS = (RIGHT, TOO_MUCH, TOO_LITTLE)

LEVEL_INDEX = {BRIEF: 0, STANDARD: 1, DETAILED: 2}


def lower_level(level: str) -> str:
    return REPORT_LEVELS[max(0, LEVEL_INDEX[level] - 1)]


def higher_level(level: str) -> str:
    return REPORT_LEVELS[min(len(REPORT_LEVELS) - 1, LEVEL_INDEX[level] + 1)]


def choose_report_level(
    state: UserState,
    task_type: str,
    confidence: float = 0.55,
    min_observations: float = 2.0,
) -> str:
    """Pick the detail level for this user's next report.

    New task types inherit a hierarchical prior from everything already known
    about the user, so a person who consistently wants brief emails gets brief
    reports in brand-new task categories too.
    """

    belief = state.get_task_belief(task_type)
    if (
        belief.detail_observations >= min_observations
        and belief.detail_posterior[belief.detail_map] >= confidence
    ):
        return belief.detail_map
    return STANDARD


def learn_from_report_feedback(
    state: UserState,
    task_type: str,
    level_used: str,
    feedback: str,
) -> None:
    """Update detail beliefs from the user's reaction to a report.

    Directional feedback moves mass toward the neighboring level: 'too much'
    shifts toward the next level down, 'too little' toward the next level up,
    and 'right' reinforces the level that was used.
    """

    if feedback not in FEEDBACKS:
        raise ValueError(f"feedback must be one of {FEEDBACKS}, got {feedback!r}")
    if level_used not in LEVEL_INDEX:
        raise ValueError(f"level must be one of {REPORT_LEVELS}, got {level_used!r}")

    if feedback == RIGHT:
        target = level_used
    elif feedback == TOO_MUCH:
        target = lower_level(level_used)
    else:
        target = higher_level(level_used)

    belief = state.get_task_belief(task_type)
    belief.detail_counts[target] = belief.detail_counts.get(target, 0.0) + 1.0
    belief.report_total += 1
    if feedback == RIGHT:
        belief.report_right += 1

    state.pooled_detail[target] = state.pooled_detail.get(target, 0.0) + 0.5


def evaluate_report_calibration(level_used: str, desired_level: str) -> bool:
    """Score a report against the user's true preferred level.

    Used by the simulation to measure calibration; production deployments
    learn directly from feedback instead.
    """

    return level_used == desired_level


def sample_report(level: str, task_type: str) -> str:
    """Demo-sized example of what each report level produces."""

    label = task_type.replace("_", " ").title()
    if level == BRIEF:
        return f"{label}: done. Headline result in one sentence. Ask if you want more."
    if level == DETAILED:
        return (
            f"{label} — full report: executive summary, findings, analysis, "
            "methodology, caveats, and recommended next steps."
        )
    return f"{label} — answer plus the three key facts and one recommended next step."
