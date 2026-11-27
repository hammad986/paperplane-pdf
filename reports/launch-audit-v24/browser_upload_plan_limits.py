"""Browser-side checks for guest, Free, Exam Pass, and paid upload boundaries."""
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
    evidence: dict = {"rounds": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-upload-limits-") as temp:
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
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                response = page.goto(base, wait_until="domcontentloaded", timeout=20000)
                visible_copy = page.locator("#file-hint").inner_text()
                checks = page.evaluate("""() => {
                  const MiB = 1024 * 1024;
                  const check = (tier, authenticated, bytes) => {
                    state.user = authenticated ? {tier} : null;
                    return checkAccessRequirement('merge', [{name:'boundary.pdf', size:bytes}]);
                  };
                  const results = {
                    guest_50mb_allowed: check('free', false, 50 * MiB),
                    guest_over_50mb_blocked: !check('free', false, 50 * MiB + 1),
                    signed_in_free_500mb_allowed: check('free', true, 500 * MiB),
                    signed_in_free_over_service_max_blocked: !check('free', true, 500 * MiB + 1),
                    exam_pass_500mb_allowed: check('exam_pass', true, 500 * MiB),
                    exam_pass_over_500mb_blocked: !check('exam_pass', true, 500 * MiB + 1),
                    paid_500mb_allowed: check('developer', true, 500 * MiB),
                    limits: state.planLimits
                  };
                  return results;
                }""")
                evidence.update({"http_status": response.status if response else None,
                                 "visible_copy": visible_copy, "checks": checks})
                page.screenshot(path=str(ROOT / "reports" / "launch-audit-v24" / "upload-limits-mobile.png"))
                browser.close()

            c = evidence["checks"]
            evidence["result"] = (evidence["http_status"] == 200 and "Guests up to 50 MB/file" in evidence["visible_copy"]
                                  and all(c[name] for name in ("guest_50mb_allowed", "guest_over_50mb_blocked",
                                                               "signed_in_free_500mb_allowed", "signed_in_free_over_service_max_blocked",
                                                               "exam_pass_500mb_allowed", "exam_pass_over_500mb_blocked",
                                                               "paid_500mb_allowed"))
                                  and c["limits"]["guest_max_file_size_mb"] == 50
                                  and c["limits"]["exam_pass_max_file_size_mb"] == 500
                                  and c["limits"]["platform_max_file_size_mb"] == 500
                                  and not evidence["page_errors"] and not evidence["console_errors"])
            output = ROOT / "reports" / "launch-audit-v24" / "browser-upload-plan-limits.json"
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
