from pathlib import Path
from tempfile import TemporaryDirectory
import base64, json, socket, sys, time
import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id113-') as temp:
    root = Path(temp)
    source_path = root / 'source.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), 'RECOVERABLE XREF DAMAGE CHECK')
        page.insert_text((72, 140), 'Invoice reference: PP-113-54821')
        doc.save(source_path)
    raw = bytearray(source_path.read_bytes())
    startxref = raw.rfind(b'startxref')
    assert startxref >= 0
    raw[startxref:startxref + len(b'startxref')] = b'startxxxx'
    damaged = root / 'damaged-xref.pdf'
    damaged.write_bytes(raw)

    app, base, _ = helper.start_server(root / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)

        rounds = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            for number in (1, 2):
                context = browser.new_context()
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/repair-pdf', wait_until='domcontentloaded')
                result = page.evaluate('''async ({data, roundNumber}) => {
                  const raw=Uint8Array.from(atob(data), c=>c.charCodeAt(0));
                  const form=new FormData();
                  form.append('file', new File([raw], `damaged-${roundNumber}.pdf`, {type:'application/pdf'}));
                  form.append('mode','automatic');
                  const response=await fetch('/api/studio/repair',{method:'POST',body:form});
                  const bytes=new Uint8Array(await response.arrayBuffer());
                  let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
                  return {status:response.status,repairValid:response.headers.get('x-repair-valid'),recoveredPages:response.headers.get('x-recovered-pages'),contentType:response.headers.get('content-type'),bytes:btoa(binary)};
                }''', {'data': base64.b64encode(damaged.read_bytes()).decode(), 'roundNumber': number})
                assert result['status'] == 200, result
                assert result['repairValid'] == 'True' and result['recoveredPages'] == '1', result
                output = root / f'repaired-{number}.pdf'
                output.write_bytes(base64.b64decode(result.pop('bytes')))
                with fitz.open(output) as repaired:
                    content = repaired[0].get_text()
                    assert repaired.page_count == 1 and 'RECOVERABLE XREF DAMAGE CHECK' in content and 'PP-113-54821' in content, content
                assert not errors, errors
                result.update({'round':number,'outputBytes':output.stat().st_size,'pageCount':1,'text':content,'pageErrors':errors})
                rounds.append(result)
                context.close()
            browser.close()

        evidence = {'sourceBytes':source_path.stat().st_size,'damagedBytes':damaged.stat().st_size,'damage':'startxref marker changed to startxxxx','rounds':rounds}
        (OUT / 'browser-id113-repair-damaged-xref.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        print(json.dumps(evidence, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
