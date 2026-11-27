"""Confirm attacker-controlled AcroForm labels/options stay inert in Chromium."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys
import time
from contextlib import nullcontext
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

payload = {
    "field_count": 3,
    "fields": [
        {"field_name": 'name"><img id="pp-xss-name" src="x" onerror="window.__pdfXss++">',
         "field_type": 1, "field_value": 'value"><img id="pp-xss-value" src="x" onerror="window.__pdfXss++">',
         "field_type_string": "Text", "page": 0},
        {"field_name": 'choice"><img id="pp-xss-choice-name" src="x" onerror="window.__pdfXss++">',
         "field_type": 3, "field_value": 'selected"><img id="pp-xss-choice-value" src="x" onerror="window.__pdfXss++">',
         "choice_values": ['allowed', 'choice"><img id="pp-xss-choice" src="x" onerror="window.__pdfXss++">'],
         "field_type_string": "Choice", "page": 0},
        {"field_name": 'check"><img id="pp-xss-check" src="x" onerror="window.__pdfXss++">',
         "field_type": 2, "field_value": "Yes", "field_type_string": "Checkbox", "page": 0},
    ],
}
security_payload = {
    "is_encrypted": True,
    "encryption_type": 'AES"><img id="pp-xss-encryption" src="x" onerror="window.__pdfXss++">',
    "open_password_required": False,
    "has_javascript": False,
    "attachment_count": '0"><img id="pp-xss-attachments" src="x" onerror="window.__pdfXss++">',
    "form_field_count": '3"><img id="pp-xss-count" src="x" onerror="window.__pdfXss++">',
    "is_digitally_signed": False,
    "permissions": {"can_print": True, "can_copy": True, "can_modify": False},
}
signature_payload = {
    "is_signed": True,
    "signature_count": 1,
    "overall_status": 'UNKNOWN"><img id="pp-xss-overall" src="x" onerror="window.__pdfXss++">',
    "signatures": [{
        "index": 1,
        "status": 'INVALID"><img id="pp-xss-signature" src="x" onerror="window.__pdfXss++">',
        "byte_range": [0, 10, 20, 30],
        "certificate": {"subject": "fixture", "issuer": "fixture"},
    }],
}
repair_payload = {
    "report": {
        "valid": False,
        "message": "Malformed document",
        "detected_issues": ['xref"><img id="pp-xss-repair" src="x" onerror="window.__pdfXss++">'],
    }
}


def fulfill_api(route) -> None:
    if route.request.url.endswith("/api/studio/forms/analyze"):
        body = payload
    elif route.request.url.endswith("/api/studio/security/inspect"):
        body = security_payload
    elif route.request.url.endswith("/api/studio/sign/verify"):
        body = signature_payload
    elif route.request.url.endswith("/api/studio/repair"):
        body = repair_payload
    else:
        route.continue_()
        return
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

external_base = os.getenv("PAPERPLANE_TEST_BASE", "").rstrip("/")
temporary_context = nullcontext(None) if external_base else TemporaryDirectory(prefix="paperplane-form-xss-")
with temporary_context as temporary:
    if external_base:
        app, base = None, external_base
    else:
        app, base, _ = helper.start_server(Path(temporary) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local app failed to start")

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            rounds = []
            for round_no in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                page = context.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/api/studio/**", fulfill_api)
                page.goto(base + "/", wait_until="networkidle", timeout=20000)
                page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=15000)
                page.evaluate("window.__pdfXss = 0")
                page.evaluate("""async () => {
                  const file = new File(['fixture'], 'hostile-form.pdf', {type:'application/pdf'});
                  await window.PaperplaneSecurityForms.openFormsModal(file);
                }""")
                page.wait_for_selector("#forms-fields-list .form-field-edit-row")
                snapshot = page.evaluate("""() => ({
                  injected: [...document.querySelectorAll('[id^="pp-xss-"]')].map(x=>x.id),
                  executionCount: window.__pdfXss,
                  names: [...document.querySelectorAll('#forms-fields-list strong')].map(x=>x.textContent),
                  values: [...document.querySelectorAll('#forms-fields-list input[type=text]')].map(x=>x.value),
                  optionLabels: [...document.querySelectorAll('#forms-fields-list option')].map(x=>x.textContent),
                  controls: [...document.querySelectorAll('#forms-fields-list .form-field-input')].map(x=>({name:x.dataset.name,type:x.type,value:x.value,checked:x.checked})),
                  formControls: document.querySelectorAll('#forms-fields-list .form-field-input').length
                })""")
                assert snapshot["injected"] == [], snapshot
                assert snapshot["executionCount"] == 0, snapshot
                assert len(snapshot["names"]) == 3 and '<img' in snapshot["names"][0], snapshot
                assert '<img' in snapshot["values"][0], snapshot
                assert '<img' in snapshot["optionLabels"][1], snapshot
                assert snapshot["formControls"] == 3, snapshot
                assert len(snapshot["controls"]) == 3 and snapshot["controls"][1]["value"] == "allowed", snapshot
                assert snapshot["controls"][2]["checked"] is True, snapshot
                page.evaluate("window.PaperplaneSecurityForms.refreshSecurityAudit()")
                page.wait_for_function("document.querySelector('#sec-audit-report').innerText.includes('AES')")
                audit = page.evaluate("""() => ({
                  injected: [...document.querySelectorAll('[id^="pp-xss-"]')].map(x=>x.id),
                  text: document.querySelector('#sec-audit-report').innerText
                })""")
                assert audit["injected"] == [] and '<img' in audit["text"], audit
                page.evaluate("window.PaperplaneSecurityForms.verifyDocumentSignatures()")
                page.wait_for_function("document.querySelector('#verify-report-container').innerText.includes('UNKNOWN')")
                signatures = page.evaluate("""() => ({
                  injected: [...document.querySelectorAll('[id^="pp-xss-"]')].map(x=>x.id),
                  text: document.querySelector('#verify-report-container').innerText
                })""")
                assert signatures["injected"] == [] and '<img' in signatures["text"], signatures
                page.evaluate("""async () => {
                  const file = new File(['fixture'], 'hostile-repair-report.pdf', {type:'application/pdf'});
                  window.PaperplaneOptimization.openRepairModal(file);
                  document.querySelector('#repair-modal input[name="repair-mode"][value="validate_only"]').checked = true;
                  document.querySelector('#btn-apply-repair').click();
                }""")
                page.wait_for_function("document.querySelector('#repair-report-box').style.display === 'block'")
                repair = page.evaluate("""() => ({
                  injected: [...document.querySelectorAll('[id^="pp-xss-"]')].map(x=>x.id),
                  text: document.querySelector('#repair-issues-list').textContent,
                  html: document.querySelector('#repair-issues-list').innerHTML
                })""")
                assert repair["injected"] == [] and '<img' in repair["text"], repair
                assert '&lt;img' in repair["html"] and '<img' not in repair["html"], repair
                page.evaluate("""async () => {
                  const label = 'page"><img id="pp-xss-page-label" src="x" onerror="window.__pdfXss++">';
                  const file = new File(['fixture'], 'hostile-label.pdf', {type:'application/pdf'});
                  window.PaperplanePageOrganizer.loadDocument(null, file, file.name, 1,
                    {pages:[{page:1,label,width:595,height:842}]});
                  await new Promise(resolve => setTimeout(resolve, 20));
                }""")
                pageLabel = page.evaluate("""() => ({
                  injected: [...document.querySelectorAll('[id^="pp-xss-"]')].map(x=>x.id),
                  text: document.querySelector('.thumb-page-num')?.textContent || ''
                })""")
                assert pageLabel["injected"] == [] and '<img' in pageLabel["text"], pageLabel
                assert page.evaluate("window.__pdfXss") == 0
                assert not errors, errors
                rounds.append({"round": round_no, "snapshot": snapshot, "audit": audit,
                               "signatures": signatures, "repair_report": repair,
                               "page_label": pageLabel, "page_errors": errors})
                context.close()
            browser.close()
            result = {"rounds": rounds, "passed": True}
    finally:
        if app is not None:
            app.terminate()
            try:
                app.wait(timeout=15)
            except Exception:
                app.kill()

output_name = "browser-security-form-fields-xss-docker.json" if external_base else "browser-security-form-fields-xss.json"
output = ROOT / "reports" / "launch-audit-v23" / output_name
output.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps({"passed": result["passed"], "rounds": len(result["rounds"]), "evidence": str(output)}, indent=2))
