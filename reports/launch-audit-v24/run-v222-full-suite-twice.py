"""Run the exact v221 source tree's full pytest suite twice and retain evidence."""
from __future__ import annotations
import json, re, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
REPORT=Path(__file__).resolve().parent
results=[]
for run in (1,2):
    started=time.monotonic()
    completed=subprocess.run([sys.executable,"-m","pytest","-q"],cwd=ROOT,text=True,capture_output=True)
    elapsed=round(time.monotonic()-started,2)
    output=completed.stdout+completed.stderr
    log=REPORT/f"pytest-v222-run-{run}.log"
    log.write_text(output,encoding="utf-8")
    summary=re.findall(r"\d+ passed(?:, [^\n]+)? in [^\n]+",output)
    results.append({"run":run,"exit_code":completed.returncode,"elapsed_seconds":elapsed,
                    "summary":summary[-1] if summary else None,"log":log.name})
    print(json.dumps(results[-1]))
    if completed.returncode:
        (REPORT/"pytest-v222-summary.json").write_text(json.dumps({"runs":results,"passed_twice":False},indent=2),encoding="utf-8")
        print(output[-12000:])
        raise SystemExit(completed.returncode)
(REPORT/"pytest-v222-summary.json").write_text(json.dumps({"runs":results,"passed_twice":len(results)==2 and all(r["exit_code"]==0 for r in results)},indent=2),encoding="utf-8")
