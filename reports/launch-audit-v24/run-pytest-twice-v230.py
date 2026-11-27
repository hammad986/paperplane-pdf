from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "launch-audit-v24"
results = []
for run in (1, 2):
    started = time.monotonic()
    process = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.monotonic() - started
    output = process.stdout + process.stderr
    (REPORTS / f"pytest-v230-run-{run}.log").write_text(output, encoding="utf-8")
    match = re.search(r"(\d+) passed, (\d+) warnings in ([\d.]+)s", output)
    results.append({"run": run, "returncode": process.returncode,
                    "passed": int(match.group(1)) if match else None,
                    "failed": 0 if match else None, "skipped": 0 if match else None,
                    "warnings": int(match.group(2)) if match else None,
                    "duration_seconds": float(match.group(3)) if match else round(elapsed, 2)})
    if process.returncode:
        print(output[-12000:])
        break
summary = {"candidate": "v230 strict exam-photo byte ranges and exact byte display",
           "full_suite": results,
           "exact_source_twice_passed": len(results) == 2 and all(x["returncode"] == 0 for x in results)}
(REPORTS / "pytest-v230-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
if not summary["exact_source_twice_passed"]:
    raise SystemExit(1)
