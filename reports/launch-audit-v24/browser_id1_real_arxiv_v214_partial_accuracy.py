"""Exercise the real failed-live 15-page arXiv PDF through current Translate UI.

Only the upstream provider call is replaced with a deterministic bilingual
response; PDF extraction, segmentation, overlay/redaction, coverage checks,
HTTP route, browser interaction, and downloaded PDF parsing are real.
"""
from __future__ import annotations
import hashlib, json, os, socket, sys, threading, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
import re
import uvicorn
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"reports/launch-audit-v24/fixtures/arxiv-1706.03762v7.pdf"
OUT=ROOT/"reports/launch-audit-v24"/os.environ.get("PAPERPLANE_ID1_OUTPUT", "browser-id1-real-arxiv-v214-partial-accuracy.json")
ROUNDS=int(os.environ.get("PAPERPLANE_ID1_ROUNDS", "1"))
LANGUAGE_VALUES=os.environ.get("PAPERPLANE_ID1_LANGUAGES", "es,hi").split(",")
assert SOURCE.is_file(), SOURCE

with TemporaryDirectory(prefix="paperplane-id1-real-arxiv-") as td:
    tmp=Path(td); data=tmp/"data"; data.mkdir()
    os.environ.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_ADMIN_KEY":"controlled-test-admin-key","PAPERPLANE_ADMIN_CODE":"controlled-test-admin-code","PAPERPLANE_SECURE_COOKIES":"false","BLUESMINDS_API_KEY":"controlled-test-provider-key"})
    if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
    import ai_engine, persistence
    from server import app
    persistence.init_db()
    calls={"requests":0,"segments":0}
    def deterministic_provider(system_prompt,user_prompt,timeout_seconds=None,max_attempts=2,**kwargs):
        language="hi" if re.search(r"\b(?:hi|hindi)\b",system_prompt.lower()) else "es"
        payload=json.loads(user_prompt)
        translated=[]
        for item in payload:
            block_id=int(item["id"])
            source=str(item["text"])
            words=re.findall(r"\w+",source,flags=re.UNICODE)
            if len(words)<=2:
                # Keep one/two-word labels short enough for their original
                # diagram/table boxes; long provider boilerplate would fail to fit.
                text="हाँ" if language=="hi" else "es"
            else:
                text=(f"अनुवादित {block_id}" if language=="hi"
                      else f"Traducido {block_id}")
            translated.append({"id":item["id"],"text":text})
        calls["requests"]+=1; calls["segments"]+=len(translated)
        return json.dumps({"translations":translated},ensure_ascii=False)
    ai_engine.call_llm=deterministic_provider
    with socket.socket() as sock: sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
    uv=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=port,log_level="warning",access_log=False))
    thread=threading.Thread(target=uv.run,daemon=True); thread.start()
    evidence={"fixture":{"filename":SOURCE.name,"source_url":"https://arxiv.org/pdf/1706.03762v7","bytes":SOURCE.stat().st_size,"sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),"pages":15},"matrix":[],"page_errors":[],"console_errors":[],"provider":"deterministic local stub; no external AI request"}
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1",port),timeout=.2): break
            except OSError: time.sleep(.1)
        else: raise RuntimeError("local Uvicorn app failed to start")
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True)
            for round_no in range(1, ROUNDS + 1):
                for value,language,marker in (("es","Spanish","Traducido"),("hi","Hindi","अनुवादित")):
                    if value not in LANGUAGE_VALUES:
                        continue
                    context=browser.new_context(viewport={"width":1366,"height":900},accept_downloads=True)
                    page=context.new_page(); errors=[]; console=[]; statuses=[]; failed_requests=[]
                    page.on("pageerror",lambda err:errors.append(str(err)))
                    page.on("console",lambda msg:console.append(msg.text) if msg.type=="error" else None)
                    page.on("response",lambda res:statuses.append(res.status) if "/api/ai/translate" in res.url else None)
                    page.on("requestfailed",lambda req:failed_requests.append({"url":req.url,"error":req.failure}) if "/api/ai/translate" in req.url else None)
                    response=page.goto(f"http://127.0.0.1:{port}/translate-pdf",wait_until="domcontentloaded")
                    assert response and response.status==200
                    page.wait_for_function("window.state && state.operation === 'translate'")
                    page.locator("#file-input").set_input_files(str(SOURCE))
                    page.locator("#target_language").select_option(label=f"{value} ({language})")
                    page.locator("#run-button").click()
                    try:
                        page.locator("#result-content a.btn-download").wait_for(state="visible",timeout=250000)
                    except Exception:
                        evidence["last_failure"]={"round":round_no,"language":language,"api_statuses":statuses,"failed_requests":failed_requests,"page_errors":errors,"console_errors":console,"result_content":page.locator("#result-content").inner_text(timeout=5000) if page.locator("#result-content").count() else "<missing>","visible_toasts":page.locator(".toast, [role=alert]").all_inner_texts()}
                        print(json.dumps(evidence["last_failure"], ensure_ascii=False, indent=2), flush=True)
                        raise
                    result_meta=page.locator("#result-meta").inner_text()
                    assert "99.9% character coverage" in result_meta and "99.5% text block coverage" in result_meta,result_meta
                    assert "Download partial translation" in page.locator("#result-content").inner_text(), page.locator("#result-content").inner_text()
                    assert "Some source text remains unchanged" in page.locator("#result-content").inner_text(), page.locator("#result-content").inner_text()
                    output=tmp/f"round-{round_no}-{value}.pdf"
                    with page.expect_download(timeout=30000) as event: page.locator("#result-content a.btn-download").click()
                    event.value.save_as(output)
                    with fitz.open(output) as pdf:
                        texts=[pg.get_text() for pg in pdf]
                        assert pdf.page_count==15
                        assert all(marker in text or ("es" in text if value=="es" else "हाँ" in text) for text in texts),[(i+1,marker in text) for i,text in enumerate(texts)]
                        assert all(len(text.strip())>0 for text in texts)
                        assert "�" not in "\n".join(texts)
                        assert "Traducci" not in "\n".join(texts) if value=="hi" else "हिंदी" not in "\n".join(texts)
                    assert statuses and statuses[-1]==200,statuses
                    assert not errors and not console,(errors,console)
                    evidence["matrix"].append({"round":round_no,"language":language,"http":statuses[-1],"pages":15,"output_bytes":output.stat().st_size,"result_meta":result_meta,"target_text_present_on_all_pages":True,"page_errors":errors,"console_errors":console})
                    if round_no==2 and value=="hi": page.screenshot(path=str(OUT.parent/"id1-real-arxiv-hindi-result.png"))
                    context.close()
            browser.close()
        evidence["provider_calls"]=calls
        assert calls["requests"] <= 112, calls
        evidence["result"]="passed"
    finally:
        uv.should_exit=True; thread.join(timeout=10)
OUT.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(evidence,ensure_ascii=True,indent=2))
