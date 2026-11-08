"""Runnable demo: the harness learning three distinct users over time."""

from __future__ import annotations

import argparse
from pathlib import Path

from .pricing import build_schedule
from .simulate import SyntheticUser, SimulationResult, simulate_conversations, window_metrics
from .state import UserState


USERS = [
    SyntheticUser(
        "startup_founder",
        {"deep_research": 0.9, "code_review": 0.05, "email_draft": 0.8, "summarize": 0.5},
        {
            "deep_research": "detailed",
            "code_review": "brief",
            "email_draft": "brief",
            "summarize": "standard",
        },
    ),
    SyntheticUser(
        "oncall_engineer",
        {"deep_research": 0.2, "code_review": 0.05, "email_draft": 0.3, "summarize": 0.4},
        {
            "deep_research": "brief",
            "code_review": "brief",
            "email_draft": "brief",
            "summarize": "brief",
        },
    ),
    SyntheticUser(
        "evening_student",
        {"deep_research": 0.7, "code_review": 0.3, "email_draft": 0.6, "summarize": 0.85},
        {
            "deep_research": "detailed",
            "code_review": "standard",
            "email_draft": "standard",
            "summarize": "standard",
        },
    ),
]


def run(user: SyntheticUser, n_conversations: int, seed: int, state_dir: str | None, verbose: bool) -> tuple[UserState, SimulationResult]:
    state_path = Path(state_dir) / f"{user.user_id}.json" if state_dir else None
    if state_path and state_path.exists():
        state = UserState.load(user.user_id, state_dir)
    else:
        state = UserState(user.user_id)
    schedule = build_schedule(days=3)
    result = simulate_conversations(
        user, state, schedule, n_conversations, seed=seed, log_prefix=f"[{user.user_id}]", verbose=verbose
    )
    if state_dir:
        path = state.save(state_dir)
        print(f"[{user.user_id}] state saved -> {path}")
    return state, result


def main() -> None:
    parser = argparse.ArgumentParser(description="Off-Peak Inference learning demo")
    parser.add_argument("--conversations", type=int, default=40)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    for index, user in enumerate(USERS):
        state, result = run(user, args.conversations, args.seed + index, args.state_dir, args.verbose)
        early = window_metrics(result.records[: max(4, args.conversations // 4)])
        late = window_metrics(result.records[-max(4, args.conversations // 4):])

        print(f"\n=== {user.user_id} ({args.conversations} conversations) ===")
        print(f"true flexibility: {user.true_flexibility}")
        print(f"true detail:      {user.true_detail}")
        print("learned beliefs:")
        for task_type, belief in sorted(state.task_types.items()):
            print(f"  {task_type:<13} p_flexible={belief.belief.mean:.2f}  obs={int(belief.observations):02d}  timing_correct={belief.correctness_rate}  detail={belief.detail_map}  right_feedback={belief.right_feedback_rate}")
        print(f"savings: ${result.savings_usd:.2f} (vs ${result.baseline_savings_usd:.2f} theoretical max)")
        print(f"early window: ask_rate={early['ask_rate']:.0%} override_rate={early['override_rate']:.0%} correctness={early['autonomous_correctness']}")
        print(f"late  window: ask_rate={late['ask_rate']:.0%} override_rate={late['override_rate']:.0%} correctness={late['autonomous_correctness']}")
        print(f"report calibration: early={early['report_calibration']:.0%} late={late['report_calibration']:.0%} overall={result.report_calibration_rate:.0%} (avg level error {result.level_error / result.report_total:.2f})")
        print(f"overall: asks={result.asks} defers={result.defers} ({result.defers_accepted} accepted / {result.defers_overridden} overridden) run_now={result.run_now}")


if __name__ == "__main__":
    main()
