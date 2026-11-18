"""Verify a new signed-in account cannot restore the prior account's Studio PDF."""
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
import json
import socket
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix="paperplane-id114-account-switch-") as temp:
    root = Path(temp)
    fixture = root / "previous-account-private-document.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "PRIVATE ACCOUNT ALPHA DOCUMENT 114")
        document.save(fixture)

    app, base, identities = helper.start_server(root / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            if app.poll() is not None:
                raise RuntimeError(f"app exited with {app.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.15)

        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for number in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                context.add_cookies([{"name": "paperplane_token", "value": identities["accounts"][0][1], "url": base, "httpOnly": True}])
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/studio", wait_until="domcontentloaded")
                page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=10000)
                page.locator("#studio-file-input").set_input_files(str(fixture))
                page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered==='true'", timeout=20000)
                previous_account = page.evaluate("""async () => {
                  const db=await new Promise((resolve,reject)=>{const q=indexedDB.open('paperplane-local-work');q.onsuccess=()=>resolve(q.result);q.onerror=()=>reject(q.error)});
                  const keys=await new Promise((resolve,reject)=>{const q=db.transaction('work').objectStore('work').getAllKeys();q.onsuccess=()=>resolve(q.result);q.onerror=()=>reject(q.error)});
                  db.close();return {userId:state.user?.user_id,keys,filename:state.studio.srcFile?.name,pageCount:state.studio.totalCount};
                }""")
                assert previous_account["userId"] and previous_account["filename"] == fixture.name and previous_account["pageCount"] == 1, previous_account
                assert any(str(key).endswith(":studio-pdf") for key in previous_account["keys"]), previous_account

                context.add_cookies([{"name": "paperplane_token", "value": identities["accounts"][1][1], "url": base, "httpOnly": True}])
                page.goto(base + "/studio", wait_until="domcontentloaded")
                page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=10000)
                page.wait_for_timeout(1200)
                new_account = page.evaluate("""() => ({userId:state.user?.user_id,pageCount:document.querySelector('#page-total-indicator')?.textContent,canvasRendered:document.querySelector('#pdf-canvas')?.dataset.rendered==='true',pageText:document.querySelector('#studio-page-stack')?.innerText||'',loading:document.querySelector('#studio-loading-overlay')?.hidden===false})""")
                assert new_account["userId"] and new_account["userId"] != previous_account["userId"], new_account
                assert new_account["pageCount"] == "0" and not new_account["canvasRendered"] and "PRIVATE ACCOUNT ALPHA" not in new_account["pageText"], new_account
                assert not errors, errors
                page.screenshot(path=str(OUT / f"id114-account-switch-round{number}.png"), full_page=True)
                rounds.append({"round": number, "previous_account": previous_account, "new_account": new_account, "page_errors": errors})
                context.close()
            browser.close()
        result = {"scenario": "switch from an account with saved Studio work to a different account in the same browser session", "rounds": rounds}
        (OUT / "browser-id114-account-workspace-isolation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        if sys.platform == "win32" and app.poll() is None:
            import subprocess
            subprocess.run(["taskkill", "/PID", str(app.pid), "/T", "/F"], capture_output=True, text=True)
        if app.poll() is None:
            app.terminate()
        app.wait(timeout=5)
