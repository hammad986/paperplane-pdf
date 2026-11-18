"""Run the mobile PWA browser checks against an isolated current-source app."""
import os
from pathlib import Path
import runpy
import socket
import sys
import time
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id357-local-source-") as temp:
    app, base, _ = helper.start_server(Path(temp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local PWA verification app did not start.")
        os.environ["PAPERPLANE_TEST_BASE"] = base
        runpy.run_path(str(ROOT / "reports" / "launch-audit-v23" / "browser_id357_mobile_scan_pwa.py"), run_name="__main__")
    finally:
        app.terminate()
        try:
            app.wait(timeout=8)
        except Exception:
            app.kill()
