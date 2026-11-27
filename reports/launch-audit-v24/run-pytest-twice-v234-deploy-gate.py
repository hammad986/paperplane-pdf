from __future__ import annotations
import json, re, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
results = []
for number in (1, 2):
    start = time.monotonic()
    process = subprocess.run([sys.executable, '-m', 'pytest', '-q'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    elapsed = time.monotonic() - start
    output = process.stdout + process.stderr
    (OUT / f'pytest-v234-deploy-gate-round{number}.log').write_text(output, encoding='utf-8')
    match = re.search(r'(\d+) passed, (\d+) warnings(?:, (\d+) subtests passed)? in ([\d.]+)s', output)
    failed = re.findall(r'^FAILED (.+)$', output, re.MULTILINE)
    row = {'round': number, 'returncode': process.returncode, 'passed': int(match.group(1)) if match else None,
           'warnings': int(match.group(2)) if match else None, 'subtests': int(match.group(3) or 0) if match else 0,
           'duration_seconds': float(match.group(4)) if match else round(elapsed, 2), 'failed_tests': failed}
    results.append(row)
    print(json.dumps(row), flush=True)
    if process.returncode:
        print(output[-8000:], flush=True)
        break
summary = {'candidate': 'current source after mobile result clearance and test-gated, host-pinned deploy workflow',
           'suite': results, 'both_runs_passed': len(results) == 2 and all(row['returncode'] == 0 for row in results)}
(OUT / 'pytest-v234-deploy-gate-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2), flush=True)
if not summary['both_runs_passed']:
    raise SystemExit(1)
