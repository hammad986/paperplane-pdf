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
    with TemporaryDirectory(prefix="paperplane-v24-id357-") as temp:
        app, base, _ = helper.start_server(Path(temp) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local Paperplane server exited before startup")
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, service_workers="allow")
                page = context.new_page()
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                manifest_response = page.goto(f"{base}/manifest.webmanifest", wait_until="domcontentloaded")
                assert manifest_response and manifest_response.status == 200
                manifest = manifest_response.json()
                assert manifest.get("start_url") and manifest.get("icons")
                for round_no in (1, 2):
                    response = page.goto(f"{base}/scan-pdf", wait_until="domcontentloaded")
                    assert response and response.status == 200
                    page.locator("#scan-camera-control").wait_for(state="visible")
                    camera = page.locator("#scan-camera-input")
                    assert "image" in camera.get_attribute("accept").lower()
                    assert camera.get_attribute("capture") == "environment"
                    for width in (320, 390):
                        page.set_viewport_size({"width": width, "height": 844})
                        target = page.locator("#scan-camera-btn").bounding_box()
                        assert target and target["height"] >= 44, target
                        bounds = page.evaluate("({viewport:innerWidth, document:document.documentElement.scrollWidth})")
                        assert bounds["document"] <= bounds["viewport"], bounds
                        page.evaluate("""() => {
                          const event = new Event('beforeinstallprompt', {cancelable:true});
                          event.prompt = async () => {};
                          event.userChoice = Promise.resolve({outcome:'accepted'});
                          window.dispatchEvent(event);
                        }""")
                        install = page.locator("#install-app-btn")
                        assert install.is_visible(), width
                        install_box = install.bounding_box()
                        assert install_box and install_box["height"] >= 44, install_box
                        install.click()
                        assert page.locator("#install-app-status").inner_text() == "Paperplane was installed."
                        evidence["rounds"].append({"round": round_no, "http": response.status,
                            "mobile_width": width, "rear_camera_capture": True,
                            "camera_button_height_px": target["height"], "install_button_height_px": install_box["height"],
                            "horizontal_overflow": False, "install_prompt_accept_flow": True})
                browser.close()
        finally:
            app.terminate()
    evidence["passed"] = len(evidence["rounds"]) == 4 and not evidence["page_errors"] and not evidence["console_errors"]
    output = ROOT / "reports" / "launch-audit-v24" / "browser-id357-mobile-pwa-scan.json"
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
