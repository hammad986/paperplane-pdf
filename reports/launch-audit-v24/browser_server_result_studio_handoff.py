"""Reproduce v24 ID 360 for server-mode result -> Studio handoff."""
from __future__ import annotations

import base64
import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v24"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def pdf_text(path: Path) -> tuple[int, str]:
    with fitz.open(path) as document:
        return document.page_count, "\n".join(page.get_text() for page in document)


def main() -> None:
    evidence: dict = {"rounds": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id360-") as temp:
        root = Path(temp)
        app, base, _ = helper.start_server(root / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                for round_number in (1, 2):
                    fixture = root / f"server-result-round-{round_number}.pdf"
                    markers = [f"SERVER RESULT ROUND {round_number} PAGE {page}" for page in (1, 2)]
                    with fitz.open() as document:
                        for marker in markers:
                            document.new_page().insert_text((72, 72), marker)
                        document.save(fixture)
                    original_pages, original_text = pdf_text(fixture)

                    context = browser.new_context(
                        viewport={"width": 1366, "height": 900},
                        accept_downloads=True,
                    )
                    context.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode','server')")
                    page = context.new_page()
                    page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                    page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                    page.on("response", lambda response: evidence.setdefault("http_errors", []).append(
                        {"status": response.status, "url": response.url}
                    ) if response.status >= 400 else None)
                    response = page.goto(base + "/compress-pdf", wait_until="domcontentloaded", timeout=20000)
                    assert page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')") == "server"
                    page.locator("#file-input").set_input_files(str(fixture))
                    page.wait_for_function("state.files?.length === 1")
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=60000)
                    assert page.locator("#result-view-studio-btn").is_visible()

                    studio_before_download = None
                    if round_number == 2:
                        page.locator("#result-view-studio-btn").click()
                        page.wait_for_function(
                            "location.pathname === '/studio' && document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'",
                            timeout=45000,
                        )
                        page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent !== '0'", timeout=30000)
                        studio_before_download = page.evaluate("""async () => {
                          const file = window.PaperplaneEditor?.editorState?.sourceFile;
                          if (!file) return null;
                          const bytes = new Uint8Array(await file.arrayBuffer());
                          let binary = '';
                          for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
                          return {name: file.name, data: btoa(binary), pageCount: document.querySelector('#page-total-indicator')?.textContent};
                        }""")
                        assert studio_before_download, "Studio opened before the download but has no source file"
                        before_download_pdf = root / f"studio-before-download-round-{round_number}.pdf"
                        before_download_pdf.write_bytes(base64.b64decode(studio_before_download["data"]))
                        before_pages, before_text = pdf_text(before_download_pdf)
                        assert before_pages == original_pages and all(marker in before_text for marker in markers)
                        page.evaluate("switchWorkspaceView('desk')")
                        page.wait_for_function("state.activeView === 'desk'")
                        page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=10000)

                    with page.expect_download(timeout=30000) as download_info:
                        page.locator("#result-download-link").click()
                    download = download_info.value
                    downloaded_pdf = root / f"download-round-{round_number}.pdf"
                    download.save_as(downloaded_pdf)
                    output_pages, output_text = pdf_text(downloaded_pdf)
                    download_has_content = output_pages == original_pages and all(marker in output_text for marker in markers)

                    page.locator("#result-view-studio-btn").click()
                    try:
                        page.wait_for_function("location.pathname === '/studio'", timeout=12000)
                        page.wait_for_timeout(18000)
                    except Exception:
                        pass
                    state_snapshot = page.evaluate("""() => ({
                      pathname: location.pathname,
                      activeView: state.activeView,
                      operation: state.operation,
                      studioIsLoading: state.studio?.isLoading,
                      hasPdfDoc: !!state.studio?.pdfDoc,
                      studioPageCount: state.studio?.totalCount,
                      renderedCanvasCount: document.querySelectorAll('#studio-canvas-area canvas').length,
                      renderedFlag: document.querySelector('#pdf-canvas')?.dataset.rendered || null,
                      pageIndicator: document.querySelector('#page-total-indicator')?.textContent || null,
                      studioText: document.querySelector('#view-pdf-studio')?.innerText?.slice(0,1200) || '',
                      resultVisible: !document.querySelector('#result')?.hidden,
                      toast: document.querySelector('.toast-notice')?.innerText || ''
                    })""")
                    evidence["rounds"].append({
                        "round": round_number,
                        "state_snapshot": state_snapshot,
                        "studio_before_download_checked": studio_before_download is not None,
                    })
                    page.screenshot(path=str(OUT / f"id360-server-studio-debug-round-{round_number}.png"))
                    if state_snapshot["pathname"] != "/studio" or not state_snapshot["hasPdfDoc"]:
                        raise AssertionError(f"Server result did not load into Studio: {state_snapshot}")
                    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent !== '0'", timeout=30000)
                    studio_payload = page.evaluate("""async () => {
                      const file = window.PaperplaneEditor?.editorState?.sourceFile;
                      if (!file) return null;
                      const bytes = new Uint8Array(await file.arrayBuffer());
                      let binary = '';
                      for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
                      return {name: file.name, data: btoa(binary), pageCount: document.querySelector('#page-total-indicator')?.textContent};
                    }""")
                    assert studio_payload, f"Studio source missing in round {round_number}"
                    studio_pdf = root / f"studio-round-{round_number}.pdf"
                    studio_pdf.write_bytes(base64.b64decode(studio_payload["data"]))
                    studio_pages, studio_text = pdf_text(studio_pdf)
                    studio_has_content = studio_pages == original_pages and all(marker in studio_text for marker in markers)
                    evidence["rounds"][-1].update({
                        "round": round_number,
                        "http_status": response.status if response else None,
                        "processing_mode": page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')"),
                        "download_name": download.suggested_filename,
                        "download_pages": output_pages,
                        "download_content_checked": download_has_content,
                        "studio_route": page.url.endswith("/studio"),
                        "studio_pages": studio_pages,
                        "studio_source_name": studio_payload["name"],
                        "studio_content_checked": studio_has_content,
                        "page_errors_after_round": list(evidence["page_errors"]),
                    })
                    assert download_has_content, f"server output content check failed in round {round_number}"
                    assert studio_has_content, f"Studio opened stale or incomplete content in round {round_number}"
                    page.screenshot(path=str(OUT / f"id360-server-studio-round-{round_number}.png"))
                    context.close()
                browser.close()

            evidence["result"] = (
                len(evidence["rounds"]) == 2
                and all(item["http_status"] == 200 and item["processing_mode"] == "server"
                        and item["studio_route"] and item["download_content_checked"]
                        and item["studio_content_checked"] for item in evidence["rounds"])
                and not evidence["page_errors"] and not evidence["console_errors"]
            )
            output = OUT / "browser-server-result-studio-handoff.json"
            output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if not evidence["result"]:
                raise SystemExit(1)
        except Exception as error:
            evidence["fatal_error"] = f"{type(error).__name__}: {error}"
            (OUT / "browser-server-result-studio-handoff.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            raise
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
