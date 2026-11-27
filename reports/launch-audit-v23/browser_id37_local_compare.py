from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
import json
import os
import subprocess
import socket
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def write_pdf(path: Path, lines: list[str]) -> None:
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((60, 70), "\n".join(lines), fontsize=11)
        document.save(path)


with TemporaryDirectory(prefix="paperplane-id37-local-compare-") as temp:
    root = Path(temp)
    left = root / "comparison-old.pdf"
    right = root / "comparison-new.pdf"
    write_pdf(left, ["COMMON HEADER", "Keep this paragraph", "Old total: 19", "COMMON FOOTER"])
    write_pdf(right, ["COMMON HEADER", "Keep this paragraph", "Inserted line", "New total: 24", "COMMON FOOTER"])

    base = os.environ.get("PAPERPLANE_TEST_BASE")
    app = None
    if not base:
        app, base, _ = helper.start_server(root / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)

        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_number in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                context.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode', 'local')")
                page = context.new_page()
                errors = []
                job_posts = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: job_posts.append(request.url)
                        if request.method == "POST" and "/api/jobs" in request.url else None)
                page.goto(base + "/?tool=compare", wait_until="domcontentloaded")
                algorithm_cases = page.evaluate("""() => {
                  const cases = [
                    [[], []],
                    [['a', 'b'], ['a', 'x', 'b']],
                    [['a', 'b', 'c'], ['a', 'c']],
                    [['a', 'b'], ['c', 'd']],
                    [['a', 'b', 'a'], ['a', 'a', 'b', 'a']],
                    [['same', 'same'], ['same', 'same']],
                  ];
                  const reconstructionCases = cases.map(([before, after]) => {
                    const edits = diffPdfTextLines(before, after);
                    const reconstructedBefore = edits.filter(edit => edit.type !== '+').map(edit => edit.text);
                    const reconstructedAfter = edits.filter(edit => edit.type !== '-').map(edit => edit.text);
                    return JSON.stringify(reconstructedBefore) === JSON.stringify(before)
                      && JSON.stringify(reconstructedAfter) === JSON.stringify(after);
                  });
                  let workLimitEnforced = false;
                  try {
                    diffPdfTextLines(Array.from({length: 40}, (_, i) => `left-${i}`),
                      Array.from({length: 40}, (_, i) => `right-${i}`), 20);
                  } catch (error) {
                    workLimitEnforced = error.message.includes('too large for the browser');
                  }
                  return {reconstructionCases, workLimitEnforced};
                }""")
                assert all(algorithm_cases["reconstructionCases"]), algorithm_cases
                assert algorithm_cases["workLimitEnforced"], algorithm_cases
                page.locator("#file-input").set_input_files([str(left), str(right)])
                assert "selectable text on this device" in page.locator("#options").inner_text().lower()
                assert page.locator("#client-privacy-toggle").is_checked()
                page.locator("#run-button").click()
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=45000)
                with page.expect_download(timeout=20000) as event:
                    page.locator("#result-download-link").click()
                download = event.value
                output_path = root / f"local-compare-round{round_number}.txt"
                download.save_as(output_path)
                text = output_path.read_text(encoding="utf-8")
                assert download.suggested_filename.endswith("_comparison.txt"), download.suggested_filename
                assert "File A: comparison-old.pdf" in text and "File B: comparison-new.pdf" in text, text
                assert "Scope: selectable PDF text only" in text
                assert " COMMON HEADER" in text and " COMMON FOOTER" in text, text
                assert "+Inserted line" in text and "-Old total: 19" in text and "+New total: 24" in text, text
                assert not job_posts, job_posts
                assert not errors, errors
                results.append({"round": round_number, "filename": download.suggested_filename,
                                "has_context": True, "insertion_and_replacement_detected": True,
                                "diff_algorithm_cases": len(algorithm_cases["reconstructionCases"]),
                                "diff_work_limit_enforced": algorithm_cases["workLimitEnforced"],
                                "job_posts": job_posts, "page_errors": errors})
                context.close()
            browser.close()

        docker_runtime = bool(os.environ.get("PAPERPLANE_TEST_BASE"))
        result = {"base": base, "runtime": "Docker image" if docker_runtime else "local server",
                  "image_id": subprocess.check_output(
                      ["docker", "image", "inspect", "paperplane-v23-audit:codex-current", "--format", "{{.Id}}"],
                      text=True).strip() if docker_runtime else None,
                  "rounds": results}
        evidence_name = "browser-id37-local-compare-docker.json" if docker_runtime else "browser-id37-local-compare-local.json"
        (OUT / evidence_name).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        if app:
            app.terminate()
            app.wait(timeout=5)
