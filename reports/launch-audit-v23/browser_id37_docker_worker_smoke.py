"""Content-check browser-local Forms and Metadata in the production Docker image."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

import fitz
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
        assert not jobs, jobs
        browser.close()

assert not errors, errors
report = {"base": BASE, "results": results, "api_job_posts": jobs, "page_errors": errors}
(OUT / "browser-id37-docker-worker-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
