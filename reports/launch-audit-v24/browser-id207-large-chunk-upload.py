"""Content-check a >10 MB server-backed browser job and record upload progress."""
import io, json, os, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"reports"/"launch-audit-v24"
with TemporaryDirectory(prefix="paperplane-id207-") as tmp:
    temp=Path(tmp);images=[];source=temp/"large-chunk-upload.pdf"
    for index in range(2):
        image=Image.frombytes("RGB",(2400,2400),os.urandom(2400*2400*3))
        image_path=temp/f"noise-{index}.jpg";image.save(image_path,"JPEG",quality=94);images.append(image_path)
    with fitz.open() as doc:
        for index,image_path in enumerate(images,1):
            page=doc.new_page(width=612,height=792);page.insert_text((48,40),f"ID207 upload page {index} marker UPLOAD-CHUNK-{index}")
            page.insert_image(fitz.Rect(30,60,582,760),filename=str(image_path),keep_proportion=True)
        doc.save(source,garbage=3,deflate=True)
    generated_content_bytes=source.stat().st_size
    # Reproduce the reported transfer-size boundary without claiming this is
    # the owner's original 58 MB fixture: valid PDF trailing whitespace pads
    # the two-page marker fixture to exactly 58 MiB.
    target_size=58*1024*1024
    if generated_content_bytes < target_size:
        with source.open("ab") as stream: stream.write(b" "*(target_size-generated_content_bytes))
    size=source.stat().st_size;assert size==target_size,(size,target_size)
    with fitz.open(source) as check: assert check.page_count==2
    sys.path.insert(0,str(ROOT/"reports"/"launch-audit-v14"))
    import browser_acceptance_v14 as helper
    app,base,identity=helper.start_server(temp/"data")
    port=int(base.rsplit(":",1)[1])
    try:
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1",port),timeout=.2):break
            except OSError:time.sleep(.2)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True);context=browser.new_context(viewport={"width":1366,"height":900},accept_downloads=True)
            context.add_cookies([{"name":"paperplane_token","value":identity["accounts"][1][1],"url":base,"httpOnly":True}]);page=context.new_page()
            requests=[];responses=[];errors=[]
            page.on("request",lambda r:requests.append({"method":r.method,"path":r.url.split(str(port))[-1]}) if "/api/uploads/chunked" in r.url or "/api/jobs" in r.url else None)
            page.on("response",lambda r:responses.append({"status":r.status,"path":r.url.split(str(port))[-1]}) if "/api/uploads/chunked" in r.url or "/api/jobs" in r.url else None)
            page.on("pageerror",lambda e:errors.append(str(e)))
            delayed_chunks=[]
            def slow_chunk(route):
                if route.request.method=="PUT":
                    delayed_chunks.append(route.request.url)
                    time.sleep(.15)
                route.continue_()
            page.route("**/api/uploads/chunked/**",slow_chunk)
            page.goto(base+"/protect-pdf",wait_until="domcontentloaded")
            page.locator("#file-input").set_input_files(str(source));page.wait_for_function("state.files.length===1")
            page.locator("#password").fill("Chunk-Upload-Password!24")
            page.locator("#run-button").click()
            progress=[];last=None
            deadline=time.monotonic()+300
            while time.monotonic()<deadline:
                sample=page.evaluate("()=>({title:document.querySelector('#progress-status-title')?.textContent||'',percent:document.querySelector('#progress-percent')?.textContent||''})")
                if sample["title"] or sample["percent"]:
                    if sample!=last:progress.append(sample);last=sample
                if page.locator("#result").is_visible():break
                time.sleep(.1)
            else:raise TimeoutError("large-file server job did not reach a result")
            with page.expect_download(timeout=30000) as download_info:page.locator("#result-download-link").click()
            download=download_info.value;output=temp/"protected-large-output.pdf";download.save_as(output)
            with fitz.open(output) as result:
                encrypted=result.is_encrypted;unlocked=result.authenticate("Chunk-Upload-Password!24") if encrypted else 0
                text="\n".join(p.get_text() for p in result) if unlocked else "";pages=result.page_count
            chunk_requests=[r for r in requests if r["method"]=="PUT" and "/api/uploads/chunked/" in r["path"]]
            progress_titles=[e["title"] for e in progress if e["title"]]
            assert chunk_requests and len(delayed_chunks)>=1 and all(r["status"]<400 for r in responses),{"requests":requests,"responses":responses}
            assert len(set(progress_titles))>=2,progress
            assert encrypted and unlocked and pages==2 and "UPLOAD-CHUNK-1" in text and "UPLOAD-CHUNK-2" in text
            assert not errors,errors
            evidence={"input_bytes":size,"input_mib":round(size/(1024*1024),2),"fixture":"synthetic two-page marker PDF padded with valid trailing whitespace; not the owner's reported original 58 MB file","account_tier":"signed-in Free (isolated local fixture)","generated_pdf_content_bytes":generated_content_bytes,"input_pages":2,"used_chunked_upload":bool(chunk_requests),"chunk_put_requests":len(chunk_requests),"chunk_requests_deliberately_slowed":len(delayed_chunks),"upload_and_job_responses":responses,"progress_samples":progress,"distinct_progress_statuses":len(set(progress_titles)),"output_bytes":output.stat().st_size,"output_pages":pages,"protected":encrypted,"password_authenticated":bool(unlocked),"both_source_markers_present":all(f"UPLOAD-CHUNK-{n}" in text for n in (1,2)),"page_errors":errors,"production_endpoints_contacted":False,"result":"passed"}
            (OUT/"browser-id207-large-chunk-upload.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
            print(json.dumps(evidence,indent=2));browser.close()
    finally:app.terminate();app.wait(timeout=5)
