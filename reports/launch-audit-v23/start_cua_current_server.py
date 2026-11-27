from __future__ import annotations
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

temporary = tempfile.TemporaryDirectory(prefix="paperplane-cua-current-")
app = None
try:
    app, base, _ = helper.start_server(Path(temporary.name) / "data")
    print(base, flush=True)
    app.wait()
finally:
    if app and app.poll() is None:
        app.terminate()
        app.wait(timeout=10)
    temporary.cleanup()
