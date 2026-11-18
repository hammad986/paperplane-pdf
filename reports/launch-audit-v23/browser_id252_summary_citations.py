from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id252-") as tmp:
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
                result = page.evaluate("""() => {
                  const mount = document.createElement('div');
                  mount.innerHTML = summaryCitationHtml([1,2,3,4,5,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34]);
                  const labels = [...mount.querySelectorAll('.ai-citation-tag')].map(e => e.textContent.trim());
                  const compact = mount.querySelector('.ai-citation-tag')?.getBoundingClientRect();
                  return {labels, text: mount.innerText, firstLabelWidth: compact ? Math.round(compact.width) : 0};
                }""")
                assert result["labels"][0] == "Pages 1-6", result
                assert result["labels"][-1] == "+7 more ranges" and len(result["labels"]) == 9, result
                assert len(result["text"]) < 180 and not errors, (result, errors)
                rounds.append({"round": round_no, **result, "page_errors": errors})
                page.close()
            browser.close()
        (OUT / "browser-id252-summary-citations.json").write_text(json.dumps(rounds, indent=2), encoding="utf-8")
        print(json.dumps(rounds, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
