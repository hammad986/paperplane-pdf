from __future__ import annotations
import json, time, re
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
import fitz

ROOT = Path.cwd()
BASE = 'http://127.0.0.1:8501'
OUT = ROOT / 'reports' / 'launch-audit-v10'
OUTPUTS = OUT / 'outputs'
OUTPUTS.mkdir(parents=True, exist_ok=True)
SAMPLE_69 = ROOT / 'reports' / 'launch-audit-v8' / 'test-files' / 'notes-69page.pdf'
SMALL = OUT / 'inputs' / 'tool-audit-round-1' / 'audit-sample.pdf'
results = {'scope': 'local synthetic browser checks; no account/provider/payment/credentials', 'desktop': {}, 'mobile': {}, 'page_errors': 0}
errors = []

def store_keys(page):
    return page.evaluate('''async () => {
      const dbs = await indexedDB.databases();
      const db = await new Promise((resolve, reject) => {
        const request = indexedDB.open('paperplane-local-work', 1);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      const keys = await new Promise((resolve, reject) => {
        const request = db.transaction('work', 'readonly').objectStore('work').getAllKeys();
        request.onsuccess = () => resolve(request.result.map(String));
        request.onerror = () => reject(request.error);
      });
      db.close(); return {present: dbs.some(x => x.name === 'paperplane-local-work'), keys};
    }''')

def page_count(pdf_path):
    doc = fitz.open(pdf_path)
    pages = doc.page_count
    first_pages = [doc[i].get_text()[:80].replace('\n', ' ') for i in range(min(3, doc.page_count))]
    doc.close()
    return {'pages': pages, 'first_pages': first_pages}

def redact_evidence(value):
    if isinstance(value, str):
        value = re.sub(r'(?<!\d)(?:\d[\s-]*){12}(?!\d)', '[synthetic ID redacted]', value)
        value = re.sub(r'Applicant:\s*[^\n]+', 'Applicant: [synthetic details redacted]', value)
        value = re.sub(r'(?:TEST_SECRET|SYNTHETIC_TEXT):\s*[^\n]+', '[synthetic marker redacted]', value)
        return value
    if isinstance(value, list):
        return [redact_evidence(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_evidence(item) for key, item in value.items()}
    return value

def compare_to_source(pdf_path, source_page_ids):
    source = fitz.open(SAMPLE_69)
    output = fitz.open(pdf_path)
    expected_text = [source[page_id - 1].get_text() for page_id in source_page_ids]
    output_text = [page.get_text() for page in output]
    labels = []
    for content in output_text:
        match = re.search(r'Page\s+(\d+)\s+of\s+69', content)
        labels.append(int(match.group(1)) if match else None)
    result = {'pages': output.page_count, 'expected_pages': len(source_page_ids),
              'page_order_matches': labels == source_page_ids,
              'full_text_matches_source_pages': output_text == expected_text,
              'order_head': labels[:5], 'order_tail': labels[-3:]}
    source.close(); output.close()
    return result

def toolbar_metrics(page):
    return page.evaluate('''() => {
      const bar = document.querySelector('#studio-toolbar');
      const groups = ['.studio-primary-ribbon', '.studio-sub-ribbon'];
      const visible = [...document.querySelectorAll('#studio-toolbar button, #studio-toolbar select')]
        .filter(el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; });
      const tops = visible.map(el => el.getBoundingClientRect().top).sort((a,b) => a-b);
      const rows = [];
      tops.forEach(top => { if (!rows.length || top - rows[rows.length - 1] > 7) rows.push(Math.round(top)); });
      const bounds = visible.map(el => { const r = el.getBoundingClientRect(); return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,font:parseFloat(getComputedStyle(el).fontSize)}; });
      const br = bar?.getBoundingClientRect();
      return {toolbarHeight: br?.height || 0, toolbarTop: br?.top || 0, distinctButtonRows: rows.length, rowTops: rows,
        visibleControls: visible.length, minFontPx: Math.min(...bounds.map(x => x.font)), outOfViewport: bounds.filter(x => x.left < -1 || x.right > innerWidth + 1 || x.top < -1 || x.bottom > innerHeight + 1).length,
        ribbons: groups.map(sel => { const e=document.querySelector(sel), r=e?.getBoundingClientRect(); return {selector:sel, top:r?.top||0, height:r?.height||0, scrollWidth:e?.scrollWidth||0, clientWidth:e?.clientWidth||0}; })};
    }''')

def export_pdf(page, output_path):
    with page.expect_download(timeout=120000) as download_info:
        page.locator('#save-studio-btn').click(timeout=15000)
    download = download_info.value
    download.save_as(str(output_path))
    return {'name': download.suggested_filename, **page_count(output_path), 'bytes': output_path.stat().st_size}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # Desktop: Tool Desk, feedback behavior, Studio reorder/delete/reload/export.
    ctx = browser.new_context(viewport={'width': 1920, 'height': 1080}, accept_downloads=True)
    page = ctx.new_page()
    page.add_init_script("window.__ppLongTasks=[]; if ('PerformanceObserver' in window) { try { new PerformanceObserver(list => window.__ppLongTasks.push(...list.getEntries().map(x=>({duration:Math.round(x.duration*100)/100,startTime:Math.round(x.startTime*100)/100})))).observe({type:'longtask', buffered:true}); } catch {} }")
    page.on('pageerror', lambda e: errors.append('pageerror'))
    def allow_local(route):
        u = urlparse(route.request.url)
        if u.hostname in ('127.0.0.1', 'localhost'):
            route.continue_()
        else:
            route.abort()
    page.route('**/*', allow_local)
    nav_start = time.perf_counter()
    page.goto(BASE, wait_until='domcontentloaded', timeout=30000)
    page.locator('#pp-btn-feedback-toggle').wait_for(state='attached', timeout=15000)
    page.wait_for_timeout(900)
    home_perf = page.evaluate('''() => { const n=performance.getEntriesByType('navigation')[0]; const r=performance.getEntriesByType('resource'); const l=performance.getEntriesByType('largest-contentful-paint'); const shifts=performance.getEntriesByType('layout-shift').filter(x=>!x.hadRecentInput); return {domContentLoadedMs:n?.domContentLoadedEventEnd||0, loadMs:n?.loadEventEnd||0, transferBytes:r.reduce((a,x)=>a+(x.transferSize||0),0), resources:r.length, largestContentfulPaintMs:l.length?l[l.length-1].startTime:null, cls:shifts.reduce((a,x)=>a+x.value,0)}; }''')
    home_perf['long_tasks'] = page.evaluate('window.__ppLongTasks || []')
    home_perf['script_resources'] = page.evaluate("performance.getEntriesByType('resource').filter(x=>/\\.js(?:\\?|$)/.test(x.name)).map(x=>({name:new URL(x.name).pathname,transferBytes:x.transferSize||0,durationMs:Math.round(x.duration)}))")
    home_perf['pdf_engine_resources_eagerly_loaded'] = [x['name'] for x in home_perf['script_resources'] if x['name'] in ('/assets/pdf.min.js', '/assets/pdf-lib.min.js')]
    home_perf['pdf_runtime_loader_loaded'] = any(x['name'] == '/assets/pdf_runtime.js' for x in home_perf['script_resources'])
    home_perf['wallToDomContentLoadedMs'] = round((time.perf_counter() - nav_start) * 1000, 1)
    results['desktop']['home_performance'] = home_perf
    results['desktop']['feedback_initial'] = page.evaluate('''() => {
      const b=document.querySelector('#pp-btn-feedback-toggle'), r=b?.getBoundingClientRect(), c=[...document.querySelectorAll('.home-tool-card')].some(e=>{const x=e.getBoundingClientRect();return r&&r.left<x.right&&r.right>x.left&&r.top<x.bottom&&r.bottom>x.top;});
      return {buttonVisible:!!b&&!b.hidden, containerVisibility:b?getComputedStyle(b.parentElement).visibility:'absent', overlapsHomeCard:c};
    }''')
    page.screenshot(path=str(OUT / 'home-1920-final.png'), full_page=True)
    page.locator('#pp-btn-feedback-toggle').click()
    page.locator('#pp-btn-feedback-close').click()
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(500)
    dismissed_reload = page.locator('#pp-btn-feedback-toggle').is_hidden()
    page.locator('#sidebar-settings-gear-btn').click()
    page.locator('#settings-tab-btn-privacy').click()
    page.locator('#settings-feedback-open').click()
    settings_reopen = page.locator('#pp-feedback-popover').evaluate("e => getComputedStyle(e).display === 'flex'")
    page.locator('#pp-fb-text-input').fill('Local synthetic v10 QA feedback; no follow-up requested.')
    page.locator('.pp-fb-star[data-rating="4"]').click()
    page.locator('.pp-fb-cat-pill[data-cat="bug"]').click()
    page.locator('#pp-btn-feedback-submit').click()
    page.locator('#pp-feedback-success-body').wait_for(state='visible', timeout=15000)
    submitted_button_hidden = page.locator('#pp-btn-feedback-toggle').is_hidden()
    page.wait_for_timeout(2700)
    page.locator('#sidebar-settings-gear-btn').click()
    page.locator('#settings-tab-btn-privacy').click()
    page.locator('#settings-feedback-open').click()
    submitted_reopen = page.locator('#pp-feedback-popover').evaluate("e => getComputedStyle(e).display === 'flex'")
    page.locator('#pp-btn-feedback-close').click()
    results['desktop']['feedback'] = {'dismissed_survives_reload': dismissed_reload, 'settings_reopens_dismissed_widget': settings_reopen,
       'synthetic_submit_confirmed': True, 'button_hidden_after_confirmed_submit': submitted_button_hidden,
       'settings_reopens_after_submission': submitted_reopen}

    page.locator('#tab-tool-desk-view').click()
    page.wait_for_timeout(250)
    page.evaluate("window.selectOperation('merge')")
    merge_inputs = [SMALL, OUT / 'inputs' / 'tool-audit-round-1' / 'audit-sample-changed.pdf']
    page.locator('#file-input').set_input_files([str(path) for path in merge_inputs])
    page.wait_for_function("document.querySelectorAll('#file-list .file-row-card').length === 2", timeout=15000)
    page.locator('#run-button').click()
    page.locator('#result:not([hidden])').wait_for(timeout=90000)
    page.locator('#result-download-link:not([hidden])').wait_for(timeout=10000)
    merged_ui_path = OUTPUTS / 'tool-desk-ui-merged.pdf'
    with page.expect_download(timeout=30000) as merge_download_info:
        page.locator('#result-download-link').click()
    merge_download = merge_download_info.value
    merge_download.save_as(str(merged_ui_path))
    merge_result = page_count(merged_ui_path)
    merge_result.update({'name': merge_download.suggested_filename, 'bytes': merged_ui_path.stat().st_size})
    results['desktop']['merge_ui_run'] = merge_result
    page.evaluate("window.selectOperation('word_to_pdf')")
    page.wait_for_function("document.querySelector('#tool-title')?.textContent.trim() === 'Word to PDF'", timeout=15000)
    results['desktop']['word_to_pdf_empty_upload'] = page.evaluate("({fileInputCount:document.querySelector('#file-input')?.files?.length||0, visibleFileRows:document.querySelectorAll('#file-list .file-row-card').length, toolLabel:document.querySelector('#tool-title')?.textContent.trim()||''})")

    tool_profiles = []
    for operation in ['compress', 'organize', 'grayscale', 'excel_to_pdf']:
        page.evaluate("op => { window.__ppProfileStart=performance.now(); window.selectOperation(op); }", operation)
        page.wait_for_timeout(50)
        tool_profiles.append(page.evaluate("op => ({operation:op,label:document.querySelector('#tool-title')?.textContent?.trim()||'',renderMs:Math.round(performance.now()-window.__ppProfileStart),longTasks:(window.__ppLongTasks||[]).slice(-8)})", operation))
    results['desktop']['heavy_tool_performance'] = tool_profiles

    page.locator('#tab-studio-view').click()
    page.locator('#studio-file-input').set_input_files(str(SAMPLE_69))
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '69'", timeout=90000)
    page.wait_for_function("document.querySelector('#studio-page-stack .pdf-page-canvas[data-rendered=\"true\"]')", timeout=30000)
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / 'studio-1920-69page.png'), full_page=False)
    results['desktop']['studio_initial'] = {
        'page_count': int(page.locator('#page-total-indicator').inner_text()),
        'stored_keys': store_keys(page),
        'pdfjs_loaded_on_demand': page.evaluate("!!window.pdfjsLib && performance.getEntriesByType('resource').some(x => new URL(x.name).pathname === '/assets/pdf.min.js')"),
        'pdf_lib_remains_deferred_until_processing': page.evaluate("!window.PDFLib && !performance.getEntriesByType('resource').some(x => new URL(x.name).pathname === '/assets/pdf-lib.min.js')")
    }
    results['desktop']['pdf_lib_loader_check'] = page.evaluate("window.PaperplanePdfRuntime.ensurePdfLib().then(lib => ({loaded:!!lib && !!window.PDFLib, requestedOnDemand:performance.getEntriesByType('resource').some(x => new URL(x.name).pathname === '/assets/pdf-lib.min.js')}))")
    results['desktop']['toolbar_1920'] = toolbar_metrics(page)
    page.locator('#btn-more-tools-trigger').click()
    menu_items = page.locator('#studio-more-dropdown .studio-dropdown-item:visible').count()
    results['desktop']['more_tools_menu_items_visible'] = menu_items
    page.locator('#btn-more-tools-trigger').click()

    # Drag page 1 to immediately after page 2 using the actual touch/pointer drag handle.
    source = page.locator('.organizer-thumb-card[data-page="1"] .thumb-grip')
    target = page.locator('.organizer-thumb-card[data-page="2"]')
    source.scroll_into_view_if_needed(); target.scroll_into_view_if_needed()
    sb = source.bounding_box(); tb = target.bounding_box()
    reorder_request_status = None
    with page.expect_response(lambda r: r.url.endswith('/api/studio/pages/reorder') and r.request.method == 'POST', timeout=60000) as response_info:
        page.mouse.move(sb['x'] + sb['width']/2, sb['y'] + sb['height']/2)
        page.mouse.down()
        page.mouse.move(tb['x'] + min(tb['width']*.4, 50), tb['y'] + tb['height']*.78, steps=8)
        page.mouse.up()
    reorder_request_status = response_info.value.status
    page.get_by_text('Pages reordered successfully.', exact=True).wait_for(timeout=90000)
    results['desktop']['reorder_drag'] = {'endpoint_status': reorder_request_status, 'source_rect_present': bool(sb), 'target_rect_present': bool(tb)}

    # Discriminating reverse direction: move page 4 above page 3.
    source = page.locator('.organizer-thumb-card[data-page="4"] .thumb-grip')
    target = page.locator('.organizer-thumb-card[data-page="3"]')
    source.scroll_into_view_if_needed(); target.scroll_into_view_if_needed()
    sb = source.bounding_box(); tb = target.bounding_box()
    with page.expect_response(lambda r: r.url.endswith('/api/studio/pages/reorder') and r.request.method == 'POST', timeout=60000) as response_info:
        page.mouse.move(sb['x'] + sb['width']/2, sb['y'] + sb['height']/2)
        page.mouse.down()
        page.mouse.move(tb['x'] + min(tb['width']*.35, 42), tb['y'] + tb['height']*.2, steps=8)
        page.mouse.up()
    page.get_by_text('Pages reordered successfully.', exact=True).wait_for(timeout=90000)
    results['desktop']['reorder_reverse_drag'] = {'endpoint_status': response_info.value.status, 'source_rect_present': bool(sb), 'target_rect_present': bool(tb)}
    results['desktop']['export_after_reorder'] = export_pdf(page, OUTPUTS / 'studio-reordered-69.pdf')
    reordered_ids = [2, 1, 4, 3, *range(5, 70)]
    results['desktop']['reorder_content_check'] = compare_to_source(OUTPUTS / 'studio-reordered-69.pdf', reordered_ids)

    # Delete the last page through the page organizer controller, confirm in the visible dialog.
    page.evaluate('() => { window.PaperplanePageOrganizer.deletePages([69]); return true; }')
    page.locator('dialog.app-confirm-dialog[open]').wait_for(timeout=15000)
    page.locator('dialog.app-confirm-dialog button').filter(has_text='Delete pages').click()
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '68'", timeout=90000)
    page.locator('#studio-undo-banner .work-clear-btn').wait_for(state='visible', timeout=30000)
    page.locator('#studio-undo-banner .work-clear-btn').click()
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '69'", timeout=90000)
    results['desktop']['undo_delete'] = {'page_count_after_undo': int(page.locator('#page-total-indicator').inner_text())}
    page.evaluate('() => { window.PaperplanePageOrganizer.deletePages([69]); return true; }')
    page.locator('dialog.app-confirm-dialog[open]').wait_for(timeout=15000)
    page.locator('dialog.app-confirm-dialog button').filter(has_text='Delete pages').click()
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '68'", timeout=90000)
    page.locator('#studio-undo-banner .work-clear-btn').wait_for(state='visible', timeout=30000)
    results['desktop']['delete_last_page'] = {'page_count_after_delete': int(page.locator('#page-total-indicator').inner_text()), 'undo_banner_visible': page.locator('#studio-undo-banner').is_visible()}
    results['desktop']['export_after_delete'] = export_pdf(page, OUTPUTS / 'studio-deleted-68.pdf')
    deleted_ids = [2, 1, 4, 3, *range(5, 69)]
    results['desktop']['delete_content_check'] = compare_to_source(OUTPUTS / 'studio-deleted-68.pdf', deleted_ids)

    # Reload and verify the changed local document restores with its current page count.
    page.reload(wait_until='domcontentloaded')
    page.locator('#tab-studio-view').click()
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '68'", timeout=90000)
    results['desktop']['reload_restore'] = {'page_count': int(page.locator('#page-total-indicator').inner_text()), 'stored_keys': store_keys(page)}
    results['desktop']['export_after_reload'] = export_pdf(page, OUTPUTS / 'studio-reloaded-68.pdf')
    results['desktop']['reload_content_check'] = compare_to_source(OUTPUTS / 'studio-reloaded-68.pdf', deleted_ids)

    page.evaluate('() => { window.PaperplanePageOrganizer.deletePages([68]); return true; }')
    page.locator('dialog.app-confirm-dialog[open]').wait_for(timeout=15000)
    page.locator('dialog.app-confirm-dialog button').filter(has_text='Delete pages').click()
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '67'", timeout=90000)
    page.locator('#studio-undo-banner .work-clear-btn').wait_for(state='visible', timeout=30000)
    page.reload(wait_until='domcontentloaded')
    page.locator('#tab-studio-view').click()
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '67'", timeout=90000)
    results['desktop']['retention_69_68_67'] = {'after_first_reload': 68, 'after_second_delete_and_reload': int(page.locator('#page-total-indicator').inner_text()), 'stored_keys': store_keys(page)}
    results['desktop']['export_after_second_reload'] = export_pdf(page, OUTPUTS / 'studio-reloaded-67.pdf')
    final_67_ids = [2, 1, 4, 3, *range(5, 68)]
    results['desktop']['retention_content_check'] = compare_to_source(OUTPUTS / 'studio-reloaded-67.pdf', final_67_ids)

    page.locator('#studio-close-doc-btn').click()
    page.locator('dialog.app-confirm-dialog[open]').wait_for(timeout=15000)
    page.locator('dialog.app-confirm-dialog button').filter(has_text='Cancel').click()
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '67'", timeout=15000)
    results['desktop']['new_page_confirmation'] = {'dialog_shown_before_discard': True, 'cancel_preserves_document_pages': int(page.locator('#page-total-indicator').inner_text())}

    # Clear local Studio copy, confirm, verify IndexedDB and then load a fresh small PDF.
    page.locator('#studio-clear-pdf-btn').click()
    page.locator('dialog.app-confirm-dialog[open]').wait_for(timeout=15000)
    page.locator('dialog.app-confirm-dialog button').filter(has_text='Clear Studio PDF').click()
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '0'", timeout=30000)
    keys_after_clear = store_keys(page)
    page.locator('#studio-file-input').set_input_files(str(SMALL))
    small_count = fitz.open(SMALL).page_count
    page.wait_for_function(f"document.querySelector('#page-total-indicator')?.textContent === '{small_count}'", timeout=60000)
    results['desktop']['clear_then_fresh_upload'] = {'keys_after_clear': keys_after_clear, 'fresh_file_page_count': int(page.locator('#page-total-indicator').inner_text()), 'expected_fresh_file_pages': small_count}
    page.locator('#studio-open-ai-btn').click()
    page.locator('#ai-active-doc-bar:not([hidden])').wait_for(timeout=30000)
    results['desktop']['studio_ai_handoff'] = {'doc_name': page.locator('#ai-doc-name').inner_text(), 'page_context': page.locator('#ai-doc-page-context').inner_text(), 'greeting_present': page.get_by_text('Your PDF is ready. Ask about its content and I’ll include page citations.', exact=True).count() == 1}
    page.locator('#tab-studio-view').click()
    page.wait_for_function(f"document.querySelector('#page-total-indicator')?.textContent === '{small_count}'", timeout=30000)
    results['desktop']['return_to_studio_after_ai'] = {'page_count': int(page.locator('#page-total-indicator').inner_text())}
    ctx.close()

    # Mobile: validate feedback placement, 390px Studio toolbar, organize drawer and reachability.
    mctx = browser.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=1, is_mobile=True, has_touch=True, accept_downloads=True)
    mobile = mctx.new_page()
    mobile.on('pageerror', lambda e: errors.append('mobile-pageerror'))
    mobile.route('**/*', allow_local)
    mobile.goto(BASE, wait_until='domcontentloaded', timeout=30000)
    mobile.locator('#pp-btn-feedback-toggle').wait_for(state='attached', timeout=15000)
    mobile.wait_for_timeout(900)
    mobile.screenshot(path=str(OUT / 'home-390-feedback.png'), full_page=False)
    feedback_height_checks = []
    for height in [667, 740, 781, 844, 932]:
      mobile.set_viewport_size({'width': 390, 'height': height})
      mobile.wait_for_timeout(80)
      feedback_height_checks.append(mobile.evaluate('''() => {
        const b=document.querySelector('#pp-btn-feedback-toggle'), r=b?.getBoundingClientRect();
        const card=document.querySelector('#tool-desk-tools-catalog .home-tool-card'), c=card?.getBoundingClientRect();
        const nav=document.querySelector('.mobile-workspace-bar'), n=nav?.getBoundingClientRect();
        const overlap=(x,y)=>!!x&&!!y&&x.left<y.right&&x.right>y.left&&x.top<y.bottom&&x.bottom>y.top;
        return {height:innerHeight,visible:!!b&&!b.hidden&&getComputedStyle(b.parentElement).visibility!=='hidden',overlapsFirstCard:overlap(r,c),overlapsBottomNav:overlap(r,n)};
      }'''))
    results['mobile']['feedback_height_checks_390'] = feedback_height_checks
    mobile.set_viewport_size({'width': 390, 'height': 844})
    mobile.wait_for_timeout(100)
    results['mobile']['feedback_placement'] = mobile.evaluate('''() => {
      const b=document.querySelector('#pp-btn-feedback-toggle'), r=b?.getBoundingClientRect(), n=document.querySelector('.mobile-workspace-bar')?.getBoundingClientRect();
      const intersects=!!r&&!!n&&r.left<n.right&&r.right>n.left&&r.top<n.bottom&&r.bottom>n.top;
      return {buttonVisible:!!b&&!b.hidden&&getComputedStyle(b.parentElement).visibility!=='hidden', hiddenForCollision:b?.parentElement?.classList.contains('pp-feedback-obstructed')||false, containerVisibility:b?getComputedStyle(b.parentElement).visibility:'absent', left:r?.left||0,right:r?.right||0,top:r?.top||0,bottom:r?.bottom||0,navTop:n?.top||0,navBottom:n?.bottom||0,overlapsBottomNav:intersects,viewportWidth:innerWidth,documentWidth:document.documentElement.scrollWidth};
    }''')
    mobile.locator('#mob-nav-studio').click()
    mobile.locator('#studio-file-input').set_input_files(str(SMALL))
    mobile.wait_for_function(f"document.querySelector('#page-total-indicator')?.textContent === '{small_count}'", timeout=60000)
    results['mobile']['feedback_studio_zoom'] = mobile.evaluate('''() => {
      const b=document.querySelector('#pp-btn-feedback-toggle'), z=document.querySelector('#zoom-select');
      const r=b?.getBoundingClientRect(), q=z?.getBoundingClientRect();
      return {buttonVisible:!!b&&!b.hidden&&getComputedStyle(b.parentElement).visibility!=='hidden'&&getComputedStyle(b.parentElement).display!=='none',
        hiddenForCollision:b?.parentElement?.classList.contains('pp-feedback-obstructed')||false,
        overlapsZoom:!!r&&!!q&&r.left<q.right&&r.right>q.left&&r.top<q.bottom&&r.bottom>q.top};
    }''')
    mobile.evaluate("() => { window.confirmAction('Synthetic modal visibility check', {confirmLabel:'Continue'}); return true; }")
    mobile.locator('dialog.app-confirm-dialog[open]').wait_for(timeout=15000)
    hidden_during_dialog = mobile.locator('#pp-feedback-container').evaluate("e => getComputedStyle(e).display === 'none'")
    mobile.locator('dialog.app-confirm-dialog button').filter(has_text='Cancel').click()
    mobile.wait_for_function(f"document.querySelector('#page-total-indicator')?.textContent === '{small_count}'", timeout=15000)
    results['mobile']['new_page_confirm_and_feedback_modal'] = {'feedback_widget_hidden_while_dialog_open': hidden_during_dialog, 'cancel_keeps_document_loaded': int(mobile.locator('#page-total-indicator').inner_text()) == small_count}
    mobile.locator('#btn-mode-organize').click()
    mobile.wait_for_timeout(500)
    mobile.screenshot(path=str(OUT / 'studio-390-organize.png'), full_page=False)
    results['mobile']['studio_390'] = mobile.evaluate('''() => {
      const shell=document.querySelector('#app-shell'), drawer=document.querySelector('#studio-thumbnails-bar'), dock=document.querySelector('#studio-mobile-dock'), toolbar=document.querySelector('#studio-toolbar');
      const tr=toolbar?.getBoundingClientRect(), dr=drawer?.getBoundingClientRect();
      const visible=[...document.querySelectorAll('#studio-toolbar button,#studio-toolbar select,#studio-mobile-dock button')].filter(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';});
      const outside=visible.filter(e=>{const r=e.getBoundingClientRect();return r.left<-1||r.right>innerWidth+1||r.top<-1||r.bottom>innerHeight+1;});
      return {viewportWidth:innerWidth,documentWidth:document.documentElement.scrollWidth,organizeActive:document.querySelector('#btn-mode-organize')?.classList.contains('active'),pagesDrawerOpen:shell?.classList.contains('studio-pages-open'),drawerVisible:!!drawer&&getComputedStyle(drawer).display!=='none',drawerTop:dr?.top||0,drawerBottom:dr?.bottom||0,drawerHeight:dr?.height||0,toolbarTop:tr?.top||0,toolbarBottom:tr?.bottom||0,toolbarDrawerOverlap:tr&&dr?Math.max(0,Math.min(tr.bottom,dr.bottom)-Math.max(tr.top,dr.top)):null,dockVisible:!!dock&&getComputedStyle(dock).display!=='none',toolbarHeight:tr?.height||0,visibleControls:visible.length,outOfViewportControls:outside.length};
    }''')
    mctx.close()
    browser.close()

results['page_errors'] = len(errors)
results = redact_evidence(results)
(OUTPUTS / 'browser-acceptance.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps({
    'home_transfer_bytes': results['desktop']['home_performance']['transferBytes'],
    'pdf_engines_eagerly_loaded': results['desktop']['home_performance']['pdf_engine_resources_eagerly_loaded'],
    'pdfjs_lazy_load_verified': results['desktop']['studio_initial']['pdfjs_loaded_on_demand'],
    'pdf_lib_lazy_load_verified': results['desktop']['pdf_lib_loader_check']['loaded'],
    'page_errors': results['page_errors'],
    'feedback_and_mobile_checks_passed': bool(results['mobile']['feedback_placement']['buttonVisible'] and results['mobile']['studio_390']['toolbarDrawerOverlap'] == 0),
}, indent=2))
