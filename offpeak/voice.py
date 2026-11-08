"""Natural-language voice: offers, confirmations, and savings reports."""

from __future__ import annotations

from datetime import datetime

from offpeak.tasks import Task


def _time(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def _pct(fraction: float) -> str:
    return f"{fraction * 100:.0f}%"


def _money(amount: float) -> str:
    return f"${amount:.2f}"


def offer(
    task: Task,
    best_start: datetime,
    now_price: float,
    best_price: float,
    savings_frac: float,
    savings_usd: float,
) -> str:
    deeper = ""
    if task.est_tokens >= 50_000 and best_price > 0:
        deeper = (
            f" — the same budget buys ~{now_price / best_price:.1f}x deeper"
            " thinking at that hour"
        )
    return (
        f"⚡ OffPeak: I can schedule this {task.category} task for"
        f" {_time(best_start)} at ${best_price:.2f}/Mtok — {_pct(savings_frac)}"
        f" cheaper than running now (${now_price:.2f}/Mtok). That's ~"
        f"{_money(savings_usd)} saved on {task.est_tokens:,} tokens{deeper}."
        " Want me to defer it?"
    )


def deferred(
    task: Task,
    best_start: datetime,
    best_price: float,
    now_price: float,
    savings_frac: float,
    *,
    auto: bool = False,
) -> str:
    lead = "🌙 Auto-scheduled (you usually accept these)" if auto else "🌙 Scheduled"
    return (
        f"{lead} for {_time(best_start)} at ${best_price:.2f}/Mtok —"
        f" {_pct(savings_frac)} below the price right now. I'll run it in the"
        " cheap window and report the savings."
    )


def run_now(now_price: float, reason: str = "prices are already near the day's low") -> str:
    return f"▶ Running now — {reason} (${now_price:.2f}/Mtok)."


def rejected(now_price: float) -> str:
    return (
        f"▶ Got it — running now (${now_price:.2f}/Mtok). Noted: you wanted"
        " this task type sooner. I'll keep asking before deferring these."
    )


def completion(entry: dict, completed_at: datetime) -> str:
    if entry.get("deferred"):
        return (
            f"✓ Ran at {_time(completed_at)} for ${entry['paid_price']:.2f}/Mtok"
            f" — saved {_money(entry['savings_vs_now'])} vs running at submit"
            f" time (${entry['submit_price']:.2f}/Mtok)."
        )
    return f"✓ Ran immediately for ${entry['paid_price']:.2f}/Mtok."


def savings_report(totals: dict, flexibility: dict | None = None) -> str:
    lines = [
        "💰 OffPeak savings",
        f"   Tasks completed: {totals['tasks']}"
        f" ({totals['deferred']} deferred to cheap windows)",
        f"   Spend: {_money(totals['spend_usd'])} · saved vs immediate:"
        f" {_money(totals['savings_vs_now_usd'])}"
        f" ({totals['avg_discount_pct']:.0f}% avg discount)",
        f"   Saved vs daily peak: {_money(totals['savings_vs_peak_usd'])}",
    ]
    if flexibility:
        learned = " · ".join(
            f"{category} {data['accepted']}/{data['offers']}"
            for category, data in list(flexibility.items())[:5]
        )
        lines.append(f"   Flexibility learned: {learned}")
    return "\n".join(lines)
