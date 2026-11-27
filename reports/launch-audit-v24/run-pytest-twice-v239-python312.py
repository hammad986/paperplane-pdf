from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PYTHON = Path(__import__("tempfile").gettempdir()) / "paperplane-ci-py312-v24" / "Scripts" / "python.exe"
assert PYTHON.is_file(), PYTHON

rows = []
for round_number in (1, 2):
    started = time.monotonic()
    run = subprocess.run(
        [str(PYTHON), "-m", "pytest", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = run.stdout + run.stderr
    (OUT / f"pytest-v239-python312-run-{round_number}.log").write_text(output, encoding="utf-8")
    match = re.search(r"(\d+) passed, (\d+) warnings(?:, (\d+) subtests passed)? in ([\d.]+)s", output)
    failed = re.findall(r"^FAILED (.+)$", output, re.MULTILINE)
    row = {
        "round": round_number,
        "returncode": run.returncode,
        "passed": int(match.group(1)) if match else None,
        "warnings": int(match.group(2)) if match else None,
        "subtests": int(match.group(3) or 0) if match else 0,
        "duration_seconds": float(match.group(4)) if match else round(time.monotonic() - started, 2),
        "failed_tests": failed,
    }
    rows.append(row)
    print(json.dumps(row), flush=True)
    if run.returncode:
        print(output[-8000:], flush=True)
        break

summary = {
    "candidate": "app.js v239 accessibility-label scheduling optimization",
    "runtime": "Python 3.12 deployment test environment",
    "suite": rows,
    "both_runs_passed": len(rows) == 2 and all(row["returncode"] == 0 for row in rows),
}
(OUT / "pytest-v239-python312-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2), flush=True)
if not summary["both_runs_passed"]:
    raise SystemExit(1)
