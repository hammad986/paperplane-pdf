"""Check metadata-result layout at phone and desktop widths in Chromium."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main() -> None:
    evidence: dict = {"viewports": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-metadata-layout-") as temp:
        app, base, _ = helper.start_server(Path(temp) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                for width, height in ((320, 740), (390, 844), (1366, 900)):
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                    page.on("console", lambda message: evidence["console_errors"].append(message.text)
                            if message.type == "error" else None)
                    page.goto(base + "/pdf-metadata", wait_until="domcontentloaded")
                    page.wait_for_function("state.activeView === 'desk' && state.operation === 'metadata'")
                    page.evaluate("""() => {
                      const card = document.querySelector('#result');
                      const info = card.querySelector('.result-info');
                      const content = card.querySelector('#result-content');
                      const actions = card.querySelector('.result-actions');
                      const meta = document.createElement('section');
                      meta.className = 'metadata-json-result';
                      meta.innerHTML = '<div class="metadata-json-result__header"><h3>Updated PDF metadata</h3><button>Download JSON</button></div><p class="metadata-json-result__status">Metadata ready</p><pre class="metadata-json-result__output"></pre>';
                      meta.querySelector('pre').textContent = JSON.stringify({
                        file_name: 'annual-report-with-a-long-file-name.pdf',
                        title: 'A long descriptive report title that should remain readable on a phone',
                        author: 'Example Author', subject: 'Metadata preview layout', keywords: Array(16).fill('searchable metadata value')
                      }, null, 2);
                      content.replaceChildren(meta);
                      content.hidden = false;
                      card.hidden = false;
                      info.querySelector('strong').textContent = 'Your document is ready!';
                      info.querySelector('small').textContent = 'annual-report-with-a-long-file-name.pdf · 2.1 MB';
                      actions.querySelector('#result-download-link').hidden = false;
                    }""")
                    page.wait_for_timeout(120)
                    state = page.evaluate("""() => {
                      const rect = selector => {
                        const r = document.querySelector(selector).getBoundingClientRect();
                        return {x:r.x,y:r.y,width:r.width,height:r.height};
                      };
                      return {
                        viewportWidth: innerWidth,
                        documentWidth: document.documentElement.scrollWidth,
                        card: rect('#result'), info: rect('#result .result-info'),
                        content: rect('#result-content'), output: rect('.metadata-json-result__output'),
                        actions: rect('#result .result-actions'),
                        cssLayout: getComputedStyle(document.querySelector('#result')).display,
                        outputScrollWidth: document.querySelector('.metadata-json-result__output').scrollWidth,
                        outputClientWidth: document.querySelector('.metadata-json-result__output').clientWidth
                      };
                    }""")
                    page.screenshot(path=str(ROOT / "reports" / "launch-audit-v24" / f"metadata-result-{width}.png"), full_page=True)
                    evidence["viewports"].append(state)
                    page.close()
                browser.close()

        finally:
            app.terminate()

    evidence["result"] = all(
        row["documentWidth"] == row["viewportWidth"]
        and row["cssLayout"] == "grid"
        and (row["content"]["width"] >= row["viewportWidth"] - 100 if row["viewportWidth"] <= 600 else row["content"]["width"] >= row["card"]["width"] * 0.9)
        and (row["output"]["width"] >= row["viewportWidth"] - 120 if row["viewportWidth"] <= 600 else row["output"]["width"] >= row["content"]["width"] * 0.9)
        and row["info"]["y"] < row["content"]["y"] < row["actions"]["y"]
        and row["outputScrollWidth"] <= row["outputClientWidth"]
        for row in evidence["viewports"]
    ) and not evidence["page_errors"] and not evidence["console_errors"]
    output = ROOT / "reports" / "launch-audit-v24" / "browser-metadata-result-mobile.json"
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["result"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
