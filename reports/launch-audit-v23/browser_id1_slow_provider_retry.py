"""Browser-check the translation route with a controlled 15s-capable provider."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright
import uvicorn

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
ROUND = int(os.environ.get("ID1_SLOW_PROVIDER_ROUND", "1"))
data_directory = TemporaryDirectory(prefix="paperplane-id1-slow-provider-data-")
os.environ.update({
    "PAPERPLANE_SKIP_DOTENV": "1",
    "PAPERPLANE_ENV": "development",
    "PAPERPLANE_DATA_DIR": data_directory.name,
    "PAPERPLANE_ADMIN_KEY": "synthetic-local-admin-key",
    "PAPERPLANE_ADMIN_CODE": "synthetic-local-admin-code",
    "PAPERPLANE_SECURE_COOKIES": "false",
})
sys.path.insert(0, str(ROOT))

import ai_engine  # noqa: E402
import persistence  # noqa: E402
from server import app  # noqa: E402

ai_engine.AI_KILL_SWITCH = False
ai_engine._current_bluesminds_api_key = lambda: "synthetic-local-provider-key"
ai_engine._runtime_ai_config = lambda: {
    "provider": "openai_compatible",
    "base_url": "https://provider.invalid/v1",
    "model": "synthetic-model",
    "api_key": "synthetic-local-provider-key",
}


class FakeResponse:
    status = 200

    def __init__(self, content: str):
        self.content = content.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.content


provider_calls: list[dict] = []


def slow_but_healthy_provider(request, timeout: float):
    # Emulate the upstream's real latency after checking the attempt budget.
    call_started = time.monotonic()
    if timeout < 15:
        provider_calls.append({"timeout_seconds": timeout, "elapsed_seconds": 0})
        raise TimeoutError("controlled provider needs a 15-second response window")
    time.sleep(15.1)
    provider_calls.append({"timeout_seconds": timeout, "elapsed_seconds": round(time.monotonic() - call_started, 2)})
    request_data = json.loads(request.data)
    items = json.loads(request_data["messages"][1]["content"])
    translations = [
        {"id": item["id"], "text": f"Texto traducido marcador {item['id']}"}
        for item in items
    ]
    response_text = json.dumps({"translations": translations}, ensure_ascii=False)
    return FakeResponse(json.dumps({"choices": [{"message": {"content": response_text}}]}, ensure_ascii=False))


ai_engine._open_ai_request = slow_but_healthy_provider
persistence.init_db()
with socket.socket() as candidate:
    candidate.bind(("127.0.0.1", 0))
    port = candidate.getsockname()[1]
uvicorn_server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                               log_level="warning", access_log=False))
server_thread = threading.Thread(target=uvicorn_server.run, daemon=True)
server_thread.start()

evidence = {"viewport": 1366, "provider_calls": provider_calls}
try:
    for _ in range(150):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError("Local Paperplane server did not start")

    with TemporaryDirectory(prefix="paperplane-id1-slow-provider-") as temp_dir:
        source = Path(temp_dir) / "slow-provider-fixture.pdf"
        output = Path(temp_dir) / "slow-provider-translated.pdf"
        with fitz.open() as document:
            for index in range(10):
                page = document.new_page()
                page.insert_text((72, 72),
                                 f"SOURCE-PAGE-{index + 1:03d} The Paperplane service is ready for review.",
                                 fontsize=12)
            document.save(source)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = context.new_page()
            page_errors = []
            response_statuses = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on("response", lambda response: response_statuses.append(response.status)
                    if "/api/ai/translate" in response.url else None)
            response = page.goto(f"http://127.0.0.1:{port}/translate-pdf", wait_until="domcontentloaded")
            assert response and response.status == 200
            page.locator("#file-input").set_input_files(str(source))
            page.locator("#target_language").select_option(label="es (Spanish)")
            page.locator("#run-button").click()
            page.wait_for_function("""()=>{
              const link=document.querySelector('#result-content a.btn-download');
              return !!(link && !link.hidden && link.getBoundingClientRect().width > 0)
                || (document.querySelector('#result')?.innerText||'').toLowerCase().includes('failed');
            }""", timeout=45000)
            link = page.locator("#result-content a.btn-download")
            assert link.is_visible(), page.locator("#result").inner_text()
            with page.expect_download(timeout=15000) as download_event:
                link.click()
            download_event.value.save_as(output)
            with fitz.open(output) as translated:
                assert len(translated) == 10
                page_texts = [translated_page.get_text() for translated_page in translated]
            assert all(f"Texto traducido marcador {index}" in " ".join(page_texts) for index in range(10)), page_texts
            assert "SOURCE-PAGE-" not in " ".join(page_texts), page_texts
            assert provider_calls and min(call["timeout_seconds"] for call in provider_calls) >= 15, provider_calls
            assert min(call["elapsed_seconds"] for call in provider_calls) >= 15, provider_calls
            assert response_statuses == [200], response_statuses
            assert not page_errors, page_errors
            evidence.update({
                "status": "PASS",
                "output_bytes": output.stat().st_size,
                "pages": len(page_texts),
                "translated_markers": 10,
                "source_markers_preserved": False,
                "api_statuses": response_statuses,
                "page_errors": page_errors,
            })
            page.screenshot(path=str(OUT / f"id1-slow-provider-retry-round{ROUND}.png"), full_page=True)
            context.close()
            browser.close()
finally:
    uvicorn_server.should_exit = True
    server_thread.join(timeout=5)
    evidence["provider_calls"] = provider_calls
    (OUT / f"browser-id1-slow-provider-retry-round{ROUND}.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    data_directory.cleanup()
