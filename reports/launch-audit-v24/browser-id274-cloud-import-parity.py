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

OPS = ["merge", "compress", "pdf_to_text", "photo_resizer"]


def main():
    errors = []
    checks = []
    with TemporaryDirectory(prefix="paperplane-id274-") as td:
        app, base, _ = helper.start_server(Path(td) / "data")
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

            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("console", lambda m: errors.append({"text": m.text, "location": m.location}) if m.type == "error" else None)
                page.on("response", lambda r: errors.append({"http404": r.url}) if r.status == 404 else None)
                page.goto(base, wait_until="domcontentloaded")
                page.wait_for_function("window.selectOperation && window.state")
                for op in OPS:
                    page.evaluate("op => window.selectOperation(op)", op)
                    drop = page.locator("#cloud-drop-btn")
                    drop.wait_for(state="visible")
                    drop.click()
                    modal = page.locator("#cloud-modal")
                    modal.wait_for(state="visible")
                    snapshot = page.evaluate("""() => ({
                      visibleDialogCount: [...document.querySelectorAll('[role=dialog]')].filter(x => x.getClientRects().length && !x.closest('[hidden]')).length,
                      title: document.querySelector('#cloud-modal-title')?.textContent.trim(),
                      label: document.querySelector('label[for=cloud-url]')?.textContent.trim(),
                      inputType: document.querySelector('#cloud-url')?.type,
                      inputRequired: document.querySelector('#cloud-url')?.required,
                      submit: document.querySelector('#cloud-submit-btn')?.innerText.trim().replace(/\\s+/g, ' '),
                      oldContinue: [...document.querySelectorAll('button')].some(x => x.innerText.trim() === 'Continue'),
                      sampleAction: [...document.querySelectorAll('button')].some(x => /try the sample/i.test(x.innerText)),
                      focused: document.activeElement?.id,
                      overflow: document.documentElement.scrollWidth > innerWidth
                    })""")
                    page.keyboard.press("Escape")
                    page.wait_for_function("document.querySelector('#cloud-modal').hidden")
                    snapshot["closedOnEscape"] = True
                    drop.click()
                    page.wait_for_function("!document.querySelector('#cloud-modal').hidden")
                    page.mouse.click(3, 3)
                    page.wait_for_function("document.querySelector('#cloud-modal').hidden")
                    snapshot["backdropFocusRestored"] = page.evaluate("document.activeElement?.id === 'cloud-drop-btn'")
                    checks.append({"operation": op, **snapshot})

                # The topbar entry is a desktop control; verify it at its visible breakpoint.
                page.set_viewport_size({"width": 1366, "height": 900})
                page.wait_for_timeout(100)
                page.locator("#topbar-cloud-btn").click()
                header_same = page.locator("#cloud-modal").is_visible() and page.locator("#cloud-url").is_visible()
                page.keyboard.press("Escape")
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)

    out = {
        "item": 274,
        "candidate": "current local source",
        "contexts": checks,
        "headerEntryPointSameDialog": header_same,
        "browserErrors": errors,
        "passed": len(checks) == len(OPS)
        and all(x["visibleDialogCount"] == 1 for x in checks)
        and all(x["title"] == "Cloud Document Import" for x in checks)
        and all(x["label"] == "Shareable File Link" and x["inputType"] == "url" and x["inputRequired"] for x in checks)
        and all(x["submit"] == "Fetch & Import Document →" for x in checks)
        and all(not x["oldContinue"] and not x["sampleAction"] and x["closedOnEscape"] and x["backdropFocusRestored"] and not x["overflow"] for x in checks)
        and header_same and not errors,
    }
    (ROOT / "reports" / "launch-audit-v24" / "browser-id274-cloud-import-parity.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    if not out["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
