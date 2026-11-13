from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE = "http://127.0.0.1:8501"
PDF = str(Path("web/assets/sample_document.pdf").resolve())


def main() -> None:
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width, height, name in [(1440, 960, "desktop"), (390, 844, "phone")]:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                is_mobile=width < 600,
                has_touch=width < 600,
            )
            page = context.new_page()
            errors: list[str] = []
            dialogs: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("dialog", lambda dialog: (dialogs.append(dialog.type), dialog.accept()))
            page.goto(BASE, wait_until="domcontentloaded", timeout=20_000)
            page.locator("#sidebar-tools-container .sidebar-tool-item").first.wait_for(state="attached", timeout=20_000)
            page.evaluate("switchWorkspaceView('studio')")
            page.locator("#studio-file-input").set_input_files(PDF)
            page.locator('#pdf-canvas[data-rendered="true"]').wait_for(timeout=30_000)
            before = page.evaluate("""() => ({
              view: sessionStorage.getItem('paperplane-active-view'),
              marker: sessionStorage.getItem('paperplane-last-local-document'),
              pageCanvas: !!document.querySelector('#pdf-canvas[data-rendered="true"]'),
              toast: document.querySelector('.toast-notice')?.innerText || null
            })""")
            page.reload(wait_until="domcontentloaded", timeout=20_000)
            page.wait_for_timeout(1200)
            after = page.evaluate("""() => ({
              studioVisible: !document.querySelector('#view-pdf-studio').hidden,
              marker: sessionStorage.getItem('paperplane-last-local-document'),
              pageCanvas: !!document.querySelector('#pdf-canvas[data-rendered="true"]'),
              toast: document.querySelector('.toast-notice')?.innerText || null
            })""")
            row = {"device": name, "viewport": width, "before": before, "after_reload": after,
                   "beforeunload_dialogs": dialogs, "page_errors": errors}
            results.append(row)
            page.screenshot(path=f"reports/launch-audit-v3/{name}-studio-reload.png")
            assert before["pageCanvas"] and before["marker"] == "sample_document.pdf", row
            assert after["studioVisible"] and after["marker"] is None and not after["pageCanvas"], row
            assert "cleared after reload" in (after["toast"] or ""), row
            assert dialogs == ["beforeunload"] and not errors, row
            context.close()
        browser.close()
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
