import json
import socket
import sys
import time
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from PIL import Image, ImageStat
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def zip_image_evidence(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        colors = {}
        for name in names:
            with archive.open(name) as stream:
                image = Image.open(stream).convert("RGB")
                colors[name] = tuple(round(value) for value in ImageStat.Stat(image).mean)
        return names, colors


def main():
    errors = []
    runs = []
    with TemporaryDirectory(prefix="paperplane-id327-") as td:
        temp = Path(td)
        source = temp / "three-color-pages.pdf"
        colors = [(224, 42, 42), (38, 194, 72), (38, 62, 224)]
        doc = fitz.open()
        for index, color in enumerate(colors, 1):
            page = doc.new_page(width=360, height=480)
            page.draw_rect(page.rect, color=tuple(channel / 255 for channel in color), fill=tuple(channel / 255 for channel in color))
            page.insert_text((30, 40), f"SOURCE PAGE {index}", fontsize=16, color=(1, 1, 1))
        doc.save(source)
        doc.close()

        app, base, _ = helper.start_server(temp / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("local server did not start")

            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                for round_no, (mode, width) in enumerate((("browser", 390), ("server", 1366)), 1):
                    context = browser.new_context(viewport={"width": width, "height": 900}, accept_downloads=True)
                    page = context.new_page()
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                    api_jobs = []
                    page.on("request", lambda req: api_jobs.append(req.url) if req.method == "POST" and "/api/jobs" in req.url else None)
                    context.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode', " + json.dumps("local" if mode == "browser" else "server") + ")")
                    page.goto(base + "/pdf-to-jpg", wait_until="domcontentloaded")
                    page.locator("#pages").wait_for(state="visible")
                    page.locator("#file-input").set_input_files(str(source))
                    page.wait_for_function("state.files?.some(file=>file.name==='three-color-pages.pdf')", timeout=15000)
                    active_mode = page.evaluate("state.clientSideMode ? 'browser' : 'server'")
                    page.locator("#pages").fill("1, 3")
                    page.locator("#run-button").click()
                    page.locator("#result").wait_for(state="visible", timeout=30000)
                    page.locator("#result-download-link").wait_for(state="visible", timeout=30000)
                    with page.expect_download(timeout=30000) as download_event:
                        page.locator("#result-download-link").click()
                    output = temp / f"selected-{mode}.zip"
                    download_event.value.save_as(output)
                    names, rendered_colors = zip_image_evidence(output)
                    runs.append({"round": round_no, "mode": mode, "activeMode": active_mode, "width": width, "zip_bytes": output.stat().st_size, "members": names, "mean_rgb": rendered_colors, "api_job_posts": len(api_jobs), "overflow": page.evaluate("document.documentElement.scrollWidth > innerWidth")})

                    if mode == "server":
                        page.locator("#pages").fill("4")
                        page.locator("#run-button").click()
                        page.locator("#result").wait_for(state="visible", timeout=30000)
                        page.wait_for_timeout(250)
                        runs[-1]["invalidRangeError"] = page.locator("#result-meta").inner_text()
                        runs[-1]["invalidRangeTitle"] = page.locator("#result-title").inner_text()
                        runs[-1]["invalidRangeDownloadHidden"] = page.locator("#result-download-link").is_hidden()
                    context.close()
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)

    expected_members = ["page_001.jpg", "page_003.jpg"]
    out = {
        "item": 327,
        "candidate": "current local source",
        "sourcePages": 3,
        "selection": "1, 3",
        "runs": runs,
        "browserErrors": errors,
        "passed": len(runs) == 2
        and all(run["members"] == expected_members and run["zip_bytes"] > 1000 and not run["overflow"] for run in runs)
        and all(run["activeMode"] == run["mode"] for run in runs)
        and all(run["mode"] == "browser" or run["api_job_posts"] >= 1 for run in runs)
        and all(run["mode"] == "browser" or "Choose pages from 1 to 3" in run["invalidRangeError"] and run["invalidRangeTitle"] == "Need a little more information" and run["invalidRangeDownloadHidden"] for run in runs)
        and all(run["mean_rgb"]["page_001.jpg"][0] > run["mean_rgb"]["page_001.jpg"][2] * 1.7 for run in runs)
        and all(run["mean_rgb"]["page_003.jpg"][2] > run["mean_rgb"]["page_003.jpg"][0] * 1.7 for run in runs)
        and not errors,
    }
    (ROOT / "reports" / "launch-audit-v24" / "browser-id327-pdf-to-jpg-selected-pages.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    if not out["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
