"""Run the exact v223 source tree's full pytest suite twice and retain evidence."""
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
    log=REPORT/f"pytest-v223-run-{run}.log"
    log.write_text(output,encoding="utf-8")
    summaries=re.findall(r"\d+ passed(?:, [^\n]+)? in [^\n]+",output)
    result={"run":run,"exit_code":completed.returncode,"elapsed_seconds":elapsed,
            "summary":summaries[-1] if summaries else None,"log":log.name}
    results.append(result); print(json.dumps(result))
    if completed.returncode:
        (REPORT/"pytest-v223-summary.json").write_text(json.dumps({"runs":results,"passed_twice":False},indent=2),encoding="utf-8")
        print(output[-12000:]); raise SystemExit(completed.returncode)
(REPORT/"pytest-v223-summary.json").write_text(json.dumps({"runs":results,"passed_twice":len(results)==2 and all(x["exit_code"]==0 for x in results)},indent=2),encoding="utf-8")
