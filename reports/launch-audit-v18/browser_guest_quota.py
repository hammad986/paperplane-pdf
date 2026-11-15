"""Prove guest operation quotas are isolated between real browser profiles."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = r'''
import persistence, server, uvicorn
persistence.init_db()
server.executor.submit = lambda *_args, **_kwargs: None
uvicorn.run(server.app, host="127.0.0.1", port=int(__import__("os").environ["PAPERPLANE_PORT"]), log_level="error")
'''


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="paperplane-guest-quota-v18-") as temp:
        directory = Path(temp)
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("PAPERPLANE_", "CASHFREE_", "OPENAI_", "GEMINI_", "BLUESMINDS_", "ADMIN_"))}
        env.update(PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_ENV="development",
                   PAPERPLANE_DATA_DIR=str(directory / "data"), PAPERPLANE_PORT=str(port),
                   PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(64),
                   PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(32))
        app = subprocess.Popen([sys.executable, "-c", BOOTSTRAP], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Isolated quota test server exited")
                    time.sleep(.1)
            else:
                raise RuntimeError("Isolated quota test server did not start")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                results = []
                contexts = [browser.new_context(), browser.new_context()]
                pages = [context.new_page() for context in contexts]
                for page in pages:
                    page.goto(base + "/", wait_until="domcontentloaded")
                    cookie = next(item for item in page.context.cookies(base)
                                  if item["name"] == "paperplane_guest_quota")
                    assert cookie["httpOnly"] and cookie["value"]
                cookies = [[item["value"] for item in context.cookies(base)
                            if item["name"] == "paperplane_guest_quota"][0] for context in contexts]
                assert cookies[0] != cookies[1]

                first_usage = None
                for index in (0, 0, 1):
                    first_usage = pages[index].evaluate("""async () => {
                      const body = new FormData();
                      body.append('operation', 'html_to_pdf');
                      body.append('options', JSON.stringify({url: 'https://example.com'}));
                      const submitted = await fetch('/api/jobs', {method: 'POST', body});
                      const queued = submitted.status;
                      if (queued !== 202) return {queued, error: await submitted.text()};
                      return {queued, ...(await (await fetch('/api/billing/status')).json())};
                    }""")
                    assert first_usage["queued"] == 202, first_usage
                    results.append({"profile": "A" if index == 0 else "B",
                                    "usage_after_job": first_usage["usage_today"],
                                    "remaining": first_usage["remaining_today"]})
                assert results[0]["usage_after_job"] == 1
                assert results[1]["usage_after_job"] == 2
                assert results[2]["usage_after_job"] == 1
                output = ROOT / "reports" / "launch-audit-v18" / "browser-guest-quota.json"
                output.write_text(json.dumps({"results": results, "profiles": 2,
                                              "signed_http_only_cookies": True}, indent=2), encoding="utf-8")
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=10)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait()
    print(json.dumps({"browser_profiles": 2, "quota_runs": 3,
                      "evidence": "reports/launch-audit-v18/browser-guest-quota.json"}))


if __name__ == "__main__":
    main()
