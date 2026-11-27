"""Check that nested translation API errors produce readable browser errors."""
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
    evidence = {"cases": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-translate-error-") as temp:
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
                page = browser.new_page()
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                page.goto(base + "/translate-pdf", wait_until="domcontentloaded", timeout=20000)
                cases = [
                    ({"detail": {"code": "TRANSLATION_RATE_LIMITED", "message": "Translation provider rate limited (HTTP 429)."}}, 429),
                    ({"detail": "Translation service temporarily unavailable."}, 503),
                    ({"detail": {"code": "UNKNOWN_ERROR"}}, 502),
                ]
                for payload, status in cases:
                    def fulfill_error(route, _request, data=payload, code=status):
                        route.fulfill(status=code, headers={"content-type": "application/json", "retry-after": "3"}, body=json.dumps(data))

                    page.route("**/mock-translation-error", fulfill_error)
                    result = page.evaluate("""async () => {
                      try { await fetchBinary('/mock-translation-error'); return {rejected:false}; }
                      catch (error) { return {rejected:true,message:error.message,status:error.status,retryAfterMs:error.retryAfterMs}; }
                    }""")
                    evidence["cases"].append({"http_status": status, **result})
                    page.unroute("**/mock-translation-error")
                browser.close()

            expected_messages = ["Translation provider rate limited (HTTP 429).",
                                 "Translation service temporarily unavailable.",
                                 "Request failed with status 502"]
            expected_console_patterns = ("status of 429", "status of 503", "status of 502")
            evidence["unexpected_console_errors"] = [message for message in evidence["console_errors"]
                                                     if not any(pattern in message for pattern in expected_console_patterns)]
            evidence["result"] = (all(item["rejected"] and item["message"] == expected
                                       and item["status"] == item["http_status"] and item["retryAfterMs"] == 3000
                                       for item, expected in zip(evidence["cases"], expected_messages))
                                  and all("[object Object]" not in item.get("message", "") for item in evidence["cases"])
                                  and not evidence["page_errors"] and not evidence["unexpected_console_errors"])
            output = ROOT / "reports" / "launch-audit-v24" / "browser-translation-error-format.json"
            output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if not evidence["result"]:
                raise SystemExit(1)
        finally:
            app.terminate()
            try:
                app.wait(timeout=8)
            except Exception:
                app.kill()


if __name__ == "__main__":
    main()
