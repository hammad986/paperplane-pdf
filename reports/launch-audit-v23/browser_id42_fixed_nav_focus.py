"""Verify mobile focus targets scroll clear of the fixed workspace navigation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FIXTURE = OUT / "fixtures" / "ai-mobile-context-check.pdf"
external_base = os.environ.get("PAPERPLANE_BROWSER_BASE_URL")
evidence_suffix = os.environ.get("PAPERPLANE_BROWSER_EVIDENCE_SUFFIX", "")
if evidence_suffix not in ("", "-docker"):
    raise ValueError("Unsupported evidence suffix")
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix="paperplane-fixed-nav-focus-") as temporary:
    if external_base:
        class NoopProcess:
            @staticmethod
            def terminate():
                return None

        app, base = NoopProcess(), external_base.rstrip("/")
    else:
        app, base, _ = helper.start_server(Path(temporary) / "data")
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local Paperplane app failed to start")

        rounds: list[dict] = []
        page_errors: list[str] = []
        summary_fixture = "Executive Brief\n\n" + "\n\n".join(
            f"Section {index}: a controlled sample finding with supporting context and an actionable next step."
            for index in range(1, 81)
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_number in (1, 2):
                for width, height in ((320, 844), (390, 844), (390, 600), (820, 600), (820, 432)):
                    page = browser.new_page(
                        viewport={"width": width, "height": height},
                        is_mobile=width < 500,
                        has_touch=width < 500,
                    )
                    page.on("pageerror", lambda error: page_errors.append(str(error)))
                    page.route(
                        "**/api/ai/capabilities",
                        lambda route: route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps({"executive_brief_available": True, "reason": None}),
                        ),
                    )
                    page.route(
                        "**/api/ai/summarize",
                        lambda route: route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps({
                                "status": "success",
                                "summary": summary_fixture,
                                "citations": [1, 2],
                                "summary_mode": "offline_extractive",
                            }),
                        ),
                    )
                    response = page.goto(f"{base}/ai-chat", wait_until="domcontentloaded", timeout=20_000)
                    page.wait_for_timeout(80)
                    page.locator("#ai-file-input").set_input_files(str(FIXTURE))
                    page.wait_for_function(
                        "document.querySelector('#ai-active-doc-bar')?.hidden === false && "
                        "document.querySelector('#ai-doc-name')?.textContent.includes('ai-mobile-context-check.pdf')",
                        timeout=30_000,
                    )
                    layout = page.evaluate("""() => ({
                      width: innerWidth,
                      height: innerHeight,
                      documentWidth: document.documentElement.scrollWidth,
                      css: [...document.styleSheets].map(sheet => sheet.href).find(href => href?.includes('styles.css')),
                      rootScrollPaddingBottom: getComputedStyle(document.documentElement).scrollPaddingBottom,
                      mainAreaScrollPaddingBottom: getComputedStyle(document.querySelector('.main-area')).scrollPaddingBottom,
                      navTop: Math.round(document.querySelector('.mobile-workspace-bar').getBoundingClientRect().top)
                    })""")
                    summary_button = page.locator("#trigger-summary-btn")
                    if summary_button.is_disabled():
                        raise AssertionError("Controlled AI capability did not enable the brief button")
                    summary_button.click()
                    page.locator("#download-summary-pdf-btn").wait_for(state="visible", timeout=10_000)
                    selector = "#download-summary-pdf-btn"
                    page.locator(selector).focus()
                    page.wait_for_timeout(30)
                    focused = page.evaluate("""selector => {
                      const element = document.querySelector(selector);
                      const rect = element.getBoundingClientRect();
                      const nav = document.querySelector('.mobile-workspace-bar').getBoundingClientRect();
                      return {active: document.activeElement === element, top: Math.round(rect.top), bottom: Math.round(rect.bottom), navTop: Math.round(nav.top), visibleAboveNav: rect.top >= 0 && rect.bottom <= nav.top};
                    }""", selector)
                    focus_results = focused
                    if round_number == 1 and width == 390:
                        page.screenshot(path=str(OUT / "browser-id42-fixed-nav-focus-390.png"), full_page=False)
                    rounds.append({"round": round_number, "http": response.status if response else None, **layout, "focus_targets": focus_results})
                    page.close()
            browser.close()

        passed = (
            not page_errors
            and all(row["http"] == 200 and row["documentWidth"] <= row["width"] for row in rounds)
            and all(row["css"].endswith("styles.css?v=56") for row in rounds)
            and all(row["rootScrollPaddingBottom"] == "76px" for row in rounds)
            and all(row["mainAreaScrollPaddingBottom"] == "76px" for row in rounds)
            and all(target["active"] and target["visibleAboveNav"] for row in rounds for target in [row["focus_targets"]])
        )
        evidence = {
            "item": 42,
            "rounds": rounds,
            "page_errors": page_errors,
            "pass": passed,
        }
        (OUT / f"browser-id42-fixed-nav-focus{evidence_suffix}.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        if not passed:
            raise SystemExit(1)
    finally:
        app.terminate()
