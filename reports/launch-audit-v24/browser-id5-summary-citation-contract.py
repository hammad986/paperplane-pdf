"""Verify API and UI citation sets survive the summary route's display truncation."""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main() -> None:
    evidence: dict = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id5-") as temp_name:
        temp = Path(temp_name)
        data_dir = temp / "data"
        data_dir.mkdir()
        fixture = temp / "scattered-summary-citations-120-pages.pdf"
        with fitz.open() as pdf:
            for page_no in range(1, 121):
                page = pdf.new_page()
                page.insert_text((72, 72), f"Citation parity source page {page_no}: audited fact {page_no * 7}.")
            pdf.save(fixture)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        runner = temp / "controlled_server.py"
        runner.write_text(
            '''import os, re, uvicorn
import ai_engine, server
def controlled_summary(system_prompt, user_prompt, **kwargs):
    if user_prompt.startswith("Synthesize these page-grounded section notes"):
        pages = ", ".join(str(n) for n in range(1, 120, 2))
        return f"The audited findings vary across the source. [Pages {pages}]"
    pages = [int(n) for n in re.findall(r"--- Page (\\d+) ---", user_prompt)]
    return f"Section findings include source pages {pages[0]} and {pages[-1]}. [Pages {pages[0]}-{pages[-1]}]"
ai_engine.call_llm = controlled_summary
uvicorn.run(server.app, host="127.0.0.1", port=int(os.environ["PAPERPLANE_PORT"]), log_level="error")
''',
            encoding="utf-8",
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith((
                "PAPERPLANE_", "CASHFREE_", "SMTP_", "RESEND_", "OPENAI_", "OPENROUTER_",
                "BLUESMINDS_", "ANTHROPIC_", "GEMINI_", "DEEPSEEK_", "GOOGLE_API_", "AI_", "ADMIN_",
            ))
            and key not in {"TESTING", "SESSION_SECRET_KEY"}
        }
        env.update({
            "PAPERPLANE_SKIP_DOTENV": "1",
            "PAPERPLANE_ENV": "development",
            "PAPERPLANE_DATA_DIR": str(data_dir),
            "PAPERPLANE_PORT": str(port),
            "PAPERPLANE_ADMIN_KEY": secrets.token_urlsafe(48),
            "PAPERPLANE_ADMIN_CODE": secrets.token_urlsafe(32),
            "PAPERPLANE_SESSION_SECRET": secrets.token_urlsafe(48),
            "PAPERPLANE_SECURE_COOKIES": "false",
            "PYTHONPATH": str(ROOT),
        })
        app = subprocess.Popen(
            [sys.executable, str(runner)], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("Local test server did not start")

            expected_pages = list(range(1, 120, 2))
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 390, "height": 844}, accept_downloads=True)
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                page.route(
                    "**/api/ai/capabilities",
                    lambda route: route.fulfill(
                        status=200, content_type="application/json",
                        body=json.dumps({"executive_brief_available": True, "reason": None}),
                    ),
                )
                page.goto(f"http://127.0.0.1:{port}/ai-intelligence", wait_until="domcontentloaded")
                page.locator("#ai-file-input").set_input_files(str(fixture))
                page.locator("#ai-active-doc-bar").wait_for(state="visible", timeout=30000)
                page.wait_for_function(
                    "document.querySelector('#trigger-summary-btn') && !document.querySelector('#trigger-summary-btn').disabled",
                    timeout=30000,
                )
                with page.expect_response(lambda response: "/api/ai/summarize" in response.url, timeout=300000) as response_event:
                    page.locator("#trigger-summary-btn").click()
                response = response_event.value
                payload = response.json()
                assert response.status == 200, payload
                summary = payload["summary"]
                assert payload["citations"] == expected_pages, {
                    "actual_count": len(payload.get("citations", [])),
                    "expected_count": len(expected_pages),
                    "actual": payload.get("citations"),
                }
                citation_label = __import__("re").search(r"\[Pages [^\]]+\]", summary).group(0)
                assert citation_label == "[Pages 1, 3, 5, 7, 9, 11, 13, 15, … +52 more pages]"
                assert len(citation_label) <= 120
                page.wait_for_function(
                    "document.querySelector('#summary-mode-badge')?.innerText === 'AI Synthesis'",
                    timeout=30000,
                )
                citations_panel = page.locator("#summary-display .ai-result-citations")
                assert citations_panel.is_visible()
                chip_labels = citations_panel.locator(".ai-citation-tag").all_inner_texts()
                assert chip_labels[:8] == [f"Page {n}" for n in expected_pages[:8]], chip_labels
                assert chip_labels[-1] == "+52 more ranges", chip_labels
                evidence.update({
                    "http_status": response.status,
                    "summary_mode": payload.get("summary_mode"),
                    "inline_citation_label": citation_label,
                    "api_citation_pages": len(payload["citations"]),
                    "api_citation_set_matches_expected": payload["citations"] == expected_pages,
                    "rendered_chip_labels": chip_labels,
                    "inline_label_is_bounded_with_omitted_count": "… +52 more pages" in citation_label,
                })
                page.screenshot(path=str(OUT / "browser-id5-summary-citation-contract.png"), full_page=True)
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=5)

    evidence["result"] = "passed"
    (OUT / "browser-id5-summary-citation-contract.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
