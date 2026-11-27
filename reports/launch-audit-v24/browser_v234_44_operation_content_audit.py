"""Two-round current-source browser catalog with downloaded-output content checks."""
from __future__ import annotations
import base64, importlib.util, json, os, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
AUDIT_VERSION = os.environ.get("PAPERPLANE_AUDIT_VERSION", "v234")

def load(name: str, location: Path):
    spec = importlib.util.spec_from_file_location(name, location)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module

def main():
    checks_module = load("v21checks", ROOT / "reports/launch-audit-v21/tool_content_audit.py")
    helper = load("v14helper", ROOT / "reports/launch-audit-v14/browser_acceptance_v14.py")
    with TemporaryDirectory(prefix="paperplane-v234-browser-catalog-") as temporary:
        root = Path(temporary)
        app, base, identities = helper.start_server(root / "server-data")
        page_errors = []
        records = []
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Isolated local Paperplane server exited before startup")
                    time.sleep(.2)
            else:
                raise RuntimeError("Isolated local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                context.add_cookies([{"name": "paperplane_token", "value": identities["accounts"][0][1], "url": base, "httpOnly": True}])
                page = context.new_page()
                page.on("pageerror", lambda error: page_errors.append(str(error).splitlines()[0][:200]))
                response = page.goto(base + "/", wait_until="domcontentloaded", timeout=15000)
                if not response or response.status != 200:
                    raise RuntimeError("Local app home page did not load")
                page.wait_for_function("typeof state === 'object' && Object.keys(state.operations || {}).length > 0", timeout=20000)
                os.environ["PAPERPLANE_DATA_DIR"] = str(root / "processor-data")
                sys.path.insert(0, str(ROOT))
                import server
                last_request = [0.0]
                def browser_process(operation, paths, options, output_dir):
                    pause = max(0.0, 3.2 - (time.monotonic() - last_request[0]))
                    if pause:
                        time.sleep(pause)
                    last_request[0] = time.monotonic()
                    payload = {
                        "op": operation,
                        "options": options,
                        "files": [{"name": path.name, "data": base64.b64encode(path.read_bytes()).decode("ascii")} for path in paths],
                    }
                    result = page.evaluate("""async c => {
                      const form = new FormData(); form.append('operation', c.op); form.append('options', JSON.stringify(c.options));
                      for (const file of c.files) {
                        const raw = atob(file.data), bytes = new Uint8Array(raw.length);
                        for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
                        form.append('files', new File([bytes], file.name));
                      }
                      let response = await fetch('/api/jobs', {method: 'POST', body: form});
                      const body = await response.json().catch(() => ({}));
                      if (!response.ok) throw new Error(`job submission ${response.status}: ${JSON.stringify(body)}`);
                      const job = body; let state;
                      for (let i = 0; i < 1200; i++) {
                        await new Promise(resolve => setTimeout(resolve, 250));
                        response = await fetch(job.status_url);
                        if (!response.ok) throw new Error(`job status ${response.status}`);
                        state = await response.json();
                        if (state.status === 'completed') break;
                        if (state.status === 'failed') throw new Error(state.error || 'job failed');
                      }
                      if (state?.status !== 'completed') throw new Error('job timeout');
                      response = await fetch(job.download_url);
                      if (!response.ok) throw new Error(`download ${response.status}`);
                      const bytes = new Uint8Array(await response.arrayBuffer()); let binary = '';
                      for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
                      return {name: state.output_name, data: btoa(binary)};
                    }""", payload)
                    target = Path(output_dir) / Path(result["name"]).name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(base64.b64decode(result["data"]))
                    return target
                server.process = browser_process
                checks = checks_module.load_previous_checks()
                for number in (1, 2):
                    run_dir = OUT / f"browser-{AUDIT_VERSION}-content-round-{number}"
                    result = checks_module.round_result(number, server, checks, run_dir)
                    records.append(result)
                    counts = {status: sum(row["status"] == status for row in result["results"])
                              for status in sorted({row["status"] for row in result["results"]})}
                    print(json.dumps({"round": number, "operations": len(result["results"]), "counts": counts,
                                      "failures": [row for row in result["results"] if row["status"] == "failed"]}), flush=True)
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=15)
    if page_errors:
        raise AssertionError(f"Chromium page errors: {page_errors}")
    evidence = {
        "runtime": f"current local {AUDIT_VERSION} source; isolated local app; installed Chrome browser HTTP uploads and downloads; temporary data; synthetic fixtures; AI provider disabled",
        "base": "127.0.0.1 isolated ephemeral port",
        "rounds": records,
        "page_errors": page_errors,
    }
    target = OUT / f"browser-{AUDIT_VERSION}-44-operation-content-audit.json"
    target.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"evidence={target}", flush=True)

if __name__ == "__main__":
    main()
