from playwright.sync_api import sync_playwright
from pathlib import Path
import fitz,json,time
import re
BASE='http://127.0.0.1:8501'
PDF69=str(Path('runtime_data_codex_audit/notes_69pages_audit.pdf').resolve())
PDF3=str(Path('runtime_data_codex_audit/delete_3pages_audit.pdf').resolve())
def load(page,pdf):
    page.goto(BASE,wait_until='domcontentloaded',timeout=15000)
    page.evaluate("switchWorkspaceView('studio')")
    page.locator('#studio-file-input').set_input_files(pdf)
    page.locator('#pdf-canvas[data-rendered="true"]').wait_for(timeout=45000)
    page.locator('.organizer-thumb-card').last.wait_for(timeout=45000)
    page.wait_for_timeout(250)
def choose(page,num):
    page.locator(f'.organizer-thumb-card[data-page="{num}"] .thumb-checkbox-label').click(force=True)
with sync_playwright() as p:
    b=p.chromium.launch(headless=True)
    results=[]
    for selection,label in [([2],'delete-one'),([2,4,5],'delete-multiple')]:
        page=b.new_page(viewport={'width':1440,'height':1000})
        errors=[]
        page.on('pageerror',lambda err:errors.append(str(err)))
        page.on('dialog',lambda dialog:dialog.accept())
        load(page,PDF69)
        page.locator('#btn-mode-organize').click()
        for num in selection: choose(page,num)
        before=page.locator('#studio-page-count').inner_text()
        selected=page.locator('#batch-selection-count').inner_text()
        page.locator('#batch-delete-btn').click()
        deadline=time.monotonic()+40
        while page.locator('#studio-page-count').inner_text()!=str(69-len(selection)) and time.monotonic()<deadline:
            page.wait_for_timeout(100)
        after=page.locator('#studio-page-count').inner_text()
        cards=page.locator('.organizer-thumb-card').count()
        with page.expect_download(timeout=60000) as exported:
            page.locator('#save-studio-btn').click()
        download=exported.value
        dest=f'reports/launch-audit-v3/{label}_studio_export.pdf'
        download.save_as(dest)
        output=fitz.open(dest)
        page_numbers=[]
        for output_page in output:
            match=re.search(r'Page\s+(\d+)',output_page.get_text())
            page_numbers.append(int(match.group(1)) if match else None)
        expected=[n for n in range(1,70) if n not in selection]
        result={'case':label,'selection':selection,'before':before,'selected':selected,'after':after,'thumbs':cards,'download_filename':download.suggested_filename,'download_pages':output.page_count,'download_page_numbers_match':page_numbers==expected,'removed_pages_absent':not (set(selection)&set(page_numbers)),'first_pages':page_numbers[:6],'errors':errors,'toast':page.locator('.toast-notice').inner_text() if page.locator('.toast-notice').count() else None}
        output.close()
        results.append(result)
        page.close()
    page=b.new_page(viewport={'width':1440,'height':1000})
    load(page,PDF3)
    page.locator('#btn-mode-organize').click()
    choose(page,2)
    with page.expect_download(timeout=30000) as download_info:
        page.locator('#batch-extract-btn').click()
    download=download_info.value
    dest='reports/launch-audit-v3/'+download.suggested_filename
    download.save_as(dest)
    doc=fitz.open(dest)
    extracted={'case':'extract-one','filename':download.suggested_filename,'bytes':Path(dest).stat().st_size,'pages':doc.page_count,'text':doc[0].get_text().strip(),'mime':'application/pdf'}
    results.append(extracted)
    print(json.dumps(results,indent=2))
    b.close()
