from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import ai_engine
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id349-') as temp:
    source=Path(temp)/'unitless-report.pdf'
    with fitz.open() as doc:
        for number in range(1,25):
            page=doc.new_page();page.insert_text((72,72),f'Page {number}: unitless amount 42000, limit 900000, and service fee 5000 USD are recorded.')
        doc[0].insert_text((72,130),'No further deadlines are identified.')
        doc[23].insert_text((72,180),'Cancellation deadline 15 December 2026.')
        doc.save(source)
    original_call=ai_engine.call_llm
    ai_engine.call_llm=lambda *_a,**_k: ('### Executive Summary\nNo further deadlines are identified. [Page 1]\n\n'
        '### Executive Summary\nNo additional dates are present. The budget is $42,000 and the cap is $900,000. [Page 24]')
    try:
        duplicate_summary=ai_engine.summarize_pdf(source)
        ai_engine.call_llm=lambda *_a,**_k: ('### Executive Summary\nNo further deadlines are identified. No additional dates are present. [Page 1]\n'
            'The budget is $42,000, the cap is $900,000, and the service fee is 5,000 USD. [Page 24]')
        mixed_currency_summary=ai_engine.summarize_pdf(source)
    finally: ai_engine.call_llm=original_call
    assert duplicate_summary.count('### Executive Summary')==1 and 'Offline Analysis' in duplicate_summary
    assert mixed_currency_summary.count('### Executive Summary')==1 and '$42,000' not in mixed_currency_summary and '$900,000' not in mixed_currency_summary
    assert 'no additional dates are present' not in mixed_currency_summary.lower() and 'No further deadlines are identified.' in mixed_currency_summary
    assert '5,000 USD' in mixed_currency_summary
    app,base,identity=helper.start_server(Path(temp)/'db')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for number in (1,2):
                context=browser.new_context(viewport={'width':1280,'height':800})
                context.route('**/api/ai/capabilities',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps({'executive_brief_available':True,'reason':None})))
                response_summary=duplicate_summary if number==1 else mixed_currency_summary
                response_mode='offline_extractive' if number==1 else 'provider_synthesized'
                response_body=json.dumps({'status':'success','summary':response_summary,'citations':[1,24],'summary_mode':response_mode})
                context.route('**/api/ai/summarize',lambda route:route.fulfill(status=200,content_type='application/json',body=response_body))
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/ai-intelligence',wait_until='domcontentloaded')
                page.locator('#ai-file-input').set_input_files(str(source));page.locator('#ai-active-doc-bar').wait_for(state='visible',timeout=30000)
                with page.expect_response(lambda r:'/api/ai/summarize' in r.url):page.locator('#trigger-summary-btn').click()
                page.wait_for_function("document.querySelector('#summary-display')?.innerText.includes('Executive Summary')",timeout=30000)
                rendered=page.locator('#summary-display').inner_text()
                assert rendered.count('Executive Summary')==1 and '$42,000' not in rendered and '$900,000' not in rendered,rendered
                supported_fee='5000 USD' if number==1 else '5,000 USD'
                unitless_amount='42000' if number==1 else '42,000'
                unitless_limit='900000' if number==1 else '900,000'
                assert unitless_limit in rendered and supported_fee in rendered,rendered
                assert 'no additional dates are present' not in rendered.lower()
                assert 'No further deadlines are identified.' in rendered
                expected_mode='Offline Analysis' if number==1 else 'AI Synthesis'
                assert page.locator('#summary-mode-badge').inner_text()==expected_mode
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id349-quality-round{number}.png'))
                rounds.append({'round':number,'summary_heading_count':rendered.count('Executive Summary'),'unsupported_currency_assigned':('$42,000' in rendered or '$900,000' in rendered),'supported_usd_preserved':supported_fee in rendered,'unitless_amounts_preserved':unitless_amount in rendered and unitless_limit in rendered,'unsupported_absence_claim_present':'no additional dates are present' in rendered.lower(),'supported_absence_statement_preserved':'No further deadlines are identified.' in rendered,'mode':page.locator('#summary-mode-badge').inner_text(),'page_errors':errors})
                context.close()
            browser.close()
        evidence={'rounds':rounds,'duplicate_summary_fell_back_to_one_offline_heading':True,'currency_attribution_checked_per_amount':True,'unsupported_document_wide_absence_claim_removed':True,'supported_absence_statement_preserved':True,'source_pages':24}
        (OUT/'browser-id349-summary-quality.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        print(json.dumps(evidence,indent=2))
    finally:app.terminate();app.wait(timeout=5)
