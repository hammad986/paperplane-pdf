"""Check truthful browser/server processing controls and exercise local paths."""
from __future__ import annotations

import ast
import json
import socket
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from urllib.parse import urlsplit

import fitz
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
sys.path.insert(0, str(HELPER.parent))
import browser_acceptance_v14 as helper  # noqa: E402

PDF_LOCAL = {"merge", "split", "remove", "rotate", "organize", "forms", "flatten", "metadata", "pdf_to_text", "page_numbers", "crop"}
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
        photo_a = directory / "photo-a.png"
        photo_b = directory / "photo-b.png"
        Image.new("RGB", (96, 48), (180, 20, 40)).save(photo_a)
        Image.new("RGB", (64, 32), (20, 40, 180)).save(photo_b)

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
                    assert page.locator("#run-button").is_enabled(), f"run control disabled: {operation}"
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
            evidence["local_operation_outputs_checked"] = len(evidence["local_operations"]) == len(ALL_LOCAL)
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
            app.terminate()
            try:
                app.wait(timeout=8)
            except Exception:
                app.kill()


if __name__ == "__main__":
    main()
