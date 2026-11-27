import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

TITLE = "Aurora Field Research — 2026"


def main():
    errors = []
    rounds = []
    with TemporaryDirectory(prefix="paperplane-id305-") as td:
        temp = Path(td)
        pdf = temp / "title-fixture.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Field observations about aurora visibility.")
        doc.set_metadata({"title": TITLE, "author": "Audit fixture"})
        doc.save(pdf)
        doc.close()
        app, base, _ = helper.start_server(temp / "data")
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
                for round_no in (1, 2):
                    page = browser.new_page(viewport={"width": 390 if round_no == 1 else 1366, "height": 900})
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                    api = []
                    page.on("response", lambda r: api.append({"status": r.status, "url": r.url}) if "/api/ai/chat/stream" in r.url else None)
                    page.goto(base + "/ai-intelligence", wait_until="domcontentloaded")
                    page.locator("#ai-file-input").set_input_files(str(pdf))
                    page.wait_for_function("state.files?.some(file=>file.name==='title-fixture.pdf')", timeout=15000)
                    page.locator("#chat-input").fill("What is the title of this PDF?")
                    page.locator("#chat-send-btn").click()
                    page.wait_for_function("[...document.querySelectorAll('.ai-stream-bubble')].some(b=>b.innerText.includes('document title'))", timeout=20000)
                    bubble = page.locator(".ai-stream-bubble").last
                    answer = bubble.locator(".ai-stream-text").inner_text()
                    rounds.append({"round": round_no, "viewport": page.evaluate("innerWidth"), "title": page.locator("#ai-doc-filename").inner_text() if page.locator("#ai-doc-filename").count() else None, "answer": answer, "api": api, "overflow": page.evaluate("document.documentElement.scrollWidth > innerWidth")})
                    page.close()
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)

    out = {
        "item": 305,
        "candidate": "current local source; actual API request, no mocked chat stream",
        "expectedPdfMetadataTitle": TITLE,
        "rounds": rounds,
        "browserErrors": errors,
        "passed": len(rounds) == 2
        and all(TITLE in r["answer"] and r["api"] and r["api"][-1]["status"] == 200 and not r["overflow"] for r in rounds)
        and not errors,
    }
    (ROOT / "reports" / "launch-audit-v24" / "browser-id305-chat-pdf-title.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    if not out["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
