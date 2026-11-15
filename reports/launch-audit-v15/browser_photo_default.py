"""Verify photo-compress applies its untouched 100 KB default in Chromium."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("photo_default_helpers", HELPER)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)


def main() -> None:
    rounds = []
    with tempfile.TemporaryDirectory(prefix="paperplane-photo-default-") as tmp:
        folder = Path(tmp)
        source = folder / "2400x1800-noisy.png"
        from PIL import Image
        import random
        rng = random.Random(711)
        pixels = bytes(rng.randrange(256) for _ in range(2400 * 1800 * 3))
        Image.frombytes("RGB", (2400, 1800), pixels).save(source)
        app, base, _ = helpers.start_server(folder)
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local app exited during startup")
                    time.sleep(0.1)
            else:
                raise RuntimeError("Local app did not become ready")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                for n in (1, 2):
                    page = browser.new_page(accept_downloads=True)
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(base + "/compress-image-online", wait_until="domcontentloaded")
                    assert page.locator("#target_kb").input_value() == "100"
                    with page.expect_file_chooser() as chooser:
                        page.locator("#browse").click()
                    chooser.value.set_files(str(source))
                    page.locator("#run-button").click()
                    link = page.locator("#result-download-link")
                    link.wait_for(state="visible", timeout=30000)
                    with page.expect_download() as download:
                        link.click()
                    out = folder / f"compressed-{n}.jpg"
                    download.value.save_as(out)
                    assert out.stat().st_size <= 100 * 1024, out.stat().st_size
                    assert not errors, errors
                    rounds.append({"round": n, "input_bytes": source.stat().st_size,
                                   "displayed_default_kb": 100, "output_bytes": out.stat().st_size,
                                   "page_errors": errors})
                    page.close()
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=10)
    output = ROOT / "reports" / "launch-audit-v15" / "browser-photo-default.json"
    output.write_text(json.dumps(rounds, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rounds, indent=2))


if __name__ == "__main__":
    main()
