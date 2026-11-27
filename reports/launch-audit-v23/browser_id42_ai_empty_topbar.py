"""Verify empty AI workspace compaction and loaded-document context layout."""
from __future__ import annotations

import fitz
import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

FIXTURE = OUT / "fixtures" / "ai-mobile-context-check.pdf"
FIXTURE.parent.mkdir(parents=True, exist_ok=True)
with fitz.open() as document:
    for page_number in range(1, 3):
        document.new_page().insert_text((72, 72), f"AI_CONTEXT_PAGE_{page_number}")
    document.save(FIXTURE)

with TemporaryDirectory(prefix="paperplane-ai-empty-topbar-") as temporary:
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

        empty_rounds = []
        page_errors: list[str] = []
        loaded_document = None
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for width in (320, 390, 820, 1366):
                page = browser.new_page(viewport={"width": width, "height": 844})
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                response = page.goto(f"{base}/ai-chat", wait_until="domcontentloaded", timeout=20_000)
                page.wait_for_timeout(100)
                metrics = page.evaluate("""() => {
                  const rect = selector => {
                    const element = document.querySelector(selector);
                    if (!element) return null;
                    const box = element.getBoundingClientRect();
                    return {top: Math.round(box.top), bottom: Math.round(box.bottom), height: Math.round(box.height)};
                  };
                  return {
                    css: [...document.styleSheets].map(sheet => sheet.href).find(href => href?.includes('styles.css')),
                    viewport: innerWidth,
                    documentWidth: document.documentElement.scrollWidth,
                    topbar: rect('.ai-studio-topbar'),
                    container: rect('.ai-studio-container'),
                    chat: rect('.ai-chat-card'),
                    chatGapAfterTopbar: Math.round(document.querySelector('.ai-chat-card').getBoundingClientRect().top - document.querySelector('.ai-studio-topbar').getBoundingClientRect().bottom),
                    howToVisible: !!document.querySelector('.ai-howto-section') && getComputedStyle(document.querySelector('.ai-howto-section')).display !== 'none',
                    documentContextHidden: document.querySelector('#ai-active-doc-bar').hidden
                  };
                }""")
                empty_rounds.append({"http": response.status if response else None, **metrics})
                if width == 390:
                    page.screenshot(path=str(OUT / "browser-id42-ai-empty-topbar-fixed-390.png"), full_page=True)
                    page.locator("#ai-file-input").set_input_files(str(FIXTURE))
                    page.wait_for_function(
                        "document.querySelector('#ai-active-doc-bar')?.hidden === false && "
                        "document.querySelector('#ai-doc-name')?.textContent.includes('ai-mobile-context-check.pdf')",
                        timeout=30_000,
                    )
                    loaded_document = page.evaluate("""() => {
                      const rect = selector => {
                        const box = document.querySelector(selector).getBoundingClientRect();
                        return {top: Math.round(box.top), bottom: Math.round(box.bottom), height: Math.round(box.height)};
                      };
                      return {
                        context: rect('#ai-active-doc-bar'), topbar: rect('.ai-studio-topbar'), chat: rect('.ai-chat-card'),
                        chatGapAfterTopbar: Math.round(document.querySelector('.ai-chat-card').getBoundingClientRect().top - document.querySelector('.ai-studio-topbar').getBoundingClientRect().bottom),
                        documentName: document.querySelector('#ai-doc-name').textContent.trim(),
                        documentContextHidden: document.querySelector('#ai-active-doc-bar').hidden,
                        documentWidth: document.documentElement.scrollWidth
                      };
                    }""")
                    page.screenshot(path=str(OUT / "browser-id42-ai-loaded-topbar-preserved-390.png"), full_page=True)
                page.close()
            browser.close()

        mobile = [row for row in empty_rounds if row["viewport"] <= 820]
        desktop = next(row for row in empty_rounds if row["viewport"] == 1366)
        passed = (
            not page_errors
            and all(row["http"] == 200 and row["documentWidth"] <= row["viewport"] for row in empty_rounds)
            and all(row["topbar"]["height"] <= 30 and row["chatGapAfterTopbar"] <= 20 for row in mobile)
            and desktop["topbar"]["height"] <= 30 and desktop["howToVisible"]
            and loaded_document is not None
            and loaded_document["documentContextHidden"] is False
            and loaded_document["documentName"] == FIXTURE.name
            and loaded_document["topbar"]["height"] >= 50
            and loaded_document["chatGapAfterTopbar"] <= 20
            and loaded_document["documentWidth"] <= 390
        )
        evidence = {
            "item": 42,
            "source": "app.js v115, styles.css v55, offline shell v46",
            "empty_state_viewports": empty_rounds,
            "loaded_document_390": loaded_document,
            "page_errors": page_errors,
            "pass": passed,
        }
        (OUT / "browser-id42-ai-empty-topbar-fix.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        if not passed:
            raise SystemExit(1)
    finally:
        app.terminate()
