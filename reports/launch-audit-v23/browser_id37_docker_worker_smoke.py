"""Content-check browser-local Forms and Metadata in the production Docker image."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

import fitz
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v23"
BASE = "http://127.0.0.1:18502"
tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))
slugs = next(ast.literal_eval(node.value) for node in tree.body
             if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id == "OPERATION_SLUGS" for target in node.targets))
results = []
errors = []
jobs = []

with TemporaryDirectory(prefix="paperplane-docker-worker-smoke-") as temporary:
    temp = Path(temporary)
    fillable = temp / "fillable.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_text((40, 45), "DOCKER-FORMS-MARKER", fontsize=14)
        widget = fitz.Widget()
        widget.field_name = "Applicant"
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.rect = fitz.Rect(40, 75, 250, 105)
        widget.field_value = "Original"
        page.add_widget(widget)
        doc.save(fillable)

    metadata = temp / "metadata.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_text((40, 70), "DOCKER-METADATA-MARKER", fontsize=14)
        doc.set_metadata({"title": "Existing Title", "author": "Existing Author",
                          "subject": "Keep Subject", "creator": "Keep Creator"})
        doc.save(metadata)

    scan_images = [temp / "scan-red.png", temp / "scan-blue.png"]
    Image.new("RGB", (80, 40), (190, 25, 35)).save(scan_images[0])
    Image.new("RGB", (40, 80), (25, 45, 190)).save(scan_images[1])
    wide_scan_image = temp / "wide-scan.png"
    Image.new("RGB", (9000, 20), (70, 140, 30)).save(wide_scan_image)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
        page = context.new_page()
        page.on("pageerror", lambda err: errors.append(str(err)))
        context.on("request", lambda req: jobs.append(req.url)
                   if req.method == "POST" and req.url.split("/", 3)[-1].split("?", 1)[0] == "api/jobs" else None)

        page.goto(f"{BASE}/{slugs['forms']}", wait_until="domcontentloaded")
        assert page.locator("#client-privacy-toggle").is_checked()
        page.locator("#file-input").set_input_files(str(fillable))
        page.locator("#fields").fill('{"Applicant":"DOCKER-FORM-FILLED"}')
        page.locator("#run-button").click()
        page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
        with page.expect_download() as event:
            page.locator("#result-download-link").click()
        form_path = temp / event.value.suggested_filename
        event.value.save_as(form_path)
        with fitz.open(form_path) as doc:
            form_fields = {field.field_name: field.field_value for field in (doc[0].widgets() or [])}
            assert "DOCKER-FORMS-MARKER" in doc[0].get_text()
            assert form_fields.get("Applicant") == "DOCKER-FORM-FILLED", form_fields
        results.append({"operation": "fill_forms", "output_bytes": form_path.stat().st_size,
                        "field_value_checked": True, "source_text_checked": True})

        page.goto(f"{BASE}/{slugs['metadata']}", wait_until="domcontentloaded")
        assert page.locator("#client-privacy-toggle").is_checked()
        page.locator("#file-input").set_input_files(str(metadata))
        page.locator("#title").fill("Docker Updated Title")
        page.locator("#author").fill("Docker Updated Author")
        page.locator("#run-button").click()
        page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
        page.locator("#metadata-json-result").wait_for(state="visible")
        json_text = page.locator("#metadata-json-output").inner_text()
        json_obj = json.loads(json_text)
        assert json_obj["title"] == "Docker Updated Title" and json_obj["author"] == "Docker Updated Author"
        assert json_obj["subject"] == "Keep Subject" and json_obj["creator"] == "Keep Creator"
        with page.expect_download() as event:
            page.locator("#result-download-link").click()
        metadata_path = temp / event.value.suggested_filename
        event.value.save_as(metadata_path)
        with fitz.open(metadata_path) as doc:
            saved = doc.metadata
            assert saved["title"] == "Docker Updated Title" and saved["author"] == "Docker Updated Author"
            assert saved["subject"] == "Keep Subject" and saved["creator"] == "Keep Creator"
            assert "DOCKER-METADATA-MARKER" in doc[0].get_text()
        results.append({"operation": "edit_metadata", "output_bytes": metadata_path.stat().st_size,
                        "updated_json_checked": True, "preserved_metadata_checked": True, "source_text_checked": True})

        page.goto(f"{BASE}/{slugs['crop']}", wait_until="domcontentloaded")
        assert page.locator("#client-privacy-toggle").is_checked()
        page.locator("#file-input").set_input_files(str(metadata))
        page.locator("#left").fill("10")
        page.locator("#top").fill("15")
        page.locator("#right").fill("20")
        page.locator("#bottom").fill("25")
        page.locator("#run-button").click()
        page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
        with page.expect_download() as event:
            page.locator("#result-download-link").click()
        crop_path = temp / event.value.suggested_filename
        event.value.save_as(crop_path)
        with fitz.open(crop_path) as doc:
            assert len(doc) == 1
            assert abs(doc[0].rect.width - 270) < 0.1 and abs(doc[0].rect.height - 160) < 0.1
            assert "DOCKER-METADATA-MARKER" in doc[0].get_text()
        results.append({"operation": "crop", "output_bytes": crop_path.stat().st_size,
                        "page_dimensions_checked": [270, 160], "source_text_checked": True})

        page.goto(f"{BASE}/{slugs['watermark']}", wait_until="domcontentloaded")
        assert page.locator("#client-privacy-toggle").is_checked()
        page.locator("#file-input").set_input_files(str(metadata))
        page.locator("#text").fill("DOCKER LOCAL WATERMARK")
        page.locator("#opacity").fill("0.35")
        page.locator("#mark_color").fill("#cc2200")
        page.locator("#run-button").click()
        page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
        with page.expect_download() as event:
            page.locator("#result-download-link").click()
        watermark_path = temp / event.value.suggested_filename
        event.value.save_as(watermark_path)
        with fitz.open(watermark_path) as doc:
            assert len(doc) == 1 and "DOCKER LOCAL WATERMARK" in doc[0].get_text()
            assert "DOCKER-METADATA-MARKER" in doc[0].get_text()
            pixmap = doc[0].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
            samples = pixmap.samples
            red_pixels = sum(1 for i in range(0, len(samples), pixmap.n)
                             if samples[i] > samples[i + 1] + 2 and samples[i] > samples[i + 2] + 4)
            assert red_pixels > 5
        results.append({"operation": "watermark_text", "output_bytes": watermark_path.stat().st_size,
                        "watermark_text_checked": True, "configured_color_pixels": red_pixels})

        page.goto(f"{BASE}/{slugs['scan_pdf']}", wait_until="domcontentloaded")
        assert page.locator("#client-privacy-toggle").is_checked()
        page.locator("#file-input").set_input_files([str(path) for path in scan_images])
        page.locator("#page_size").select_option("letter")
        page.locator("#run-button").click()
        page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
        with page.expect_download() as event:
            page.locator("#result-download-link").click()
        scan_path = temp / event.value.suggested_filename
        event.value.save_as(scan_path)
        with fitz.open(scan_path) as doc:
            assert len(doc) == 2
            expected_sizes = ((792, 612), (612, 792))
            assert all(abs(p.rect.width - size[0]) < .1 and abs(p.rect.height - size[1]) < .1
                       for p, size in zip(doc, expected_sizes))
            for scan_page, color in zip(doc, ((190, 25, 35), (25, 45, 190))):
                pix = scan_page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                pixel = pix.pixel(pix.width // 2, pix.height // 2)
                assert all(abs(pixel[index] - color[index]) < 50 for index in range(3)), (pixel, color)
        results.append({"operation": "scan_to_pdf", "output_bytes": scan_path.stat().st_size,
                        "pages": 2, "letter_dimensions_checked": True, "sampled_image_colors_checked": True})

        page.goto(f"{BASE}/{slugs['scan_pdf']}", wait_until="domcontentloaded")
        page.locator("#file-input").set_input_files(str(wide_scan_image))
        page.locator("#page_size").select_option("original")
        page.locator("#run-button").click()
        page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
        with page.expect_download() as event:
            page.locator("#result-download-link").click()
        wide_path = temp / event.value.suggested_filename
        event.value.save_as(wide_path)
        with fitz.open(wide_path) as doc:
            assert len(doc) == 1 and abs(doc[0].rect.width - 3240) < .2
            assert abs(doc[0].rect.height - 7.2) < .2 and doc[0].get_images()
        results.append({"operation": "wide_scan_original", "source_pixels": [9000, 20],
                        "page_points": [3240, 7.2], "embedded_image_checked": True})

        page.goto(f"{BASE}/{slugs['jpg_to_pdf']}", wait_until="domcontentloaded")
        assert page.locator("#client-privacy-toggle").is_checked()
        page.locator("#file-input").set_input_files([str(path) for path in scan_images])
        page.locator("#run-button").click()
        page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
        with page.expect_download() as event:
            page.locator("#result-download-link").click()
        images_pdf_path = temp / event.value.suggested_filename
        event.value.save_as(images_pdf_path)
        with fitz.open(images_pdf_path) as doc:
            assert len(doc) == 2
            expected_sizes = ((841.89, 595.28), (595.28, 841.89))
            assert all(abs(p.rect.width - size[0]) < .1 and abs(p.rect.height - size[1]) < .1
                       for p, size in zip(doc, expected_sizes))
            for converted_page, color in zip(doc, ((190, 25, 35), (25, 45, 190))):
                pix = converted_page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                pixel = pix.pixel(pix.width // 2, pix.height // 2)
                assert all(abs(pixel[index] - color[index]) < 50 for index in range(3)), (pixel, color)
        results.append({"operation": "jpg_png_to_pdf", "output_bytes": images_pdf_path.stat().st_size,
                        "pages": 2, "a4_auto_orientation_checked": True, "sampled_image_colors_checked": True})
        assert not jobs, jobs
        browser.close()

assert not errors, errors
report = {"base": BASE, "results": results, "api_job_posts": jobs, "page_errors": errors}
(OUT / "browser-id37-docker-codex-final-v111.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
