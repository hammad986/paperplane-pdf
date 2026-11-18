"""Controlled four-job Chromium check for v23 checklist ID 90."""
from __future__ import annotations

import fitz
import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def main() -> None:
    report_dir = Path(__file__).resolve().parent
    with TemporaryDirectory(prefix="paperplane-v23-concurrency-") as temp_name:
        temp = Path(temp_name)
        source = temp / "concurrency-source.pdf"
        with fitz.open() as document:
            document.new_page().insert_text((72, 72), "Synthetic four-job concurrency content.")
            document.save(source)
        app, base, identities = helper.start_server(temp / "server-data")
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=.2):
                        break
                except OSError:
                    time.sleep(.15)
            else:
                raise RuntimeError("Local Paperplane server did not start.")
            email, token = identities["accounts"][0]
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(accept_downloads=True)
                context.add_cookies([{"name": "paperplane_token", "value": token,
                                      "domain": "127.0.0.1", "path": "/", "httpOnly": True,
                                      "secure": False, "sameSite": "Lax"}])
                page = context.new_page()
                page_errors: list[str] = []
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(base + "/merge-pdf", wait_until="domcontentloaded")

                responses = page.evaluate("""async ({url, jobs, bytes}) => Promise.all(jobs.map(async name => {
                  const form = new FormData();
                  form.append('operation', 'merge'); form.append('options', '{}');
                  form.append('files', new Blob([new Uint8Array(bytes)], {type:'application/pdf'}), name);
                  const response = await fetch(url, {method:'POST', body:form});
                  return {status:response.status, body:await response.json()};
                }))""", {"url": base + "/api/jobs", "jobs": [f"parallel-{i}.pdf" for i in range(4)],
                     "bytes": list(source.read_bytes())})
                assert all(item["status"] == 202 for item in responses), responses
                job_ids = [item["body"]["job_id"] for item in responses]
                assert len(set(job_ids)) == 4, job_ids
                outcomes = []
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline and len(outcomes) < 4:
                    outcomes = []
                    for job_id in job_ids:
                        response = context.request.get(base + f"/api/jobs/{job_id}")
                        payload = response.json()
                        outcomes.append({"job_id": job_id, "http_status": response.status,
                                         "status": payload.get("status"), "payload": payload})
                    if all(row["status"] in ("completed", "failed") for row in outcomes):
                        break
                    time.sleep(.2)
                assert all(row["status"] == "completed" for row in outcomes), outcomes
                downloads = []
                for row in outcomes:
                    response = context.request.get(base + f"/api/jobs/{row['job_id']}/download")
                    assert response.status == 200, {"job": row["job_id"], "status": response.status}
                    with fitz.open(stream=response.body(), filetype="pdf") as document:
                        text = " ".join(page.get_text() for page in document)
                        assert document.page_count == 1 and "Synthetic four-job concurrency content." in text
                        downloads.append({"http_status": response.status, "pages": document.page_count,
                                          "content_checked": True})
                assert not page_errors, page_errors
                round_number = 1 + len(list(report_dir.glob("browser-id90-concurrency-round*.json")))
                result = {"check": "id90_four_parallel_merge_jobs", "round": round_number, "user": email,
                          "submit_statuses": [item["status"] for item in responses],
                          "job_statuses": [row["status"] for row in outcomes], "downloads": downloads,
                          "page_errors": page_errors, "evidence": "four one-page PDFs opened and text checked"}
                (report_dir / f"browser-id90-concurrency-round{round_number}.json").write_text(
                    json.dumps(result, indent=2), encoding="utf-8")
                (report_dir / "browser-id90-concurrency.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                print(json.dumps(result, indent=2))
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=15)


if __name__ == "__main__":
    main()
