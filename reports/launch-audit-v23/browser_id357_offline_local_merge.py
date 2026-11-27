"""Verify whether a cold offline PWA can still run a browser-local PDF operation."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory
from urllib.request import urlopen

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

rounds = []
with TemporaryDirectory(prefix="paperplane-offline-local-merge-") as name:
    directory = Path(name)
    source_a, source_b = directory / "offline-a.pdf", directory / "offline-b.pdf"
    for path, marker in ((source_a, "OFFLINE-LOCAL-A"), (source_b, "OFFLINE-LOCAL-B")):
        with fitz.open() as document:
            document.new_page().insert_text((72, 72), marker)
            document.save(path)
    app, base, _ = helper.start_server(directory / "data")
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
            for round_no in (1, 2):
                context = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True,
                                              service_workers="allow")
                page = context.new_page()
                errors = []
                console_messages = []
                request_failures = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda message: console_messages.append({"type": message.type, "text": message.text[:300]}))
                page.on("requestfailed", lambda request: request_failures.append({"url": request.url, "error": request.failure}))
                home = page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)
                assert home and home.status == 200
                page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=20000)
                cache_ready = page.wait_for_function("""async () => {
                  const cache = await caches.open('paperplane-shell-v96');
                  const assets = await cache.keys();
                  const paths = assets.map(request => new URL(request.url).pathname);
                  return ['/assets/app.js','/assets/pdf.min.js','/assets/pdf.worker.min.js','/assets/pdf-lib.min.js']
                    .every(path => paths.includes(path));
                }""", timeout=20000)
                assert cache_ready is not None
                context.set_offline(True)
                offline_route = page.goto(base + "/merge-pdf", wait_until="domcontentloaded", timeout=20000)
                assert offline_route and offline_route.status == 200
                assert page.locator("#client-privacy-toggle").is_checked()
                page.locator("#file-input").set_input_files([str(source_a), str(source_b)])
                page.wait_for_function("!document.querySelector('#run-button').disabled", timeout=20000)
                outcome = ""
                output = None
                before_urls = page.evaluate("performance.getEntriesByType('resource').map(entry => entry.name)")
                try:
                    page.locator("#run-button").click()
                    page.wait_for_function("""() => {
                      const link=document.querySelector('#result-download-link');
                      const dialog=document.querySelector('dialog.app-confirm-dialog');
                      return (link && !link.hidden && link.getClientRects().length > 0)
                        || (dialog && dialog.open);
                    }""", timeout=20000)
                    dialog = page.locator("dialog.app-confirm-dialog")
                    if dialog.is_visible():
                        outcome = "offline_local_merge_fell_back_to_server_consent: " + dialog.inner_text()[:240]
                    else:
                        page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=5000)
                        with page.expect_download(timeout=15000) as download:
                            page.locator("#result-download-link").click()
                        output = directory / f"offline-merge-round{round_no}.pdf"
                        download.value.save_as(output)
                        with fitz.open(output) as document:
                            actual = [page.get_text() for page in document]
                            assert len(document) == 2
                            assert "OFFLINE-LOCAL-A" in actual[0] and "OFFLINE-LOCAL-B" in actual[1]
                        outcome = "downloaded_content_checked_pdf"
                except Exception as error:
                    outcome = f"offline_local_merge_unavailable: {type(error).__name__}: {str(error)[:240]}"
                diagnostics = page.evaluate("""() => ({
                  runDisabled:document.querySelector('#run-button')?.disabled,
                  resultText:document.querySelector('#result')?.innerText?.slice(0,1000)||'',
                  toast:document.querySelector('.toast-notice')?.innerText?.slice(0,500)||'',
                  dialog:document.querySelector('dialog.app-confirm-dialog')?.innerText?.slice(0,500)||'',
                  downloadHidden:document.querySelector('#result-download-link')?.hidden,
                  localMode:document.querySelector('#client-privacy-toggle')?.checked,
                  jobPosts:performance.getEntriesByType('resource').filter(entry=>entry.name.includes('/api/jobs')).map(entry=>entry.name)
                })""")
                rounds.append({
                    "round": round_no,
                    "offline_navigation_status": offline_route.status,
                    "local_mode_default": True,
                    "outcome": outcome,
                    "output_bytes": output.stat().st_size if output else None,
                    "browser_errors": errors,
                    "console_messages": console_messages,
                    "request_failures": request_failures,
                    "diagnostics": diagnostics,
                    "resources_loaded_before_offline": len(before_urls),
                })
                context.close()
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=10)

report = {"asset_version": "v152/v20/v25/v4/v93", "rounds": rounds,
          "cold_offline_local_merge_passed": all(row["outcome"] == "downloaded_content_checked_pdf" for row in rounds)}
(OUT / "browser-id357-offline-local-merge.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
