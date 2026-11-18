from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id304-") as tmp:
    app, base, _ = helper.start_server(Path(tmp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/summarize-pdf", wait_until="networkidle")
                rendered = page.evaluate("""() => {
                  showSummaryDeskResult('## Executive Summary\\n\\n- **Critical:** loss is 12%.\\n- Deadline: 15 Dec 2026.', [1, 2]);
                  const root = document.querySelector('.ai-result-markdown');
                  return {html:root?.innerHTML, text:root?.innerText, rawMarkers:root?.innerText.includes('**') || root?.innerText.includes('##')};
                }""")
                assert '<h3>Executive Summary</h3>' in rendered["html"]
                assert '<strong>Critical:</strong>' in rendered["html"]
                assert not rendered["rawMarkers"], rendered
                assert not errors, errors
                results.append({"round": round_no, **rendered, "page_errors": errors})
                page.close()
            browser.close()
        (OUT / "browser-id304-summary-markdown-render.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
