"""Command-line interface: price charts, task submission, and savings reports."""

from __future__ import annotations

import argparse
import os
import tempfile
from datetime import datetime, timedelta

from offpeak.clock import SimClock
from offpeak.harness import OffPeakHarness


def _harness(args: argparse.Namespace) -> OffPeakHarness:
    return OffPeakHarness(db_path=args.db)


def cmd_price(args: argparse.Namespace) -> None:
    summary = _harness(args).forecast_summary(args.hours)
    now_price = summary["price_now_per_mtok"]
    print(f"Prices are $/Mtok. Now: ${now_price:.2f} · peak: ${summary['peak_per_mtok']:.2f}")
    if summary["best_window"]:
        best = summary["best_window"]
        best_time = datetime.fromisoformat(best["start"])
        print(f"Best upcoming window: {best_time:%I:%M %p} at ${best['price_per_mtok']:.2f}")
    print()
    top = max(p["price_per_mtok"] for p in summary["points"])
    best_price = summary["best_window"]["price_per_mtok"] if summary["best_window"] else None
    for point in summary["points"]:
        at = datetime.fromisoformat(point["at"])
        bar = "█" * max(1, int(point["price_per_mtok"] / top * 28))
        marker = ""
        if best_price is not None and abs(point["price_per_mtok"] - best_price) < 1e-9:
            marker = "  ★ cheapest"
        elif abs(point["price_per_mtok"] - summary["peak_per_mtok"]) < 1e-9:
            marker = "  ▲ peak"
        print(f"{at:%I:%M %p}  ${point['price_per_mtok']:.2f} {bar}{marker}")


def cmd_submit(args: argparse.Namespace) -> None:
    harness = _harness(args)
    deadline = datetime.now() + timedelta(hours=args.deadline_hours)
    decision = harness.submit(
        args.prompt,
        category=args.category,
        est_tokens=args.tokens,
        deadline=deadline,
        duration_min=args.duration_min,
    )
    print(decision.message)
    print(f"(task id: {decision.task_id})")
    if decision.action != "ask_user":
        return
    if args.yes:
        print(harness.respond_to_offer(decision.task_id, True))
    elif args.no:
        print(harness.respond_to_offer(decision.task_id, False))
    else:
        answer = input("Defer? [y/N] ").strip().lower()
        print(harness.respond_to_offer(decision.task_id, answer in ("y", "yes")))


def cmd_run_due(args: argparse.Namespace) -> None:
    harness = _harness(args)
    ready = harness.ready_tasks()
    if not ready:
        print("No deferred tasks are due yet.")
        return
    for task in ready:
        # Without an attached handler, simulate completion for accounting demos.
        print(harness.complete_task(task.id)["message"])


def cmd_savings(args: argparse.Namespace) -> None:
    print(_harness(args).savings_report())


def cmd_tasks(args: argparse.Namespace) -> None:
    tasks = _harness(args).tasks(args.status)
    if not tasks:
        print("No tasks.")
        return
    for task in tasks:
        scheduled = f" → {task.scheduled_at:%I:%M %p}" if task.scheduled_at else ""
        print(f"{task.id}  {task.status:8}  {task.category:12} {task.est_tokens:>8,} tok{scheduled}")


def cmd_demo(_: argparse.Namespace) -> None:
    clock = SimClock(datetime.now().replace(hour=18, minute=0, second=0, microsecond=0))
    with tempfile.TemporaryDirectory() as tmp:
        harness = OffPeakHarness(db_path=os.path.join(tmp, "demo.db"), clock=clock)
        print("≈ OffPeak demo — a day in the life of a cost-aware agent ≈")
        print(f"\n[{clock.now():%I:%M %p}] Submitting two deep-research tasks at evening peak…")
        for label in (
            "Research the market for grid-aware inference scheduling",
            "Draft a deep comparison of inference deferral policies",
        ):
            decision = harness.submit(
                label,
                category="research",
                est_tokens=2_000_000,
                deadline=clock.now() + timedelta(hours=12),
            )
            print(decision.message)
            print("> (user accepts)")
            print(harness.respond_to_offer(decision.task_id, True))
            print()
        clock.advance(hours=9)
        print(f"[{clock.now():%I:%M %p}] Cheap window arrived — running deferred tasks…")
        for task in harness.ready_tasks():
            print(harness.complete_task(task.id)["message"])
        clock.advance(hours=5)
        print(f"\n[{clock.now():%I:%M %p}] Morning report:")
        print(harness.savings_report())
        clock.advance(hours=10)
        print(f"\n[{clock.now():%I:%M %p}] Next evening — submitting another research task…")
        decision = harness.submit(
            "Outline a technical blog post about temporal inference pricing",
            category="research",
            est_tokens=1_500_000,
            deadline=clock.now() + timedelta(hours=12),
        )
        print(decision.message)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="offpeak",
        description="Temporal inference cost arbitrage for AI agents.",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--db",
        default=os.environ.get("OFFPEAK_DB", "offpeak.db"),
        help="SQLite database path (default: $OFFPEAK_DB or ./offpeak.db)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("price", parents=[common], help="Show the price forecast and best windows")
    p.add_argument("--hours", type=int, default=24)
    p.set_defaults(func=cmd_price)

    p = sub.add_parser("submit", parents=[common], help="Submit a task for scheduling")
    p.add_argument("prompt")
    p.add_argument("--category", default="general")
    p.add_argument("--tokens", type=int, default=10_000)
    p.add_argument("--deadline-hours", type=float, default=24)
    p.add_argument("--duration-min", type=int, default=5)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--yes", action="store_true", help="Auto-accept any deferral offer")
    group.add_argument("--no", action="store_true", help="Auto-reject any deferral offer")
    p.set_defaults(func=cmd_submit)

    p = sub.add_parser("run-due", parents=[common], help="Run tasks whose cheap window arrived")
    p.set_defaults(func=cmd_run_due)

    p = sub.add_parser("savings", parents=[common], help="Show the savings report")
    p.set_defaults(func=cmd_savings)

    p = sub.add_parser("tasks", parents=[common], help="List tasks")
    p.add_argument("--status", default=None)
    p.set_defaults(func=cmd_tasks)

    p = sub.add_parser("demo", parents=[common], help="Run an offline end-to-end demo")
    p.set_defaults(func=cmd_demo)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

