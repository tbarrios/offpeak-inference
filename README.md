# OffPeak

**Temporal inference cost arbitrage for AI agents.**

Inference prices rise and fall with grid load — cheap overnight, expensive at evening peak. OffPeak is an open-source harness that lets any agent or LLM app defer non-urgent work to cheap hours, track every dollar saved, and learn how much scheduling flexibility each user actually has.

> Built for **AGI House Hackathon** · November 2026 · MIT licensed

## The problem

AI agents burn tokens at expensive hours. California's wholesale grid cost already varies materially through the day, and inference providers increasingly pass energy and capacity costs through as time-varying $/Mtok pricing. Yet agents often run *everything* immediately — even when the same work can run in the next low-cost grid window.

## What OffPeak does

- **Temporal pricing connector** — reads a provider's time-varying inference price schedule. The default connector uses an official CAISO day-ahead trading-hub snapshot; swap in a provider connector when your provider exposes one.
- **Price-aware scheduling** — for every task, the harness finds the cheapest window before the task's deadline and decides: run now, defer, or ask.
- **Savings ledger** — tracks actual spend, savings vs. running immediately, and savings vs. the daily peak. Honest numbers only.
- **Voices the savings** — agents tell users what was saved and what could be saved: *"I can run this at 2:00 AM for 18% less under the current CAISO schedule."*
- **Learns your flexibility** — every accept/reject of a deferral offer updates a per-category model of your urgency preferences. Once you usually accept, OffPeak auto-defers.
- **Calibrates reports** — directional feedback updates whether each user wants brief, standard, or detailed output for each task type.
- **Works with any agent** — MCP-native, plus a clean Python API. Zero required dependencies.

## How it works

```mermaid
flowchart LR
    A[Agent / LLM app] -->|submit task| H[OffPeak harness]
    H --> P[Pricing connector]
    P -->|price forecast| H
    H -->|run now? defer? ask?| A
    H -->|deferred tasks at cheap windows| A
    H --> L[(savings ledger)]
    H --> F[flexibility learner]
    A -->|accept / reject offers| F
    H -->|savings reports| A
```

## Quickstart

```bash
git clone https://github.com/tbarrios/offpeak-inference.git
cd offpeak-inference
pip install -e .

# Offline end-to-end demo (no LLM, no network, deterministic)
offpeak demo

# See today's price curve and the cheapest upcoming window
offpeak price

# Submit a task for price-aware scheduling
offpeak submit "Research the market for X" --category research --tokens 80000
```

Sample demo output:

```
≈ OffPeak demo — a day in the life of a cost-aware agent ≈

[06:00 PM] Submitting two deep-research tasks at evening peak…
⚡ OffPeak: I can schedule this research task for 02:00 AM at $1.35/Mtok
   — 18% cheaper than running now ($1.65/Mtok). That's ~$0.60 saved on
   2,000,000 tokens under the current CAISO snapshot.
   Want me to defer it?
> (user accepts)
🌙 Scheduled for 02:00 AM at $1.35/Mtok — 18% below the price right now…

[02:00 AM] Cheap window arrived — running deferred tasks…
✓ Ran at 02:00 AM for $1.35/Mtok — saved $0.60 vs running at submit time ($1.65/Mtok).

[08:00 AM] Morning report:
💰 OffPeak savings
   Tasks completed: 2 (2 deferred to cheap windows)
   ...

[06:00 PM] Next evening — submitting another research task…
🌙 Auto-scheduled (you usually accept these) for 02:00 AM …
```

## Use it from any agent (MCP)

OffPeak ships an MCP server, so Codex, Claude, or any MCP-compatible client can use it directly:

```toml
# ~/.codex/config.toml
[mcp_servers.offpeak]
command = "python3"
args = ["-m", "offpeak.mcp_server"]
```

Tools exposed: `get_price_forecast`, `submit_task`, `respond_to_offer`, `get_ready_tasks`, `complete_task`, `get_savings_report`.

A typical agent flow:
1. Agent gets a deep-research question and calls `submit_task`.
2. The harness finds a 3 AM window at 70% off and returns an offer message.
3. The agent relays the offer to the user ("want me to schedule deeper thinking for tonight?").
4. The user accepts → `respond_to_offer`. Overnight, the agent pulls `get_ready_tasks`, runs the work, and reports usage via `complete_task`.
5. The harness keeps the ledger and learns the user's flexibility.

## Python API

```python
from datetime import datetime, timedelta
from offpeak import OffPeakHarness

harness = OffPeakHarness()  # sqlite-backed, persistent

decision = harness.submit(
    "Deep research on grid-aware inference scheduling",
    category="research",
    est_tokens=2_000_000,
    deadline=datetime.now() + timedelta(hours=12),
)
print(decision.message)          # includes the savings offer
harness.respond_to_offer(decision.task_id, accept=True)

# ... at the cheap window (cron, daemon, or your event loop):
for task in harness.ready_tasks():
    output = my_llm(task.prompt)           # your agent runs the work
    harness.complete_task(task.id, actual_tokens=output.usage)

print(harness.savings_report())
```

You can also attach a handler and let the harness execute deferred work itself:

```python
harness.submit(prompt, handler=lambda task: my_llm(task.prompt))
harness.run_due()  # executes any handler-attached tasks whose window arrived
```

## Pricing connectors

Connectors live in `offpeak/connectors/` and implement two methods:

```python
class PricingSource(ABC):
    def price_at(self, at: datetime) -> float: ...      # $/Mtok at a moment
    def forecast(self, start, hours=24) -> list[PricePoint]: ...
```

- **`CaisoDayAheadPricing`** (default) — the hourly average of CAISO's NP15, SP15, and ZP26 trading-hub day-ahead LMPs for the 2026-11-08 operating day. The snapshot's low is `$11.7264/MWh` in the 09:00 interval and high is `$55.5284/MWh` in the 21:00 interval. Use `caiso_pricing_for_date(date.today())` to refresh from the official OASIS API.
- **Inference markup** — modeled inference price is `CAISO LMP × 0.0006 MWh/Mtok × markup`. The default `50×` markup is an explicit, configurable placeholder for provider overhead—not a market quote.
- **`TimeOfDayPricing`** (legacy) — a configurable 24h multiplier curve retained for compatibility and comparisons.

CAISO source: official OASIS `PRC_LMP` day-ahead market report for trading date
2026-11-08, averaged across the NP15, SP15, and ZP26 trading hubs.
- **`CrusoePricing`** (stub) — wire this to Crusoe's temporal inference pricing when available. The integration point is documented in the code.

To add a connector for another provider (OpenRouter, a grid API like WattTime, your own spot-price feed), subclass `PricingSource` and pass it to `OffPeakHarness(pricing=MyPricing())`.

## How savings are computed

Every completed task records three numbers:

| Metric | Meaning |
|---|---|
| `cost_usd` | What you actually paid (`tokens × price at run time`) |
| `savings_vs_now` | What you saved vs. running at submission time — the honest arbitrage number |
| `savings_vs_peak` | What you saved vs. the day's most expensive hour |

Immediate runs record **zero** deferral savings — no inflated numbers.

## Personal preference learning

The `offpeak` package is the operational harness, CLI, and MCP server. The
`offpeak_inference` package adds the simulation and learning engine used to
evaluate demand-response behavior.

- **Urgency flexibility** — a conservative `Beta(1, 2)` belief tracks each
  user's acceptance probability for each task type. Accepted deferrals,
  overrides, direct answers, and wasted immediacy update the posterior.
  Overrides receive 1.5× weight, and new task types inherit a hierarchical
  prior from the rest of the user's behavior.
- **Temporal-choice correctness** — every autonomous decision is scored against
  the user's revealed preference. If recent correctness falls below 60%, the
  policy becomes more conservative and avoids repeating the same mistake.
- **Report calibration** — `right`, `too_much`, and `too_little` feedback moves
  a per-task posterior across brief, standard, and detailed reports. New task
  types inherit a pooled detail preference.
- **Persistent learning** — user state is stored as JSON and loaded on the next
  run, so background decisions continue seamlessly across conversations.

Expected deferral utility is `p × savings − (1 − p) × penalty`, where `p` is the
learned flexibility. The harness defers when the utility is positive, runs
immediately when savings are immaterial, and asks only while its belief is
still uncertain.

## Development

```bash
pip install -e ".[dev,mcp]"
python -m unittest discover -v   # or: pytest
python tests/run_tests.py

# Run the closed-loop learning simulation for three synthetic users
python -m offpeak_inference.demo --conversations 40 --state-dir state
```

## Roadmap

- Real temporal-pricing connectors (Crusoe inference, OpenRouter, grid APIs)
- Carbon-aware scheduling (co-optimize price × grid carbon intensity)
- Deadline-aware priority queues with multiple concurrent windows
- Price-elastic model routing (cheap models at peak, deep models overnight)

## License

MIT — see [LICENSE](LICENSE).
