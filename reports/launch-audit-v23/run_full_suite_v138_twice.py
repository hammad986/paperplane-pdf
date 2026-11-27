from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUNNER = ROOT / "reports" / "launch-audit-v10" / "run_full_suite_twice.py"
spec = importlib.util.spec_from_file_location("suite_safety_helpers", RUNNER)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)


def main() -> int:
    runs = []
    for number in (1, 2):
        env = helpers.safe_environment()
        env["PAPERPLANE_DATA_DIR"] = str(Path(os.environ.get("TEMP", ".")) / f"paperplane-v138-suite-run-{number}")
        started = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"], cwd=ROOT, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        output = helpers.sanitize_output(result.stdout + result.stderr)
        log = OUT / f"pytest-current-v138-run{number}.log"
        log.write_text(output, encoding="utf-8")
        summary = next((line.strip() for line in reversed(output.splitlines()) if " passed" in line), "missing pytest summary")
        runs.append({
            "run": number,
            "exit_code": result.returncode,
            "duration_seconds": round(time.perf_counter() - started, 2),
            "summary": summary,
            "log": log.name,
        })
    evidence = {
        "command": "python -m pytest -q",
        "runs_sequential": True,
        "dotenv_disabled": True,
        "credential_environment_removed": True,
        "production_endpoints_contacted": False,
        "runs": runs,
    }
    (OUT / "pytest-current-v138-summary.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0 if all(run["exit_code"] == 0 for run in runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())




