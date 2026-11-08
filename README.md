# Off-Peak Inference — Demand-Side Flexibility Harness

An open-source harness that makes AI agent workloads *flexible*: it learns each
user's willingness to let tasks run later, then schedules non-urgent compute in
cheaper, lower-carbon windows of the grid — without breaking the experience of
users who need answers immediately.

## What it does

1. **Decides** for every task: run now, defer to a cheaper hour, or ask the user
   (only while beliefs are still uncertain).
2. **Learns the user** via Bayesian updating: accepted deferrals, overrides,
   direct answers, and wasted immediacy all update per-task-type beliefs about
   that person's flexibility.
3. **Learns its own decisions**: after every conversation it scores whether
   the temporal choice (immediate vs. deferred) matched the user's revealed
   preference, and feeds that correctness rate back into the policy so repeated
   mistakes make it more conservative.
4. **Calibrates reports**: after each report, directional feedback (`right`,
   `too_much`, or `too_little`) updates a per-user, per-task detail preference.
   The next report defaults to the learned level without asking an extra
   question.
5. **Persists per-user state** so learning continues seamlessly across runs.
6. **Reports savings** against a duck-curve electricity price schedule.

## Design

### Belief model (per user, per task type)

- `Beta(α, β)` posterior over "probability the user accepts deferral".
- Conservative prior `Beta(1, 2)`: assume immediacy until shown otherwise.
- Overrides count 1.5× — a user overriding a deferral is strong evidence.
- **Hierarchical prior**: a brand-new task type inherits a blend of the base
  prior and everything already learned about this user, so the harness learns
  people, not just categories.

### Decision policy

Expected utility of deferring, for learned flexibility `p` and savings ratio `s`:

```
EU(defer) = p·s − (1−p)·penalty
```

- If `EU > 0` and the belief is confident → **defer autonomously**.
- If savings are small → **run now** (never pester users for pennies).
- If savings are material but the belief is uncertain → **ask once**, then stop
  asking as evidence accumulates. This is what makes the harness fade into the
  background.
- The penalty scales up when the recent temporal-choice correctness rate for a
  task type falls below 60%: mistakes make the agent more careful.

### Temporal-choice correctness

After each conversation the harness evaluates its own timing choice against
the user's revealed preference:

| Agent action | User signal | Scored as |
|---|---|---|
| Deferred | accepted | correct |
| Deferred | overrode ("I need it now") | incorrect |
| Ran now | user engaged immediately | correct |
| Ran now | user signaled "could have waited" | incorrect |
| Asked | any answer | not scored (no autonomous mistake possible) |

### Report calibration

The harness tracks a posterior over three detail levels: brief, standard, and
detailed. `right` reinforces the level just used, `too_much` shifts toward a
briefer level, and `too_little` shifts toward a more detailed level. New task
types inherit a pooled detail prior from the user's other tasks. The
simulation measures exact report calibration against synthetic users' hidden
preferences; production deployments learn directly from real feedback.

## Quick start

```bash
python -m offpeak_inference.demo --conversations 40 --state-dir state
python tests/run_tests.py
```

The demo runs three synthetic users with distinct hidden preferences and shows
beliefs converging, ask rates falling, override rates falling, report
calibration improving, and savings accruing.

## Mapping to the judging criteria

1. **Agentic loop & functionality** — decide → observe → learn → re-decide is
   fully closed; the simulation shows behavior changing across runs.
2. **Energy innovation & simulation** — inference is treated as a dispatchable
   load against a duck-curve price schedule; savings are measured in dollars
   via a placeholder tokens→MWh efficiency.
3. **Evaluation & learning** — objective metrics: ask rate, override rate,
   autonomous correctness rate, report calibration, and savings vs.
   theoretical maximum.
4. **Technical execution** — dependency-free Python, persisted state, runnable
   demo, test suite.
5. **Theme alignment** — demand response for AI: flexible compute demand that
   follows cheap, low-carbon supply.

## Limitations (for an honest demo)

- Price schedule is a placeholder duck curve; production would use live CAISO /
  Electricity Maps signals.
- The tokens→MWh efficiency constant is a placeholder until measured.
- Correctness and calibration signals are simulated; a live deployment derives
  them from overrides, explicit feedback, and engagement telemetry.
