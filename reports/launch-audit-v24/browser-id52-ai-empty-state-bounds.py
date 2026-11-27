"""Verify the AI empty-state copy is visible within the chat card responsively."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

output = Path(__file__).resolve().parent / "browser-id52-ai-empty-state-bounds.json"
errors: list[str] = []
measurements: list[dict[str, object]] = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    for width, height in ((320, 844), (390, 844), (820, 900), (1366, 900)):
        page = browser.new_page(viewport={"width": width, "height": height})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto("http://127.0.0.1:8766/", wait_until="domcontentloaded")
        page.evaluate("window.switchWorkspaceView('ai')")
        page.wait_for_timeout(250)
        measurements.append(page.evaluate("""() => {
          const chat = document.querySelector('#chat-messages').getBoundingClientRect();
          const header = document.querySelector('.ai-chat-header').getBoundingClientRect();
          const copy = document.querySelector('#ai-empty-state .ai-empty-copy span');
          const text = copy.getBoundingClientRect();
          return {
            width: innerWidth,
            copy: copy.innerText,
            copyVisible: getComputedStyle(copy).display !== 'none' && text.width > 0 && text.height > 0,
            belowHeader: text.top >= header.bottom - 1,
            withinChatCard: text.top >= chat.top && text.bottom <= chat.bottom,
            noPageHorizontalOverflow: document.documentElement.scrollWidth <= innerWidth
          };
        }"""))
        page.close()
    browser.close()
result = {
    "build": "app.js?v=191",
    "measurements": measurements,
    "browser_errors": errors,
    "passed": len(measurements) == 4 and all(all(v for k, v in row.items() if k not in ("width", "copy")) and "page citations" in row["copy"] for row in measurements) and not errors,
}
output.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
