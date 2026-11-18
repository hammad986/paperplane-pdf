"""Local Chromium checks for v23 P0 UI/download regressions."""
from __future__ import annotations

import json
import base64
import io
import os
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
import time

import fitz
from PIL import Image
from pypdf import PdfReader
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def main():
    results = []
    with TemporaryDirectory(prefix="paperplane-v23-browser-") as temp_name:
        temp = Path(temp_name)
        source = temp / "signed-source.pdf"
        with fitz.open() as document:
            document.new_page().insert_text((72, 72), "Paperplane v23 browser download verification.")
            document.save(source)
        unattributed = temp / "unattributed-report.pdf"
        with fitz.open() as document:
            document.new_page().insert_text((72, 72), "A technical note about processing reliability.")
            document.save(unattributed)
        section_number = temp / "section-number-not-date.pdf"
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((72, 72), "3.3.1 Fragments")
            page.insert_text((72, 112), "Machine Learning methods are discussed here.")
            document.save(section_number)
        annotate_redact_source = temp / "annotate-redact-same-text.pdf"
        with fitz.open() as document:
            document.new_page().insert_text((72, 72), "Important review note for cross-tool search verification.")
            document.save(annotate_redact_source)
        app, base, identity = helper.start_server(temp / "server-data")
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=.2):
                        break
                except OSError:
                    time.sleep(.15)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(accept_downloads=True, viewport={"width": 846, "height": 712})
                page = context.new_page()
                page_errors = []
                page.on("pageerror", lambda err: page_errors.append(str(err)))
                page.goto(base + "/", wait_until="domcontentloaded")
                admin = context.new_page()
                admin.add_init_script("(token => sessionStorage.setItem('pp_admin_session', token))(" + json.dumps(identity["admin"]) + ")")
                admin.goto(base + "/admin", wait_until="domcontentloaded")
                admin.locator("#tab-feedback-btn").click()
                ai_capabilities_response=page.request.get(base+"/api/ai/capabilities")
                ai_connection_response=page.request.post(base+"/api/ai/test-connection")
                ai_health_response=page.request.get(base+"/api/admin/ai-health",headers={"X-Admin-Session":identity["admin"]})
                ai_capabilities=ai_capabilities_response.json(); ai_connection=ai_connection_response.json(); ai_health=ai_health_response.json()
                assert ai_capabilities_response.status==200 and ai_capabilities=={"executive_brief_available":False,"reason":"ai_service_not_configured"},ai_capabilities
                assert ai_connection_response.status==200 and ai_connection.get("status")=="configuration_missing" and ai_connection.get("fallback_active") is False,ai_connection
                assert ai_health_response.status==200 and ai_health.get("status")=="configuration_missing" and ai_health.get("configured") is False,ai_health
                results.append({"case":"ai_capability_and_connection_status_match_missing_provider","capabilities":ai_capabilities,"connection_status":ai_connection.get("status"),"admin_health_status":ai_health.get("status"),"secrets_exposed":False})
                feedback_message = "Synthetic v23 live browser feedback delivery check"
                feedback_post = page.evaluate("""async message => {
                  const response=await fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({message,rating:4,category:'bug'})});
                  return {status:response.status,data:await response.json()};
                }""", feedback_message)
                assert feedback_post["status"] == 200 and feedback_post["data"].get("feedback_id"), feedback_post
                admin.locator("#feedback-tbody").get_by_text(feedback_message, exact=True).wait_for(timeout=15000)
                feedback_delete = page.request.delete(
                    base + "/api/admin/feedback/" + feedback_post["data"]["feedback_id"],
                    headers={"X-Admin-Session":identity["admin"]},
                )
                assert feedback_delete.status == 200, feedback_delete.status
                results.append({"case":"feedback_submission_visible_in_admin_poll_without_refresh","post_status":feedback_post["status"],"admin_row_visible":True,"disposable_entry_deleted":True})
                proxy_audit_emails=[f"proxy-browser-{os.urandom(4).hex()}@example.invalid" for _ in range(2)]
                proxy_audit_ips=["203.0.113.81","203.0.113.82"]
                proxy_audit_attempts=[]
                for email, forwarded_ip in zip(proxy_audit_emails,proxy_audit_ips):
                    attempt=page.evaluate("""async ({email,forwardedIp}) => {
                      const form=new FormData();form.append('email',email);form.append('password','invalid');
                      const response=await fetch('/api/auth/login',{method:'POST',headers:{'X-Forwarded-For':forwardedIp},body:form});
                      return {status:response.status};
                    }""",{"email":email,"forwardedIp":forwarded_ip})
                    assert attempt["status"]==401,attempt
                    proxy_audit_attempts.append(attempt)
                proxy_audit_rows=admin.evaluate("""async ({token,emails}) => {
                  const response=await fetch('/api/admin/audit-summary',{headers:{'X-Admin-Session':token}});
                  const body=await response.json();
                  return Object.fromEntries(body.recent_activity.filter(row=>emails.includes(row.email)).map(row=>[row.email,row.ip_address]));
                }""",{"token":identity["admin"],"emails":proxy_audit_emails})
                assert [proxy_audit_rows.get(email) for email in proxy_audit_emails]==proxy_audit_ips,proxy_audit_rows
                results.append({"case":"trusted_proxy_distinct_client_ips_reach_admin_audit","attempts":proxy_audit_attempts,
                                "audit_ips":proxy_audit_rows,"forwarded_ips":proxy_audit_ips})
                for route in ("/summarize-pdf", "/compare-pdf", "/edit-pdf"):
                    page.goto(base + route, wait_until="domcontentloaded")
                    page.locator("#file-input").set_input_files(str(source))
                    page.wait_for_timeout(120)
                    cloud_modal_open = page.locator("#cloud-modal").evaluate("el => !el.hidden")
                    assert not cloud_modal_open, {"route":route,"cloud_modal_open":cloud_modal_open}
                results.append({"case":"cloud_import_does_not_open_during_dropzone_file_selection","routes":["/summarize-pdf","/compare-pdf","/edit-pdf"],"cloud_modal_open":False})
                cloud_results = []
                cloud_urls = {
                    "w3c_direct_pdf": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
                    "owner_drive_view": "https://drive.google.com/file/d/1dAovOT7FCFaur33cX5_M6SsL6EvZT9rS/view",
                }
                for label, cloud_url in cloud_urls.items():
                    for attempt in (1, 2):
                        response = page.request.post(base + "/api/cloud/sync", multipart={"file_url":cloud_url})
                        payload = response.json()
                        item = {"source":label,"attempt":attempt,"status":response.status}
                        if response.status == 200:
                            imported = base64.b64decode(payload["data_url"].split(",",1)[1])
                            with fitz.open(stream=imported,filetype="pdf") as imported_pdf:
                                item.update({"filename":payload.get("filename"),"pages":imported_pdf.page_count,
                                             "content_checked":imported_pdf.page_count > 0})
                            assert item["content_checked"]
                        else:
                            item["detail"] = payload.get("detail", "")
                        cloud_results.append(item)
                assert [item["status"] for item in cloud_results[:2]] == [200,200], cloud_results
                results.append({"case":"cloud_import_p0_paths_twice","results":cloud_results,
                                "owner_drive_passed":all(item["status"] == 200 for item in cloud_results[2:])})
                author_response = page.request.post(
                    base + "/api/ai/chat",
                    multipart={
                        "question": "Was this written by Albert Einstein?",
                        "file": {"name": "unattributed-report.pdf", "mimeType": "application/pdf", "buffer": unattributed.read_bytes()},
                    },
                )
                author_result = author_response.json()
                assert author_response.status == 200
                assert "can't verify" in author_result["answer"].lower()
                assert "authorship" in author_result["answer"].lower()
                results.append({"case":"unattributed_pdf_false_author_claim", "http_status":author_response.status,
                                "answer":author_result["answer"], "citations":author_result.get("citations")})
                greeting_response = page.request.post(
                    base + "/api/ai/chat",
                    multipart={
                        "question":"Hello, how are you?",
                        "file":{"name":"signed-source.pdf","mimeType":"application/pdf","buffer":source.read_bytes()},
                    },
                )
                greeting_result = greeting_response.json()
                assert greeting_response.status == 200 and "ready to help" in greeting_result["answer"].lower(), greeting_result
                assert not greeting_result.get("citations")
                results.append({"case":"general_greeting_works_with_document_loaded","http_status":greeting_response.status,
                                "answer":greeting_result["answer"],"citations":greeting_result.get("citations")})
                extraction_response = page.request.post(
                    base + "/api/ai/extract",
                    multipart={
                        "doc_type": "general",
                        "file": {"name": "section-number-not-date.pdf", "mimeType": "application/pdf", "buffer": section_number.read_bytes()},
                    },
                )
                extraction_result = extraction_response.json()
                assert extraction_response.status == 200
                extraction_data = extraction_result["data"]
                assert extraction_data["general_data"].get("document_date") is None
                assert "3.3.1" not in " ".join(extraction_data["general_data"].get("detected_topics", []))
                results.append({"case":"smart_metadata_section_number_not_date", "http_status":extraction_response.status,
                                "document_date":extraction_data["general_data"].get("document_date"),
                                "topics":extraction_data["general_data"].get("detected_topics"),
                                "warnings":extraction_data.get("warnings", [])})
                same_text_bytes = annotate_redact_source.read_bytes()
                annotation_response = page.request.post(
                    base + "/api/pdf/annotate",
                    multipart={
                        "annotations": json.dumps([{"type":"highlight","page":1,"text":"Important"}]),
                        "file": {"name":"annotate-redact-same-text.pdf","mimeType":"application/pdf","buffer":same_text_bytes},
                    },
                )
                redaction_response = page.request.post(
                    base + "/api/studio/security/redact",
                    multipart={
                        "redactions": json.dumps([{"page":0,"text":"Important"}]),
                        "file": {"name":"annotate-redact-same-text.pdf","mimeType":"application/pdf","buffer":same_text_bytes},
                    },
                )
                assert annotation_response.status == 200 and redaction_response.status == 200
                annotation_doc = fitz.open(stream=annotation_response.body(), filetype="pdf")
                redaction_doc = fitz.open(stream=redaction_response.body(), filetype="pdf")
                try:
                    assert len(list(annotation_doc[0].annots() or [])) == 1
                    assert "review note" in redaction_doc[0].get_text()
                    assert "Important" not in redaction_doc[0].get_text()
                finally:
                    annotation_doc.close()
                    redaction_doc.close()
                results.append({"case":"annotate_and_redact_find_same_keyword","annotation_status":annotation_response.status,
                                "redaction_status":redaction_response.status,"annotation_count":1,"redacted_text_verified":True})
                chat_source = temp / "chat-markdown.pdf"
                with fitz.open() as document:
                    chat_page = document.new_page()
                    chat_page.insert_text((72, 72), "Project result: total $42. The delivery deadline is 15 December 2026.")
                    document.save(chat_source)
                ai_empty_context=browser.new_context(viewport={"width":1366,"height":900})
                ai_empty_page=ai_empty_context.new_page()
                ai_empty_page.goto(base+"/ai-intelligence",wait_until="domcontentloaded")
                ai_empty_page.locator("#ai-empty-state").wait_for(state="visible")
                ai_upload_copy=ai_empty_page.locator("#ai-upload-zone").inner_text()
                ai_upload_geometry=ai_empty_page.locator("#ai-upload-zone").evaluate("el=>({width:el.getBoundingClientRect().width,scrollWidth:el.scrollWidth,documentWidth:document.documentElement.scrollWidth,buttonVisible:!!document.querySelector('#ai-upload-btn')?.getClientRects().length})")
                assert "Upload PDF to chat" in ai_upload_copy and ai_upload_geometry["buttonVisible"], (ai_upload_copy,ai_upload_geometry)
                assert ai_upload_geometry["documentWidth"]==1366 and ai_upload_geometry["scrollWidth"]<=ai_upload_geometry["width"],ai_upload_geometry
                ai_empty_page.set_viewport_size({"width":390,"height":844})
                ai_empty_page.wait_for_timeout(100)
                ai_upload_mobile=ai_empty_page.locator("#ai-upload-zone").evaluate("el=>({width:el.getBoundingClientRect().width,scrollWidth:el.scrollWidth,documentWidth:document.documentElement.scrollWidth,copyVisible:el.innerText.includes('Upload PDF to chat'),buttonVisible:!!document.querySelector('#ai-upload-btn')?.getClientRects().length})")
                assert ai_upload_mobile["copyVisible"] and ai_upload_mobile["buttonVisible"] and ai_upload_mobile["documentWidth"]==390 and ai_upload_mobile["scrollWidth"]<=ai_upload_mobile["width"],ai_upload_mobile
                ai_empty_page.set_viewport_size({"width":1366,"height":900})
                ai_empty_page.locator("#chat-input").fill("Hello, how are you?")
                ai_empty_page.locator("#chat-send-btn").click()
                ai_empty_page.wait_for_function("document.querySelector('.ai-stream-bubble .ai-stage-line span:last-child')?.textContent === 'Complete'",timeout=20000)
                ai_empty_page.locator("#ai-chat-clear-btn").click()
                ai_empty_page.locator("#ai-empty-state").wait_for(state="visible",timeout=5000)
                clear_chat_copy=ai_empty_page.locator("#ai-upload-zone").inner_text()
                assert "Upload PDF to chat" in clear_chat_copy
                results.append({"case":"ai_empty_state_invites_pdf_upload_to_chat","desktop":ai_upload_geometry,"mobile":ai_upload_mobile,"empty_after_clear_chat":True})
                ai_empty_context.close()
                page.goto(base+"/ai-intelligence",wait_until="domcontentloaded")
                page.locator("#ai-file-input").set_input_files(str(chat_source))
                page.locator("#chat-input").fill("Summarize the main points in the uploaded PDF.")
                page.locator("#chat-send-btn").click()
                page.wait_for_function("document.querySelector('.ai-stream-bubble .ai-stage-line span:last-child')?.textContent === 'Complete'", timeout=20000)
                chat_rendered = page.locator(".ai-stream-bubble").evaluate("node => ({html:node.querySelector('.ai-stream-text').innerHTML,text:node.querySelector('.ai-stream-text').textContent,citations:[...node.querySelectorAll('.chat-citation-tags [data-ai-page]')].map(el=>Number(el.dataset.aiPage))})")
                assert "[[Page" not in chat_rendered["html"] and "[Page" not in chat_rendered["html"], chat_rendered
                assert "**" not in chat_rendered["text"] and chat_rendered["citations"], chat_rendered
                assert len(chat_rendered["citations"]) == 1
                assert chat_rendered["html"].count('data-ai-page="1"') == 1, chat_rendered
                results.append({"case":"ai_chat_markdown_and_nested_citation_rendering", **chat_rendered})
                page.goto(base + "/pricing", wait_until="domcontentloaded")
                sticky_nav_checks = []
                page.set_viewport_size({"width":1104,"height":760})
                for path in ("/ocr-pdf", "/remove-pages-pdf"):
                    page.goto(base + path, wait_until="domcontentloaded")
                    page.locator("#tool-title").wait_for()
                    page.evaluate("document.querySelector('.main-area').scrollTop=560")
                    page.wait_for_timeout(100)
                    geometry = page.evaluate("""() => {
                      const title=document.querySelector('#tool-title');
                      const header=document.querySelector('.topbar');
                      const mobileBar=document.querySelector('.mobile-workspace-bar');
                      const t=title.getBoundingClientRect(),h=header.getBoundingClientRect(),m=mobileBar.getBoundingClientRect();
                      return {title:[t.top,t.bottom],topbar:[h.top,h.bottom],mobileBar:[m.top,m.bottom],mainScroll:document.querySelector('.main-area').scrollTop};
                    }""")
                    sticky_nav_checks.append({"path":path,"geometry":geometry})
                    assert geometry["mainScroll"] >= 500
                    assert geometry["title"][0] >= geometry["topbar"][1] - 1 or geometry["title"][1] <= geometry["topbar"][0] + 1, geometry
                results.append({"case":"tool_heading_not_obscured_after_scroll_1104px","checks":sticky_nav_checks})
                page.set_viewport_size({"width":1366,"height":900})
                page.goto(base + "/pricing", wait_until="domcontentloaded")
                developers_response=page.goto(base+"/developers",wait_until="domcontentloaded")
                assert developers_response and developers_response.status==200
                developers_text=page.locator("body").inner_text().lower()
                assert "bluesminds" not in developers_text, "internal provider branding leaked onto the public developer page"
                public_assets={path:page.request.get(base+path).text().lower() for path in ("/","/assets/app.js")}
                assert all("ilovepdf" not in content for content in public_assets.values()), "competitor name leaked into shipped HTML/JS"
                spec_links={"swagger":page.locator("#view-api-docs a.swagger-link").get_attribute("href"),
                            "redoc":page.locator("#view-api-docs a.redoc-link").get_attribute("href"),
                            "footer":page.locator("#footer-link-api-docs").get_attribute("href")}
                assert spec_links=={"swagger":"/spec/swagger","redoc":"/spec/redoc","footer":"/spec/swagger"},spec_links
                for path, marker in ((spec_links["swagger"],"SwaggerUIBundle"),(spec_links["redoc"],"redoc")):
                    spec_response=page.request.get(base+path)
                    assert spec_response.status==200 and marker.lower() in spec_response.text().lower()
                schema_response=page.request.get(base+"/spec/openapi.json")
                schema=schema_response.json()
                assert schema_response.status==200 and len(schema.get("paths",{}))>50
                results.append({"case":"developer_swagger_redoc_and_openapi_routes","links":spec_links,
                                "openapi_paths":len(schema["paths"]),"all_local_routes_status_200":True,
                                "no_public_bluesminds_leak":True,"no_shipped_ilovepdf_reference":True})
                tool_desk_response=page.goto(base+"/tool-desk",wait_until="domcontentloaded")
                page.wait_for_function("!document.querySelector('#view-tool-desk-directory').hidden")
                assert tool_desk_response and tool_desk_response.status==200
                assert page.locator("#tool-desk-tools-catalog").is_visible()
                alias_routes={}
                for alias, canonical in (("/fill-form","/fill-pdf-form"),("/ai-translate","/translate-pdf")):
                    page.goto(base+alias,wait_until="domcontentloaded")
                    alias_routes[alias]={"final_url":page.url,"status":page.locator("#tool-title").count()}
                    assert page.url.endswith(canonical) and page.locator("#tool-title").count()==1, alias_routes[alias]
                results.append({"case":"tool_desk_view_and_tool_route_aliases","directory_visible":True,"aliases":alias_routes})
                merge_context_response=page.request.get(base+"/api/seo/merge")
                split_context_response=page.request.get(base+"/api/seo/split")
                assert merge_context_response.ok and split_context_response.ok
                merge_context=merge_context_response.json(); split_context=split_context_response.json()
                assert merge_context["heading"] != split_context["heading"]
                page.goto(base+"/merge-pdf",wait_until="domcontentloaded")
                page.wait_for_function("document.querySelector('.seo-content')?.dataset.operation === 'merge'")
                initial_seo=page.locator(".seo-content").inner_text()
                assert merge_context["heading"] in initial_seo
                page.locator('#sidebar-tools-container [data-select-operation="split"]').click()
                page.wait_for_function("document.querySelector('.seo-content')?.dataset.operation === 'split'")
                active_seo=page.locator(".seo-content").inner_text()
                assert split_context["heading"] in active_seo and merge_context["heading"] not in active_seo
                assert split_context["faqs"][0][0] in active_seo and merge_context["faqs"][0][0] not in active_seo
                results.append({"case":"spa_tool_landing_clears_previous_workflow_faq_copy","initial_operation":"merge","previous_heading":merge_context["heading"],"next_operation":"split","final_heading":split_context["heading"],"final_first_faq":split_context["faqs"][0][0],"old_heading_absent":True,"old_faq_absent":True})
                page.goto(base+"/merge-pdf",wait_until="domcontentloaded")
                page.set_viewport_size({"width":390,"height":844})
                page.wait_for_timeout(150)
                run_label=page.locator("#run-button").evaluate("el=>({text:el.innerText.trim(),wordBreak:getComputedStyle(el).wordBreak,overflowWrap:getComputedStyle(el).overflowWrap,whiteSpace:getComputedStyle(el).whiteSpace,rect:el.getBoundingClientRect().toJSON()})")
                assert run_label["wordBreak"] in ("normal","keep-all") and run_label["overflowWrap"] in ("normal","break-word"),run_label
                results.append({"case":"run_button_label_does_not_split_midword","viewport":390,"label":run_label})
                page.set_viewport_size({"width":1366,"height":900})
                page.goto(base+"/studio",wait_until="domcontentloaded")
                page.locator("#studio-pages-toggle-btn").click()
                toggle_geometry=page.evaluate("""() => {
                  const sidebar=document.querySelector('#studio-thumbnails-bar').getBoundingClientRect();
                  const toolbar=document.querySelector('#studio-toolbar').getBoundingClientRect();
                  return {sidebar:[sidebar.x,sidebar.right,sidebar.width],toolbar:[toolbar.x,toolbar.right,toolbar.width],
                    collapsed:document.querySelector('#app-shell').classList.contains('studio-pages-collapsed')};
                }""")
                assert toggle_geometry["collapsed"] and toggle_geometry["toolbar"][2]>0,toggle_geometry
                page.locator("#studio-pages-toggle-btn").click()
                toggle_geometry=page.evaluate("""() => {
                  const sidebar=document.querySelector('#studio-thumbnails-bar').getBoundingClientRect();
                  const toolbar=document.querySelector('#studio-toolbar').getBoundingClientRect();
                  return {sidebar:[sidebar.x,sidebar.right,sidebar.width],toolbar:[toolbar.x,toolbar.right,toolbar.width],
                    collapsed:document.querySelector('#app-shell').classList.contains('studio-pages-collapsed')};
                }""")
                assert not toggle_geometry["collapsed"] and toggle_geometry["sidebar"][2]>0 and toggle_geometry["toolbar"][0]>=toggle_geometry["sidebar"][1]-1,toggle_geometry
                results.append({"case":"studio_sidebar_toggle_does_not_cover_toolbar","expanded_geometry":toggle_geometry})
                page.set_viewport_size({"width":1366,"height":900})
                page.goto(base+"/studio",wait_until="domcontentloaded")
                start=time.perf_counter()
                first_open=page.evaluate("""async payload => {
                  const bytes=Uint8Array.from(atob(payload),ch=>ch.charCodeAt(0));
                  return await loadDocumentIntoStudio(new File([bytes],'first-paint.pdf',{type:'application/pdf'}));
                }""",base64.b64encode(source.read_bytes()).decode("ascii"))
                assert first_open
                page.wait_for_function("""() => {
                  const canvas=document.querySelector('#studio-page-stack .studio-page-sheet[data-page="1"] .pdf-page-canvas');
                  if(!canvas?.width||!canvas?.height)return false;
                  const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
                  for(let i=0;i<pixels.length;i+=32)if(pixels[i]<245||pixels[i+1]<245||pixels[i+2]<245)return true;
                  return false;
                }""",timeout=5000)
                first_paint_seconds=time.perf_counter()-start
                assert first_paint_seconds<5.0,first_paint_seconds
                results.append({"case":"studio_first_page_canvas_paints_within_5_seconds","elapsed_seconds":round(first_paint_seconds,3)})
                page.goto(base+"/ai-intelligence",wait_until="domcontentloaded")
                ai_text=page.locator("#view-ai-studio").inner_text()
                ai_banner_phrase="Your AI PDF and full chat history save in this browser"
                assert ai_banner_phrase.lower() not in ai_text.lower(), "obsolete AI local-history banner is visible"
                results.append({"case":"ai_studio_has_no_obsolete_local_history_banner","banner_absent":True})
                page.goto(base+"/studio",wait_until="domcontentloaded")
                page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=10000)
                # Let the initial route/auth reconciliation finish before
                # measuring scroll-driven footer visibility.
                page.wait_for_timeout(300)
                studio_shell=page.evaluate("""() => {
                  const buttons=[...document.querySelectorAll('#studio-toolbar button')].filter(el=>el.getClientRects().length);
                  const tops=buttons.map(el=>Math.round(el.getBoundingClientRect().top)).sort((a,b)=>a-b);
                  const rows=[]; for(const top of tops){if(!rows.length||top-rows[rows.length-1]>10)rows.push(top);}
                  const footer=document.querySelector('.app-global-footer');
                  return {text:document.querySelector('#view-pdf-studio').innerText,
                    toolbar:document.querySelector('#studio-toolbar').getBoundingClientRect().toJSON(),
                    visibleButtons:buttons.length,toolbarRowTops:rows,viewport:innerWidth,
                    documentWidth:document.documentElement.scrollWidth,footerVisibility:footer?getComputedStyle(footer).visibility:'missing'};
                }""")
                assert "PDF and page edits save here" not in studio_shell["text"]
                assert "Clear saved work" not in studio_shell["text"]
                assert studio_shell["viewport"] == 1366 and len(studio_shell["toolbarRowTops"]) <= 4,studio_shell
                assert studio_shell["toolbar"]["height"] <= 180 and studio_shell["visibleButtons"] >= 20,studio_shell
                assert studio_shell["documentWidth"] <= 1366
                assert studio_shell["footerVisibility"] == "hidden",studio_shell
                scroll_test_before=page.evaluate("""() => { const main=document.querySelector('.main-area');
                  const spacer=document.createElement('div'); spacer.dataset.auditScrollSpacer='1'; spacer.style.height='2000px';
                  main.dataset.auditOriginalStyle=main.getAttribute('style')||'';
                  main.style.height='320px'; main.style.overflowY='auto'; main.appendChild(spacer); main.scrollTop=20;
                  main.dispatchEvent(new Event('scroll',{bubbles:true})); window.dispatchEvent(new Event('scroll'));
                  return {scrollTop:main.scrollTop,scrollHeight:main.scrollHeight,clientHeight:main.clientHeight,
                    revealed:document.documentElement.classList.contains('footer-revealed')};
                }""")
                assert scroll_test_before["scrollTop"] > 12,scroll_test_before
                page.wait_for_function("getComputedStyle(document.querySelector('.app-global-footer')).visibility === 'visible'", timeout=3000)
                footer_revealed=page.evaluate("getComputedStyle(document.querySelector('.app-global-footer')).visibility")
                assert footer_revealed == "visible",footer_revealed
                page.evaluate("""() => { document.querySelector('[data-audit-scroll-spacer]')?.remove();
                  const main=document.querySelector('.main-area'); const original=main.dataset.auditOriginalStyle;
                  if(original)main.setAttribute('style',original);else main.removeAttribute('style'); delete main.dataset.auditOriginalStyle;
                }""")
                results.append({"case":"studio_desktop_has_no_persistent_save_banner_and_fits","banner_absent":True,
                                "toolbar_height":studio_shell["toolbar"]["height"],"toolbar_rows":len(studio_shell["toolbarRowTops"]),
                                "visible_buttons":studio_shell["visibleButtons"],"document_width":studio_shell["documentWidth"],
                                "footer_hidden_until_scroll":True,"footer_revealed_after_scroll":footer_revealed})
                page.goto(base+"/pricing",wait_until="domcontentloaded")
                page.wait_for_selector("#pricing-limits-table tbody tr", timeout=10000)
                limits_rows = page.locator("#pricing-limits-table tbody tr").count()
                operation_count = page.evaluate("Object.keys(JSON.parse(document.querySelector('#paperplane-bootstrap').textContent).operations).length")
                assert limits_rows == operation_count, {"rows":limits_rows,"operations":operation_count}
                for slug, expected in (("refund","owner approval"),("contact","response expectation"),("status","No live uptime monitor")):
                    response=page.goto(base + "/" + slug, wait_until="domcontentloaded")
                    assert response and response.status == 200
                    assert expected.lower() in page.locator(".seo-lede").inner_text().lower()
                page.goto(base + "/privacy", wait_until="domcontentloaded")
                assert "owner review required" in page.locator("#view-legal .view-header-badge").inner_text().lower()
                assert "AI provider" in page.locator("#full-privacy-pane").inner_text()
                page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                assert page.locator(".seo-limits-link a[href='/pricing#pricing-limits-table']").count() == 1
                results.append({"case":"per_tool_limits_and_draft_billing_support_pages","operations":limits_rows,"draft_routes":["/privacy","/refund","/contact","/status"]})
                for path in ("/split-pdf", "/merge-pdf", "/compress-pdf"):
                    response = page.goto(base + path, wait_until="domcontentloaded")
                    assert response and response.status == 200
                    page.locator("#tool-title").wait_for()
                    page.locator("#file-input").set_input_files(str(source))
                    page.locator("#run-button").scroll_into_view_if_needed()
                    geometry = page.evaluate("""() => {
                      const button = document.querySelector('#run-button');
                      const nav = document.querySelector('.mobile-workspace-bar');
                      const b = button.getBoundingClientRect(), n = nav.getBoundingClientRect();
                      return {button: [b.left,b.top,b.right,b.bottom], nav: [n.left,n.top,n.right,n.bottom],
                        intersects: b.width > 0 && b.left < n.right && b.right > n.left && b.top < n.bottom && b.bottom > n.top};
                    }""")
                    assert not geometry["intersects"], (path, geometry)
                    results.append({"case": "mobile_action_uncovered", "path": path, "viewport": [846,712], **geometry})
                for width, height in ((1280,800),(1024,768)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.goto(base + "/ai-intelligence", wait_until="domcontentloaded")
                    page.wait_for_timeout(500)
                    crumb = page.locator(".breadcrumb-trail").inner_text()
                    assert "Paperplane" in crumb and "Workspace" in crumb and "AI Document Intelligence" in crumb, crumb
                    sizes = page.locator(".breadcrumb-trail span, .breadcrumb-trail b").evaluate_all(
                        "els => els.map(e => ({text:e.textContent.trim(), client:e.clientWidth, scroll:e.scrollWidth}))")
                    results.append({"case":"breadcrumb", "viewport":[width,height], "text":crumb, "items":sizes})
                pro_token = identity["accounts"][0][1]
                context.add_cookies([{"name":"paperplane_token","value":pro_token,"url":base,"httpOnly":True}])

                guest_context = browser.new_context()
                guest_page = guest_context.new_page()
                guest_page.goto(base + "/", wait_until="domcontentloaded")
                independent_guest_context=browser.new_context()
                independent_guest_page=independent_guest_context.new_page()
                independent_guest_page.goto(base+"/",wait_until="domcontentloaded")
                first_guest_status=guest_page.evaluate("""async payload => {
                  const form=new FormData();form.append('operation','metadata');form.append('options','{}');
                  form.append('files',new File([Uint8Array.from(atob(payload),c=>c.charCodeAt(0))],'quota.pdf'));
                  return (await fetch('/api/jobs',{method:'POST',body:form})).status;
                }""",base64.b64encode(source.read_bytes()).decode("ascii"))
                assert first_guest_status==202,first_guest_status
                first_guest_usage=guest_page.evaluate("async () => (await(await fetch('/api/billing/status')).json()).usage_today")
                independent_guest_usage=independent_guest_page.evaluate("async () => (await(await fetch('/api/billing/status')).json()).usage_today")
                assert first_guest_usage==1 and independent_guest_usage==0,{
                    "first_guest_usage":first_guest_usage,"independent_guest_usage":independent_guest_usage}
                guest_quota = guest_page.evaluate("""async ({payload,firstStatus}) => {
                  const makeRequest = async () => {
                    const form=new FormData(); form.append('operation','metadata'); form.append('options','{}');
                    form.append('files',new File([Uint8Array.from(atob(payload),c=>c.charCodeAt(0))],'quota.pdf'));
                    return await fetch('/api/jobs',{method:'POST',body:form});
                  };
                  const statuses=[firstStatus];
                  for(let i=1;i<10;i++){const response=await makeRequest();statuses.push(response.status);if(!response.ok)break;}
                  const usage=await(await fetch('/api/billing/status')).json();
                  const eleventh=await makeRequest();
                  const cap=await eleventh.json();
                  return {statuses,usageToday:usage.usage_today,remaining:usage.remaining_today,
                    eleventhStatus:eleventh.status,capCode:cap.detail?.code,capUsage:cap.detail?.usage};
                }""",{"payload":base64.b64encode(source.read_bytes()).decode("ascii"),"firstStatus":first_guest_status})
                assert guest_quota["statuses"] == [202]*10 and guest_quota["usageToday"] == 10, guest_quota
                assert guest_quota["remaining"] == 0 and guest_quota["eleventhStatus"] == 402
                assert guest_quota["capCode"] == "TIER_LIMIT_REACHED" and guest_quota["capUsage"] == 10, guest_quota
                assert any(cookie["name"] == "paperplane_guest_quota" for cookie in guest_context.cookies(base))
                results.append({"case":"guest_daily_server_operation_cap_enforced","evidence":guest_quota,
                                "isolated_browser_usage":{"active_guest":first_guest_usage,"independent_guest":independent_guest_usage}})
                independent_guest_context.close()
                guest_context.close()

                free_context=browser.new_context(viewport={"width":1366,"height":900})
                free_context.add_cookies([{"name":"paperplane_token","value":identity["accounts"][1][1],"url":base,"httpOnly":True}])
                free_page=free_context.new_page()
                free_page.goto(base+"/",wait_until="domcontentloaded")
                free_quota=free_page.evaluate("""async payload => {
                  const submit=async()=>{const form=new FormData();form.append('operation','metadata');form.append('options','{}');
                    form.append('files',new File([Uint8Array.from(atob(payload),c=>c.charCodeAt(0))],'free-quota.pdf'));
                    const response=await fetch('/api/jobs',{method:'POST',body:form});return {status:response.status,body:await response.json()};};
                  const allowed=[];for(let i=0;i<10;i++)allowed.push((await submit()).status);
                  const usage=await(await fetch('/api/billing/status')).json();const eleventh=await submit();
                  return {allowed,usageToday:usage.usage_today,dailyLimit:usage.daily_limit,eleventhStatus:eleventh.status,
                    code:eleventh.body.detail?.code,tier:eleventh.body.detail?.tier,blockedUsage:eleventh.body.detail?.usage};
                }""",base64.b64encode(source.read_bytes()).decode("ascii"))
                assert free_quota["allowed"]==[202]*10 and free_quota["usageToday"]==10 and free_quota["dailyLimit"]==10,free_quota
                assert free_quota["eleventhStatus"]==402 and free_quota["code"]=="TIER_LIMIT_REACHED" and free_quota["tier"]=="free" and free_quota["blockedUsage"]==10,free_quota
                results.append({"case":"authenticated_free_tier_cannot_bypass_daily_operation_cap","evidence":free_quota})
                free_context.close()

                def browser_job(operation, filename, payload, options):
                    result = page.evaluate("""async ({operation, filename, payload, options}) => {
                      const bytes = Uint8Array.from(atob(payload), ch => ch.charCodeAt(0));
                      const form = new FormData();
                      form.append('operation', operation);
                      form.append('options', JSON.stringify(options));
                      form.append('files', new File([bytes], filename));
                      const started = await fetch('/api/jobs', {method:'POST', body:form});
                      if (!started.ok) throw new Error(await started.text());
                      const job = await started.json();
                      let state;
                      for (let i=0; i<240; i++) {
                        await new Promise(resolve => setTimeout(resolve, 250));
                        const response = await fetch(job.status_url);
                        state = await response.json();
                        if (state.status === 'completed') break;
                        if (state.status === 'failed') throw new Error(state.error || 'job failed');
                      }
                      if (state?.status !== 'completed') throw new Error('job timed out');
                      const download = await fetch(job.download_url);
                      if (!download.ok) throw new Error(`download failed: ${download.status}`);
                      const output = new Uint8Array(await download.arrayBuffer());
                      let binary = '';
                      for (let i=0; i<output.length; i+=8192) binary += String.fromCharCode(...output.subarray(i,i+8192));
                      return {name:state.output_name, data:btoa(binary), warning:state.warning, outputSize:state.output_size};
                    }""", {"operation":operation,"filename":filename,
                          "payload":base64.b64encode(payload).decode("ascii"),"options":options})
                    return result

                aadhaar_source=fitz.open()
                aadhaar_page=aadhaar_source.new_page(width=595,height=842)
                aadhaar_page.insert_text((72,100),"Synthetic Aadhaar: 1234 5678 9012",fontsize=18)
                aadhaar_bytes=aadhaar_source.tobytes();aadhaar_source.close()
                aadhaar_result=browser_job("mask_aadhaar","synthetic-aadhaar.pdf",aadhaar_bytes,{})
                aadhaar_output_path=temp/"synthetic-aadhaar-masked.pdf"
                aadhaar_output_path.write_bytes(base64.b64decode(aadhaar_result["data"]))
                with fitz.open(aadhaar_output_path) as aadhaar_output:
                    aadhaar_text=aadhaar_output[0].get_text()
                    mask_rects=aadhaar_output[0].search_for("XXXX XXXX")
                    assert "1234 5678" not in aadhaar_text and "12345678" not in aadhaar_text,aadhaar_text
                    assert "9012" in aadhaar_text and mask_rects,aadhaar_text
                    pix=aadhaar_output[0].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
                    masked_render=Image.frombytes("RGB",(pix.width,pix.height),pix.samples)
                    rect=mask_rects[0]*2
                    mask_crop=masked_render.crop((int(rect.x0),int(rect.y0),int(rect.x1),int(rect.y1)))
                    mean_mask_luminance=sum(mask_crop.convert("L").getdata())/max(1,mask_crop.width*mask_crop.height)
                    assert mean_mask_luminance<90,mean_mask_luminance
                results.append({"case":"aadhaar_mask_output_hides_first_eight_and_preserves_last_four","source":"1234 5678 9012","output_text":aadhaar_text.strip(),"rendered_mask_mean_luminance":round(mean_mask_luminance,2),"content_checked":True})

                flatten_source=fitz.open()
                flatten_page=flatten_source.new_page(width=595,height=842)
                flatten_page.insert_text((72,90),"Highlight appearance must be baked into page content.",fontsize=12)
                highlight=flatten_page.add_highlight_annot(fitz.Rect(70,72,365,96))
                highlight.set_info(content="v23 flattened annotation evidence")
                flatten_bytes=flatten_source.tobytes()
                flatten_source.close()
                flattened_job=browser_job("flatten","flatten-highlight-fixture.pdf",flatten_bytes,{})
                flattened_path=temp/"flatten-highlight-output.pdf"
                flattened_path.write_bytes(base64.b64decode(flattened_job["data"]))
                with fitz.open(flattened_path) as flattened_doc:
                    flattened_text=flattened_doc[0].get_text()
                    active_annots=list(flattened_doc[0].annots() or [])
                    pix=flattened_doc[0].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
                    pixels=Image.frombytes("RGB",(pix.width,pix.height),pix.samples)
                    yellow_pixels=sum(1 for red,green,blue in pixels.get_flattened_data() if red>150 and green>150 and blue<190 and red>blue+25)
                    flattened_pages=flattened_doc.page_count
                assert flattened_pages==1 and not active_annots and "Highlight appearance must be baked" in flattened_text and yellow_pixels>100,{
                    "pages":flattened_pages,"active_annotations":len(active_annots),"text":flattened_text,"yellow_pixels":yellow_pixels}
                results.append({"case":"flatten_bakes_highlight_appearance_and_removes_active_annotation",
                                "pages":flattened_pages,"active_annotations":len(active_annots),"yellow_pixels":yellow_pixels,
                                "content_checked":True})

                split_range_source=fitz.open()
                for page_number in range(1,11):
                    split_page=split_range_source.new_page()
                    split_page.insert_text((72,72),f"Split range source page {page_number}.")
                split_range_bytes=split_range_source.tobytes()
                split_range_source.close()
                range_outputs=[]
                for label, page_spec, expected_pages in (("range_1_2","1-2",[1,2]),("single_page_1","1",[1]),("duplicate_selection","1,1,2",[1,2])):
                    result=browser_job("split","split-range-source.pdf",split_range_bytes,{"pages":page_spec})
                    output_path=temp/f"split-range-{label}.pdf"
                    output_path.write_bytes(base64.b64decode(result["data"]))
                    with fitz.open(output_path) as split_output:
                        texts=[" ".join(split_output[index].get_text().split()) for index in range(split_output.page_count)]
                    expected_texts=[f"Split range source page {number}." for number in expected_pages]
                    assert texts==expected_texts,(label,page_spec,texts,expected_texts)
                    range_outputs.append({"selection":label,"page_spec":page_spec,"pages":len(texts),"texts":texts})
                results.append({"case":"split_ranges_and_duplicate_selection_match_requested_content",
                                "runs":range_outputs,"content_checked":True})

                remove_latency_source = temp / "remove-latency-fixture.pdf"
                with fitz.open() as document:
                    for page_number in range(1,11):
                        image = Image.effect_noise((1300,900),70).convert("RGB")
                        image_bytes = io.BytesIO()
                        image.save(image_bytes,format="JPEG",quality=55)
                        pdf_page = document.new_page(width=595,height=842)
                        pdf_page.insert_image(fitz.Rect(0,0,595,842),stream=image_bytes.getvalue())
                        pdf_page.insert_text((24,36),f"Remove latency fixture page {page_number}.",fontsize=10,color=(0,0,0))
                    document.save(remove_latency_source,deflate=True,garbage=3)
                remove_source_bytes=remove_latency_source.read_bytes()
                if not 4_500_000 <= len(remove_source_bytes) <= 6_500_000:
                    raise AssertionError(f"Controlled Remove Pages input must be 4.5–6.5 MB, got {len(remove_source_bytes)} bytes")
                remove_rounds=[]
                for remove_round in (1,2):
                    started=time.monotonic()
                    removed=browser_job("remove",remove_latency_source.name,remove_source_bytes,{"pages":"2"})
                    removed_path=temp/f"remove-latency-output-{remove_round}.pdf"
                    removed_path.write_bytes(base64.b64decode(removed["data"]))
                    with fitz.open(removed_path) as removed_doc:
                        assert removed_doc.page_count==9
                        assert "page 3" in removed_doc[1].get_text().lower()
                    elapsed=round(time.monotonic()-started,3)
                    remove_rounds.append({"round":remove_round,"elapsed_seconds":elapsed,
                                          "output_bytes":removed_path.stat().st_size,"pages":9,"page2_is_original_page3":True})
                results.append({"case":"remove_pages_first_attempt_latency_on_5mb_pdf","source_bytes":len(remove_source_bytes),
                                "source_pages":10,"runs":remove_rounds})

                metadata_source = temp / "metadata-source.pdf"
                with fitz.open() as document:
                    document.new_page().insert_text((72,72), "Browser metadata provenance fixture")
                    document.set_metadata({"title":"Before title","author":"Original Author","creator":"LaTeX with hyperref",
                                           "producer":"Original Producer","creationDate":"D:20200102030405Z"})
                    document.save(metadata_source)
                metadata_job = browser_job("metadata", metadata_source.name, metadata_source.read_bytes(), {"title":"After title"})
                metadata_output = temp / metadata_job["name"]
                metadata_output.write_bytes(base64.b64decode(metadata_job["data"]))
                edited_metadata = PdfReader(str(metadata_output)).metadata
                assert edited_metadata.title == "After title" and edited_metadata.author == "Original Author"
                assert edited_metadata.creator == "LaTeX with hyperref" and edited_metadata.producer == "Original Producer"
                assert edited_metadata.raw_get("/CreationDate") == "D:20200102030405Z"
                results.append({"case":"metadata_browser_output_preserves_provenance","content_checked":True})

                markdown_job = browser_job("pdf_to_markdown", "a5e7074e4bb844cdb8a39a50783e06b5_browser-download.pdf",
                                             source.read_bytes(), {"pages":"all"})
                markdown = base64.b64decode(markdown_job["data"]).decode("utf-8")
                assert "a5e7074e4bb844cdb8a39a50783e06b5" not in markdown
                assert "Paperplane v23 browser download verification" in markdown
                results.append({"case":"pdf_to_markdown_browser_output_content_checked","output_name":markdown_job["name"]})

                photo_source = temp / "wide-photo.png"
                Image.new("RGB", (200,100), "red").save(photo_source)
                photo_job = browser_job("photo_resize", photo_source.name, photo_source.read_bytes(), {"width":100,"height":100})
                photo_output = temp / photo_job["name"]
                photo_output.write_bytes(base64.b64decode(photo_job["data"]))
                with Image.open(photo_output) as resized:
                    assert resized.size == (100,100) and resized.convert("RGB").getpixel((50,10)) == (255,255,255)
                results.append({"case":"photo_resize_browser_output_aspect_preserved","size":[100,100]})

                import random
                rng = random.Random(230319)
                noise = bytes(rng.randrange(256) for _ in range(1200 * 1600 * 3))
                noisy_photo = Image.frombytes("RGB", (1200,1600), noise)
                noisy_jpg = temp / "target-miss.jpg"
                noisy_photo.save(noisy_jpg, "JPEG", quality=98)
                compression_source = temp / "target-miss.pdf"
                with fitz.open() as document:
                    pdf_page = document.new_page(width=595,height=842)
                    pdf_page.insert_image(pdf_page.rect, filename=str(noisy_jpg))
                    document.save(compression_source, garbage=3, deflate=True)
                compression_job = browser_job("compress", compression_source.name, compression_source.read_bytes(), {"preset":"100kb"})
                compressed_pdf = temp / compression_job["name"]
                compressed_pdf.write_bytes(base64.b64decode(compression_job["data"]))
                assert compression_job["warning"] and "target could not be reached" in compression_job["warning"], compression_job
                assert compression_job["outputSize"] > 98 * 1024
                with fitz.open(compressed_pdf) as output_doc:
                    assert output_doc.page_count == 1
                    pix = output_doc[0].get_pixmap(matrix=fitz.Matrix(.25,.25), alpha=False)
                    assert sum(pix.samples) / len(pix.samples) > 10
                results.append({"case":"compression_missed_target_warning_content_checked","output_bytes":compression_job["outputSize"],"warning":compression_job["warning"]})

                page.goto(base + "/split-pdf", wait_until="domcontentloaded")
                page.locator("#run-button").wait_for()
                progress = page.evaluate("""() => {
                  updateProgress(2, 9.6, 'Uploading files…');
                  const determinate = {value:document.querySelector('#progress-bar-fill').value,
                    label:document.querySelector('#progress-percent').textContent};
                  updateProgress(2, null, 'Processing document…');
                  const indeterminate = {hasValue:document.querySelector('#progress-bar-fill').hasAttribute('value'),
                    label:document.querySelector('#progress-percent').textContent};
                  showToast('Download complete!', 'success', 3000);
                  const marker=document.createElement('button'); marker.id='toast-hit-test';
                  marker.style.cssText='position:fixed;top:76px;right:24px;width:140px;height:40px;z-index:249';
                  document.body.appendChild(marker);
                  const target=document.elementFromPoint(innerWidth-50,96);
                  return {determinate,indeterminate,toastPointerEvents:getComputedStyle(document.querySelector('.toast-notice')).pointerEvents,
                    underlyingTargetReceivesPointer:target===marker};
                }""")
                assert progress["determinate"] == {"value":10,"label":"10%"}, progress
                assert progress["indeterminate"] == {"hasValue":False,"label":"Working"}, progress
                assert progress["toastPointerEvents"] == "none" and progress["underlyingTargetReceivesPointer"], progress
                results.append({"case":"progress_consistency_and_toast_hit_target","evidence":progress})

                for path, option, value, expected in (
                    ("/protect-pdf", "#password", "v23-local-pass", "password protected"),
                    ("/sign-pdf", "#signature", "Paperplane QA", "Paperplane QA"),
                ):
                    for round_no in (1,2):
                        page.goto(base + path, wait_until="domcontentloaded")
                        page.locator("#file-input").set_input_files(str(source))
                        page.locator(option).fill(value)
                        page.locator("#run-button").click()
                        page.locator("#result-download-link:not([hidden])").wait_for(timeout=30000)
                        failed_once = {"value": False}
                        def make_download_fail_once(route):
                            if round_no == 2 and "/api/jobs/" in route.request.url and "/download" in route.request.url and not failed_once["value"]:
                                failed_once["value"] = True
                                route.abort()
                            else:
                                route.continue_()
                        if round_no == 2:
                            page.route("**/api/jobs/**/download", make_download_fail_once)
                        with page.expect_download(timeout=30000) as captured:
                            page.locator("#result-download-link").click()
                        if round_no == 2:
                            page.unroute("**/api/jobs/**/download", make_download_fail_once)
                            assert failed_once["value"], "The controlled download failure was not injected."
                        output = temp / f"{Path(path).name}-{round_no}.pdf"
                        captured.value.save_as(output)
                        with fitz.open(output) as pdf:
                            assert pdf.page_count == 1
                            if "sign" in path:
                                assert expected in pdf[0].get_text()
                            else:
                                assert pdf.needs_pass
                        results.append({"case":path,"round":round_no,"bytes":output.stat().st_size,"pages":1,"content_checked":True})
                page.set_viewport_size({"width":1366,"height":900})
                page.goto(base + "/summarize-pdf", wait_until="domcontentloaded")
                summary_response = page.request.post(base + "/api/ai/summarize", multipart={
                    "file": {"name":source.name,"mimeType":"application/pdf","buffer":source.read_bytes()}
                })
                assert summary_response.ok, summary_response.text()
                summary_data = summary_response.json()
                assert summary_data["summary_mode"] == "offline_extractive"
                summary_response_2=page.request.post(base+"/api/ai/summarize",multipart={
                    "file":{"name":source.name,"mimeType":"application/pdf","buffer":source.read_bytes()}
                })
                assert summary_response_2.ok,summary_response_2.text()
                summary_data_2=summary_response_2.json()
                assert summary_data_2["summary"]==summary_data["summary"]
                assert summary_data_2["citations"]==summary_data["citations"]
                text_citations=sorted({int(value) for value in __import__("re").findall(r"\[(?:Page|Pages)\s+(\d+)",summary_data["summary"])})
                assert text_citations==summary_data["citations"],{"text_citations":text_citations,"chips":summary_data["citations"]}
                results.append({"case":"executive_brief_repeated_citation_parity","rounds":2,
                                "citations":summary_data["citations"],"summary_identical":True})
                page.evaluate("data => showSummaryDeskResult(data.summary, data.citations, data.summary_mode)", summary_data)
                assert "offline extractive notes" in page.locator("#result-meta").inner_text().lower()
                with page.expect_download(timeout=30000) as brief_download:
                    page.locator("#desk-download-summary-pdf-btn").click()
                brief_path = temp / "executive-brief.pdf"
                brief_download.value.save_as(brief_path)
                with fitz.open(brief_path) as brief:
                    assert brief.page_count >= 1 and "Paperplane v23" in brief[0].get_text()
                    brief_pages = brief.page_count
                results.append({"case":"executive_brief_pdf_download","bytes":brief_path.stat().st_size,"pages":brief_pages,"content_checked":True})
                page.set_viewport_size({"width":390,"height":844})
                page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                page.evaluate("""payload => {
                  const raw = atob(payload);
                  const bytes = Uint8Array.from(raw, char => char.charCodeAt(0));
                  const blob = new Blob([bytes], {type:'application/pdf'});
                  const url = URL.createObjectURL(blob);
                  showDownloadResult({output_name:'local-result.pdf',output_size:blob.size,status:'completed',local_processing:true}, url, {blob});
                }""", base64.b64encode(source.read_bytes()).decode("ascii"))
                page.locator("#result-view-studio-btn").click()
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '1'", timeout=15000)
                page.wait_for_function("document.querySelector('#studio-loading-overlay')?.hidden === true", timeout=15000)
                page.wait_for_timeout(5500)
                canvas_size = page.locator(".pdf-page-canvas").evaluate("c => [c.width,c.height]")
                assert canvas_size[0] > 0 and canvas_size[1] > 0
                studio_mobile=page.evaluate("""() => {
                  const selectors=['#studio-toolbar','#studio-thumbnails-bar','#studio-canvas-area','#studio-mobile-page-summary','#studio-local-work-banner'];
                  const boxes={}; for(const selector of selectors){const el=document.querySelector(selector);if(!el)continue;const r=el.getBoundingClientRect();boxes[selector]={visible:r.width>0&&r.height>0,rect:[r.x,r.y,r.width,r.height],scrollHeight:el.scrollHeight};}
                  return {width:innerWidth,documentWidth:document.documentElement.scrollWidth,boxes,
                    toolbarButtons:[...document.querySelectorAll('#studio-toolbar button')].filter(b=>getComputedStyle(b).display!=='none').length};
                }""")
                assert studio_mobile["documentWidth"]<=390 and studio_mobile["boxes"]["#studio-toolbar"]["visible"]
                assert not studio_mobile["boxes"].get("#studio-local-work-banner", {}).get("visible", False)
                page.screenshot(path=str(ROOT/"reports"/"launch-audit-v23"/"studio-loaded-390.png"),full_page=False)
                results.append({"case":"local_blob_open_in_studio","pages":1,"rendered_canvas":canvas_size,"mobile_layout":studio_mobile})
                page.set_viewport_size({"width":1366,"height":900})
                page.locator("#sidebar-settings-gear-btn").click()
                page.locator("#settings-tab-btn-appearance").click()
                page.locator("#theme-dark-btn").click()
                dark_theme = page.locator("#app-shell").evaluate("el=>({theme:document.documentElement.dataset.paperplaneTheme,studio:getComputedStyle(document.querySelector('.pdf-studio')).backgroundColor,toolbar:getComputedStyle(document.querySelector('.studio-primary-ribbon')).backgroundColor})")
                assert dark_theme["theme"] == "dark" and dark_theme["studio"] == "rgb(28, 38, 40)", dark_theme
                page.locator("#theme-light-btn").click()
                page.add_style_tag(content="*, *::before, *::after { transition: none !important; animation: none !important; }")
                page.wait_for_timeout(50)  # Measure the settled theme state, not a color-transition frame.
                light_theme = page.locator("#app-shell").evaluate("el=>({theme:document.documentElement.dataset.paperplaneTheme,studio:getComputedStyle(document.querySelector('.pdf-studio')).backgroundColor,canvasArea:getComputedStyle(document.querySelector('.studio-canvas-area')).backgroundColor,toolbar:getComputedStyle(document.querySelector('.studio-primary-ribbon')).backgroundColor,toolbarText:getComputedStyle(document.querySelector('#studio-pages-toggle-btn')).color,stored:localStorage.getItem('paperplane_theme')})")
                assert light_theme == {"theme":"light","studio":"rgb(237, 241, 239)","canvasArea":"rgb(248, 250, 249)","toolbar":"rgb(248, 250, 249)","toolbarText":"rgb(38, 55, 58)","stored":"light"}, light_theme
                page.locator("#close-settings-modal").click()
                page.reload(wait_until="domcontentloaded")
                page.wait_for_function("document.querySelector('#studio-loading-overlay')?.hidden === true", timeout=15000)
                persisted_theme = page.evaluate("({theme:document.documentElement.dataset.paperplaneTheme,studio:getComputedStyle(document.querySelector('.pdf-studio')).backgroundColor,canvasArea:getComputedStyle(document.querySelector('.studio-canvas-area')).backgroundColor})")
                assert persisted_theme == {"theme":"light","studio":"rgb(237, 241, 239)","canvasArea":"rgb(248, 250, 249)"}, persisted_theme
                page.locator(".toast-notice").wait_for(state="visible", timeout=5000)
                desktop_toast = page.evaluate("""() => {
                  const toast=document.querySelector('.toast-notice'), tr=toast.getBoundingClientRect();
                  const overlaps=[...document.querySelectorAll('.studio-toolbar button')].filter(button=>getComputedStyle(button).display!=='none').filter(button=>{
                    const r=button.getBoundingClientRect();return r.width&&r.height&&tr.left<r.right&&tr.right>r.left&&tr.top<r.bottom&&tr.bottom>r.top;
                  }).map(button=>button.id||button.textContent.trim());
                  return {top:tr.top,toolbarBottom:document.querySelector('.studio-toolbar').getBoundingClientRect().bottom,overlaps};
                }""")
                assert desktop_toast["overlaps"] == [] and desktop_toast["top"] > desktop_toast["toolbarBottom"], desktop_toast
                page.set_viewport_size({"width":390,"height":844})
                page.wait_for_timeout(120)
                mobile_toast = page.evaluate("""() => {
                  const toast=document.querySelector('.toast-notice'),tr=toast.getBoundingClientRect();
                  const overlaps=[...document.querySelectorAll('.studio-toolbar button')].filter(button=>getComputedStyle(button).display!=='none').filter(button=>{
                    const r=button.getBoundingClientRect();return r.width&&r.height&&tr.left<r.right&&tr.right>r.left&&tr.top<r.bottom&&tr.bottom>r.top;
                  }).map(button=>button.id||button.textContent.trim());
                  return {top:tr.top,toolbarBottom:document.querySelector('.studio-toolbar').getBoundingClientRect().bottom,overlaps};
                }""")
                assert mobile_toast["overlaps"] == [] and mobile_toast["top"] > mobile_toast["toolbarBottom"], mobile_toast
                mobile_stage = page.evaluate("({theme:document.documentElement.dataset.paperplaneTheme,canvasArea:getComputedStyle(document.querySelector('.studio-canvas-area')).backgroundColor,scrollWidth:document.documentElement.scrollWidth})")
                assert mobile_stage == {"theme":"light","canvasArea":"rgb(248, 250, 249)","scrollWidth":390}, mobile_stage
                page.screenshot(path=str(ROOT/"reports"/"launch-audit-v23"/"studio-loaded-390.png"),full_page=False)
                results.append({"case":"studio_uses_and_persists_selected_account_theme","dark":dark_theme,"light":light_theme,"after_reload":persisted_theme,"desktop_restore_toast":desktop_toast,"mobile_restore_toast":mobile_toast,"mobile_after_reload":mobile_stage})
                second_source = temp / "second-studio-open.pdf"
                with fitz.open() as document:
                    document.new_page().insert_text((72,72), "Fresh second Studio open.")
                    document.save(second_source)
                loading_state = page.evaluate("""async payload => {
                  const bytes=Uint8Array.from(atob(payload),ch=>ch.charCodeAt(0));
                  const file=new File([bytes],'second-studio-open.pdf',{type:'application/pdf'});
                  const nativeArrayBuffer=file.arrayBuffer.bind(file);
                  file.arrayBuffer=async()=>{await new Promise(resolve=>setTimeout(resolve,500));return await nativeArrayBuffer();};
                  window.__studioSecondLoad=loadDocumentIntoStudio(file);
                  await new Promise(resolve=>setTimeout(resolve,50));
                  return {visible:!document.querySelector('#studio-loading-overlay').hidden,
                    label:document.querySelector('#studio-loading-text').textContent};
                }""", base64.b64encode(second_source.read_bytes()).decode("ascii"))
                assert loading_state["visible"] and "Loading document" in loading_state["label"], loading_state
                second_loaded=page.evaluate("async()=>await window.__studioSecondLoad")
                assert second_loaded
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '1'")
                page.wait_for_function("document.querySelector('#studio-loading-overlay')?.hidden === true", timeout=15000)
                page.wait_for_timeout(5500)
                page.screenshot(path=str(ROOT/"reports"/"launch-audit-v23"/"studio-empty-or-second-open-390.png"),full_page=False)
                page.locator("#tool-text-btn").click()
                assert "cannot read properties of null (reading 'style')" not in (page.locator(".toast-notice").inner_text().lower() if page.locator(".toast-notice").count() else "")
                results.append({"case":"first_and_subsequent_studio_open_tool_activation","pages":1,"text_tool_active":page.locator("#tool-text-btn").evaluate("el=>el.classList.contains('active')")})
                extract_button = page.locator("#editor-extract-page-btn")
                if not extract_button.is_visible():
                    page.locator("#studio-mobile-pages-btn").click()
                    page.wait_for_timeout(100)
                assert extract_button.count() == 1 and extract_button.is_visible(), {
                    "count":extract_button.count(),"visible":extract_button.is_visible(),
                    "chain":extract_button.evaluate("el=>{const a=[];for(let n=el;n&&a.length<7;n=n.parentElement)a.push({id:n.id,className:n.className,hidden:n.hidden,display:getComputedStyle(n).display,visibility:getComputedStyle(n).visibility});return a}"),
                    "studioToolbar":page.locator("#studio-toolbar").evaluate("el=>({display:getComputedStyle(el).display,rect:el.getBoundingClientRect().toJSON()})")}
                with page.expect_download(timeout=15000) as extracted_download:
                    extract_button.click()
                extracted_path = temp / "studio-extracted.pdf"
                extracted_download.value.save_as(extracted_path)
                with fitz.open(extracted_path) as extracted_pdf:
                    assert extracted_pdf.page_count == 1
                    assert "Fresh second Studio open." in extracted_pdf[0].get_text()
                    extracted_pages = extracted_pdf.page_count
                results.append({"case":"studio_single_page_extract_download_content_checked","bytes":extracted_path.stat().st_size,
                                "pages":extracted_pages,"download_name":extracted_download.value.suggested_filename})
                long_source = temp / "studio-page-jump-69.pdf"
                with fitz.open() as document:
                    for page_number in range(1, 70):
                        pdf_page = document.new_page()
                        pdf_page.insert_text((72, 72), f"Studio jump verification page {page_number}.")
                    document.save(long_source)
                long_loading = page.evaluate("""async payload => {
                  const bytes=Uint8Array.from(atob(payload),ch=>ch.charCodeAt(0));
                  return await loadDocumentIntoStudio(new File([bytes],'studio-page-jump-69.pdf',{type:'application/pdf'}));
                }""", base64.b64encode(long_source.read_bytes()).decode("ascii"))
                assert long_loading
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '69'", timeout=20000)
                page.wait_for_function("""() => {
                  const active=window.state?.studio?.currentPage||1; const canvas=document.querySelector(`#studio-page-stack .studio-page-sheet[data-page="${active}"] .pdf-page-canvas`); if(!canvas?.width||!canvas?.height)return false;
                  const ctx=canvas.getContext('2d'); const data=ctx.getImageData(0,0,canvas.width,canvas.height).data;
                  for(let i=0;i<data.length;i+=32) if(data[i]<245||data[i+1]<245||data[i+2]<245) return true;
                  return false;
                }""", timeout=15000)
                page.locator("#page-jump-input").fill("69")
                page.locator("#page-jump-input").dispatch_event("change")
                page.wait_for_function("window.state?.studio?.currentPage === 69", timeout=10000)
                page.wait_for_function("""() => {
                  const active=window.state?.studio?.currentPage||1; const canvas=document.querySelector(`#studio-page-stack .studio-page-sheet[data-page="${active}"] .pdf-page-canvas`); if(!canvas?.width||!canvas?.height)return false;
                  const ctx=canvas.getContext('2d'); const data=ctx.getImageData(0,0,canvas.width,canvas.height).data;
                  for(let i=0;i<data.length;i+=32) if(data[i]<245||data[i+1]<245||data[i+2]<245) return true;
                  return false;
                }""", timeout=15000)
                page.locator("#page-jump-input").fill("1")
                page.locator("#page-jump-input").dispatch_event("change")
                page.wait_for_function("window.state?.studio?.currentPage === 1", timeout=10000)
                page.wait_for_function("""() => {
                  const active=window.state?.studio?.currentPage||1; const canvas=document.querySelector(`#studio-page-stack .studio-page-sheet[data-page="${active}"] .pdf-page-canvas`); if(!canvas?.width||!canvas?.height)return false;
                  const ctx=canvas.getContext('2d'); const data=ctx.getImageData(0,0,canvas.width,canvas.height).data;
                  for(let i=0;i<data.length;i+=32) if(data[i]<245||data[i+1]<245||data[i+2]<245) return true;
                  return false;
                }""", timeout=15000)
                results.append({"case":"studio_page_jump_1_69_1_canvas_rendered","pages":69,"targets":[1,69,1],"canvas_nonblank":True})
                delete_started = time.monotonic()
                delete_result = page.evaluate("""async () => {
                  window.confirmAction=async()=>true;
                  return await window.PaperplanePageOrganizer.deletePages([34]);
                }""")
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '68'", timeout=30000)
                delete_seconds = round(time.monotonic() - delete_started, 3)
                deleted_document = page.evaluate("""async () => {
                  const doc=window.state.studio.pdfDoc;
                  const page34=await doc.getPage(34);
                  const viewport=page34.getViewport({scale:1});
                  const text=await page34.getTextContent();
                  return {pages:doc.numPages,page34Text:text.items.map(item=>item.str).join(' ')};
                }""")
                assert delete_result is None or delete_result is True
                assert deleted_document["pages"] == 68 and "page 35" in deleted_document["page34Text"].lower()
                results.append({"case":"studio_delete_one_page_updates_count_and_content","deleted_page":34,
                                "remaining_pages":deleted_document["pages"],"page34_text":deleted_document["page34Text"],
                                "elapsed_seconds":delete_seconds})
                retention_source=fitz.open()
                for page_number in range(1,11):
                    retention_page=retention_source.new_page()
                    retention_page.insert_text((72,72),f"Studio retention verification page {page_number}.")
                retention_bytes=retention_source.tobytes()
                retention_source.close()
                retention_loaded=page.evaluate("""async payload => {
                  const bytes=Uint8Array.from(atob(payload),ch=>ch.charCodeAt(0));
                  return await loadDocumentIntoStudio(new File([bytes],'studio-retention-10page.pdf',{type:'application/pdf'}));
                }""",base64.b64encode(retention_bytes).decode('ascii'))
                assert retention_loaded
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '10'",timeout=20000)
                page.evaluate("""async () => { window.confirmAction=async()=>true; await window.PaperplanePageOrganizer.deletePages([1]); }""")
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '9'",timeout=30000)
                page.wait_for_function("""async () => {
                  const record=await readLocalWork('studio-pdf'); if(!record?.blob)return false;
                  const pdf=await pdfjsLib.getDocument(await record.blob.arrayBuffer()).promise;
                  if(pdf.numPages!==9)return false;
                  const text=await (await pdf.getPage(1)).getTextContent();
                  return text.items.map(item=>item.str).join(' ').includes('page 2');
                }""",timeout=20000)
                page.reload(wait_until="domcontentloaded")
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '9'",timeout=20000)
                page.wait_for_timeout(30000)
                retention_after_reload=page.evaluate("""async () => {
                  const doc=window.state?.studio?.pdfDoc;if(!doc||doc.numPages!==9)return {pages:doc?.numPages||0,page1Text:''};
                  const text=await (await doc.getPage(1)).getTextContent();
                  return {pages:doc.numPages,page1Text:text.items.map(item=>item.str).join(' ')};
                }""")
                assert retention_after_reload["pages"]==9 and "page 2" in retention_after_reload["page1Text"].lower(),retention_after_reload
                results.append({"case":"studio_page_deletion_survives_reload_after_30_seconds","initial_pages":10,
                                "remaining_pages":retention_after_reload["pages"],"first_page_text":retention_after_reload["page1Text"],
                                "guest_browser":True,"wait_after_reload_seconds":30})
                export_attempts=[]
                def fail_first_export(route):
                    export_attempts.append(route.request.url)
                    if len(export_attempts)==1: route.abort(error_code="failed")
                    else: route.continue_()
                page.route("**/api/studio/apply-edits",fail_first_export)
                source_payload=base64.b64encode(source.read_bytes()).decode("ascii")
                page.evaluate("""payload => {
                  const bytes=Uint8Array.from(atob(payload),ch=>ch.charCodeAt(0));
                  window.PaperplaneEditor.loadDocument(new File([bytes],'studio-export-retry.pdf',{type:'application/pdf'}),'studio-export-retry.pdf',1);
                }""",source_payload)
                with page.expect_download(timeout=20000) as download_info:
                    export_success=page.evaluate("async () => Boolean(await window.PaperplaneEditor.exportPDF())")
                retry_download=download_info.value
                retry_output=Path(temp_name)/"studio-export-retry.pdf"
                retry_download.save_as(str(retry_output))
                with fitz.open(retry_output) as exported:
                    retry_pages=exported.page_count
                    retry_text=exported[0].get_text()
                assert export_success and len(export_attempts)==2 and retry_pages==1 and "browser download verification" in retry_text.lower(), {
                    "success":export_success,"attempts":len(export_attempts),"pages":retry_pages,"text":retry_text}
                results.append({"case":"studio_export_retries_one_dropped_fetch_and_downloads_content_checked","attempts":len(export_attempts),
                                "download_bytes":retry_output.stat().st_size,"pages":retry_pages,"content_checked":True})
                page.unroute("**/api/studio/apply-edits",fail_first_export)
                export_503_attempts=[]
                def fail_first_export_503(route):
                    export_503_attempts.append(route.request.url)
                    if len(export_503_attempts)==1:
                        route.fulfill(status=503,content_type="application/json",body='{"detail":"synthetic transient export failure"}')
                    else: route.continue_()
                page.route("**/api/studio/apply-edits",fail_first_export_503)
                with page.expect_download(timeout=20000) as download_503_info:
                    export_503_success=page.evaluate("async () => Boolean(await window.PaperplaneEditor.exportPDF())")
                retry_503_download=download_503_info.value
                retry_503_output=Path(temp_name)/"studio-export-retry-503.pdf"
                retry_503_download.save_as(str(retry_503_output))
                with fitz.open(retry_503_output) as exported:
                    retry_503_pages=exported.page_count
                    retry_503_text=exported[0].get_text()
                assert export_503_success and len(export_503_attempts)==2 and retry_503_pages==1 and "browser download verification" in retry_503_text.lower(), {
                    "success":export_503_success,"attempts":len(export_503_attempts),"pages":retry_503_pages,"text":retry_503_text}
                results.append({"case":"studio_export_retries_503_and_downloads_content_checked","attempts":len(export_503_attempts),
                                "download_bytes":retry_503_output.stat().st_size,"pages":retry_503_pages,"content_checked":True})
                page.unroute("**/api/studio/apply-edits",fail_first_export_503)
                pro_context=browser.new_context(viewport={"width":1366,"height":900})
                pro_context.add_cookies([{"name":"paperplane_token","value":identity["accounts"][0][1],"url":base}])
                pro_page=pro_context.new_page()
                pro_page_errors=[]
                pro_page.on("pageerror",lambda err:pro_page_errors.append(str(err)))
                def delay_auth_response(route):
                    # DOMContentLoaded can take longer on a warm/cold route
                    # than the auth API itself. Keep auth pending long enough
                    # to inspect the actual first paint consistently.
                    time.sleep(2.0)
                    route.continue_()
                pro_context.route("**/api/auth/me",delay_auth_response)
                for auth_route in ("/","/split-pdf","/merge-pdf","/edit-pdf","/compress-pdf","/settings","/studio"):
                    response=pro_page.goto(base+auth_route,wait_until="domcontentloaded",timeout=15000)
                    assert response and response.status==200,(auth_route,response.status if response else None)
                    initial_auth=pro_page.evaluate("""() => ({pending:document.body.classList.contains('auth-pending'),
                      guestNameVisible:document.querySelector('#user-name').getClientRects().length>0&&getComputedStyle(document.querySelector('#user-name')).visibility==='visible',
                      guestActionsVisible:document.querySelector('#topbar-auth-guest').getClientRects().length>0&&!document.querySelector('#topbar-auth-guest').hidden&&getComputedStyle(document.querySelector('#topbar-auth-guest')).visibility==='visible',
                      upgradeVisible:document.querySelector('#sidebar-upgrade-btn').getClientRects().length>0&&getComputedStyle(document.querySelector('#sidebar-upgrade-btn')).visibility==='visible'})""")
                    assert initial_auth["pending"] and not initial_auth["guestNameVisible"] and not initial_auth["guestActionsVisible"] and not initial_auth["upgradeVisible"],{
                      "route":auth_route,"initial":initial_auth}
                    pro_page.wait_for_function("!document.body.classList.contains('auth-pending')",timeout=10000)
                    resolved_auth=pro_page.evaluate("""() => ({name:document.querySelector('#user-name')?.textContent.trim(),
                      guestActionsHidden:document.querySelector('#topbar-auth-guest')?.hidden,
                      upgradeHidden:document.querySelector('#sidebar-upgrade-btn')?.hidden||getComputedStyle(document.querySelector('#sidebar-upgrade-btn')).display==='none'})""")
                    expected_email=identity["accounts"][0][0]
                    assert resolved_auth["name"]==expected_email and resolved_auth["guestActionsHidden"] and resolved_auth["upgradeHidden"],{
                      "route":auth_route,"resolved":resolved_auth,"expected":expected_email}
                    results.append({"case":"signed_in_first_paint_has_auth_skeleton","route":auth_route,
                                    "guest_defaults_hidden":True,"resolved_email":resolved_auth["name"]})
                pro_studio_loaded=pro_page.evaluate("""async payload => {
                  const bytes=Uint8Array.from(atob(payload),ch=>ch.charCodeAt(0));
                  return await loadDocumentIntoStudio(new File([bytes],'pro-studio-restore.pdf',{type:'application/pdf'}));
                }""",base64.b64encode(retention_bytes).decode('ascii'))
                assert pro_studio_loaded
                pro_page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '10'",timeout=20000)
                pro_page.wait_for_function("""async () => {
                  const record=await readLocalWork('studio-pdf'); if(!record?.blob)return false;
                  const pdf=await pdfjsLib.getDocument(await record.blob.arrayBuffer()).promise;
                  return pdf.numPages===10;
                }""",timeout=15000)
                pro_page.reload(wait_until="domcontentloaded")
                restore_first_paint=pro_page.evaluate("""() => ({overlayVisible:!document.querySelector('#studio-loading-overlay').hidden,
                  overlayText:document.querySelector('#studio-loading-text').textContent,
                  emptyStateVisible:document.querySelector('.studio-empty-state')?.getClientRects().length>0})""")
                assert restore_first_paint["overlayVisible"] and "saved PDF" in restore_first_paint["overlayText"],restore_first_paint
                pro_page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '10'",timeout=20000)
                restore_content=pro_page.evaluate("""async () => {
                  const doc=window.state?.studio?.pdfDoc;if(!doc||doc.numPages!==10)return {pages:doc?.numPages||0,page1Text:''};
                  const text=await (await doc.getPage(1)).getTextContent();
                  return {pages:doc.numPages,page1Text:text.items.map(item=>item.str).join(' ')};
                }""")
                assert restore_content["pages"]==10 and "page 1" in restore_content["page1Text"].lower(),restore_content
                results.append({"case":"studio_saved_document_restores_without_empty_state_flash",
                                "initial_overlay":restore_first_paint,"restored_pages":restore_content["pages"],
                                "restored_first_page_text":restore_content["page1Text"]})
                assert not pro_page_errors,pro_page_errors
                pro_context.close()
                assert not page_errors, page_errors
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=15)
    report = ROOT / "reports" / "launch-audit-v23" / "browser-p0.json"
    payload=json.dumps({"results":results,"page_errors":page_errors},indent=2)
    round_number=8
    while (report.parent / f"browser-p0-round{round_number}.json").exists(): round_number+=1
    (report.parent / f"browser-p0-round{round_number}.json").write_text(payload,encoding="utf-8")
    report.write_text(payload,encoding="utf-8")
    print(json.dumps({"checks":len(results),"page_errors":page_errors,"report":str(report)},indent=2))


if __name__ == "__main__":
    main()
