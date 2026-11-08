"""Post-conversation learning: update beliefs and evaluate temporal choices."""

from __future__ import annotations


FLEXIBLE = "flexible"
IMMEDIATE = "immediate"


def learn_from_ask(state, task_type: str, flexible: bool) -> None:
    """Update beliefs from the user's direct answer to an urgency question."""

    belief = state.get_task_belief(task_type)
    if flexible:
        belief.asked_flexible += 1
        belief.alpha += 1.0
        state.overall_alpha += 0.5
    else:
        belief.asked_inflexible += 1
        belief.beta += 1.0
        state.overall_beta += 0.5


def learn_from_defer(state, task_type: str, accepted: bool) -> bool:
    """Update beliefs after a deferral was proposed.

    Returns the revealed preference ('flexible' if accepted, 'immediate' if
    the user overrode the deferral).
    """

    belief = state.get_task_belief(task_type)
    if accepted:
        belief.defer_accepted += 1
        belief.alpha += 1.0
        state.overall_alpha += 0.5
        return True
    belief.defer_overridden += 1
    belief.beta += 1.5
    state.overall_beta += 0.75
    return False


def learn_from_immediate(
    state, task_type: str, would_have_waited: bool, material: bool = True
) -> bool:
    """Update beliefs after a task ran immediately.

    Returns the revealed preference ('immediate' if the user engaged right
    away, 'flexible' if they signaled they would have waited).
    """

    belief = state.get_task_belief(task_type)
    if would_have_waited and material:
        belief.immediate_waste += 1
        belief.alpha += 0.5
        state.overall_alpha += 0.25
        return True
    belief.immediate_engaged += 1
    belief.beta += 0.25
    state.overall_beta += 0.125
    return False


def evaluate_temporal_choice(
    state,
    task_type: str,
    action,
    revealed_preference: str,
    savings_ratio: float = 1.0,
    material_savings: float = 0.25,
) -> bool:
    """Record whether the autonomous temporal choice matched the user.

    An ASK is never scored as incorrect: by checking with the user it cannot
    mismatch. DEFER is correct when the user revealed flexibility, RUN_NOW is
    correct when the user wanted immediacy. The per-task correctness rate feeds
    back into the policy, making repeated mistakes progressively more
    conservative.
    """

    belief = state.get_task_belief(task_type)
    correct = (
        (action == "defer" and revealed_preference == FLEXIBLE)
        or (action == "run_now" and revealed_preference == IMMEDIATE)
    )
    if action == "run_now" and revealed_preference == FLEXIBLE and savings_ratio < material_savings:
        correct = True
    if action in ("defer", "run_now"):
        belief.decision_total += 1
        if correct:
            belief.decision_correct += 1
    return correct
