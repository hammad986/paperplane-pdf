from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as harness

with TemporaryDirectory(prefix="paperplane-id212-") as temp_dir:
    app, base, _ = harness.start_server(Path(temp_dir) / "db")
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.15)
        else:
            raise RuntimeError("Local Paperplane server did not start")

        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_number in (1, 2):
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base + "/repair-pdf", wait_until="domcontentloaded")
                assert response.status == 200
                options = page.locator("#mode option").evaluate_all(
                    "items => items.map(item => ({value:item.value,label:item.textContent.trim()}))"
                )
                assert options == [
                    {"value": "automatic", "label": "Automatic recovery"},
                    {"value": "validate_only", "label": "Validate structure only"},
                ], options
                assert not any("automatic (" in item["label"].casefold() or "validate_xref" in item["label"].casefold()
                               for item in options)
                page.screenshot(path=str(OUT / f"id212-repair-labels-round{round_number}.png"))
                assert not errors, errors
                rounds.append({"round": round_number, "status": response.status, "options": options, "page_errors": errors})
                page.context.close()
            browser.close()
        evidence = {"rounds": rounds}
        (OUT / "browser-id212-repair-labels.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
