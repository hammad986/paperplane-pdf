"""Browser verification of repeated-segment translation on current source."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from tempfile import TemporaryDirectory
from urllib.request import urlopen

import fitz
import uvicorn
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "launch-audit-v23" / "fixtures" / "totpdf-sample-5-pages.pdf"
OUT = HERE / "browser-v241-repeated-translation.json"
PDF_OUT = HERE / "browser-v241-repeated-translation.pdf"


def main() -> None:
    evidence = {"source_pages": 5, "rounds": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v241-translation-") as temp:
        os.environ.update({"PAPERPLANE_SKIP_DOTENV": "1", "PAPERPLANE_ENV": "development",
                           "PAPERPLANE_DATA_DIR": str(Path(temp) / "data"),
                           "PAPERPLANE_ADMIN_KEY": "synthetic-local-admin-key",
                           "PAPERPLANE_ADMIN_CODE": "synthetic-local-admin-code",
                           "PAPERPLANE_SECURE_COOKIES": "false",
                           "BLUESMINDS_API_KEY": "synthetic-controlled-key"})
        sys.path.insert(0, str(ROOT))
        import ai_engine  # noqa: E402
        from server import app  # noqa: E402

        calls: list[list[int]] = []
        translations = {
            "TotPDF sample": "Muestra de TotPDF",
            "Free local PDF tools": "Herramientas PDF locales gratuitas: nada sale de su dispositivo.",
            "This page exists only": "Esta página existe solo para probar una herramienta. Combínela, divídala, gírela o comprímala.",
            "Every sample file": "TotPDF crea cada archivo de muestra y permite usarlo gratis para pruebas y tutoriales.",
            "No account": "Sin cuenta, sin carga, sin seguimiento.",
        }

        def bounded_provider(batch, *_args, **_kwargs):
            calls.append([segment_id for segment_id, _ in batch])
            if len(batch) <= 2:
                raise RuntimeError("synthetic provider response budget exhausted")
            return {segment_id: next((value for prefix, value in translations.items()
                                     if text.startswith(prefix)), "Texto traducido.")
                    for segment_id, text in batch[:10]}

        ai_engine._translate_text_batch = bounded_provider
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                try:
                    with urlopen(base + "/api/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except Exception:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Local server did not become healthy")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(accept_downloads=True, service_workers="block",
                                              viewport={"width": 390, "height": 844})
                page = context.new_page()
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda message: evidence["console_errors"].append(message.text)
                        if message.type == "error" else None)
                for round_no in (1, 2):
                    response = page.goto(base + "/translate-pdf", wait_until="domcontentloaded")
                    assert response and response.status == 200
                    page.wait_for_function("window.state && state.operation === 'translate'")
                    page.locator("#file-input").set_input_files(str(SOURCE))
                    page.locator("#target_language").select_option(label="es (Spanish)")
                    page.locator("#run-button").click()
                    link = page.locator("#result-content a.btn-download")
                    link.wait_for(state="visible", timeout=45000)
                    with page.expect_download(timeout=15000) as event:
                        link.click()
                    output = PDF_OUT if round_no == 2 else HERE / "browser-v241-repeated-translation-round1.pdf"
                    event.value.save_as(output)
                    with fitz.open(output) as translated:
                        extracted = [pdf_page.get_text() for pdf_page in translated]
                    studio_action_count = page.get_by_role("button", name="View in Studio").count()
                    generic_studio_hidden = page.locator("#result-view-studio-btn").is_hidden()
                    passed = len(extracted) == 5 and all(
                        "Muestra de TotPDF" in text and "Herramientas PDF locales" in text
                        and "Esta página existe" in text and "Sin cuenta" in text
                        and "Free local PDF tools" not in text
                        for text in extracted
                    )
                    passed &= studio_action_count == 1 and generic_studio_hidden
                    evidence["rounds"].append({"round": round_no, "output_pages": len(extracted),
                                               "download_bytes": output.stat().st_size,
                                               "all_pages_content_verified": passed,
                                               "visible_studio_actions": studio_action_count,
                                               "generic_studio_action_hidden": generic_studio_hidden,
                                               "result_text": page.locator("#result").inner_text()[:350]})
                    page.screenshot(path=str(HERE / f"browser-v241-repeated-translation-round{round_no}.png"))
                browser.close()
            evidence["provider_calls"] = calls
            evidence["unique_segment_ids_sent"] = len({segment_id for call in calls for segment_id in call})
            evidence["passed"] = all(item["all_pages_content_verified"] for item in evidence["rounds"])
            evidence["passed"] &= not evidence["page_errors"] and not evidence["console_errors"]
        finally:
            server.should_exit = True
            thread.join(timeout=10)
    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
