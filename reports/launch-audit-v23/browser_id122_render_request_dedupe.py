"""Browser regression for reusing pending Studio renders per page."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix="paperplane-id122-render-dedupe-") as temp_name:
    temp = Path(temp_name)
    app, base, _ = helper.start_server(temp / "data")
    try:
        for _ in range(150):
            try:
                with urlopen(base + "/api/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("isolated local app did not become ready")

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            response = page.goto(base + "/studio", wait_until="domcontentloaded")
            assert response and response.status == 200
            page.wait_for_function("typeof window.renderStudioPage === 'function' && window.state?.studio?.pageRenderQueues instanceof Map")
            result = page.evaluate("""async () => {
              const original = window.renderStudioPageNow;
              const queue = window.state.studio.pageRenderQueues;
              let calls = 0;
              window.renderStudioPageNow = async () => {
                calls += 1;
                await new Promise(resolve => setTimeout(resolve, 30));
                return true;
              };
              queue.clear();
              const first = window.renderStudioPage(999, { priority: true });
              const duplicate = window.renderStudioPage(999);
              const duplicateResults = await Promise.all([first, duplicate]);
              const duplicateCalls = calls;
              queue.clear();
              calls = 0;
              const initial = window.renderStudioPage(1000);
              const forced = window.renderStudioPage(1000, { force: true, priority: true });
              const forcedResults = await Promise.all([initial, forced]);
              const forcedCalls = calls;
              window.renderStudioPageNow = original;
              queue.clear();
              return { duplicateCalls, duplicateResults, forcedCalls, forcedResults };
            }""")
            assert result == {
                "duplicateCalls": 1,
                "duplicateResults": [True, True],
                "forcedCalls": 2,
                "forcedResults": [True, True],
            }, result
            assert not errors, errors
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=15)

report = {
    "asset_version": "app151-shell92",
    "same_page_pending_request_reuses_inflight_render": True,
    "forced_request_runs_after_current_render": True,
    "browser_errors": errors,
    "verdict": "PASS",
}
(OUT / "browser-id122-render-request-dedupe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
