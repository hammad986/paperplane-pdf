"""Verify server/local mode preference persists across routes and server jobs run."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import socket
import time
from playwright.sync_api import sync_playwright
import fitz

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("mode_persistence_helpers", HELPER)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)


def main() -> None:
    records = []
    with helpers.TemporaryDirectory(prefix="paperplane-mode-persistence-") as temp:
        folder = Path(temp)
        source = folder / "mode-check.pdf"
        second = folder / "mode-check-second.pdf"
        with fitz.open() as pdf:
            for n in range(1, 3):
                pdf.new_page().insert_text((72, 72), f"MODE_PAGE_{n}")
            pdf.save(source)
        with fitz.open() as pdf:
            pdf.new_page().insert_text((72, 72), "MODE_PAGE_3")
            pdf.save(second)
        app, base, _ = helpers.start_server(folder)
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local app exited during startup")
                    time.sleep(0.1)
            else:
                raise RuntimeError("Local app did not become ready")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                for n in (1, 2):
                    context = browser.new_context(accept_downloads=True)
                    page = context.new_page()
                    errors, job_posts = [], []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.on("request", lambda req: job_posts.append(req.url) if req.method == "POST" and req.url.endswith("/api/jobs") else None)
                    page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                    toggle = page.locator("#client-privacy-toggle")
                    toggle.wait_for(state="attached")
                    toggle.evaluate("el => { el.checked = false; el.dispatchEvent(new Event('change', { bubbles: true })); }")
                    assert page.locator("#privacy-mode-label").inner_text() == "Server Mode"
                    page.goto(base + "/split-pdf", wait_until="domcontentloaded")
                    assert page.locator("#client-privacy-toggle").is_checked() is False
                    assert page.locator("#privacy-mode-label").inner_text() == "Server Mode"
                    page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                    assert page.locator("#client-privacy-toggle").is_checked() is False
                    with page.expect_file_chooser() as chooser:
                        page.locator("#browse").click()
                    chooser.value.set_files(str(source))
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
                    assert len(job_posts) == 1, job_posts
                    server_job_count = len(job_posts)
                    downloaded = folder / f"mode-output-{n}.pdf"
                    with page.expect_download() as event:
                        page.locator("#result-download-link").click()
                    event.value.save_as(downloaded)
                    with fitz.open(downloaded) as result:
                        text = [p.get_text().strip() for p in result]
                    assert text == ["MODE_PAGE_1", "MODE_PAGE_2"], text
                    job_posts.clear()
                    toggle = page.locator("#client-privacy-toggle")
                    toggle.evaluate("el => { el.checked = true; el.dispatchEvent(new Event('change', { bubbles: true })); }")
                    page.goto(base + "/remove-pages-pdf", wait_until="domcontentloaded")
                    assert page.locator("#client-privacy-toggle").is_checked() is True
                    assert page.locator("#privacy-mode-label").inner_text() == "Local Processing"
                    page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                    with page.expect_file_chooser() as chooser:
                        page.locator("#browse").click()
                    chooser.value.set_files([str(source), str(second)])
                    page.locator(".file-row-card").nth(1).wait_for(state="visible", timeout=15000)
                    assert not job_posts, "Local merge unexpectedly posted to /api/jobs"
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
                    assert not job_posts, "Local merge unexpectedly posted to /api/jobs"
                    with page.expect_download() as event:
                        page.locator("#result-download-link").click()
                    event.value.save_as(folder / f"local-mode-output-{n}.pdf")
                    started = time.perf_counter()
                    page.goto(base + "/", wait_until="domcontentloaded", timeout=2000)
                    navigation_seconds = time.perf_counter() - started
                    assert navigation_seconds < 2, navigation_seconds
                    assert not errors, errors
                    records.append({"round": n, "server_job_posts": server_job_count,
                                    "local_merge_job_posts": len(job_posts),
                                    "server_mode_persisted_across_routes": True,
                                    "local_mode_persisted_across_routes": True,
                                    "server_output_text": text, "local_mode_navigation_seconds": navigation_seconds,
                                    "page_errors": errors})
                    context.close()
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=10)
    out = ROOT / "reports" / "launch-audit-v15" / "browser-processing-mode-persistence.json"
    out.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
