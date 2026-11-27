"""Check truthful browser/server processing controls and exercise local paths."""
from __future__ import annotations

import ast
import io
import json
import os
import socket
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from urllib.parse import urlsplit

import fitz
from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
sys.path.insert(0, str(HELPER.parent))
import browser_acceptance_v14 as helper  # noqa: E402

PDF_LOCAL = {"merge", "split", "remove", "rotate", "organize", "scan_pdf", "jpg_to_pdf", "pdf_to_jpg", "forms", "flatten", "metadata", "pdf_to_text", "page_numbers", "crop", "watermark", "edit", "sign"}
IMAGE_LOCAL = {"photo_resizer", "photo_compress", "photo_resize", "photo_merge"}
ALL_LOCAL = PDF_LOCAL | IMAGE_LOCAL


def make_pdf(path: Path, labels: list[str]) -> None:
    with fitz.open() as document:
        for label in labels:
            page = document.new_page(width=300, height=200)
            page.insert_text((40, 70), label, fontsize=16)
        document.save(path)


def make_fillable_pdf(path: Path) -> None:
    with fitz.open() as document:
        page = document.new_page(width=300, height=200)
        page.insert_text((40, 40), "FLATTEN-SOURCE-MARKER", fontsize=14)
        widget = fitz.Widget()
        widget.field_name = "Applicant"
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.rect = fitz.Rect(40, 70, 260, 100)
        widget.field_value = "FILLED-APPLICANT-VALUE"
        widget.text_fontsize = 12
        page.add_widget(widget)
        document.save(path)


def make_metadata_pdf(path: Path) -> None:
    with fitz.open() as document:
        page = document.new_page(width=300, height=200)
        page.insert_text((40, 70), "METADATA-SOURCE-MARKER", fontsize=14)
        document.set_metadata({"title": "ORIGINAL METADATA TITLE", "author": "ORIGINAL METADATA AUTHOR",
                               "subject": "ORIGINAL METADATA SUBJECT", "creator": "ORIGINAL CREATOR",
                               "producer": "ORIGINAL PRODUCER"})
        document.save(path)


def main() -> None:
    tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))
    slugs = next(ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "OPERATION_SLUGS" for target in node.targets))
    report_dir = Path(__file__).resolve().parent
    round_id = sys.argv[1] if len(sys.argv) > 1 else None
    evidence: dict = {"round": round_id, "routes": [], "local_operations": [], "page_errors": [], "server_job_posts": [],
                      "preference_persistence": {}, "local_failure_fallback": {}}

    with TemporaryDirectory(prefix="paperplane-v23-zero-upload-") as temporary:
        directory = Path(temporary)
        source = directory / "local-two-pages.pdf"
        second = directory / "local-second.pdf"
        fillable = directory / "local-fillable.pdf"
        metadata_source = directory / "local-metadata.pdf"
        make_pdf(source, ["LOCAL-PAGE-ONE", "LOCAL-PAGE-TWO"])
        make_pdf(second, ["LOCAL-SECOND"])
        make_fillable_pdf(fillable)
        make_metadata_pdf(metadata_source)
        dark_source = directory / "local-dark-signature.pdf"
        with fitz.open() as dark_document:
            dark_page = dark_document.new_page(width=300, height=200)
            dark_page.draw_rect(dark_page.rect, fill=(0.03, 0.05, 0.08), color=(0.03, 0.05, 0.08))
            dark_page.insert_text((40, 50), "DARK-SIGN-SOURCE", color=(1, 1, 1))
            dark_document.save(dark_source)
        photo_a = directory / "photo-a.png"
        photo_b = directory / "photo-b.png"
        Image.new("RGB", (96, 48), (180, 20, 40)).save(photo_a)
        Image.new("RGB", (64, 32), (20, 40, 180)).save(photo_b)
        watermark_image = directory / "watermark-image.png"
        watermark_art = Image.new("RGBA", (120, 60), (0, 0, 0, 0))
        from PIL import ImageDraw
        ImageDraw.Draw(watermark_art).rounded_rectangle((4, 4, 116, 56), radius=12, fill=(20, 90, 220, 230))
        watermark_art.save(watermark_image)
        watermark_jpeg = directory / "watermark-image.jpg"
        Image.new("RGB", (120, 60), (30, 110, 230)).save(watermark_jpeg, quality=90)
        wide_photo = directory / "wide.png"
        Image.new("RGB", (9000, 20), (70, 140, 30)).save(wide_photo)

        base = os.environ.get("PAPERPLANE_LOCAL_MATRIX_BASE")
        app = None
        if not base:
            app, base, _identities = helper.start_server(directory / "server-data")
        try:
            for _ in range(600):
                try:
                    with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane test server did not start.")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page = context.new_page()
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                context.on("request", lambda request: evidence["server_job_posts"].append(request.url)
                           if request.method == "POST" and urlsplit(request.url).path == "/api/jobs" else None)

                # Each tool page must disclose whether browser processing is
                # genuinely supported and default supported routes to local.
                for operation, slug in slugs.items():
                    response = page.goto(f"{base}/{slug}", wait_until="domcontentloaded", timeout=60000)
                    page.locator("#client-privacy-toggle").wait_for(state="attached")
                    result = page.evaluate("""() => ({
                      localStorageChoice: localStorage.getItem('paperplane-pdf-processing-mode'),
                      checked: document.querySelector('#client-privacy-toggle').checked,
                      disabled: document.querySelector('#client-privacy-toggle').disabled,
                      label: document.querySelector('#client-privacy-toggle').getAttribute('aria-label'),
                      mode: document.querySelector('#privacy-mode-support').textContent.trim(),
                      support: document.querySelector('#privacy-mode-support').textContent.trim(),
                      bodyText: document.body.innerText
                    })""")
                    is_local = operation in ALL_LOCAL
                    row = {"operation": operation, "slug": slug, "http_status": response.status if response else None,
                           "is_local_supported": is_local, **{k: v for k, v in result.items() if k != "bodyText"}}
                    evidence["routes"].append(row)
                    row["passed"] = bool(
                        response and response.status == 200
                        and (result["checked"] if is_local else not result["checked"])
                        and (not result["disabled"] if operation in PDF_LOCAL else (result["disabled"] if operation in IMAGE_LOCAL or not is_local else False))
                        and ("not uploaded" in result["support"] if is_local else "uploads files" in result["support"])
                        and ("runs in your browser" in result["mode"] if is_local else "uploads files for temporary server processing" in result["mode"])
                    )

                def perform(operation: str, files: list[Path], output_name: str, setup=None) -> Path:
                    slug = slugs[operation]
                    response = page.goto(f"{base}/{slug}", wait_until="domcontentloaded", timeout=60000)
                    assert response and response.status == 200, f"route failed: {operation}"
                    switch = page.locator("#client-privacy-toggle")
                    assert switch.is_checked(), f"fresh profile did not default local: {operation}"
                    page.locator("#file-input").set_input_files([str(path) for path in files])
                    if setup:
                        setup()
                    worker_probe = None
                    if operation == "forms":
                        worker_probe = page.evaluate("""async () => {
                          try {
                            const result = await window.PaperplanePdfRuntime.transformLocalPdf(
                              'forms', state.files, {fields: JSON.parse(document.querySelector('#fields').value)});
                            return {ok:true, filename:result.filename, bytes:result.output.byteLength};
                          } catch (error) { return {ok:false, error:String(error && error.stack || error)}; }
                        }""")
                    page.wait_for_function("!document.querySelector('#run-button').disabled", timeout=20000)
                    before_posts = len(evidence["server_job_posts"])
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=20000)
                    with page.expect_download(timeout=20000) as download_event:
                        page.locator("#result-download-link").click()
                    result_path = directory / output_name
                    download_event.value.save_as(result_path)
                    evidence["local_operations"].append({
                        "operation": operation,
                        "output_name": download_event.value.suggested_filename,
                        "output_bytes": result_path.stat().st_size,
                        "server_job_posts_during_run": len(evidence["server_job_posts"]) - before_posts,
                        "content_checked": True,
                    })
                    assert len(evidence["server_job_posts"]) == before_posts, (
                        f"local run called /api/jobs: {operation}; "
                        f"visible toast={page.locator('.toast-notice').inner_text() if page.locator('.toast-notice').count() else 'none'}; "
                        f"result={page.locator('#result').inner_text() if page.locator('#result').count() else 'none'}; "
                        f"worker_probe={worker_probe}"
                    )
                    return result_path

                merged = perform("merge", [source, second], "local-merged.pdf")
                with fitz.open(merged) as document:
                    assert len(document) == 3 and "LOCAL-PAGE-ONE" in document[0].get_text() and "LOCAL-SECOND" in document[2].get_text()

                split = perform("split", [source], "local-split.zip", lambda: page.locator("#split_mode").select_option("all_pages"))
                from zipfile import ZipFile
                with ZipFile(split) as archive:
                    names = archive.namelist()
                    assert len(names) == 2
                    assert all(len(fitz.open(stream=archive.read(name), filetype="pdf")) == 1 for name in names)

                removed = perform("remove", [source], "local-removed.pdf", lambda: page.locator("#pages").fill("1"))
                with fitz.open(removed) as document:
                    assert len(document) == 1 and "LOCAL-PAGE-TWO" in document[0].get_text()

                rotated = perform("rotate", [source], "local-rotated.pdf", lambda: page.locator("#degrees").select_option("90"))
                with fitz.open(rotated) as document:
                    assert len(document) == 2 and document[0].rotation == 90 and "LOCAL-PAGE-ONE" in document[0].get_text()

                organized = perform("organize", [source], "local-organized.pdf", lambda: page.locator("#pages").fill("2,1"))
                with fitz.open(organized) as document:
                    assert len(document) == 2 and "LOCAL-PAGE-TWO" in document[0].get_text()

                filled = perform("forms", [fillable], "local-filled-forms.pdf",
                                 lambda: page.locator("#fields").fill('{"Applicant":"LOCAL-FORM-FILLED"}'))
                with fitz.open(filled) as document:
                    widgets = list(document[0].widgets() or [])
                    assert len(document) == 1 and "FLATTEN-SOURCE-MARKER" in document[0].get_text()
                    assert len(widgets) == 1 and widgets[0].field_value == "LOCAL-FORM-FILLED"
                    assert "FILLED-APPLICANT-VALUE" not in widgets[0].field_value

                updated_metadata = perform("metadata", [metadata_source], "local-updated-metadata.pdf",
                                            lambda: (page.locator("#title").fill("LOCAL UPDATED TITLE"),
                                                     page.locator("#author").fill("LOCAL UPDATED AUTHOR")))
                with fitz.open(updated_metadata) as document:
                    assert document.metadata["title"] == "LOCAL UPDATED TITLE"
                    assert document.metadata["author"] == "LOCAL UPDATED AUTHOR"
                    assert document.metadata["subject"] == "ORIGINAL METADATA SUBJECT"
                    assert document.metadata["creator"] == "ORIGINAL CREATOR"
                    assert "METADATA-SOURCE-MARKER" in document[0].get_text()
                metadata_json = json.loads(page.locator("#metadata-json-output").inner_text())
                assert metadata_json["title"] == "LOCAL UPDATED TITLE"
                assert metadata_json["author"] == "LOCAL UPDATED AUTHOR"
                assert metadata_json["subject"] == "ORIGINAL METADATA SUBJECT"
                assert page.locator("#metadata-json-export-btn").is_enabled()

                flattened = perform("flatten", [fillable], "local-flattened.pdf")
                with fitz.open(flattened) as document:
                    assert len(document) == 1
                    assert "FLATTEN-SOURCE-MARKER" in document[0].get_text()
                    assert "FILLED-APPLICANT-VALUE" in document[0].get_text()
                    assert not list(document[0].widgets() or [])

                extracted = perform("pdf_to_text", [source], "local-extracted.txt")
                extracted_text = extracted.read_text(encoding="utf-8")
                assert "Page 1" in extracted_text and "LOCAL-PAGE-ONE" in extracted_text
                assert "Page 2" in extracted_text and "LOCAL-PAGE-TWO" in extracted_text

                jpg_dpi = 300 if round_id and "round2" in round_id else 150
                jpg_archive = perform("pdf_to_jpg", [source], "local-pages-jpg.zip",
                                      lambda: page.locator("#dpi").select_option(str(jpg_dpi)))
                jpg_checks = []
                with fitz.open(source) as original, ZipFile(jpg_archive) as archive:
                    assert archive.namelist() == ["page_001.jpg", "page_002.jpg"]
                    for index, name in enumerate(archive.namelist()):
                        with Image.open(io.BytesIO(archive.read(name))) as image:
                            exported = image.convert("RGB")
                            assert exported.size == ((1250, 834) if jpg_dpi == 300 else (625, 417))
                            reference = original[index].get_pixmap(dpi=jpg_dpi, alpha=False)
                            expected = Image.frombytes("RGB", [reference.width, reference.height], reference.samples)
                            assert expected.size == exported.size
                            mean_difference = ImageStat.Stat(ImageChops.difference(exported, expected)).mean[0]
                            assert mean_difference < 5
                            assert ImageChops.difference(exported, Image.new("RGB", exported.size, "white")).getbbox()
                            jpg_checks.append({"name": name, "dimensions": exported.size,
                                               "reference_mean_red_difference": round(mean_difference, 3)})
                evidence["pdf_to_jpg"] = {"selected_dpi": jpg_dpi, "archive_bytes": jpg_archive.stat().st_size,
                                          "images": jpg_checks}

                numbered = perform("page_numbers", [source], "local-page-numbered.pdf",
                                   lambda: (page.locator("#position").select_option(label="Footer right"),
                                            page.locator("#format").select_option(label="Page {n} of {total}")))
                with fitz.open(numbered) as document:
                    assert len(document) == 2
                    assert "Page 1 of 2" in document[0].get_text()
                    assert "Page 2 of 2" in document[1].get_text()
                    assert "LOCAL-PAGE-ONE" in document[0].get_text()
                    assert "LOCAL-PAGE-TWO" in document[1].get_text()

                cropped = perform("crop", [source], "local-cropped.pdf",
                                  lambda: (page.locator("#left").fill("10"), page.locator("#top").fill("15"),
                                           page.locator("#right").fill("20"), page.locator("#bottom").fill("25")))
                with fitz.open(cropped) as document:
                    assert len(document) == 2
                    for crop_page, marker in zip(document, ("LOCAL-PAGE-ONE", "LOCAL-PAGE-TWO")):
                        assert abs(crop_page.rect.width - 270) < 0.1
                        assert abs(crop_page.rect.height - 160) < 0.1
                        assert marker in crop_page.get_text()

                stamp_page = 1 if round_id and "round2" in round_id else 2
                stamp_label = "LOCAL-STAMP-FIRST" if stamp_page == 1 else "LOCAL-STAMP-SECOND"
                stamp_x, stamp_y = (40, 100) if stamp_page == 1 else (90, 110)
                stamped = perform("edit", [source], "local-text-stamped.pdf",
                                  lambda: (page.locator("#text").fill(stamp_label),
                                           page.locator("#page").fill(str(stamp_page)),
                                           page.locator("#x").fill(str(stamp_x)),
                                           page.locator("#y").fill(str(stamp_y))))
                with fitz.open(stamped) as document:
                    assert len(document) == 2
                    assert "LOCAL-PAGE-ONE" in document[0].get_text()
                    assert "LOCAL-PAGE-TWO" in document[1].get_text()
                    assert stamp_label in document[stamp_page - 1].get_text()
                    assert stamp_label not in document[2 - stamp_page].get_text()
                    stamp_rects = document[stamp_page - 1].search_for(stamp_label)
                    assert len(stamp_rects) == 1
                    assert abs(stamp_rects[0].x0 - stamp_x) <= 2
                    assert stamp_y - 20 <= stamp_rects[0].y0 <= stamp_y + 2
                    evidence["edit_stamp"] = {"target_page": stamp_page, "text": stamp_label,
                                               "rect": list(stamp_rects[0])}

                page.locator("#page").fill("999")
                before_invalid_posts = len(evidence["server_job_posts"])
                page.locator("#run-button").click()
                invalid_dialog = page.locator("dialog.app-confirm-dialog")
                invalid_dialog.wait_for(state="visible", timeout=10000)
                assert "selected page does not exist" in invalid_dialog.inner_text().lower()
                invalid_dialog.locator(".app-confirm-cancel").click()
                assert len(evidence["server_job_posts"]) == before_invalid_posts
                evidence["edit_stamp"]["invalid_page_rejected_without_upload"] = True

                rotated_stamp = perform("edit", [rotated], "local-rotated-text-stamped.pdf",
                                        lambda: (page.locator("#text").fill("ROTATED-STAMP-CHECK"),
                                                 page.locator("#page").fill("2"),
                                                 page.locator("#x").fill("90"),
                                                 page.locator("#y").fill("110")))
                with fitz.open(rotated_stamp) as document, fitz.open(rotated) as original_rotated:
                    assert document[1].rotation == 90
                    assert "ROTATED-STAMP-CHECK" in document[1].get_text()
                    assert "LOCAL-PAGE-TWO" in document[1].get_text()
                    rotated_rect = document[1].search_for("ROTATED-STAMP-CHECK")
                    assert len(rotated_rect) == 1 and rotated_rect[0].intersects(document[1].rect)
                    evidence["edit_stamp"]["rotated_page_rect"] = list(rotated_rect[0])
                    before_pix = original_rotated[1].get_pixmap(alpha=False)
                    after_pix = document[1].get_pixmap(alpha=False)
                    before_image = Image.frombytes("RGB", [before_pix.width, before_pix.height], before_pix.samples)
                    after_image = Image.frombytes("RGB", [after_pix.width, after_pix.height], after_pix.samples)
                    visible_difference = ImageChops.difference(before_image, after_image).getbbox()
                    assert visible_difference, "rotated page stamp was extractable but not visible"
                    evidence["edit_stamp"]["rotated_visible_pixels_box"] = visible_difference

                typed_signature = perform("sign", [source], "local-typed-signature.pdf",
                                          lambda: page.locator("#signature").fill("LOCAL TYPED SIGNER"))
                with fitz.open(typed_signature) as document:
                    assert len(document) == 2
                    assert "LOCAL TYPED SIGNER" in document[0].get_text()
                    assert "LOCAL-PAGE-ONE" in document[0].get_text()
                    assert "LOCAL-PAGE-TWO" in document[1].get_text()
                    assert "LOCAL TYPED SIGNER" not in document[1].get_text()

                def draw_local_signature(background: str = "unknown") -> None:
                    page.locator("#signature").fill("LOCAL DRAWN SIGNER")
                    page.locator("#mark_background").select_option(background)
                    canvas = page.locator("#sign-draw-canvas")
                    canvas.scroll_into_view_if_needed()
                    bounds = canvas.bounding_box()
                    assert bounds
                    page.mouse.move(bounds["x"] + 40, bounds["y"] + 90)
                    page.mouse.down()
                    page.mouse.move(bounds["x"] + 150, bounds["y"] + 35, steps=8)
                    page.mouse.move(bounds["x"] + 260, bounds["y"] + 90, steps=8)
                    page.mouse.up()
                    assert page.locator("#signature_data").input_value().startswith("data:image/png;base64,")

                drawn_signature = perform("sign", [source], "local-drawn-signature.pdf", draw_local_signature)
                with fitz.open(drawn_signature) as document, fitz.open(source) as original:
                    assert len(document) == 2
                    assert "LOCAL DRAWN SIGNER" in document[0].get_text()
                    assert "LOCAL-PAGE-ONE" in document[0].get_text()
                    assert "LOCAL-PAGE-TWO" in document[1].get_text()
                    assert document[0].get_images(), "drawn signature image missing from PDF"
                    before_pix = original[0].get_pixmap(alpha=False)
                    after_pix = document[0].get_pixmap(alpha=False)
                    before_image = Image.frombytes("RGB", [before_pix.width, before_pix.height], before_pix.samples)
                    after_image = Image.frombytes("RGB", [after_pix.width, after_pix.height], after_pix.samples)
                    signature_difference = ImageChops.difference(before_image, after_image).getbbox()
                    assert signature_difference, "drawn signature did not change rendered pixels"
                    evidence["signatures"] = {"typed_signer_extractable": True,
                                              "drawn_signer_extractable": True,
                                              "drawn_image_embedded": True,
                                              "drawn_visible_pixels_box": signature_difference}

                rotated_signature = perform("sign", [rotated], "local-rotated-signature.pdf",
                                            lambda: page.locator("#signature").fill("ROTATED SIGNER"))
                with fitz.open(rotated_signature) as document, fitz.open(rotated) as original_rotated:
                    assert document[0].rotation == 90
                    assert "ROTATED SIGNER" in document[0].get_text()
                    before_pix = original_rotated[0].get_pixmap(alpha=False)
                    after_pix = document[0].get_pixmap(alpha=False)
                    before_image = Image.frombytes("RGB", [before_pix.width, before_pix.height], before_pix.samples)
                    after_image = Image.frombytes("RGB", [after_pix.width, after_pix.height], after_pix.samples)
                    assert ImageChops.difference(before_image, after_image).getbbox()
                    evidence["signatures"]["rotated_signature_visible"] = True

                dark_signature = perform("sign", [dark_source], "local-dark-signature.pdf",
                                         lambda: draw_local_signature("dark"))
                with fitz.open(dark_signature) as document:
                    assert document[0].get_images()
                    pixmap = document[0].get_pixmap(alpha=False)
                    image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                    mark_area = image.crop((60, 90, 260, 170))
                    bright_pixels = sum(1 for y in range(mark_area.height) for x in range(mark_area.width)
                                        if all(channel > 220 for channel in mark_area.getpixel((x, y))))
                    assert bright_pixels > 20, "drawn signature lacks a visible light edge on dark paper"
                    evidence["signatures"]["dark_background_bright_outline_pixels"] = bright_pixels

                watermarked = perform("watermark", [source], "local-watermarked.pdf",
                                       lambda: (page.locator("#text").fill("LOCAL WATERMARK"),
                                                page.locator("#opacity").fill("0.35"),
                                                page.locator("#mark_color").fill("#cc2200")))
                with fitz.open(watermarked) as document:
                    assert len(document) == 2
                    assert all("LOCAL WATERMARK" in item.get_text() for item in document)
                    assert all(marker in document[index].get_text()
                               for index, marker in enumerate(("LOCAL-PAGE-ONE", "LOCAL-PAGE-TWO")))

                image_watermarked = perform("watermark", [source], "local-image-watermarked.pdf",
                                            lambda: (page.locator("#watermark_image_file").set_input_files(str(watermark_image)),
                                                     page.locator("#text").fill(""),
                                                     page.locator("#opacity").fill("0.4")))
                image_watermark_pixels = []
                with fitz.open(image_watermarked) as document:
                    assert document.page_count == 2
                    for index, pdf_page in enumerate(document):
                        assert ("LOCAL-PAGE-ONE" if index == 0 else "LOCAL-PAGE-TWO") in pdf_page.get_text()
                        assert pdf_page.get_images(), f"image watermark missing from page {index + 1}"
                        pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                        image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                        center = image.getpixel((pixmap.width // 2, pixmap.height // 2))
                        assert center[2] > center[0] + 15, (index + 1, center)
                        image_watermark_pixels.append(center)
                jpeg_watermarked = perform("watermark", [source], "local-jpeg-watermarked.pdf",
                                           lambda: (page.locator("#watermark_image_file").set_input_files(str(watermark_jpeg)),
                                                    page.locator("#text").fill(""),
                                                    page.locator("#opacity").fill("0.4")))
                jpeg_watermark_pixels = []
                with fitz.open(jpeg_watermarked) as document:
                    assert document.page_count == 2
                    for index, pdf_page in enumerate(document):
                        assert ("LOCAL-PAGE-ONE" if index == 0 else "LOCAL-PAGE-TWO") in pdf_page.get_text()
                        assert pdf_page.get_images(), f"JPEG image watermark missing from page {index + 1}"
                        pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                        image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                        center = image.getpixel((pixmap.width // 2, pixmap.height // 2))
                        assert center[2] > center[0] + 15, (index + 1, center)
                        jpeg_watermark_pixels.append(center)
                evidence["image_watermark"] = {
                    "pages": 2,
                    "embedded_image_on_each_page": True,
                    "source_text_preserved": True,
                    "center_pixels": image_watermark_pixels,
                    "png_download_content_checked": True,
                    "jpeg_download_content_checked": True,
                    "jpeg_center_pixels": jpeg_watermark_pixels,
                    "server_job_posts": 0,
                    "content_checked": True,
                }

                for page_size, expected_size in (("a4", (595.28, 841.89)), ("letter", (612, 792)),
                                                 ("original", (34.56, 17.28))):
                    scanned = perform("scan_pdf", [photo_a, photo_b], f"local-scan-{page_size}.pdf",
                                      lambda page_size=page_size: page.locator("#page_size").select_option(page_size))
                    with fitz.open(scanned) as document:
                        assert len(document) == 2
                        page_sizes = ((34.56, 17.28), (23.04, 11.52)) if page_size == "original" else (expected_size[::-1], expected_size[::-1])
                        for pdf_page, page_expected_size in zip(document, page_sizes):
                            assert abs(pdf_page.rect.width - page_expected_size[0]) < 0.2, (page_size, pdf_page.rect, page_expected_size)
                            assert abs(pdf_page.rect.height - page_expected_size[1]) < 0.2, (page_size, pdf_page.rect, page_expected_size)
                        if page_size != "original":
                            for pdf_page, expected in zip(document, ((180, 20, 40), (20, 40, 180))):
                                pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                                pixel = pixmap.pixel(pixmap.width // 2, pixmap.height // 2)
                                assert all(abs(pixel[channel] - expected[channel]) < 45 for channel in range(3)), (page_size, pixel, expected)

                wide_scan = perform("scan_pdf", [wide_photo], "local-wide-scan.pdf",
                                    lambda: page.locator("#page_size").select_option("original"))
                with fitz.open(wide_scan) as document:
                    assert len(document) == 1
                    assert abs(document[0].rect.width - 3240) < 0.2
                    assert abs(document[0].rect.height - 7.2) < 0.2
                    assert document[0].get_images(), "downsampled photo missing from output"

                converted_images = perform("jpg_to_pdf", [photo_a, photo_b], "local-images-to-pdf.pdf")
                with fitz.open(converted_images) as document:
                    assert len(document) == 2
                    assert all(abs(pdf_page.rect.width - 841.89) < 0.2 and abs(pdf_page.rect.height - 595.28) < 0.2
                               for pdf_page in document)
                    for pdf_page, expected in zip(document, ((180, 20, 40), (20, 40, 180))):
                        pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                        pixel = pixmap.pixel(pixmap.width // 2, pixmap.height // 2)
                        assert all(abs(pixel[channel] - expected[channel]) < 45 for channel in range(3)), (pixel, expected)

                compressed = perform("photo_compress", [photo_a], "local-compressed.jpg")
                resized = perform("photo_resize", [photo_a], "local-resized.jpg", lambda: page.locator("#preset").select_option("passport"))
                merged_photos = perform("photo_merge", [photo_a, photo_b], "local-photo-merge.jpg")
                exam_photo = perform("photo_resizer", [photo_a], "local-exam-photo.jpg")
                for image_path in (compressed, resized, merged_photos, exam_photo):
                    with Image.open(image_path) as image:
                        image.verify()
                with Image.open(resized) as image:
                    assert image.size == (350, 450)
                with Image.open(exam_photo) as image:
                    assert image.size == (350, 450)

                # The explicit user choice survives reload in a fresh browser
                # profile, and returning to local mode remains the default.
                page.goto(f"{base}/{slugs['merge']}", wait_until="domcontentloaded")
                toggle = page.locator("#client-privacy-toggle")
                assert toggle.is_checked()
                toggle_label = page.locator("label.toggle-switch-sm").filter(has=toggle)
                toggle_label.click()
                assert not toggle.is_checked()
                page.reload(wait_until="domcontentloaded")
                assert not toggle.is_checked()
                assert "uploads files for temporary server processing" in page.locator("#privacy-mode-support").inner_text()
                evidence["preference_persistence"] = {"server_choice_survived_reload": True}
                toggle_label.click()
                assert toggle.is_checked()
                page.reload(wait_until="domcontentloaded")
                assert toggle.is_checked()
                assert "runs in your browser" in page.locator("#privacy-mode-support").inner_text()
                evidence["preference_persistence"]["local_choice_survived_reload"] = True

                # Inject a deterministic local worker failure. The browser must
                # communicate the quota consequence, retry once through the
                # server path, and preserve the saved local preference.
                injected_failure = page.evaluate("""() => {
                  const runtime = window.PaperplanePdfRuntime;
                  Object.defineProperty(window, 'PaperplanePdfRuntime', {
                    configurable: true,
                    value: { ...runtime, transformLocalPdf: async () => {
                      throw new Error('controlled local processing failure');
                    }}
                  });
                  return window.PaperplanePdfRuntime.transformLocalPdf.toString();
                }""")
                assert "controlled local processing failure" in injected_failure
                before_fallback_posts = len(evidence["server_job_posts"])
                page.locator("#file-input").set_input_files([str(source), str(second)])
                page.locator("#run-button").click()
                dialog = page.locator("dialog.app-confirm-dialog")
                dialog.wait_for(state="visible", timeout=10000)
                assert "daily server allowance" in dialog.inner_text()
                assert "upload the selected files" in dialog.inner_text()
                dialog.locator(".app-confirm-cancel").click()
                page.get_by_text("No files were uploaded.", exact=False).wait_for(state="visible")
                assert len(evidence["server_job_posts"]) == before_fallback_posts
                assert page.locator("#client-privacy-toggle").is_checked()
                page.locator("#run-button").click()
                dialog.wait_for(state="visible", timeout=10000)
                dialog.locator(".app-confirm-accept").click()
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=25000)
                with page.expect_download(timeout=20000) as fallback_download_event:
                    page.locator("#result-download-link").click()
                fallback_path = directory / "fallback-merged.pdf"
                fallback_download_event.value.save_as(fallback_path)
                with fitz.open(fallback_path) as document:
                    assert len(document) == 3
                    assert "LOCAL-PAGE-ONE" in document[0].get_text()
                    assert "LOCAL-SECOND" in document[2].get_text()
                assert len(evidence["server_job_posts"]) - before_fallback_posts == 1
                assert page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')") == "local"
                evidence["local_failure_fallback"] = {
                    "controlled_local_error": True,
                    "quota_disclosure_visible": True,
                    "cancel_did_not_upload": True,
                    "upload_requires_confirmation": True,
                    "server_job_posts": len(evidence["server_job_posts"]) - before_fallback_posts,
                    "output_content_checked": True,
                    "saved_local_preference_preserved": True,
                    "mode_after_server_completion": page.locator("#privacy-mode-support").inner_text().strip(),
                }
                assert "runs in your browser" in evidence["local_failure_fallback"]["mode_after_server_completion"]

                # Simulate an asynchronous selection change while consent is
                # open. The accepted consent applies only to the original files.
                page.locator("#run-button").click()
                dialog.wait_for(state="visible", timeout=10000)
                before_changed_selection = len(evidence["server_job_posts"])
                page.evaluate("state.files.reverse()")
                dialog.locator(".app-confirm-accept").click()
                dialog.wait_for(state="detached", timeout=10000)
                page.wait_for_timeout(1000)
                assert len(evidence["server_job_posts"]) == before_changed_selection
                assert page.locator("#client-privacy-toggle").is_checked()
                evidence["local_failure_fallback"]["changed_selection_did_not_upload"] = True

                browser.close()
            evidence["route_count"] = len(evidence["routes"])
            evidence["route_failures"] = [row for row in evidence["routes"] if not row.get("passed")]
            evidence["local_operation_count"] = len(evidence["local_operations"])
            evidence["local_operation_outputs_checked"] = (
                {row["operation"] for row in evidence["local_operations"]} == ALL_LOCAL
                and all(row["content_checked"] for row in evidence["local_operations"])
            )
            evidence["all_local_runs_stayed_off_api_jobs"] = all(
                row["server_job_posts_during_run"] == 0 for row in evidence["local_operations"]
            )
            evidence["server_job_posts"] = evidence["server_job_posts"]
            evidence["result"] = bool(
                evidence["route_count"] == 44 and not evidence["route_failures"]
                and evidence["local_operation_outputs_checked"] and evidence["all_local_runs_stayed_off_api_jobs"]
                and evidence["preference_persistence"].get("server_choice_survived_reload")
                and evidence["preference_persistence"].get("local_choice_survived_reload")
                and evidence["local_failure_fallback"].get("server_job_posts") == 1
                and evidence["local_failure_fallback"].get("output_content_checked")
                and evidence["local_failure_fallback"].get("saved_local_preference_preserved")
                and evidence["local_failure_fallback"].get("changed_selection_did_not_upload")
                and not evidence["page_errors"]
            )
            (report_dir / "browser-id37-id242-local-processing.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            if round_id:
                (report_dir / f"browser-id37-local-text-round{round_id}.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if not evidence["result"]:
                raise SystemExit(1)
        finally:
            if app:
                app.terminate()
                try:
                    app.wait(timeout=8)
                except Exception:
                    app.kill()


if __name__ == "__main__":
    main()
