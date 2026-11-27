from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
sys.path.insert(0, str(HELPER.parent))
import browser_acceptance_v14 as helper  # noqa: E402


def main() -> None:
    round_id = sys.argv[1] if len(sys.argv) > 1 else "round"
    evidence = {"round": round_id, "rounds": [], "server_job_posts": [], "page_errors": []}
    with TemporaryDirectory(prefix="paperplane-watermark-local-") as temporary:
        work = Path(temporary)
        source = work / "watermark-source.pdf"
        image_source = work / "watermark-image.png"
        Image.new("RGBA", (32, 32), (200, 20, 0, 180)).save(image_source)
        with fitz.open() as document:
            for index, rotation in enumerate((0, 90, 180, 270), 1):
                page = document.new_page(width=360, height=240)
                page.insert_text((40, 65), f"WATERMARK-PAGE-{index}", fontsize=15)
                if rotation:
                    page.set_rotation(rotation)
            document.save(source)
        app, base, _identity = helper.start_server(work / "server-data")
        try:
            for _ in range(300):
                try:
                    with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local app did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page = context.new_page()
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                context.on("request", lambda request: evidence["server_job_posts"].append(request.url)
                           if request.method == "POST" and request.url.split("?")[0].endswith("/api/jobs") else None)
                response = page.goto(f"{base}/watermark-pdf", wait_until="domcontentloaded", timeout=60000)
                assert response and response.status == 200
                assert page.locator("#client-privacy-toggle").is_checked()
                assert "Text watermarks can run in your browser" in page.locator(".option-help").inner_text()
                page.locator("#file-input").set_input_files(str(source))
                page.locator("#text").fill("LOCAL WATERMARK")
                page.locator("#opacity").fill("0.35")
                page.locator("#mark_color").fill("#cc2200")
                assert page.locator("#run-button").is_enabled()
                direct = page.evaluate("""async () => {
                  try { const r = await PaperplanePdfRuntime.transformLocalPdf('watermark', state.files,
                    {text: document.querySelector('#text').value, opacity: Number(document.querySelector('#opacity').value),
                     markColor: document.querySelector('#mark_color').value, markBackground: 'unknown'});
                    return {ok:true, bytes:r.output.byteLength, filename:r.filename};
                  } catch (e) { return {ok:false, error:String(e && e.stack || e)}; }
                }""")
                assert direct.get("ok"), direct
                with page.expect_download(timeout=30000) as event:
                    page.locator("#run-button").click()
                    try:
                        page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=8000)
                    except Exception as error:
                        toast = page.locator(".toast-notice").inner_text() if page.locator(".toast-notice").count() else "none"
                        raise AssertionError(f"local watermark failed: {toast}; result={page.locator('#result').inner_text() if page.locator('#result').count() else 'none'}; direct={direct}; errors={evidence['page_errors']}") from error
                    page.locator("#result-download-link").click()
                output = work / f"watermarked-{round_id}.pdf"
                event.value.save_as(output)
                with fitz.open(output) as result:
                    assert len(result) == 4
                    per_page = [p.get_text() for p in result]
                    assert all("LOCAL WATERMARK" in text for text in per_page), per_page
                    assert all(f"WATERMARK-PAGE-{i}" in text for i, text in enumerate(per_page, 1))
                    assert [p.rotation for p in result] == [0, 90, 180, 270]
                    centers = []
                    for rendered_page in result:
                        spans = [span for block in rendered_page.get_text("dict")["blocks"]
                                 for line in block.get("lines", []) for span in line.get("spans", [])
                                 if "LOCAL WATERMARK" in span["text"]]
                        assert spans, "watermark text is not visible/selectable"
                        rect = rendered_page.rect
                        render = rendered_page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                        samples = render.samples
                        red_xy = [(i // render.n % render.width, i // render.n // render.width)
                                  for i in range(0, len(samples), render.n)
                                  if samples[i] > samples[i + 1] + 2 and samples[i] > samples[i + 2] + 4]
                        red_pixels = len(red_xy)
                        assert red_pixels > 5, f"selected red mark colour missing on rotated page {rendered_page.rotation}"
                        red_center = ((min(x for x, _ in red_xy) + max(x for x, _ in red_xy)) / 2,
                                      (min(y for _, y in red_xy) + max(y for _, y in red_xy)) / 2)
                        assert abs(red_center[0] - rect.width / 2) < rect.width * 0.22, (red_center, rect)
                        assert abs(red_center[1] - rect.height / 2) < rect.height * 0.22, (red_center, rect)
                        centers.append([round(red_center[0], 1), round(red_center[1], 1)])
                assert not evidence["server_job_posts"]
                assert not evidence["page_errors"]
                page.locator("#watermark_image_file").set_input_files(str(image_source))
                page.locator("#run-button").click()
                dialog = page.locator("dialog.app-confirm-dialog")
                dialog.wait_for(state="visible", timeout=10000)
                confirmation_text = dialog.inner_text()
                assert "Image watermarks need temporary server processing" in confirmation_text
                assert "upload the selected files" in confirmation_text and "daily server allowance" in confirmation_text
                dialog.locator(".app-confirm-cancel").click()
                page.wait_for_function("!document.querySelector('#run-button').disabled")
                assert not evidence["server_job_posts"], "declining image watermark fallback must keep the file local"
                evidence["image_fallback"] = {"confirmation_shown": True, "declined": True,
                                               "server_job_posts_after_decline": 0}
                page.locator("#watermark_image_file").set_input_files([])
                page.locator("#text").fill("✓ café")
                page.locator("#run-button").click()
                dialog = page.locator("dialog.app-confirm-dialog")
                dialog.wait_for(state="visible", timeout=10000)
                assert "standard-font text" in dialog.inner_text()
                dialog.locator(".app-confirm-cancel").click()
                page.wait_for_function("!document.querySelector('#run-button').disabled")
                assert not evidence["server_job_posts"], "declining unsupported-script fallback must remain local"
                evidence["unsupported_text"] = {"fallback_explanation_shown": True, "declined": True,
                                                 "server_job_posts_after_decline": 0}
                evidence["rounds"].append({"status": "passed", "filename": event.value.suggested_filename,
                                           "bytes": output.stat().st_size, "pages": 4,
                                           "text_checked": True, "rotations_checked": [0, 90, 180, 270],
                                           "watermark_centers": centers, "selected_color_pixels_checked": True,
                                           "server_job_posts": 0})
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=10)
            except Exception:
                app.kill()
    (Path(__file__).parent / f"browser-id37-watermark-{round_id}.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
