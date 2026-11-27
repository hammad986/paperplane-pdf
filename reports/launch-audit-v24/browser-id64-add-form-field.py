"""Verify the Studio Add Field tab has its own reachable action and creates a real widget."""
import base64, json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"reports"/"launch-audit-v24"
with TemporaryDirectory(prefix="paperplane-id64-") as tmp:
    temp=Path(tmp); source=temp/"blank.pdf"
    with fitz.open() as doc:
        page=doc.new_page(width=612,height=792);page.insert_text((72,72),"ID64 form placement fixture")
        doc.save(source)
    with socket.socket() as sock: sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    sys.path.insert(0,str(ROOT/"reports"/"launch-audit-v14"))
    import browser_acceptance_v14 as helper
    app,base,_=helper.start_server(temp/"data")
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1",port),timeout=.2):break
            except OSError:time.sleep(.2)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True);page=browser.new_page(viewport={"width":1366,"height":900});errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(base+"/studio",wait_until="domcontentloaded")
            page.locator("#studio-file-input").set_input_files(str(source))
            page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='1' && document.querySelector('#studio-loading-overlay')?.hidden===true",timeout=20000)
            page.locator("#btn-more-tools-trigger").click();page.locator("#studio-forms-btn").click()
            page.wait_for_function("document.querySelector('#forms-modal')?.hidden===false")
            page.locator("#forms-tab-add").click()
            add_button=page.locator("#btn-apply-add-field")
            add_action_reachable=add_button.is_visible()
            fill_action_hidden=not page.locator("#btn-apply-form-fill").is_visible()
            assert add_action_reachable and fill_action_hidden
            field_name="id64_browser_field"
            page.locator("#new-field-name").fill(field_name)
            page.locator("#new-field-value").fill("Browser-added field value")
            with page.expect_response(lambda r:r.url.endswith("/api/studio/forms/add-field")) as added:
                add_button.click()
            response=added.value;assert response.status==200,response.status
            page.wait_for_function("document.querySelector('#forms-field-count-badge')?.textContent.includes('1 field')",timeout=15000)
            page.locator("#modal-close-forms").click()
            page.set_viewport_size({"width":390,"height":844})
            page.locator("#btn-more-tools-trigger").click();page.locator("#studio-forms-btn").click()
            page.wait_for_function("document.querySelector('#forms-modal')?.hidden===false")
            page.locator("#forms-tab-add").click()
            mobile_action=page.locator("#btn-apply-add-field")
            mobile_geometry=mobile_action.evaluate("el=>{const r=el.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom,visible:!!(r.width&&r.height)&&getComputedStyle(el).visibility!=='hidden'}}")
            assert mobile_geometry["visible"] and mobile_geometry["x"]>=0 and mobile_geometry["right"]<=390,mobile_geometry
            page.screenshot(path=str(OUT/"id64-add-field-mobile.png"),full_page=False)
            payload=page.evaluate("""async name=>{const file=window.PaperplaneSecurityForms?.currentFile;if(!file)return null;const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));return {name:file.name,data:btoa(binary)}}""",field_name)
            assert payload and payload["data"]
            out=temp/"field-added.pdf";out.write_bytes(base64.b64decode(payload["data"]))
            with fitz.open(out) as result:
                widgets=list(result[0].widgets() or [])
                checked=[{"name":w.field_name,"value":w.field_value,"type":w.field_type_string} for w in widgets]
            assert any(w["name"]==field_name and w["value"]=="Browser-added field value" for w in checked),checked
            assert not errors,errors
            evidence={"add_tab_action_visible_when_add_tab_active":add_action_reachable,"inspect_fill_action_hidden_when_add_tab_active":fill_action_hidden,"mobile_add_tab_action_geometry":mobile_geometry,"add_field_response":response.status,"page_widget_count":len(checked),"widgets":checked,"page_errors":errors,"content_checked":True,"result":"passed"}
            (OUT/"browser-id64-add-form-field.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
            print(json.dumps(evidence,indent=2));browser.close()
    finally:app.terminate();app.wait(timeout=5)
