"""Exercise SPA workspace navigation in light/dark themes and inspect the side rail."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

VIEWS = ("tool-desk", "pricing", "faq", "history", "api-docs", "settings", "desk", "studio", "ai", "download")


def inspect_theme(page, theme: str) -> list[dict]:
    page.evaluate(f"applyTheme({json.dumps(theme)})")
    rows = []
    for view in VIEWS:
        state = page.evaluate("""view => new Promise(resolve => {
          switchWorkspaceView(view, 'privacy', true);
          requestAnimationFrame(() => requestAnimationFrame(() => {
            const side = document.querySelector('.sidebar');
            const main = document.querySelector('.main-area');
            resolve({requestedView:view, activeView:window.state?.activeView,
              theme:document.documentElement.dataset.paperplaneTheme,
              bodyTheme:document.body.classList.contains('dark-mode') ? 'dark' : document.body.classList.contains('light-mode') ? 'light' : 'unset',
              sidebarBackground:side ? getComputedStyle(side).backgroundColor : null,
              sidebarText:side ? getComputedStyle(side).color : null,
              mainBackground:main ? getComputedStyle(main).backgroundColor : null,
              route:location.pathname});
          }));
        })""", view)
        assert state["theme"] == theme and state["bodyTheme"] == theme, state
        assert state["activeView"] == view, state
        rows.append(state)
    backgrounds = {row["sidebarBackground"] for row in rows}
    assert len(backgrounds) == 1, {"theme": theme, "rows": rows}
    return rows


def main() -> None:
    evidence: dict = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id287-") as temp_name:
        app, base, _identity = helper.start_server(Path(temp_name) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("Local test server did not start")

            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                page.goto(base + "/", wait_until="domcontentloaded")
                page.wait_for_function("window.state && typeof switchWorkspaceView === 'function'", timeout=30000)
                light = inspect_theme(page, "light")
                page.screenshot(path=str(OUT / "browser-id287-sidebar-light.png"), full_page=True)
                dark = inspect_theme(page, "dark")
                page.screenshot(path=str(OUT / "browser-id287-sidebar-dark.png"), full_page=True)
                evidence.update({"light_mode": light, "dark_mode": dark,
                                 "sidebar_background_same_between_themes": light[0]["sidebarBackground"] == dark[0]["sidebarBackground"]})
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)

    evidence["result"] = "passed"
    (OUT / "browser-id287-sidebar-theme-consistency.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
