"""Four parallel PDF jobs against the freshly rebuilt production image."""
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, subprocess, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:18501'
CONTAINER = 'paperplane-v23-smoke'
EMAIL = 'audit-catalog@example.com'
PASSWORD = 'Dummy-Password-Only-2026!'

with TemporaryDirectory(prefix='paperplane-id90-image-concurrency-') as td:
    root = Path(td)
    fixture = root / 'parallel-source.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        page.insert_text((72, 72), 'CURRENT-IMAGE-PARALLEL-CONTENT')
        pdf.save(fixture)
    started = subprocess.run(['docker', 'start', CONTAINER], capture_output=True, text=True)
    if started.returncode and 'already running' not in started.stderr.lower():
        raise RuntimeError(started.stderr or started.stdout)
    evidence = {'image': 'paperplane-v23-audit:local-current-20261118', 'container': CONTAINER,
                'rounds': [], 'page_errors': []}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            context = browser.new_context(viewport={'width': 1366, 'height': 900})
            page = context.new_page()
            page.on('pageerror', lambda error: evidence['page_errors'].append(str(error)))
            for _ in range(60):
                try:
                    health = context.request.get(BASE + '/api/health', timeout=3000)
                    if health.status == 200:
                        break
                except Exception:
                    time.sleep(.5)
            else:
                raise RuntimeError('Current production-image container did not become healthy.')
            health_payload = health.json()
            page.goto(BASE + '/', wait_until='domcontentloaded')
            login = context.request.post(BASE + '/api/auth/login', data={'email': EMAIL, 'password': PASSWORD},
                                         headers={'content-type': 'application/json'})
            assert login.status == 200, login.text()
            assert context.request.get(BASE + '/api/auth/me').json().get('email') == EMAIL
            pdf_bytes = list(fixture.read_bytes())
            for round_number in (1, 2):
                submitted = page.evaluate("""async ({url, bytes, roundNo}) => Promise.all(
                  Array.from({length:4}, async (_, i) => {
                    const form = new FormData();
                    form.append('operation','merge'); form.append('options','{}');
                    form.append('files',new Blob([new Uint8Array(bytes)],{type:'application/pdf'}),`parallel-${roundNo}-${i}.pdf`);
                    const response=await fetch(url,{method:'POST',body:form,credentials:'same-origin'});
                    return {status:response.status,body:await response.json()};
                  }))""", {'url': BASE + '/api/jobs', 'bytes': pdf_bytes, 'roundNo': round_number})
                assert all(item['status'] == 202 for item in submitted), submitted
                job_ids = [item['body']['job_id'] for item in submitted]
                assert len(set(job_ids)) == 4, job_ids
                outcomes = []
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    responses = [context.request.get(BASE + f'/api/jobs/{job_id}', timeout=10000)
                                 for job_id in job_ids]
                    assert all(response.status == 200 for response in responses), [r.status for r in responses]
                    outcomes = [response.json() for response in responses]
                    if all(result['status'] in {'completed', 'failed'} for result in outcomes):
                        break
                    time.sleep(.25)
                assert len(outcomes) == 4 and all(result['status'] == 'completed' for result in outcomes), outcomes
                downloads = []
                for job_id, result in zip(job_ids, outcomes):
                    response = context.request.get(BASE + f'/api/jobs/{job_id}/download', timeout=15000)
                    assert response.status == 200, response.status
                    with fitz.open(stream=response.body(), filetype='pdf') as output:
                        text = '\n'.join(p.get_text() for p in output)
                        assert output.page_count == 1 and 'CURRENT-IMAGE-PARALLEL-CONTENT' in text, text
                        downloads.append({'status': response.status, 'pages': output.page_count,
                                          'content_checked': True, 'bytes': len(response.body())})
                evidence['rounds'].append({'round': round_number, 'submitted': len(job_ids),
                                           'completed': len(outcomes), 'downloads': downloads})
            assert not evidence['page_errors'], evidence['page_errors']
            browser.close()
        evidence['health'] = health_payload
        (OUT / 'browser-id90-current-image-concurrency.json').write_text(
            json.dumps(evidence, indent=2), encoding='utf-8')
        print(json.dumps(evidence, indent=2))
    finally:
        subprocess.run(['docker', 'stop', CONTAINER], capture_output=True, text=True)
