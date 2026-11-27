"""Verify AI empty/loaded mobile layout against the current production image."""
import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:18503"
FIXTURE = OUT / "fixtures" / "ai-mobile-context-check.pdf"
IMAGE = "sha256:cc3eebfbbe6314497c21f2d1300a92228b072a9bae5f70984adb63b95b693c89"
errors: list[str] = []
empty_states = []
loaded_document = None

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    probe = browser.new_page()
    for _ in range(90):
        try:
            health_response = probe.request.get(f"{BASE}/api/health", timeout=3000)
            if health_response.status == 200:
                break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("The rebuilt production Docker image failed its health check")
    health = health_response.json()

    for width in (320, 390, 820, 1366):
        page = browser.new_page(viewport={"width": width, "height": 844})
        page.on("pageerror", lambda error: errors.append(str(error)))
        response = page.goto(f"{BASE}/ai-chat", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(100)
        metrics = page.evaluate("""() => {
          const rect = selector => {
            const box = document.querySelector(selector).getBoundingClientRect();
            return {top: Math.round(box.top), bottom: Math.round(box.bottom), height: Math.round(box.height)};
          };
          return {css: [...document.styleSheets].map(sheet => sheet.href).find(href => href?.includes('styles.css')),
            viewport: innerWidth, documentWidth: document.documentElement.scrollWidth,
            topbar: rect('.ai-studio-topbar'), chat: rect('.ai-chat-card'),
            gap: Math.round(document.querySelector('.ai-chat-card').getBoundingClientRect().top -
              document.querySelector('.ai-studio-topbar').getBoundingClientRect().bottom),
            documentContextHidden: document.querySelector('#ai-active-doc-bar').hidden};
        }""")
        empty_states.append({"http": response.status if response else None, **metrics})
        if width == 390:
            page.screenshot(path=str(OUT / "browser-id42-ai-empty-topbar-docker-390.png"), full_page=True)
            page.locator("#ai-file-input").set_input_files(str(FIXTURE))
            page.wait_for_function("document.querySelector('#ai-active-doc-bar')?.hidden === false", timeout=30_000)
            loaded_document = page.evaluate("""() => {
              const rect = selector => {
                const box = document.querySelector(selector).getBoundingClientRect();
                return {top: Math.round(box.top), bottom: Math.round(box.bottom), height: Math.round(box.height)};
              };
              return {topbar: rect('.ai-studio-topbar'), chat: rect('.ai-chat-card'),
                gap: Math.round(document.querySelector('.ai-chat-card').getBoundingClientRect().top -
                  document.querySelector('.ai-studio-topbar').getBoundingClientRect().bottom),
                documentContextHidden: document.querySelector('#ai-active-doc-bar').hidden,
                documentName: document.querySelector('#ai-doc-name').textContent.trim(),
                documentWidth: document.documentElement.scrollWidth};
            }""")
            page.screenshot(path=str(OUT / "browser-id42-ai-loaded-topbar-docker-390.png"), full_page=True)
        page.close()
    browser.close()

mobile = [row for row in empty_states if row["viewport"] <= 820]
desktop = next(row for row in empty_states if row["viewport"] == 1366)
passed = (
    not errors
    and all(row["http"] == 200 and row["documentWidth"] <= row["viewport"] and row["topbar"]["height"] <= 30
            for row in empty_states)
    and all(row["gap"] <= 20 for row in mobile)
    and desktop["topbar"]["height"] <= 30
    and loaded_document is not None
    and loaded_document["documentContextHidden"] is False
    and loaded_document["documentName"] == FIXTURE.name
    and loaded_document["topbar"]["height"] >= 50
    and loaded_document["gap"] <= 20
    and loaded_document["documentWidth"] <= 390
)
result = {"image": IMAGE, "health": health, "empty_state_viewports": empty_states,
          "loaded_document_390": loaded_document, "page_errors": errors, "pass": passed}
(OUT / "browser-id42-ai-empty-topbar-docker.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
if not passed:
    raise SystemExit(1)
