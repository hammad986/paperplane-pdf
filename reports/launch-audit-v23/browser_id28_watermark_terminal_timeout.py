"""Chromium regression for bounded server Watermark job failures."""
from __future__ import annotations
import base64
import json
import os
import psutil
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v10"))
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v23"))
import run_full_suite_twice as suite_helpers
import watermark_timeout_test_worker

def main() -> None:
    env = suite_helpers.safe_environment()
    with TemporaryDirectory(prefix="paperplane-id28-timeout-browser-") as temporary:
        env["PAPERPLANE_DATA_DIR"] = str(Path(temporary) / "data")
        env["PAPERPLANE_ADMIN_KEY"] = secrets.token_urlsafe(32)
        env["PAPERPLANE_ADMIN_CODE"] = secrets.token_urlsafe(24)
        os.environ.clear()
        os.environ.update(env)
        import server
        import uvicorn

        # Force a controlled child to start, hold the watermark file open, and
        # remain blocked beyond a short test deadline.
        server.WATERMARK_TIMEOUT_SECONDS = 1.5
        original_runner = server._run_watermark_worker_with_timeout
        def controlled_worker(*args, **kwargs):
            kwargs["worker_target"] = watermark_timeout_test_worker.block_after_start
            return original_runner(*args, **kwargs)
        server._run_watermark_worker_with_timeout = controlled_worker
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        uvicorn_server = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="error"))
        uvicorn_server.install_signal_handlers = lambda: None
        server_thread = threading.Thread(target=uvicorn_server.run, name="paperplane-id28-test-server", daemon=True)
        server_thread.start()
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("controlled local server did not start")
            source = Path(temporary) / "source.pdf"
            with fitz.open() as doc:
                doc.new_page().insert_text((72, 72), "ID28-TIMEOUT-SOURCE")
                doc.save(source)
            source_b64 = base64.b64encode(source.read_bytes()).decode("ascii")
            errors = []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base, wait_until="domcontentloaded", timeout=20_000)
                assert response and response.status == 200
                outcome = page.evaluate("""async sourceB64 => {
                  const bytes=Uint8Array.from(atob(sourceB64), c=>c.charCodeAt(0));
                  const body=new FormData(); body.append('operation','watermark');
                  body.append('options',JSON.stringify({watermark_image_data:'data:image/png;base64,'+btoa('dGVzdA==')}));
                  body.append('files',new Blob([bytes],{type:'application/pdf'}),'source.pdf');
                  const submitted=await fetch('/api/jobs',{method:'POST',body});
                  const submission=await submitted.json();
                  const until=Date.now()+8000; let status;
                  while(Date.now()<until){
                    status=await (await fetch(submission.status_url)).json();
                    if(['failed','completed','cancelled'].includes(status.status)) break;
                    await new Promise(resolve=>setTimeout(resolve,50));
                  }
                  return {submitStatus:submitted.status, jobId:submission.job_id, status:status?.status,
                    error:status?.error, outputName:status?.output_name||null};
                }""", source_b64)
                assert outcome["submitStatus"] == 202 and outcome["status"] == "failed", outcome
                assert "timed out" in outcome["error"].lower(), outcome
                assert "worker was stopped" in outcome["error"].lower(), outcome
                assert outcome["outputName"] is None, outcome
                job_dir = server.JOBS / outcome["jobId"]
                marker = job_dir / ".watermark-worker-started"
                assert marker.is_file(), "controlled child never entered its work function"
                worker_marker = json.loads(marker.read_text(encoding="utf-8"))
                worker_pid = int(worker_marker["pid"])
                try:
                    worker_process = psutil.Process(worker_pid)
                    worker_still_alive = worker_process.is_running() and worker_process.status() != psutil.STATUS_ZOMBIE \
                        and abs(worker_process.create_time() - float(worker_marker["created"])) < 0.01
                except psutil.NoSuchProcess:
                    worker_still_alive = False
                assert not worker_still_alive, f"timed-out watermark child {worker_pid} is still alive"
                assert not list(job_dir.glob("wm_*.png")), "temporary watermark image survived worker termination"
                assert not errors, errors
                browser.close()
            result = {"runtime":"isolated local Uvicorn + Chromium", "timeout_seconds":1.5,
                      "real_watermark_child_process_started_and_stopped":True,
                      "worker_pid":worker_pid,"worker_alive_after_timeout":worker_still_alive,
                      "temporary_image_removed":True,"browser_job":outcome,
                      "page_errors":errors, "passed":True}
            print(json.dumps(result, indent=2))
            (ROOT / "reports" / "launch-audit-v23" / "browser-id28-watermark-terminal-timeout.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        finally:
            uvicorn_server.should_exit = True
            server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
