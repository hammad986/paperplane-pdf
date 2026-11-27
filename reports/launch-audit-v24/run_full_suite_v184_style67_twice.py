"""Run the full local pytest suite twice and retain independent logs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
results = []
for run_number in (1, 2):
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        timeout=1200,
    )
    log_name = f"pytest-v184-style67-shell132-run{run_number}.log"
    (OUT / log_name).write_text(completed.stdout + completed.stderr, encoding="utf-8")
    summary = next((line.strip() for line in reversed(completed.stdout.splitlines())
                    if " passed" in line and " failed" not in line), "summary unavailable")
    results.append({
        "run": run_number,
        "exit_code": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 2),
        "summary": summary,
        "log": log_name,
    })
    if completed.returncode:
        break

report = {
    "command": "python -m pytest -q",
    "runs_sequential": True,
    "production_endpoints_contacted": False,
    "results": results,
}
(OUT / "pytest-v184-style67-shell132-summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
if len(results) != 2 or any(result["exit_code"] for result in results):
    raise SystemExit(1)
