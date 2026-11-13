from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8501"
OPERATIONS = [
    "merge", "split", "compress", "remove", "rotate",
    "organize", "scan_pdf", "ocr", "jpg_to_pdf", "word_to_pdf",
]


def wait_for(page, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return bool(predicate())


results = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1104, "height": 860})

    for run_number in (1, 2):
        page = context.new_page()
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(f"{BASE}/tool-desk", wait_until="domcontentloaded")
        page.locator("#view-tool-desk-directory").wait_for(state="visible")
        assert wait_for(page, lambda: len(page.evaluate("Object.keys(window.state.operations || {})")) >= 41)
        assert page.locator(".seo-content").count() == 1

        expected_contexts = {}
        for operation in OPERATIONS:
            response = page.request.get(f"{BASE}/api/seo/{operation}")
            assert response.ok, f"SEO endpoint failed for {operation}: {response.status}"
            expected_contexts[operation] = response.json()

        page.evaluate(
            """() => {
              const originalFetch = window.fetch.bind(window);
              window.__originalFetch = originalFetch;
              const requests = [];
              window.__seoRaceRequests = requests;
              window.fetch = async (input, init) => {
                const url = String(input);
                if (!url.includes('/api/seo/')) return originalFetch(input, init);
                const operation = url.split('/api/seo/')[1].split(/[?#]/)[0];
                const index = requests.length;
                const item = { operation, index, startedAt: performance.now() };
                requests.push(item);
                await new Promise(resolve => setTimeout(resolve, (10 - index) * 110));
                const response = await originalFetch(input, init);
                item.completedAt = performance.now();
                return response;
              };
            }"""
        )

        start = time.monotonic()
        for operation in OPERATIONS:
            page.evaluate("operation => window.selectOperation(operation, true)", operation)
        last_operation = OPERATIONS[-1]
        assert wait_for(
            page,
            lambda: page.locator("#seo-page-heading").count() == 1
            and page.locator("#seo-page-heading").inner_text().strip() == expected_contexts[last_operation]["heading"],
        ), "The newest tool SEO content did not render"
        latest_render_seconds = round(time.monotonic() - start, 3)
        page.wait_for_timeout(1300)
        state_after_all = page.evaluate(
            """() => ({
              heading: document.querySelector('#seo-page-heading')?.textContent?.trim() || null,
              title: document.title,
              busy: document.querySelector('.seo-content')?.getAttribute('aria-busy') || null,
              requests: window.__seoRaceRequests.map(item => item.operation),
              completionOrder: [...window.__seoRaceRequests].sort((a, b) => a.completedAt - b.completedAt).map(item => item.operation),
              operation: window.state.operation
            })"""
        )
        assert state_after_all["heading"] == expected_contexts[last_operation]["heading"]
        assert state_after_all["title"] == expected_contexts[last_operation]["title"]
        assert state_after_all["busy"] is None
        assert state_after_all["operation"] == last_operation
        assert state_after_all["requests"] == OPERATIONS
        assert state_after_all["completionOrder"][-1] == OPERATIONS[0], state_after_all["completionOrder"]

        page.evaluate("() => { window.fetch = window.__originalFetch; }")
        first_landing_by_tool = []
        for operation in OPERATIONS:
            first_landing_started = time.monotonic()
            page.evaluate("operation => window.selectOperation(operation, true)", operation)
            assert wait_for(
                page,
                lambda: page.locator("#seo-page-heading").count() == 1
                and page.locator("#seo-page-heading").inner_text().strip() == expected_contexts[operation]["heading"],
            ), f"Wrong first-landing SEO heading for {operation}"
            landing = page.evaluate(
                """() => ({
                  heading: document.querySelector('#seo-page-heading')?.textContent?.trim() || null,
                  title: document.title,
                  howTo: [...document.querySelectorAll('.seo-howto-step h3')].map(element => element.textContent.trim())
                })"""
            )
            assert landing["title"] == expected_contexts[operation]["title"]
            assert landing["howTo"] == expected_contexts[operation]["how_to"]
            first_landing_by_tool.append({
                "operation": operation,
                **landing,
                "seconds": round(time.monotonic() - first_landing_started, 3),
            })
            page.screenshot(path=str(OUT / f"after-seo-first-landing-{operation}-run-{run_number}.png"))

        page.screenshot(path=str(OUT / f"after-seo-navigation-race-run-{run_number}.png"), full_page=True)
        page.evaluate(
            """() => {
              window.fetch = (input, init) => String(input).includes('/api/seo/pdf_to_word')
                ? Promise.reject(new Error('simulated SEO network failure'))
                : window.__originalFetch(input, init);
            }""",
        )
        page.evaluate("window.selectOperation('pdf_to_word', false)")
        assert wait_for(page, lambda: "details could not load right now" in page.locator(".seo-content").inner_text())
        failure_state = page.evaluate(
            """() => ({
              text: document.querySelector('.seo-content')?.innerText || '',
              busy: document.querySelector('.seo-content')?.getAttribute('aria-busy') || null,
              title: document.title
            })"""
        )
        assert failure_state["busy"] is None
        assert "PDF to Word" in failure_state["title"]
        assert "The PDF tool is still available." in failure_state["text"]

        results.append({
            "run": run_number,
            "operations": OPERATIONS,
            "latest_content_render_seconds": latest_render_seconds,
            "final_state_after_out_of_order_responses": state_after_all,
            "first_landing_by_tool": first_landing_by_tool,
            "current_request_failure_fallback": failure_state,
            "page_errors": page_errors,
        })
        page.close()

    browser.close()

report = {"base": BASE, "results": results}
(OUT / "seo-navigation-race.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
