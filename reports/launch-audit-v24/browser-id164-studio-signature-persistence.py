"""Verify Studio signature annotations survive reload and remain exportable."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id164-studio-signature-persistence.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id164-") as temp_name:
        temp = Path(temp_name)
        source = temp / "id164-source.pdf"
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((72, 100), "ID164 persistence source marker")
            document.save(source)
        app, base, _identities = helper.start_server(temp / "data")
        evidence = {"page_errors": [], "console_errors": []}
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local Paperplane server exited before startup")
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local Paperplane server did not start")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page = context.new_page()
                page.set_default_timeout(15000)
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: evidence["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                page.goto(base + "/rotate-pdf", wait_until="domcontentloaded")
                source_bytes = source.read_bytes()
                source_b64 = __import__("base64").b64encode(source_bytes).decode("ascii")
                page.evaluate("""b64 => {
                  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                  const blob = new Blob([bytes], {type: 'application/pdf'});
                  window.showDownloadResult({output_name: 'id164-source.pdf', output_size: blob.size, page_count: 1}, URL.createObjectURL(blob), {blob});
                }""", source_b64)
                page.locator("#result-view-studio-btn").click()
                page.wait_for_function("state.studio.pdfDoc && state.studio.totalCount === 1")
                page.wait_for_function("window.PaperplaneEditor?.canvas && document.querySelector('#pdf-canvas')?.width > 0")
                page.locator("#tool-sig-btn").click()
                page.wait_for_function("window.PaperplaneEditor?._activeTool === 'signature'")
                edit_canvas = page.locator("#pdf-draw-canvas")
                edit_box = edit_canvas.bounding_box()
                if not edit_box:
                    raise AssertionError("Studio edit canvas is not visible")
                page.mouse.click(edit_box["x"] + edit_box["width"] * 0.55, edit_box["y"] + edit_box["height"] * 0.55)
                page.locator("#editor-signature-modal:not([hidden])").wait_for()
                canvas = page.locator("#editor-sig-canvas")
                box = canvas.bounding_box()
                if not box:
                    raise AssertionError("Signature drawing canvas is not visible")
                page.mouse.move(box["x"] + box["width"] * 0.15, box["y"] + box["height"] * 0.68)
                page.mouse.down()
                for ratio_x, ratio_y in ((0.28, 0.44), (0.4, 0.7), (0.55, 0.32), (0.68, 0.62), (0.82, 0.4)):
                    page.mouse.move(box["x"] + box["width"] * ratio_x, box["y"] + box["height"] * ratio_y, steps=4)
                page.mouse.up()
                page.locator("#editor-sig-place-btn").click()
                page.wait_for_function("window.PaperplaneEditor?.editorState.serialize().some(item => item.type === 'signature' && item.imageData?.startsWith('data:image/png;base64,'))")
                page.wait_for_timeout(500)
                evidence["before_reload"] = page.evaluate("""() => ({
                  object_count: window.PaperplaneEditor.editorState.serialize().length,
                  signature_count: window.PaperplaneEditor.editorState.serialize().filter(item => item.type === 'signature').length,
                  unsaved_badge_visible: !document.querySelector('#editor-unsaved-badge')?.hidden,
                  storage_has_signature: window.PaperplaneEditor.editorState.serialize().some(item => item.type === 'signature' && item.imageData)
                })""")
                page.reload(wait_until="domcontentloaded")
                page.locator("#tab-studio-view").click()
                page.wait_for_function("state.studio.pdfDoc && state.studio.totalCount === 1")
                page.wait_for_function("window.PaperplaneEditor?.editorState.serialize().some(item => item.type === 'signature' && item.imageData?.startsWith('data:image/png;base64,'))")
                evidence["after_reload"] = page.evaluate("""() => ({
                  object_count: window.PaperplaneEditor.editorState.serialize().length,
                  signature_count: window.PaperplaneEditor.editorState.serialize().filter(item => item.type === 'signature').length,
                  signature_has_image: window.PaperplaneEditor.editorState.serialize().some(item => item.type === 'signature' && item.imageData?.startsWith('data:image/png;base64,')),
                  unsaved_badge_visible: !document.querySelector('#editor-unsaved-badge')?.hidden,
                  page_count: state.studio.totalCount
                })""")
                with page.expect_download(timeout=30000) as download_event:
                    page.locator("#save-studio-btn").click()
                downloaded = temp / "id164-exported.pdf"
                download_event.value.save_as(downloaded)
                with fitz.open(downloaded) as output:
                    evidence["export"] = {
                        "pages": output.page_count,
                        "embedded_images": sum(len(output_page.get_images(full=True)) for output_page in output),
                        "source_text_preserved": "ID164 persistence source marker" in output[0].get_text(),
                        "bytes": downloaded.stat().st_size,
                    }
                page.locator("#studio-clear-pdf-btn").click()
                page.locator(".app-confirm-accept").click()
                page.wait_for_function("!state.studio.pdfDoc && window.PaperplaneEditor.editorState.serialize().length === 0")
                evidence["clear_removed_edit_record"] = page.evaluate("""async () => {
                  const db = await openLocalWorkDb();
                  const key = `${localWorkScope()}:studio-edits`;
                  return await new Promise((resolve, reject) => {
                    const request = db.transaction('work', 'readonly').objectStore('work').get(key);
                    request.onsuccess = () => resolve(request.result === undefined);
                    request.onerror = () => reject(request.error);
                  });
                }""")
                page.reload(wait_until="domcontentloaded")
                page.locator("#tab-studio-view").click()
                page.wait_for_function("!state.studio.pdfDoc && window.PaperplaneEditor.editorState.serialize().length === 0")
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)
        evidence["overall"] = "passed" if (
            evidence.get("before_reload", {}).get("signature_count") == 1
            and evidence.get("after_reload", {}).get("signature_count") == 1
            and evidence.get("after_reload", {}).get("signature_has_image")
            and evidence.get("after_reload", {}).get("unsaved_badge_visible")
            and evidence.get("export", {}).get("pages") == 1
            and evidence.get("export", {}).get("embedded_images", 0) >= 1
            and evidence.get("export", {}).get("source_text_preserved")
            and evidence.get("clear_removed_edit_record") is True
            and not evidence["page_errors"] and not evidence["console_errors"]
        ) else "failed"
        OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        if evidence["overall"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
