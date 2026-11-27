"""Run the 69-page Executive Brief end-to-end in isolated local Chrome without provider credentials."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
ROUND=os.getenv("PAPERPLANE_ID2_ROUND","1")

def main():
    evidence={"page_errors":[],"console_errors":[]}
    with TemporaryDirectory(prefix="paperplane-v24-id2-") as name:
        temp=Path(name); data=temp/"data"; data.mkdir(); fixture=temp/"summary-69-pages.pdf"
        with fitz.open() as pdf:
            for n in range(1,70):
                p=pdf.new_page(); p.insert_text((72,42),f"Quarterly Operations Review — Page {n}")
                p.insert_text((72,56),f"Unique verified fact for source page {n}: completion rate is {n} percent.")
                for row in range(30):
                    position = "beginning" if row == 0 else "middle" if row == 14 else "ending" if row == 29 else "detail"
                    marker = f"PAGE-{n:02d}-{position.upper()}-FACT"
                    p.insert_text(
                        (45, 78 + row * 21),
                        f"{marker}: page {n} operational evidence covers decisions, stakeholders, risk controls, and follow-up actions. "
                        "Routine monitoring and audit control detail.",
                        fontsize=7,
                    )
                if n==69: p.insert_text((72,730),"Final page decision: retain all 69 page records for final audit.")
            pdf.save(fixture)
        with socket.socket() as s: s.bind(("127.0.0.1",0)); port=s.getsockname()[1]
        env={k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_","CASHFREE_","SMTP_","RESEND_","OPENAI_","OPENROUTER_","BLUESMINDS_","ANTHROPIC_","GEMINI_","DEEPSEEK_","GOOGLE_API_","AI_","ADMIN_")) and k not in {"TESTING","SESSION_SECRET_KEY"}}
        env.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_PORT":str(port),"PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_SECURE_COOKIES":"false","PYTHONPATH":str(ROOT)})
        app=subprocess.Popen([sys.executable,"app.py"],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True)
                page=browser.new_page(viewport={"width":1280,"height":900})
                page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
                page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
                page.route("**/api/ai/capabilities",lambda route:route.fulfill(status=200,content_type="application/json",body=json.dumps({"executive_brief_available":True,"reason":None})))
                assert page.goto(f"http://127.0.0.1:{port}/ai-intelligence",wait_until="domcontentloaded").status==200
                page.locator("#ai-file-input").set_input_files(str(fixture)); page.locator("#ai-active-doc-bar").wait_for(state="visible",timeout=30000)
                page.wait_for_function("document.querySelector('#trigger-summary-btn') && !document.querySelector('#trigger-summary-btn').disabled",timeout=30000)
                with page.expect_response(lambda r:"/api/ai/summarize" in r.url,timeout=300000) as wait: page.locator("#trigger-summary-btn").click()
                response=wait.value; payload=response.json(); page.wait_for_function("document.querySelector('#summary-mode-badge')?.innerText.includes('Offline')",timeout=30000)
                summary=str(payload.get("summary","")); citations=payload.get("citations",[])
                missing_summary_facts=[n for n in range(1,70) if f"completion rate is {n} percent" not in summary]
                missing_summary_tails=[n for n in range(1,69) if f"PAGE-{n:02d}-ENDING-FACT" not in summary]
                missing_summary_middles=[n for n in range(1,70) if f"PAGE-{n:02d}-MIDDLE-FACT" not in summary]
                missing_summary_beginnings=[n for n in range(1,70) if f"PAGE-{n:02d}-BEGINNING-FACT" not in summary]
                evidence.update({"http_status":response.status,"mode":payload.get("summary_mode"),"citation_count":len(citations),"citation_min":min(citations) if citations else None,"citation_max":max(citations) if citations else None,"all_pages_cited":set(citations)==set(range(1,70)),"missing_page_facts_in_summary":missing_summary_facts,"missing_late_page_facts_in_summary":missing_summary_tails,"missing_middle_page_facts_in_summary":missing_summary_middles,"missing_beginning_page_facts_in_summary":missing_summary_beginnings,"first_fact_present":"completion rate is 1 percent" in summary,"final_fact_present":"retain all 69 page records" in summary,"offline_disclosure":"Offline Analysis" in summary,"badge":page.locator("#summary-mode-badge").inner_text()})
                with page.expect_download(timeout=30000) as d: page.locator("#download-summary-pdf-btn").click()
                download=d.value; output=OUT/(f"browser-id2-round-{ROUND}-"+download.suggested_filename); download.save_as(str(output))
                with fitz.open(output) as pdf:
                    text="\n".join(x.get_text() for x in pdf)
                    evidence["download"]={"filename":download.suggested_filename,"pages":pdf.page_count,"pdf_signature":output.read_bytes()[:5].decode("ascii"),"offline_disclosure":"Offline Analysis" in text,"final_fact_present":"retain all 69 page records" in text,"missing_page_facts":[n for n in range(1,70) if f"completion rate is {n} percent" not in text],"missing_beginning_facts":[n for n in range(1,70) if f"PAGE-{n:02d}-BEGINNING-FACT" not in text],"missing_middle_facts":[n for n in range(1,70) if f"PAGE-{n:02d}-MIDDLE-FACT" not in text],"missing_late_page_facts":[n for n in range(1,69) if f"PAGE-{n:02d}-ENDING-FACT" not in text],"text_chars":len(text)}
                evidence["result"]="passed" if response.status==200 and evidence["all_pages_cited"] and not evidence["missing_page_facts_in_summary"] and not evidence["missing_middle_page_facts_in_summary"] and not evidence["missing_late_page_facts_in_summary"] and evidence["first_fact_present"] and evidence["final_fact_present"] and evidence["offline_disclosure"] and evidence["download"]["pdf_signature"]=="%PDF-" and evidence["download"]["final_fact_present"] and not evidence["download"]["missing_page_facts"] and not evidence["download"]["missing_middle_facts"] and not evidence["download"]["missing_late_page_facts"] and not evidence["page_errors"] and not evidence["console_errors"] else "failed"
                browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    (OUT/f"browser-id2-69page-summary-round-{ROUND}.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8"); print(json.dumps(evidence,indent=2))
    if evidence.get("result")!="passed": raise SystemExit(1)
if __name__=="__main__": main()
