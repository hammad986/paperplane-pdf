"""Verify a post-acceptance client response loss retries without duplicating a job."""
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
import json
import secrets
import socket
import sqlite3
import sys
import time
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id106-submit-retry-") as temp:
    root = Path(temp)
    data_dir = root / "data"
    fixture = root / "retry-source.pdf"
    large_fixture = root / "retry-large-source.pdf"
    with fitz.open() as doc:
        doc.new_page(width=595, height=842).insert_text((72, 72), "ID106 IDEMPOTENT RETRY MARKER")
        doc.save(fixture)
    pixels = secrets.token_bytes(3200 * 1100 * 3)
    image_file = root / "large-noise.png"
    Image.frombytes("RGB", (3200, 1100), pixels).save(image_file, compress_level=0)
    with fitz.open() as doc:
        page = doc.new_page(width=612, height=792)
        page.insert_text((48, 48), "ID106 CHUNKED IDEMPOTENT RETRY MARKER")
        page.insert_image(fitz.Rect(30, 80, 580, 700), filename=str(image_file))
        doc.save(large_fixture)
    assert large_fixture.stat().st_size > 10 * 1024 * 1024

    app, base, identities = helper.start_server(data_dir)
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(120):
            if app.poll() is not None:
                raise RuntimeError(f"Local server exited: {app.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        else:
            raise RuntimeError("Local server did not start")

        attempts = []
        submission_statuses = []
        errors = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: submission_statuses.append(response.status)
                    if response.request.method == "POST" and (response.url.rstrip("/") == base + "/api/jobs"
                       or response.url.endswith("/commit")) else None)

            response = page.goto(base + "/rotate-pdf", wait_until="domcontentloaded")
            assert response and response.status == 200
            page.evaluate("""() => {
              const original = window.safeFetch;
              window.__id106Attempts = [];
              window.safeFetch = async (...args) => {
                const result = await original(...args);
                const requestPath = String(args[0]).split('?')[0];
                if ((requestPath === '/api/jobs' || requestPath.endsWith('/commit')) && args[1]?.method === 'POST') {
                  const entry = {job_id: result.job_id, idempotent: Boolean(result.idempotent),
                    idempotency_key: args[1]?.headers?.['Idempotency-Key']};
                  window.__id106Attempts.push(entry);
                  if (window.__id106Attempts.length === 1) {
                    const proxyFailure = new Error('controlled proxy returned 502 after job acceptance');
                    proxyFailure.status = 502;
                    window.__id106Attempts[0].client_error_status = 502;
                    throw proxyFailure;
                  }
                }
                return result;
              };
            }""")
            page.evaluate("""() => {const input=document.querySelector('#client-privacy-toggle'); if(input.checked){input.checked=false;input.dispatchEvent(new Event('change',{bubbles:true}));}}""")
            page.wait_for_function("state.clientSideMode === false")
            page.locator("#file-input").set_input_files(str(fixture))
            page.locator("#degrees").select_option("90")
            page.locator("#run-button").click()
            page.get_by_text("Retrying safely (1/2)").wait_for(state="visible", timeout=10000)
            page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
            with page.expect_download(timeout=15000) as download_event:
                page.locator("#result-download-link").click()
            output = root / "replayed-output.pdf"
            download_event.value.save_as(output)
            with fitz.open(output) as doc:
                assert doc.page_count == 1
                assert "ID106 IDEMPOTENT RETRY MARKER" in doc[0].get_text()
                assert doc[0].rotation == 90

            attempts = page.evaluate("window.__id106Attempts")
            assert len(attempts) == 2, attempts
            assert submission_statuses == [202, 200], submission_statuses
            assert attempts[0]["idempotency_key"] and attempts[0]["idempotency_key"] == attempts[1]["idempotency_key"]
            assert attempts[0]["job_id"] == attempts[1]["job_id"]
            assert not attempts[0]["idempotent"] and attempts[1]["idempotent"]
            assert not errors, errors

            # Repeat through the >10 MiB chunk assembly route under a synthetic
            # paid account so the large fixture exercises transport, not quota.
            context.add_cookies([{"name": "paperplane_token", "value": identities["accounts"][0][1], "url": base, "httpOnly": True}])
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function("state.user !== null")
            page.goto(base + "/rotate-pdf", wait_until="domcontentloaded")
            page.evaluate("""() => {
              const original = window.safeFetch;
              window.__id106Attempts = [];
              window.safeFetch = async (...args) => {
                const result = await original(...args);
                const requestPath = String(args[0]).split('?')[0];
                if ((requestPath === '/api/jobs' || requestPath.endsWith('/commit')) && args[1]?.method === 'POST') {
                  const entry = {job_id: result.job_id, idempotent: Boolean(result.idempotent),
                    idempotency_key: args[1]?.headers?.['Idempotency-Key']};
                  window.__id106Attempts.push(entry);
                  if (window.__id106Attempts.length === 1) {
                    const proxyFailure = new Error('controlled proxy returned 502 after job acceptance');
                    proxyFailure.status = 502;
                    window.__id106Attempts[0].client_error_status = 502;
                    throw proxyFailure;
                  }
                }
                return result;
              };
            }""")
            page.locator("#file-input").set_input_files(str(large_fixture))
            page.locator("#file-list .file-row-name").wait_for(state="visible", timeout=20000)
            page.locator("#degrees").select_option("90")
            before_chunk_statuses = len(submission_statuses)
            page.wait_for_function("!document.querySelector('#run-button').disabled", timeout=20000)
            page.locator("#run-button").click()
            page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=120000)
            with page.expect_download(timeout=30000) as large_download_event:
                page.locator("#result-download-link").click()
            large_output = root / "replayed-large-output.pdf"
            large_download_event.value.save_as(large_output)
            with fitz.open(large_output) as doc:
                assert doc.page_count == 1 and "ID106 CHUNKED IDEMPOTENT RETRY MARKER" in doc[0].get_text()
                assert doc[0].rotation == 90
            chunk_attempts = page.evaluate("window.__id106Attempts")
            chunk_statuses = submission_statuses[before_chunk_statuses:]
            assert len(chunk_attempts) == 2 and chunk_statuses == [202, 200], (chunk_attempts, chunk_statuses)
            assert chunk_attempts[0]["idempotency_key"] == chunk_attempts[1]["idempotency_key"]
            assert chunk_attempts[0]["job_id"] == chunk_attempts[1]["job_id"] and chunk_attempts[1]["idempotent"]
            assert not errors, errors
            browser.close()

        database = sqlite3.connect(data_dir / "paperplane.sqlite3")
        try:
            job_count = database.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            key_count = database.execute("SELECT COUNT(*) FROM app_job_submission_keys").fetchone()[0]
        finally:
            database.close()
        assert job_count == 2 and key_count == 2, (job_count, key_count)
        evidence = {"scenario": "controlled client-side proxy 502 after acceptance, on standard and >10 MiB chunk-commit submissions",
                    "standard_attempts": attempts, "standard_http_statuses": submission_statuses[:2],
                    "chunked_attempts": chunk_attempts, "chunked_http_statuses": chunk_statuses,
                    "single_job_per_submission": job_count == 2,
                    "single_idempotency_record_per_submission": key_count == 2,
                    "download": {"pages": 1, "rotation": 90, "marker_preserved": True}, "page_errors": errors}
        (OUT / "browser-id106-idempotent-submit-retry.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        if app.poll() is None:
            app.terminate()
        app.wait(timeout=8)
