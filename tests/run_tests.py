"""Dependency-free test suite: `python tests/run_tests.py`."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from offpeak_inference import (
    Action,
    SyntheticUser,
    UserState,
    RIGHT,
    TOO_MUCH,
    TOO_LITTLE,
    choose_report_level,
    decide,
    learn_from_report_feedback,
    learn_from_defer,
    learn_from_ask,
    simulate_conversations,
)
from offpeak_inference.pricing import build_schedule, best_future
from offpeak_inference.state import BetaBelief


def test_beta_belief_math():
    belief = BetaBelief(9, 3)
    assert abs(belief.mean - 0.75) < 1e-9
    assert 0 < belief.variance < 0.05
    assert belief.observations == 9


def test_accepted_deferrals_raise_flexibility():
    state = UserState("u")
    for _ in range(8):
        learn_from_defer(state, "deep_research", accepted=True)
    assert state.get_task_belief("deep_research").belief.mean > 0.75


def test_overrides_flip_policy_to_immediate():
    state = UserState("u")
    schedule = build_schedule(days=2)
    for _ in range(6):
        learn_from_defer(state, "code_review", accepted=False)
    decision = decide("code_review", 20, state, schedule)
    assert decision.action is Action.RUN_NOW


def test_confident_flexible_task_defers_autonomously():
    state = UserState("u")
    schedule = build_schedule(days=2)
    for _ in range(10):
        learn_from_defer(state, "deep_research", accepted=True)
    decision = decide("deep_research", 20, state, schedule)
    assert decision.action is Action.DEFER


def test_uncertain_task_with_big_savings_asks():
    state = UserState("u")
    schedule = build_schedule(days=2)
    decision = decide("deep_research", 20, state, schedule)
    assert decision.action is Action.ASK


def test_new_task_type_inherits_user_prior():
    state = UserState("u")
    for _ in range(10):
        learn_from_defer(state, "deep_research", accepted=True)
    new_belief = state.get_task_belief("brand_new_task")
    pooled = state.overall.mean
    assert abs(new_belief.belief.mean - (0.5 * (1.0 / 3.0) + 0.5 * pooled)) < 1e-9


def test_state_roundtrip(tmp_dir: str = "state_test_tmp"):
    from pathlib import Path
    import shutil

    state = UserState("roundtrip_user")
    learn_from_ask(state, "email_draft", flexible=True)
    path = state.save(tmp_dir)
    loaded = UserState.load("roundtrip_user", tmp_dir)
    assert loaded.task_types["email_draft"].belief.mean == state.task_types["email_draft"].belief.mean
    assert loaded.decisions == state.decisions
    shutil.rmtree(Path(tmp_dir))


def test_simulation_learns_and_saves():
    user = SyntheticUser(
        "founder",
        {"deep_research": 0.9, "code_review": 0.05, "email_draft": 0.8, "summarize": 0.5},
    )
    state = UserState("founder")
    schedule = build_schedule(days=3)
    result = simulate_conversations(user, state, schedule, 60, seed=11)

    assert result.savings_usd > 0
    assert result.autonomous_total >= result.asks
    assert result.correctness_rate >= 0.5

    code_belief = state.get_task_belief("code_review")
    research_belief = state.get_task_belief("deep_research")
    assert code_belief.belief.mean < research_belief.belief.mean


def test_ask_rate_declines_as_beliefs_sharpen():
    from offpeak_inference.simulate import window_metrics

    user = SyntheticUser(
        "student",
        {"deep_research": 0.7, "code_review": 0.3, "email_draft": 0.6, "summarize": 0.85},
    )
    state = UserState("student")
    schedule = build_schedule(days=3)
    result = simulate_conversations(user, state, schedule, 80, seed=3)

    early = window_metrics(result.records[:20])
    late = window_metrics(result.records[-20:])
    assert late["ask_rate"] < early["ask_rate"]


def test_too_much_feedback_moves_level_down():
    state = UserState("u")
    for _ in range(6):
        learn_from_report_feedback(state, "email_draft", "standard", TOO_MUCH)
    assert choose_report_level(state, "email_draft") == "brief"


def test_too_little_feedback_moves_level_up():
    state = UserState("u")
    for _ in range(6):
        learn_from_report_feedback(state, "deep_research", "standard", TOO_LITTLE)
    assert choose_report_level(state, "deep_research") == "detailed"


def test_right_feedback_reinforces_level():
    state = UserState("u")
    for _ in range(4):
        learn_from_report_feedback(state, "summarize", "brief", RIGHT)
    assert choose_report_level(state, "summarize") == "brief"


def test_new_task_inherits_pooled_detail_preference():
    state = UserState("u")
    for _ in range(8):
        learn_from_report_feedback(state, "email_draft", "standard", TOO_MUCH)
    new_belief = state.get_task_belief("brand_new_task")
    assert new_belief.detail_counts["brief"] > 1.0
    assert new_belief.detail_posterior["brief"] > new_belief.detail_posterior["detailed"]


def test_report_calibration_converges_to_true_preferences():
    user = SyntheticUser(
        "detail_user",
        {"deep_research": 0.9, "code_review": 0.1, "email_draft": 0.8, "summarize": 0.5},
        {
            "deep_research": "detailed",
            "code_review": "brief",
            "email_draft": "brief",
            "summarize": "standard",
        },
    )
    state = UserState("detail_user")
    schedule = build_schedule(days=3)
    result = simulate_conversations(user, state, schedule, 80, seed=5)

    from offpeak_inference.simulate import window_metrics

    early = window_metrics(result.records[:20])
    late = window_metrics(result.records[-20:])
    assert late["report_calibration"] > early["report_calibration"]
    assert result.report_calibration_rate > 0.5
    research = state.get_task_belief("deep_research")
    code = state.get_task_belief("code_review")
    assert research.detail_map == "detailed"
    assert code.detail_map == "brief"


def test_demo_persists_and_continues_learning_across_runs():
    import tempfile
    import shutil

    from offpeak_inference.demo import run

    state_dir = tempfile.mkdtemp()
    user = SyntheticUser("persisted_user", {"deep_research": 0.9, "code_review": 0.1})
    try:
        first_state, _ = run(user, 4, seed=1, state_dir=state_dir, verbose=False)
        second_state, _ = run(user, 4, seed=2, state_dir=state_dir, verbose=False)
        first_observations = sum(belief.observations for belief in first_state.task_types.values())
        second_observations = sum(belief.observations for belief in second_state.task_types.values())
        assert second_observations > first_observations
        assert len(second_state.decisions) == len(first_state.decisions) * 2
    finally:
        shutil.rmtree(state_dir)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as error:
            failures += 1
            print(f"FAIL {test.__name__}: {error}")
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    sys.exit(1 if failures else 0)
