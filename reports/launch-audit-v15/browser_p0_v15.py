"""Local Chromium acceptance for the v15 served-runtime and picker P0s."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
import time
from urllib.parse import urlsplit
import sys

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from scripts.check_served_pdf_runtime import verify_served_runtime
V14_SCRIPT = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("paperplane_v14_browser_helpers", V14_SCRIPT)
helpers = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(helpers)


def run_round(browser, number: int) -> dict:
    started = time.time()
    with TemporaryDirectory(prefix=f"paperplane-v15-p0-{number}-") as temp:
        directory = Path(temp)
        source = directory / "native-picker.pdf"
        with fitz.open() as pdf:
            pdf.new_page().insert_text((72, 72), "Native picker regression page one")
            pdf.save(source)

        app, base, _ = helpers.start_server(directory)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1366, "height": 900})
        page = context.new_page()
        requests = []
        errors = []
        auth_requests = []
        page.on("pageerror", lambda error: errors.append(str(error).splitlines()[0][:180]))
        page.on("request", lambda request: requests.append(request.url)
                 if request.method == "POST" and urlsplit(request.url).path == "/api/jobs" else None)
        page.add_init_script("""(() => {
          const nativeFetch = window.fetch.bind(window);
          window.fetch = (resource, options) => {
            const url = typeof resource === 'string' ? resource : resource.url;
            if (String(url).includes('/api/auth/me')) {
              window.__authProbePending = true;
              return new Promise((resolve, reject) => setTimeout(() => {
                nativeFetch(resource, options).then(resolve, reject).finally(() => { window.__authProbePending = false; });
              }, 5000));
            }
            return nativeFetch(resource, options);
          };
        })();""")
        try:
            port = int(urlsplit(base).port)
            for _ in range(80):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local server exited before the picker test started")
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local server did not become ready")
            runtime_size, runtime_url = verify_served_runtime(base)
            response = page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
            assert response and response.status == 200
            page.locator("#tool-title").wait_for(state="visible")
            page.wait_for_function("window.__authProbePending === true", timeout=5000)

            # This is the real Chromium file-chooser event path. The browser
            # receives the fixture through the chooser API because a headless
            # run has no interactive OS dialog.
            picker_started = time.perf_counter()
            with page.expect_file_chooser(timeout=3000) as chooser:
                page.locator("#browse").click()
            picker_open_ms = round((time.perf_counter() - picker_started) * 1000)
            assert picker_open_ms < 3000, f"picker was blocked by slow auth for {picker_open_ms}ms"
            assert page.evaluate("window.__authProbePending") is True, "picker opened after delayed auth had already resolved"
            chooser.value.set_files(str(source))
            page.locator(".file-row-card").wait_for(state="visible", timeout=10000)
            assert "native-picker.pdf" in page.locator("#file-list").inner_text()

            runtime = page.evaluate("typeof window.PaperplanePdfRuntime.transformLocalPdf")
            assert runtime == "function", f"served runtime export missing: {runtime}"

            page.locator("#run-button").click()
            page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
            with page.expect_download(timeout=30000) as download_event:
                page.locator("#result-download-link").click()
            output = directory / "native-picker-merged.pdf"
            download_event.value.save_as(output)
            with fitz.open(output) as pdf:
                assert pdf.page_count == 1
                assert "Native picker regression page one" in pdf[0].get_text()
            page.goto(base + "/", wait_until="domcontentloaded")
            page.wait_for_function("[...document.querySelectorAll('.nav-category-tab .nav-cat-badge')].every(el => /^\\d+$/.test(el.textContent.trim()))")
            counts = page.locator(".nav-category-tab .nav-cat-badge").all_text_contents()
            suite_total = sum(int(value) for value in counts if value.isdigit())
            catalog_count = page.evaluate("Object.keys(state.operations).length")
            assert suite_total == catalog_count == 44, (suite_total, catalog_count, counts)
            assert not requests, "Local merge unexpectedly submitted an /api/jobs request"
            assert not errors, errors
            return {
                "round": number,
                "runtime_export": runtime,
                "http_runtime_bytes": runtime_size,
                "http_runtime_url": runtime_url,
                "operation_count": catalog_count,
                "suite_badge_total": suite_total,
                "chooser_event": "opened and accepted local PDF",
                "picker_open_ms": picker_open_ms,
                "auth_pending_at_picker": True,
                "output_pages": 1,
                "output_text_verified": True,
                "server_job_posts": len(requests),
                "page_errors": errors,
                "duration_seconds": round(time.time() - started, 2),
            }
        finally:
            context.close()
            app.terminate()
            app.wait(timeout=15)


if __name__ == "__main__":
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        results = []
        for round_number in (1, 2):
            results.append(run_round(browser, round_number))
            REPORT.mkdir(parents=True, exist_ok=True)
            (REPORT / "browser-p0.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        browser.close()
        print(json.dumps(results, indent=2))
