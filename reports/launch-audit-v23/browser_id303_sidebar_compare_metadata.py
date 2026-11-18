from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id303-") as tmp:
    app, base, _ = helper.start_server(Path(tmp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        rounds = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/", wait_until="networkidle")
                page.locator('.nav-category-tab[data-category="Edit"]').click()
                items = page.locator("#sidebar-tools-container .sidebar-tool-item").all_text_contents()
                normalized = [text.strip() for text in items]
                assert "Compare PDF" in normalized and "PDF Metadata" in normalized, normalized
                rounds.append({"round": round_no, "edit_category_tools": normalized,
                               "compare_visible": True, "metadata_visible": True, "page_errors": errors})
                assert not errors, errors
                page.close()
            browser.close()
        (OUT / "browser-id303-sidebar-compare-metadata.json").write_text(json.dumps(rounds, indent=2), encoding="utf-8")
        print(json.dumps(rounds, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
