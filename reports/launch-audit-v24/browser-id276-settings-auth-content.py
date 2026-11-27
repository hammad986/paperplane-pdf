import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def main():
    with TemporaryDirectory(prefix="paperplane-id276-") as td:
        app, base, identities = helper.start_server(Path(td) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("local server did not start")

            results = []
            errors = []
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                for round_no in (1, 2):
                    context = browser.new_context(viewport={"width": 390, "height": 844})
                    context.add_cookies([{"name": "paperplane_token", "value": identities["accounts"][0][1], "url": base, "httpOnly": True, "secure": False, "sameSite": "Lax"}])
                    page = context.new_page()
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                    page.goto(base + "/settings", wait_until="domcontentloaded")
                    page.wait_for_function("window.state?.user?.email && !document.body.classList.contains('auth-pending')", timeout=15000)
                    if page.locator("#settings-modal").is_hidden():
                        page.locator("#sidebar-profile-card").click()
                    page.locator("#settings-modal").wait_for(state="visible")
                    page.locator("#pane-account").wait_for(state="visible")
                    result = page.evaluate("""() => ({
                      email: state.user.email,
                      tier: state.user.tier,
                      name: document.querySelector('#settings-user-email')?.textContent.trim(),
                      badge: document.querySelector('#settings-user-badge')?.textContent.trim(),
                      guestActionsHidden: document.querySelector('#settings-guest-actions').hidden,
                      guestActionsChildCount: document.querySelector('#settings-guest-actions').childElementCount,
                      guestActionsText: document.querySelector('#settings-guest-actions').textContent.trim(),
                      authenticatedActionsVisible: !document.querySelector('#settings-user-actions').hidden,
                      guestExplorerVisible: [...document.querySelectorAll('*')].some(e => e.children.length === 0 && e.textContent.trim() === 'Guest Explorer' && e.getClientRects().length > 0),
                      overflow: document.documentElement.scrollWidth > innerWidth
                    })""")
                    result["round"] = round_no
                    results.append(result)
                    context.close()
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)

    out = {
        "item": 276,
        "candidate": "current local source",
        "rounds": results,
        "browserErrors": errors,
        "passed": len(results) == 2
        and all(x["tier"] == "student_pro" for x in results)
        and all(x["guestActionsHidden"] and x["guestActionsChildCount"] == 0 and not x["guestActionsText"] for x in results)
        and all(x["authenticatedActionsVisible"] and not x["guestExplorerVisible"] and not x["overflow"] for x in results)
        and not errors,
    }
    (ROOT / "reports" / "launch-audit-v24" / "browser-id276-settings-auth-content.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    if not out["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
