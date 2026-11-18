from pathlib import Path
from tempfile import TemporaryDirectory
import base64, fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper


def fixture_pdf(path):
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), 'Protect-to-Unlock same-session marker')
        pdf.save(path)


with TemporaryDirectory(prefix='paperplane-id307-') as temp:
    root = Path(temp)
    source = root / 'unlock-handoff.pdf'
    fixture_pdf(source)
    app, base, _identity = helper.start_server(root / 'data')
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
            for round_no in (1, 2):
                page = browser.new_page(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/protect-pdf', wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(source))
                page.locator('#open-security-audit-tool-btn').click()
                page.locator('#security-modal').wait_for(state='visible')
                page.locator('#sec-tab-protect').click()
                page.locator('#sec-user-password').fill('handoff-pass-307')
                with page.expect_download(timeout=20000) as download_wait:
                    page.locator('#btn-apply-protect').click()
                download = download_wait.value
                download_path = root / f'protected-round-{round_no}.pdf'
                download.save_as(download_path)
                with fitz.open(download_path) as protected:
                    assert protected.is_encrypted and protected.authenticate('handoff-pass-307')
                    assert 'Protect-to-Unlock same-session marker' in protected[0].get_text()
                page.locator('#sec-tab-unlock').click()
                handoff = page.evaluate("""async () => {
                  const file = window.PaperplaneSecurityForms?.protectedHandoffFile;
                  if (!file) return null;
                  const bytes = new Uint8Array(await file.arrayBuffer());
                  let binary = '';
                  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
                  return {name: file.name, size: file.size, bytes: btoa(binary), unlockPassword: document.querySelector('#sec-unlock-password')?.value};
                }""")
                assert handoff and handoff['name'] == 'unlock-handoff_protected.pdf', handoff
                assert handoff['unlockPassword'] == 'handoff-pass-307', handoff
                protected_buffer = base64.b64decode(handoff['bytes'])
                protected_check = root / f'handoff-round-{round_no}.pdf'
                protected_check.write_bytes(protected_buffer)
                with fitz.open(protected_check) as protected:
                    assert protected.is_encrypted and protected.authenticate('handoff-pass-307')
                with page.expect_response(lambda response: '/api/studio/security/unlock' in response.url, timeout=20000) as unlock_wait:
                    page.locator('#btn-apply-unlock').click()
                unlock_response = unlock_wait.value
                page.wait_for_function("window.PaperplaneSecurityForms?.protectedHandoffFile === null", timeout=20000)
                unlocked_bytes = page.evaluate("""async () => {
                  const file = window.PaperplaneSecurityForms?.currentFile;
                  if (!file) return null;
                  const bytes = new Uint8Array(await file.arrayBuffer());
                  let binary = '';
                  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
                  return {name: file.name, size: file.size, bytes: btoa(binary)};
                }""")
                assert unlock_response.status == 200 and unlocked_bytes, (unlock_response.status, unlocked_bytes)
                unlocked_path = root / f'unlocked-round-{round_no}.pdf'
                unlocked_path.write_bytes(base64.b64decode(unlocked_bytes['bytes']))
                with fitz.open(unlocked_path) as unlocked:
                    assert not unlocked.is_encrypted
                    assert 'Protect-to-Unlock same-session marker' in unlocked[0].get_text()
                assert not errors, errors
                page.screenshot(path=str(OUT / f'id307-protect-unlock-round{round_no}.png'))
                rounds.append({
                    'round': round_no,
                    'protected_download_bytes': download_path.stat().st_size,
                    'same_session_handoff_file': handoff['name'],
                    'same_session_file_is_encrypted': True,
                    'unlock_http_status': unlock_response.status,
                    'unlocked_output_content_checked': True,
                    'page_errors': errors,
                })
                page.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id307-protect-unlock-same-session.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
