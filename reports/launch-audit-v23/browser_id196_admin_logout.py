from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as harness

with TemporaryDirectory(prefix="paperplane-id196-admin-") as temp_dir:
    rounds = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        for round_number in (1, 2):
            app, base, identity = harness.start_server(Path(temp_dir) / f"db-{round_number}")
            try:
                for _ in range(100):
                    try:
                        with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                            break
                    except OSError:
                        time.sleep(0.15)
                else:
                    raise RuntimeError("Local Paperplane server did not start")

                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.add_init_script(f"sessionStorage.setItem('pp_admin_session', {json.dumps(identity['admin'])})")
                errors, responses = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                navigation = page.goto(base + "/admin", wait_until="domcontentloaded")
                assert navigation.status == 200
                page.locator("#btn-logout").wait_for(state="visible", timeout=15000)
                page.on("response", lambda response: responses.append({"url": response.url, "status": response.status})
                          if response.url.endswith("/api/admin/auth/logout") else None)
                page.locator("#btn-logout").click()
                page.wait_for_function("getComputedStyle(document.querySelector('#step1-screen')).display !== 'none'", timeout=10000)
                assert len(responses) == 1 and responses[0]["status"] == 200, responses
                revoked_status = page.evaluate("""async token => {
                  const response = await fetch('/api/admin/dashboard', {headers:{'X-Admin-Session':token}});
                  return response.status;
                }""", identity["admin"])
                assert revoked_status == 401, revoked_status
                assert page.evaluate("sessionStorage.getItem('pp_admin_session')") is None
                assert page.locator("#step1-screen").is_visible() and not page.locator("#dashboard-view").is_visible()
                assert not errors, errors
                page.screenshot(path=str(OUT / f"id196-admin-logout-round{round_number}.png"))
                rounds.append({"round": round_number, "navigation_status": navigation.status,
                               "logout_api": responses, "revoked_token_status": revoked_status,
                               "returned_to_step1": True, "session_token_cleared": True,
                               "page_errors": errors})
                page.context.close()
            finally:
                app.terminate()
                app.wait(timeout=5)
        browser.close()
    evidence = {"rounds": rounds}
    (OUT / "browser-id196-admin-logout.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
