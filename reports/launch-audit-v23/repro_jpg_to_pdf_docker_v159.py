"""Isolate the production-image JPG/PNG-to-PDF job and content-check its output."""
from __future__ import annotations

import base64
import io
import json
import secrets
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

import fitz
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
IMAGE = "paperplane-v23-audit:codex-v159"
CONTAINER = "paperplane-v23-v159-jpg-repro"
PORT = 18540
BASE = f"http://127.0.0.1:{PORT}"


def run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=timeout)


with socket.socket() as probe:
    if probe.connect_ex(("127.0.0.1", PORT)) == 0:
        raise RuntimeError(f"Refusing occupied port {PORT}")
if subprocess.run(["docker", "ps", "-aq", "--filter", f"name=^{CONTAINER}$"], capture_output=True, text=True).stdout.strip():
    raise RuntimeError(f"Refusing existing container {CONTAINER}")

fixture_dir = OUT / "docker-catalog-fixtures-current-v159-20261119-current-v159-2026-11-22" / "round-1"
images = [base64.b64encode((fixture_dir / filename).read_bytes()).decode("ascii")
          for filename in ("audit-photo.png", "audit-photo-2.png")]

admin = secrets.token_urlsafe(48)
code = secrets.token_urlsafe(32)
session = secrets.token_urlsafe(48)
started = False
result: dict = {"image": IMAGE, "base": BASE, "rounds": [], "production_endpoints_contacted": False, "payment_submitted": False}
try:
    run([
        "docker", "run", "-d", "--name", CONTAINER, "--restart=no", "--cpus=2", "--memory=2g",
        "--security-opt=no-new-privileges", "-p", f"127.0.0.1:{PORT}:8501",
        "--tmpfs", "/data:rw,nosuid,nodev,size=256m", "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m",
        "-e", "PAPERPLANE_ENV=production", "-e", "PAPERPLANE_SKIP_DOTENV=1", "-e", "PAPERPLANE_WORKERS=4",
        "-e", "PAPERPLANE_DATA_DIR=/data", "-e", "PAPERPLANE_PORT=8501", "-e", "PAPERPLANE_PUBLIC_URL=https://paperplane.example.test", "-e", "PAPERPLANE_SECURE_COOKIES=false",
        "-e", f"PAPERPLANE_ADMIN_KEY={admin}", "-e", f"PAPERPLANE_ADMIN_CODE={code}",
        "-e", f"PAPERPLANE_SESSION_SECRET={session}", "-e", "CASHFREE_ENV=TEST", IMAGE,
    ])
    started = True
    for _ in range(90):
        try:
            with urlopen(BASE + "/api/health", timeout=2) as response:
                health = json.loads(response.read())
                if response.status == 200 and health.get("status") == "ok":
                    result["health"] = health
                    break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("v159 container failed health")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        email = "audit-catalog-v159@example.invalid"
        password = "Dummy-Password-Only-v159!"
        seed = "from persistence import create_user,get_user_by_email,set_user_tier; row=get_user_by_email('audit-catalog-v159@example.invalid'); uid=row['id'] if row else create_user('audit-catalog-v159@example.invalid','Dummy-Password-Only-v159!'); set_user_tier(uid,'pro'); print('seeded')"
        seeded = subprocess.run(["docker", "exec", CONTAINER, "python", "-c", seed], capture_output=True, text=True, timeout=30)
        assert seeded.returncode == 0 and "seeded" in seeded.stdout, seeded.stderr
        login = page.request.post(BASE + "/api/auth/login", data={"email": email, "password": password}, headers={"content-type": "application/json"})
        assert login.status == 200, login.text()
        for round_number in (1, 2):
            try:
                downloaded = page.evaluate("""async ({images,roundNumber}) => {
                  const form=new FormData();form.append('operation','jpg_to_pdf');form.append('options',JSON.stringify({}));
                  images.forEach((encoded,index)=>{const raw=atob(encoded),bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);form.append('files',new File([bytes],`marker-${index+1}.png`,{type:'image/png'}));});
                  let response=await fetch('/api/jobs',{method:'POST',body:form}),job=await response.json();if(!response.ok)throw new Error(`submit ${response.status} ${JSON.stringify(job)}`);
                  let state;for(let n=0;n<160;n++){await new Promise(resolve=>setTimeout(resolve,250));response=await fetch(job.status_url);state=await response.json();if(state.status==='completed'||state.status==='failed')break;}
                  if(state?.status!=='completed')throw new Error(`job did not complete: ${JSON.stringify(state)}`);
                  response=await fetch(job.download_url);if(!response.ok)throw new Error(`download ${response.status}`);
                  const bytes=new Uint8Array(await response.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
                  return {status:state.status,outputName:state.output_name,outputSize:state.output_size,pdfBase64:btoa(binary),round:roundNumber};
                }""", {"images": images, "roundNumber": round_number})
                pdf_bytes = base64.b64decode(downloaded.pop("pdfBase64"))
                with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
                    page_color_counts = []
                    for pdf_page in pdf:
                        pix = pdf_page.get_pixmap(matrix=fitz.Matrix(0.75, 0.75), alpha=False)
                        samples = pix.samples
                        target = (240, 95, 50) if not page_color_counts else (35, 135, 110)
                        count = sum(1 for index in range(0, len(samples) - 2, pix.n)
                                    if abs(samples[index] - target[0]) < 28
                                    and abs(samples[index + 1] - target[1]) < 28
                                    and abs(samples[index + 2] - target[2]) < 28)
                        page_color_counts.append(count)
                    content_ok = pdf.page_count == 2 and all(count > 100 for count in page_color_counts)
                    downloaded.update({"pages": pdf.page_count, "page_marker_color_pixels": page_color_counts, "content_checked": content_ok})
                downloaded["browser_page_errors"] = errors.copy()
                result["rounds"].append(downloaded)
                assert content_ok and not errors, downloaded
            except Exception as error:
                result["rounds"].append({"round": round_number, "error": str(error), "browser_page_errors": errors.copy()})
                break
        browser.close()
finally:
    if started:
        try:
            result["container_state"] = json.loads(run(["docker", "inspect", CONTAINER, "--format", "{{json .State}}"], 20).stdout)
        except Exception:
            pass
        subprocess.run(["docker", "stop", "--time", "10", CONTAINER], check=False, capture_output=True, timeout=30)
        subprocess.run(["docker", "rm", "--force", CONTAINER], check=False, capture_output=True, timeout=30)

(OUT / "browser-id37-jpg-to-pdf-docker-v159.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
if len(result["rounds"]) != 2 or any(not round_.get("content_checked") for round_ in result["rounds"]):
    raise SystemExit(1)
