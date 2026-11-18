"""Prove Settings → Storage & Privacy clears the persisted Studio document."""
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


with TemporaryDirectory(prefix="paperplane-id69-clear-storage-") as temp:
    root = Path(temp)
    fixture = root / "id69-four-pages.pdf"
    with fitz.open() as document:
        for number in range(1, 5):
            page = document.new_page()
            page.insert_text((72, 72), f"ID 69 persisted page {number}")
        document.save(fixture)

    app, base, _ = helper.start_server(root / "data")
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
            for round_number in (1, 2):
                context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/studio", wait_until="domcontentloaded")
                page.locator("#studio-file-input").set_input_files(str(fixture))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='4' && document.querySelector('#studio-loading-overlay')?.hidden===true", timeout=20000)
                stored_before = page.evaluate("""async () => {
                  const db=await new Promise((resolve,reject)=>{const request=indexedDB.open('paperplane-local-work');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error)});
                  const rows=await new Promise((resolve,reject)=>{const request=db.transaction('work','readonly').objectStore('work').getAllKeys();request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error)});
                  db.close();
                  return rows;
                }""")
                assert any("studio" in str(item).lower() for item in stored_before), stored_before

                page.locator("#mobile-menu-btn").click()
                page.wait_for_function("document.querySelector('#sidebar')?.classList.contains('mobile-open')")
                page.evaluate("document.querySelector('#sidebar').scrollTop=document.querySelector('#sidebar').scrollHeight")
                page.wait_for_timeout(250)
                page.locator("#sidebar-settings-gear-btn").click()
                page.locator("#settings-tab-btn-privacy").click()
                page.locator("#studio-clear-work-btn").click()
                dialog = page.locator("dialog.app-confirm-dialog")
                dialog.wait_for(state="visible")
                await_approve = dialog.get_by_role("button", name="Clear saved work")
                await_approve.click()
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='0'", timeout=10000)
                page.goto(base + "/studio", wait_until="domcontentloaded")
                page.wait_for_timeout(400)
                after_reload = page.evaluate("""async () => {
                  const db=await new Promise((resolve,reject)=>{const request=indexedDB.open('paperplane-local-work');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error)});
                  const rows=await new Promise((resolve,reject)=>{const request=db.transaction('work','readonly').objectStore('work').getAllKeys();request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error)});
                  db.close();
                  const canvas=document.querySelector('#pdf-canvas');
                  return {pageCount:document.querySelector('#page-total-indicator')?.textContent,canvasRendered:canvas?.dataset.rendered==='true',canvasText:canvas?.getAttribute('aria-label'),storageKeys:rows};
                }""")
                assert after_reload["pageCount"] == "0" and not after_reload["canvasRendered"], after_reload
                assert not any("studio" in str(item).lower() for item in after_reload["storageKeys"]), after_reload
                assert not errors, errors
                page.screenshot(path=str(OUT / f"id69-clear-studio-round{round_number}.png"), full_page=True)
                rounds.append({"round": round_number, "stored_before": stored_before, "after_reload": after_reload, "page_errors": errors})
                context.close()
            browser.close()
        result = {"route": "/studio", "action": "Settings > Storage & Privacy > Clear saved PDFs, AI chat, and page position", "rounds": rounds}
        (OUT / "browser-id69-clear-studio-storage.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        if sys.platform == "win32" and app.poll() is None:
            import subprocess
            subprocess.run(["taskkill", "/PID", str(app.pid), "/T", "/F"], capture_output=True, text=True)
        if app.poll() is None:
            app.terminate()
        app.wait(timeout=5)
