"""Exercise oversized watermark rejection through Chromium and local HTTP API."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import socket
import struct
import sys
from tempfile import TemporaryDirectory
import time
import zlib

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
sys.path.insert(0, str(HELPER.parent))
import browser_acceptance_v14 as helper  # noqa: E402


def oversized_png() -> bytes:
    with TemporaryDirectory(prefix="paperplane-watermark-png-") as temporary:
        path = Path(temporary) / "tiny.png"
        from PIL import Image
        Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(path)
        payload = bytearray(path.read_bytes())
    struct.pack_into(">II", payload, 16, 24_000, 1_000)
    struct.pack_into(">I", payload, 29, zlib.crc32(payload[12:29]) & 0xFFFFFFFF)
    return bytes(payload)


def run(round_number: int) -> dict:
    with TemporaryDirectory(prefix=f"paperplane-watermark-browser-{round_number}-") as temporary:
        directory = Path(temporary)
        data_dir = directory / "server-data"
        source = directory / "source.pdf"
        with fitz.open() as document:
            document.new_page().insert_text((72, 72), "WATERMARK-GUARD-SOURCE")
            document.save(source)
        result: dict = {"round": round_number}
        external_base = os.environ.get("PAPERPLANE_LOCAL_MATRIX_BASE")
        if external_base:
            app, base = None, external_base.rstrip("/")
            result["runtime"] = os.environ.get("PAPERPLANE_RUNTIME_LABEL", "external local Paperplane server")
        else:
            app, base, _identity = helper.start_server(data_dir)
        errors: list[str] = []
        result["base"] = base
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                        break
                except OSError:
                    if app is not None and app.poll() is not None:
                        raise RuntimeError("Local Paperplane server exited before browser test.")
                    time.sleep(0.1)
            else:
                raise RuntimeError("Local Paperplane server did not become ready.")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base, wait_until="domcontentloaded", timeout=20_000)
                assert response and response.status == 200
                source_b64 = base64.b64encode(source.read_bytes()).decode("ascii")
                watermark_data_url = "data:image/png;base64," + base64.b64encode(oversized_png()).decode("ascii")
                result["api"] = page.evaluate("""async ({sourceB64, watermarkDataUrl}) => {
                  const bytes = Uint8Array.from(atob(sourceB64), char => char.charCodeAt(0));
                  const body = new FormData();
                  body.append('operation', 'watermark');
                  body.append('options', JSON.stringify({watermark_image_data: watermarkDataUrl}));
                  body.append('files', new Blob([bytes], {type: 'application/pdf'}), 'source.pdf');
                  const submitted = await fetch('/api/jobs', {method: 'POST', body});
                  const submission = await submitted.json();
                  if (submitted.status !== 202) return {httpStatus: submitted.status, submission};
                  const deadline = Date.now() + 15000;
                  let latest;
                  while (Date.now() < deadline) {
                    const status = await fetch(submission.status_url);
                    latest = await status.json();
                    if (['failed', 'completed', 'cancelled'].includes(latest.status)) break;
                    await new Promise(resolve => setTimeout(resolve, 100));
                  }
                  return {httpStatus: submitted.status, jobId: submission.job_id,
                          status: latest && latest.status, error: latest && latest.error};
                }""", {"sourceB64": source_b64, "watermarkDataUrl": watermark_data_url})
                assert result["api"]["httpStatus"] == 202, result
                assert result["api"]["status"] == "failed", result
                assert "20-megapixel processing limit" in result["api"]["error"], result

                result["truncatedDataUrl"] = page.evaluate("""async ({sourceB64}) => {
                  const bytes = Uint8Array.from(atob(sourceB64), char => char.charCodeAt(0));
                  const body = new FormData();
                  body.append('operation', 'watermark');
                  body.append('options', JSON.stringify({watermark_image_data: 'data:image/png;base64'}));
                  body.append('files', new Blob([bytes], {type: 'application/pdf'}), 'source.pdf');
                  const submitted = await fetch('/api/jobs', {method: 'POST', body});
                  const submission = await submitted.json();
                  const deadline = Date.now() + 15000;
                  let latest;
                  while (submitted.status === 202 && Date.now() < deadline) {
                    const status = await fetch(submission.status_url);
                    latest = await status.json();
                    if (['failed', 'completed', 'cancelled'].includes(latest.status)) break;
                    await new Promise(resolve => setTimeout(resolve, 100));
                  }
                  return {httpStatus: submitted.status, status: latest && latest.status,
                          error: latest && latest.error};
                }""", {"sourceB64": source_b64})
                assert result["truncatedDataUrl"]["status"] == "failed", result
                assert "data URL is invalid" in result["truncatedDataUrl"]["error"], result

                from PIL import Image
                normal_path = directory / "normal.png"
                Image.new("RGBA", (64, 32), (230, 30, 20, 255)).save(normal_path)
                result["validWatermark"] = page.evaluate("""async ({sourceB64, imageB64}) => {
                  const bytes = Uint8Array.from(atob(sourceB64), char => char.charCodeAt(0));
                  const body = new FormData();
                  body.append('operation', 'watermark');
                  body.append('options', JSON.stringify({watermark_image_data: 'data:image/png;base64,' + imageB64, opacity: 1}));
                  body.append('files', new Blob([bytes], {type: 'application/pdf'}), 'source.pdf');
                  const submitted = await fetch('/api/jobs', {method: 'POST', body});
                  const submission = await submitted.json();
                  if (submitted.status !== 202) return {httpStatus: submitted.status, submission};
                  const deadline = Date.now() + 15000;
                  let latest;
                  while (Date.now() < deadline) {
                    const status = await fetch(submission.status_url);
                    latest = await status.json();
                    if (['failed', 'completed', 'cancelled'].includes(latest.status)) break;
                    await new Promise(resolve => setTimeout(resolve, 100));
                  }
                  if (latest.status !== 'completed') return {httpStatus: submitted.status, status: latest.status, error: latest.error};
                  const download = await fetch(submission.download_url);
                  const output = new Uint8Array(await (await download.blob()).arrayBuffer());
                  let binary = '';
                  for (let start = 0; start < output.length; start += 8192)
                    binary += String.fromCharCode(...output.subarray(start, start + 8192));
                  return {httpStatus: submitted.status, status: latest.status, downloadStatus: download.status,
                          filename: download.headers.get('content-disposition'), pdfB64: btoa(binary)};
                }""", {
                  "sourceB64": source_b64,
                  "imageB64": base64.b64encode(normal_path.read_bytes()).decode("ascii"),
                })
                import io
                output_bytes = base64.b64decode(result["validWatermark"].pop("pdfB64"))
                with fitz.open(stream=output_bytes, filetype="pdf") as output_pdf:
                    assert len(output_pdf) == 1
                    assert "WATERMARK-GUARD-SOURCE" in output_pdf[0].get_text()
                    images = output_pdf[0].get_images(full=True)
                    assert images, "successful image watermark output has no embedded image"
                    image_data = output_pdf.extract_image(images[0][0])["image"]
                with Image.open(io.BytesIO(image_data)) as rendered_watermark:
                    assert rendered_watermark.convert("RGB").getpixel((32, 16)) == (230, 30, 20)
                assert result["validWatermark"]["status"] == "completed", result
                assert result["validWatermark"]["downloadStatus"] == 200, result
                result["validWatermark"]["pdfContentChecked"] = True
                browser.close()
                assert not errors, errors
                result["pageErrors"] = errors
                result["passed"] = True
                return result
        finally:
            if app is not None:
                app.terminate()
            try:
                if app is not None:
                    app.wait(timeout=5)
            except Exception:
                app.kill()
                app.wait(timeout=5)


if __name__ == "__main__":
    rows = [run(round_number) for round_number in (1, 2)]
    suffix = os.environ.get("PAPERPLANE_EVIDENCE_SUFFIX", "")
    suffix = f"-{suffix}" if suffix else ""
    report = Path(__file__).with_name(f"browser-id361-watermark-image-guard{suffix}.json")
    report.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"evidence": str(report), "rounds": rows}, indent=2))
