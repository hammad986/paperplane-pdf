"""Prove all photo operations process in-browser without posting server jobs."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from PIL import Image
import random
import socket
import time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("photo_local_helpers", HELPER)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)


def main() -> None:
    results = []
    with helpers.TemporaryDirectory(prefix="paperplane-photo-local-") as temp:
        folder = Path(temp)
        rng = random.Random(720)
        first = folder / "photo-one.png"
        second = folder / "photo-two.png"
        Image.frombytes("RGB", (1200, 800), bytes(rng.randrange(256) for _ in range(1200 * 800 * 3))).save(first)
        Image.frombytes("RGB", (1200, 800), bytes(rng.randrange(256) for _ in range(1200 * 800 * 3))).save(second)
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
                    for slug, files, expected_size in (
                        ("ssc-photo-resizer", [first], (350, 450)),
                        ("compress-image-online", [first], None),
                        ("resize-image-dimensions", [first], (350, 450)),
                        ("merge-photos-online", [first, second], (2400, 800)),
                    ):
                        context = browser.new_context(accept_downloads=True)
                        page = context.new_page()
                        errors, posts = [], []
                        page.on("pageerror", lambda e: errors.append(str(e)))
                        page.on("request", lambda req: posts.append(req.url) if req.method == "POST" and req.url.endswith("/api/jobs") else None)
                        page.goto(base + "/" + slug, wait_until="domcontentloaded")
                        if slug == "resize-image-dimensions":
                            page.locator("#preset").select_option("passport")
                        if slug == "merge-photos-online":
                            page.locator("#layout").select_option("horizontal")
                        with page.expect_file_chooser() as chooser:
                            page.locator("#browse").click()
                        chooser.value.set_files([str(x) for x in files])
                        page.locator("#run-button").click()
                        link = page.locator("#result-download-link")
                        link.wait_for(state="visible", timeout=30000)
                        output = folder / f"{slug}-{n}.jpg"
                        with page.expect_download() as download:
                            link.click()
                        download.value.save_as(output)
                        with Image.open(output) as result:
                            size = result.size
                        if expected_size:
                            assert size == expected_size, (slug, size, expected_size)
                        assert not posts, (slug, posts)
                        assert not errors, (slug, errors)
                        results.append({"round": n, "slug": slug, "input_files": len(files),
                                        "output_bytes": output.stat().st_size, "dimensions": list(size),
                                        "api_jobs": len(posts), "page_errors": errors})
                        context.close()
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=10)
    out = ROOT / "reports" / "launch-audit-v15" / "browser-photo-local-processing.json"
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
