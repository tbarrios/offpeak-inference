"""Example: run deferred tasks through the Codex CLI at cheap hours.

The handler shells out to ``codex exec``, so any prompt you defer with
OffPeak runs automatically when its cheap window arrives.
"""

import subprocess


def codex_exec_handler(task) -> dict:
    result = subprocess.run(
        ["codex", "exec", task.prompt],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    return {"output": result.stdout, "usage": {}}


if __name__ == "__main__":
    import os
    import tempfile
    from datetime import datetime, timedelta

    from offpeak.harness import OffPeakHarness

    with tempfile.TemporaryDirectory() as tmp:
        harness = OffPeakHarness(db_path=os.path.join(tmp, "demo.db"))
        decision = harness.submit(
            "Research the state of grid-aware inference scheduling and write a summary.",
            category="research",
            est_tokens=80_000,
            deadline=datetime.now() + timedelta(hours=12),
            handler=codex_exec_handler,
        )
        print(decision.message)
        # When the cheap window arrives (e.g. from cron):
        for entry in harness.run_due():
            print(entry.get("message", entry))
