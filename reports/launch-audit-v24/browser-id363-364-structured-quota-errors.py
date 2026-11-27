from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
QUOTA = {"detail": {"code": "TIER_LIMIT_REACHED", "message": "Daily guest limit reached (10/10 operations). Create a free account or choose a paid plan."}}


def main() -> None:
    evidence: dict = {"success": [], "quota_rounds": [], "page_errors": [], "console_errors": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
        page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
        page.set_content("""<main><div id="forms-fields-list"></div><span id="forms-field-count-badge"></span>
          <div id="sec-audit-report"></div><div id="sec-sanitize-report"></div>
          <div id="forms-modal" hidden></div><div id="security-modal" hidden></div></main>""")
        page.evaluate("window.openUpgradeModal = message => { window.lastUpgradeMessage = message; }")
        page.add_script_tag(content=(ROOT / "web" / "assets" / "security_forms.js").read_text(encoding="utf-8"))
        page.wait_for_function("window.PaperplaneSecurityForms")
        page.evaluate("window.PaperplaneSecurityForms.currentFile = new File(['%PDF-1.4'], 'audit-fixture.pdf', {type:'application/pdf'})")
        page.evaluate("""window.fetch = async url => new Response(JSON.stringify(
          String(url).includes('/forms/analyze') ? {field_count:0, fields:[]} :
          {is_encrypted:false, open_password_required:false, has_javascript:false,
           attachment_count:0, form_field_count:0, is_digitally_signed:false,
           permissions:{can_print:true, can_copy:true, can_modify:true}}),
          {status:200, headers:{'Content-Type':'application/json'}})""")
        page.evaluate("window.PaperplaneSecurityForms.refreshFormsAnalysis()")
        page.wait_for_function("document.querySelector('#forms-fields-list').innerText.includes('No Interactive Form Fields Found')")
        page.evaluate("window.PaperplaneSecurityForms.refreshSecurityAudit()")
        page.wait_for_function("document.querySelector('#sec-audit-report').innerText.includes('Encryption:')")
        evidence["success"] = ["empty AcroForm state rendered", "security inspection summary rendered"]

        quota_json = json.dumps(QUOTA)
        page.evaluate("""quota => { window.fetch = async () => new Response(quota, {
          status:402, headers:{'Content-Type':'application/json'} }); }""", quota_json)
        for round_no in (1, 2):
            page.evaluate("window.PaperplaneSecurityForms.refreshFormsAnalysis()")
            page.wait_for_function("document.querySelector('#forms-fields-list').innerText.includes('Daily guest limit reached')")
            forms_text = page.locator("#forms-fields-list").inner_text()
            assert "Daily guest limit reached (10/10 operations)" in forms_text
            assert "Analysis failed (402)" not in forms_text
            page.evaluate("window.PaperplaneSecurityForms.refreshSecurityAudit()")
            page.wait_for_function("document.querySelector('#sec-audit-report').innerText.includes('Daily guest limit reached')")
            audit_text = page.locator("#sec-audit-report").inner_text()
            assert "Daily guest limit reached (10/10 operations)" in audit_text
            assert "Inspection failed (402)" not in audit_text
            assert page.evaluate("window.lastUpgradeMessage").startswith("Daily guest limit reached")
            evidence["quota_rounds"].append({"round": round_no, "forms_message": forms_text.strip(), "audit_message": audit_text.strip(), "upgrade_message": True})
        browser.close()
    evidence["passed"] = len(evidence["success"]) == 2 and len(evidence["quota_rounds"]) == 2 and not evidence["page_errors"] and not evidence["console_errors"]
    out = ROOT / "reports" / "launch-audit-v24" / "browser-id363-364-structured-quota-errors.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
