"""Check first-login feedback prompt visibility, dismiss, and persistence."""
from __future__ import annotations
import importlib.util, json, socket, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("feedback_prompt_helpers", HELPER)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)

def main() -> None:
    report = []
    with helpers.TemporaryDirectory(prefix="paperplane-feedback-prompt-") as temp:
        app, base, identities = helpers.start_server(Path(temp))
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2): break
                except OSError:
                    if app.poll() is not None: raise RuntimeError("Local app exited")
                    time.sleep(0.1)
            else: raise RuntimeError("Local app did not become ready")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                for n in (1, 2):
                    context = browser.new_context(viewport={"width": 390, "height": 844})
                    context.add_cookies([{"name": "paperplane_token", "value": identities["accounts"][0][1], "url": base, "httpOnly": True}])
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                    launcher = page.locator("#pp-feedback-launcher")
                    launcher.wait_for(state="visible", timeout=10000)
                    dismiss = page.locator("#pp-feedback-dismiss")
                    assert dismiss.is_visible()
                    bounds = launcher.bounding_box()
                    assert bounds and bounds["x"] > 240 and bounds["y"] > 600, bounds
                    dismiss.click()
                    assert launcher.is_hidden()
                    page.reload(wait_until="domcontentloaded")
                    assert launcher.is_hidden()
                    page.locator("#mobile-menu-btn").click()
                    page.locator("#sidebar-settings-gear-btn").click()
                    page.locator("#settings-modal:not([hidden])").wait_for(state="visible")
                    page.locator("#settings-tab-btn-privacy").click()
                    page.locator("#settings-feedback-open").click()
                    assert page.locator("#pp-feedback-popover").is_visible()
                    assert not errors, errors
                    report.append({"round": n, "viewport": [390, 844], "launcher_bounds": bounds,
                                   "dismiss_visible": True, "dismissed_after_reload": True,
                                   "settings_reopen": True, "page_errors": errors})
                    context.close()
                browser.close()
        finally:
            app.terminate(); app.wait(timeout=10)
    out = ROOT / "reports" / "launch-audit-v15" / "browser-feedback-prompt.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__": main()
