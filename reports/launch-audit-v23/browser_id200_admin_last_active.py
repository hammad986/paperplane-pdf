from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as harness

with TemporaryDirectory(prefix="paperplane-id200-") as temp_dir:
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

                email, token = identity["accounts"][0]
                user_context = browser.new_context(viewport={"width": 1366, "height": 900})
                user_context.add_cookies([{"name": "paperplane_token", "value": token, "url": base, "httpOnly": True}])
                user_page = user_context.new_page()
                user_errors = []
                user_page.on("pageerror", lambda error: user_errors.append(str(error)))
                user_page.goto(base + "/tool-desk", wait_until="domcontentloaded")
                user_page.wait_for_function("window.state?.user?.user_id", timeout=10000)

                admin_context = browser.new_context(viewport={"width": 1366, "height": 900})
                admin_page = admin_context.new_page()
                admin_page.add_init_script(f"sessionStorage.setItem('pp_admin_session', {json.dumps(identity['admin'])})")
                admin_errors = []
                admin_page.on("pageerror", lambda error: admin_errors.append(str(error)))
                response = admin_page.goto(base + "/admin", wait_until="domcontentloaded")
                assert response.status == 200
                row = admin_page.locator("#users-tbody tr").filter(has_text=email)
                row.wait_for(state="visible", timeout=15000)
                cells = row.locator("td").all_inner_texts()
                assert len(cells) >= 4 and cells[3].strip() not in ("", "—", "-"), cells
                api_user = admin_page.evaluate("""async ({email, token}) => {
                  const response = await fetch('/api/admin/users', {headers:{'X-Admin-Session':token}});
                  const data = await response.json();
                  return {status:response.status, user:data.users?.find(item=>item.email===email)};
                }""", {"email": email, "token": identity["admin"]})
                assert api_user["status"] == 200 and api_user["user"]["last_active_at"] > 0, api_user
                assert not user_errors and not admin_errors
                admin_page.screenshot(path=str(OUT / f"id200-admin-last-active-round{round_number}.png"))
                rounds.append({"round": round_number, "email": email, "admin_status": response.status,
                               "last_active_cell": cells[3].strip(),
                               "api_last_active_at": api_user["user"]["last_active_at"],
                               "page_errors": user_errors + admin_errors})
                user_context.close()
                admin_context.close()
            finally:
                app.terminate()
                app.wait(timeout=5)
        browser.close()
    evidence = {"rounds": rounds}
    (OUT / "browser-id200-admin-last-active.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
