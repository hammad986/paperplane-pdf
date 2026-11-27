from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE = "http://127.0.0.1:8501"
PDF = str(Path("web/assets/sample_document.pdf").resolve())


def main() -> None:
    result: dict = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        csp_violations: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: csp_violations.append(message.text)
                if "content security policy" in message.text.lower() or "violates the following" in message.text.lower()
                else None)
        response = page.goto(BASE, wait_until="domcontentloaded", timeout=20_000)
        csp = response.headers.get("content-security-policy", "") if response else ""
        page.locator("#sidebar-tools-container .sidebar-tool-item").first.wait_for(state="attached", timeout=20_000)
        page.evaluate("switchWorkspaceView('studio')")
        page.locator("#studio-file-input").set_input_files(PDF)
        page.locator('#pdf-canvas[data-rendered="true"]').wait_for(timeout=30_000)
        result = {
            "http_status": response.status if response else None,
            "csp": csp,
            "script_unsafe_inline_allowed": "'unsafe-inline'" in next((part for part in csp.split(";") if "script-src" in part), ""),
            "pdf_worker_rendered": bool(page.locator('#pdf-canvas[data-rendered="true"]').count()),
            "page_errors": errors,
            "csp_console_violations": csp_violations,
        }
        page.screenshot(path="reports/launch-audit-v3/csp-studio-render.png")
        browser.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert result["http_status"] == 200 and "default-src 'self'" in result["csp"], result
    assert not result["script_unsafe_inline_allowed"], result
    assert result["pdf_worker_rendered"] and not result["page_errors"] and not result["csp_console_violations"], result


if __name__ == "__main__":
    main()
