/**
 * Paperplane PDF  -  Phase 6 PDF Forms, Signing & Security Engine Controller
 * =========================================================================
 * Full client-side coordinator for:
 * 1. Interactive AcroForms (Field inspection, editing, filling, flattening, reset, JSON export/import)
 * 2. Visual & Digital Signatures (Visual stamp, detached PKCS#7 / CMS cryptographic signing, verification, tamper alert)
 * 3. PDF Security & Hardened Redaction (AES-256 encryption, granular permissions, password unlock, security inspection, sanitization, irreversible glyph redaction)
 */

'use strict';

(function () {
  function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  class PaperplaneSecurityFormsController {
    constructor() {
      this.currentFile = null;
      this.activeFormFields = [];
      this.isProcessing = false;

      this.init = this.init.bind(this);
      this.openFormsModal = this.openFormsModal.bind(this);
      this.openSignModal = this.openSignModal.bind(this);
      this.openSecurityModal = this.openSecurityModal.bind(this);
    }

    init() {
      this._bindHeaderButtons();
      this._bindFormsModal();
      this._bindSignModal();
      this._bindSecurityModal();
    }

    _getActiveFile() {
      return (window.PaperplaneEditor && window.PaperplaneEditor.editorState?.sourceFile)
        || this.currentFile
        || (window.state && window.state.files && window.state.files[0])
        || null;
    }

    _bindHeaderButtons() {
      const formsBtn = document.getElementById('studio-forms-btn');
      if (formsBtn) formsBtn.addEventListener('click', () => this.openFormsModal());

      const signBtn = document.getElementById('studio-sign-btn');
      if (signBtn) signBtn.addEventListener('click', () => this.openSignModal());

      const secBtn = document.getElementById('studio-security-btn');
      if (secBtn) secBtn.addEventListener('click', () => this.openSecurityModal());
    }

    // =========================================================================
    // 1. FORMS MODAL CONTROLLER
    // =========================================================================

    async openFormsModal(file = null) {
      const target = file || this._getActiveFile();
      if (!target) {
        window.showToast?.('Please open a PDF document in Studio first.', 'warning');
        return;
      }
      this.currentFile = target;
      const modal = document.getElementById('forms-modal');
      if (!modal) return;
      modal.hidden = false;

      this._switchFormsTab('inspect');
      await this.refreshFormsAnalysis();
    }

    _bindFormsModal() {
      const modal = document.getElementById('forms-modal');
      if (!modal) return;

      const closeBtn = document.getElementById('modal-close-forms');
      const cancelBtn = document.getElementById('btn-cancel-forms');
      if (closeBtn) closeBtn.onclick = () => { modal.hidden = true; };
      if (cancelBtn) cancelBtn.onclick = () => { modal.hidden = true; };

      // Tab switcher
      const tabInspect = document.getElementById('forms-tab-inspect');
      const tabAdd = document.getElementById('forms-tab-add');
      const tabIO = document.getElementById('forms-tab-io');

      if (tabInspect) tabInspect.onclick = () => this._switchFormsTab('inspect');
      if (tabAdd) tabAdd.onclick = () => this._switchFormsTab('add');
      if (tabIO) tabIO.onclick = () => this._switchFormsTab('io');

      // Actions
      const fillBtn = document.getElementById('btn-apply-form-fill');
      if (fillBtn) fillBtn.onclick = () => this.applyFormFill();

      const flattenBtn = document.getElementById('btn-apply-form-flatten');
      if (flattenBtn) flattenBtn.onclick = () => this.applyFormFlatten();

      const resetBtn = document.getElementById('btn-apply-form-reset');
      if (resetBtn) resetBtn.onclick = () => this.applyFormReset();

      const addFieldBtn = document.getElementById('btn-apply-add-field');
      if (addFieldBtn) addFieldBtn.onclick = () => this.applyAddField();

      const exportBtn = document.getElementById('btn-export-form-json');
      if (exportBtn) exportBtn.onclick = () => this.exportFormDataJson();

      const importBtn = document.getElementById('btn-apply-import-json');
      if (importBtn) importBtn.onclick = () => this.importFormDataJson();
    }

    _switchFormsTab(tabId) {
      ['inspect', 'add', 'io'].forEach(t => {
        const tabBtn = document.getElementById(`forms-tab-${t}`);
        const pane = document.getElementById(`forms-pane-${t}`);
        if (tabBtn) tabBtn.classList.toggle('active', t === tabId);
        if (pane) pane.style.display = (t === tabId) ? 'block' : 'none';
      });
    }

    async refreshFormsAnalysis() {
      const target = this._getActiveFile();
      if (!target) return;

      const container = document.getElementById('forms-fields-list');
      const countBadge = document.getElementById('forms-field-count-badge');
      if (container) container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; padding: 12px; text-align: center;">Scanning document for AcroForm widgets...</div>';

      try {
        const form = new FormData();
        form.append('file', target);
        const resp = await fetch('/api/studio/forms/analyze', { method: 'POST', body: form });
        if (!resp.ok) throw new Error(`Analysis failed (${resp.status})`);
        const data = await resp.json();
        this.activeFormFields = data.fields || [];

        if (countBadge) {
          countBadge.textContent = `${data.field_count} field${data.field_count === 1 ? '' : 's'} detected`;
          countBadge.className = data.field_count > 0 ? 'badge badge-full' : 'badge badge-unavail';
        }

        if (this.activeFormFields.length === 0) {
          if (container) {
            container.innerHTML = `
              <div style="padding: 24px; text-align: center; color: var(--text-muted);">
                <div style="font-size: 32px; margin-bottom: 8px;"></div>
                <strong>No Interactive Form Fields Found</strong>
                <p style="font-size: 11.5px; margin-top: 4px;">This PDF does not currently have interactive AcroForm widgets. You can add new fields using the <strong>Add Field</strong> tab above.</p>
              </div>`;
          }
          return;
        }

        // Render fields editor list
        if (container) {
          container.innerHTML = '';
          this.activeFormFields.forEach((field, idx) => {
            const row = document.createElement('div');
            row.className = 'form-field-edit-row';
            row.style.cssText = 'padding: 10px; background: rgba(30, 41, 59, 0.5); border: 1px solid var(--studio-border); border-radius: 6px; margin-bottom: 8px; font-size: 12px;';

            let inputHtml = '';
            if (field.field_type === 2) { // Checkbox
              const isChecked = field.field_value && ['Yes', '1', 'true', 'True', 'on'].includes(String(field.field_value));
              inputHtml = `<label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                <input type="checkbox" id="form-input-${idx}" class="form-field-input" data-name="${field.field_name}" ${isChecked ? 'checked' : ''} />
                <span>Checked / Active</span>
              </label>`;
            } else if (field.choice_values && field.choice_values.length > 0) {
              const options = field.choice_values.map(c => `<option value="${c}" ${c === field.field_value ? 'selected' : ''}>${c}</option>`).join('');
              inputHtml = `<select id="form-input-${idx}" class="editor-select form-field-input" data-name="${field.field_name}">${options}</select>`;
            } else {
              inputHtml = `<input type="text" id="form-input-${idx}" class="editor-input form-field-input" data-name="${field.field_name}" value="${field.field_value || ''}" placeholder="Field value..." style="width: 100%;" />`;
            }

            row.innerHTML = `
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <strong style="color: #f1f5f9; font-size: 12.5px;">${field.field_name}</strong>
                <span style="font-size: 10.5px; color: #94a3b8; background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px;">Page ${field.page + 1} · ${field.field_type_string || 'Field'}</span>
              </div>
              <div>${inputHtml}</div>
            `;
            container.appendChild(row);
          });
        }
      } catch (err) {
        if (container) container.innerHTML = `<div style="color: #ef4444; padding: 12px;">Error inspecting forms: ${err.message}</div>`;
      }
    }

    async applyFormFill() {
      const target = this._getActiveFile();
      if (!target) return;

      const inputs = document.querySelectorAll('.form-field-input');
      const values = {};
      inputs.forEach(inp => {
        const name = inp.getAttribute('data-name');
        if (!name) return;
        if (inp.type === 'checkbox') {
          values[name] = inp.checked;
        } else {
          values[name] = inp.value;
        }
      });

      try {
        window.showToast?.('Updating form field values...', 'info');
        const form = new FormData();
        form.append('file', target);
        form.append('field_values', JSON.stringify(values));

        const resp = await fetch('/api/studio/forms/fill', { method: 'POST', body: form });
        if (!resp.ok) throw new Error(`Form fill failed (${resp.status})`);

        const blob = await resp.blob();
        const newFile = new File([blob], target.name, { type: 'application/pdf' });
        if (window.loadDocumentIntoStudio) await window.loadDocumentIntoStudio(newFile);
        this.currentFile = newFile;
        await this.refreshFormsAnalysis();
        window.showToast?.('Form fields populated and appearances updated!', 'success');
      } catch (err) {
        window.showToast?.(`Error: ${err.message}`, 'error');
      }
    }

    async applyFormFlatten() {
      const target = this._getActiveFile();
      if (!target) return;

      if (!confirm('Flattening will bake all form appearances permanently into page vector streams, removing all interactive form widgets. Continue?')) {
        return;
      }

      try {
        window.showToast?.('Flattening form fields...', 'info');
        const form = new FormData();
        form.append('file', target);

        const resp = await fetch('/api/studio/forms/flatten', { method: 'POST', body: form });
        if (!resp.ok) throw new Error(`Flatten failed (${resp.status})`);

        const blob = await resp.blob();
        const newFile = new File([blob], target.name, { type: 'application/pdf' });
        if (window.loadDocumentIntoStudio) await window.loadDocumentIntoStudio(newFile);
        this.currentFile = newFile;
        await this.refreshFormsAnalysis();
        window.showToast?.('Document flattened! Form fields are now immutable vector content.', 'success');
      } catch (err) {
        window.showToast?.(`Error: ${err.message}`, 'error');
      }
    }

    async applyFormReset() {
      const target = this._getActiveFile();
      if (!target) return;

      if (!confirm('Reset all interactive form fields to empty/default states?')) return;

      try {
        window.showToast?.('Resetting form fields...', 'info');
        const form = new FormData();
        form.append('file', target);

        const resp = await fetch('/api/studio/forms/reset', { method: 'POST', body: form });
        if (!resp.ok) throw new Error(`Reset failed (${resp.status})`);

        const blob = await resp.blob();
        const newFile = new File([blob], target.name, { type: 'application/pdf' });
        if (window.loadDocumentIntoStudio) await window.loadDocumentIntoStudio(newFile);
        this.currentFile = newFile;
        await this.refreshFormsAnalysis();
        window.showToast?.('All form fields cleared and reset to defaults.', 'success');
      } catch (err) {
        window.showToast?.(`Error: ${err.message}`, 'error');
      }
    }

    async applyAddField() {
      const target = this._getActiveFile();
      if (!target) return;

      const type = document.getElementById('new-field-type')?.value || 'text';
      const name = document.getElementById('new-field-name')?.value.trim();
      const val = document.getElementById('new-field-value')?.value || '';
      const x = parseFloat(document.getElementById('new-field-x')?.value || 72);
      const y = parseFloat(document.getElementById('new-field-y')?.value || 100);
      const w = parseFloat(document.getElementById('new-field-w')?.value || 200);
      const h = parseFloat(document.getElementById('new-field-h')?.value || 28);
      const req = document.getElementById('new-field-required')?.checked || false;

      if (!name) {
        window.showToast?.('Please specify a unique field name.', 'warning');
        return;
      }

      const activePage = (window.PaperplaneEditor && window.PaperplaneEditor.editorState.currentPage) ? window.PaperplaneEditor.editorState.currentPage - 1 : 0;

      const fieldData = {
        page: activePage,
        type: type,
        name: name,
        rect: [x, y, x + w, y + h],
        value: val,
        required: req
      };

      try {
        window.showToast?.('Adding form field...', 'info');
        const form = new FormData();
        form.append('file', target);
        form.append('field_data', JSON.stringify(fieldData));

        const resp = await fetch('/api/studio/forms/add-field', { method: 'POST', body: form });
        if (!resp.ok) throw new Error(`Add field failed (${resp.status})`);

        const blob = await resp.blob();
        const newFile = new File([blob], target.name, { type: 'application/pdf' });
        if (window.loadDocumentIntoStudio) await window.loadDocumentIntoStudio(newFile);
        this.currentFile = newFile;
        this._switchFormsTab('inspect');
        await this.refreshFormsAnalysis();
        window.showToast?.(`Added ${type} field "${name}" to Page ${activePage + 1}!`, 'success');
      } catch (err) {
        window.showToast?.(`Error: ${err.message}`, 'error');
      }
    }

    async exportFormDataJson() {
      const target = this._getActiveFile();
      if (!target) return;

      try {
        const form = new FormData();
        form.append('file', target);
        const resp = await fetch('/api/studio/forms/export', { method: 'POST', body: form });
        if (!resp.ok) throw new Error(`Export failed (${resp.status})`);
        const json = await resp.json();
        const blob = new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' });
        downloadBlob(blob, `${target.name.replace(/\.pdf$/i, '')}_form_data.json`);
        window.showToast?.('Form data JSON exported and downloaded.', 'success');
      } catch (err) {
        window.showToast?.(`Export error: ${err.message}`, 'error');
      }
    }

    async importFormDataJson() {
      const target = this._getActiveFile();
      if (!target) return;

      const textarea = document.getElementById('forms-import-json-text');
      const rawText = textarea ? textarea.value.trim() : '';
      if (!rawText) {
        window.showToast?.('Please paste JSON form data to import.', 'warning');
        return;
      }

      try {
        JSON.parse(rawText); // Validate JSON syntax
        const form = new FormData();
        form.append('file', target);
        form.append('data', rawText);

        const resp = await fetch('/api/studio/forms/import', { method: 'POST', body: form });
        if (!resp.ok) throw new Error(`Import failed (${resp.status})`);

        const blob = await resp.blob();
        const newFile = new File([blob], target.name, { type: 'application/pdf' });
        if (window.loadDocumentIntoStudio) await window.loadDocumentIntoStudio(newFile);
        this.currentFile = newFile;
        this._switchFormsTab('inspect');
        await this.refreshFormsAnalysis();
        window.showToast?.('Form data imported and populated into document!', 'success');
      } catch (err) {
        window.showToast?.(`Import error: ${err.message}`, 'error');
      }
    }

    // =========================================================================
    // 2. SIGNING ENGINE (VISUAL & DIGITAL PKCS#7)
    // =========================================================================

    openSignModal(file = null) {
      const target = file || this._getActiveFile();
      if (!target) {
        window.showToast?.('Please open a PDF document in Studio first.', 'warning');
        return;
      }
      this.currentFile = target;
      const modal = document.getElementById('digital-sign-modal');
      if (!modal) return;
      modal.hidden = false;
      this._switchSignTab('digital');
    }

    _bindSignModal() {
      const modal = document.getElementById('digital-sign-modal');
      if (!modal) return;

      const closeBtn = document.getElementById('modal-close-digital-sign');
      const cancelBtn = document.getElementById('btn-cancel-digital-sign');
      if (closeBtn) closeBtn.onclick = () => { modal.hidden = true; };
      if (cancelBtn) cancelBtn.onclick = () => { modal.hidden = true; };

      // Tab switcher
      const tabDigital = document.getElementById('sign-tab-digital');
      const tabVerify = document.getElementById('sign-tab-verify');
      const tabVisual = document.getElementById('sign-tab-visual');

      if (tabDigital) tabDigital.onclick = () => this._switchSignTab('digital');
      if (tabVerify) tabVerify.onclick = () => this._switchSignTab('verify');
      if (tabVisual) tabVisual.onclick = () => this._switchSignTab('visual');

      // Actions
      const applyDigitalBtn = document.getElementById('btn-apply-digital-sign');
      if (applyDigitalBtn) applyDigitalBtn.onclick = () => this.applyDigitalSignature();

      const runVerifyBtn = document.getElementById('btn-run-verify-signatures');
      if (runVerifyBtn) runVerifyBtn.onclick = () => this.verifyDocumentSignatures();

      const runVerifyMainBtn = document.getElementById('btn-run-verify-signatures-main');
      if (runVerifyMainBtn) runVerifyMainBtn.onclick = () => this.verifyDocumentSignatures();

      const applyVisualBtn = document.getElementById('btn-apply-modal-visual-sign');
      if (applyVisualBtn) applyVisualBtn.onclick = () => this.applyModalVisualSignature();
    }

    _switchSignTab(tabId) {
      ['digital', 'verify', 'visual'].forEach(t => {
        const tabBtn = document.getElementById(`sign-tab-${t}`);
        const pane = document.getElementById(`sign-pane-${t}`);
        if (tabBtn) tabBtn.classList.toggle('active', t === tabId);
        if (pane) pane.style.display = (t === tabId) ? 'block' : 'none';
      });

      const applyDigitalBtn = document.getElementById('btn-apply-digital-sign');
      const verifyMainBtn = document.getElementById('btn-run-verify-signatures-main');
      const applyVisualBtn = document.getElementById('btn-apply-modal-visual-sign');

      if (applyDigitalBtn) applyDigitalBtn.style.display = (tabId === 'digital') ? 'inline-flex' : 'none';
      if (verifyMainBtn) verifyMainBtn.style.display = (tabId === 'verify') ? 'inline-flex' : 'none';
      if (applyVisualBtn) applyVisualBtn.style.display = (tabId === 'visual') ? 'inline-flex' : 'none';

      if (tabId === 'verify') {
        this.verifyDocumentSignatures();
      }
    }

    async applyDigitalSignature() {
      const target = this._getActiveFile();
      if (!target) return;

      const signerName = document.getElementById('digital-signer-name')?.value.trim() || 'Verified Signer';
      const reason = document.getElementById('digital-sign-reason')?.value.trim() || 'Document Integrity Verification';
      const location = document.getElementById('digital-sign-location')?.value.trim() || 'Paperplane Local';
      const addVisual = document.getElementById('digital-sign-visual-seal')?.checked || true;

      const activePage = (window.PaperplaneEditor && window.PaperplaneEditor.editorState.currentPage) ? window.PaperplaneEditor.editorState.currentPage - 1 : 0;

      try {
        window.showToast?.('Generating RSA-2048 certificate & signing detached PKCS#7...', 'info');
        const form = new FormData();
        form.append('file', target);
        form.append('signer_name', signerName);
        form.append('reason', reason);
        form.append('location', location);

        if (addVisual) {
          form.append('visual_appearance', JSON.stringify({ page: activePage, rect: [72, 650, 320, 720] }));
        }

        const resp = await fetch('/api/studio/sign/digital', { method: 'POST', body: form });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || `Signing failed (${resp.status})`);
        }

        const blob = await resp.blob();
        const signedName = target.name.replace(/\.pdf$/i, '_digitally_signed.pdf');
        const newFile = new File([blob], signedName, { type: 'application/pdf' });

        if (window.loadDocumentIntoStudio) await window.loadDocumentIntoStudio(newFile);
        this.currentFile = newFile;

        this._switchSignTab('verify');
        window.showToast?.('Cryptographic detached PKCS#7 signature successfully applied!', 'success');
      } catch (err) {
        window.showToast?.(`Digital signature error: ${err.message}`, 'error');
      }
    }

    async verifyDocumentSignatures() {
      const target = this._getActiveFile();
      const container = document.getElementById('verify-report-container');
      if (!target || !(target instanceof Blob || target instanceof File) || target.size === 0) {
        if (container) {
          container.innerHTML = `
            <div style="padding: 24px; text-align: center; color: var(--text-muted);">
              <div style="margin-bottom: 8px;"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></div>
              <strong>No Document Loaded</strong>
              <p style="font-size: 11.5px; margin-top: 4px;">Please open or upload a PDF document in Studio first to inspect digital signatures.</p>
            </div>`;
        }
        return;
      }

      if (container) container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; padding: 12px; text-align: center;">Cryptographically verifying ByteRange & certificates...</div>';

      try {
        const form = new FormData();
        form.append('file', target);
        const resp = await fetch('/api/studio/sign/verify', { method: 'POST', body: form });
        if (!resp.ok) throw new Error(`Verification failed (${resp.status})`);
        const report = await resp.json();

        if (!container) return;

        if (!report.is_signed || report.signature_count === 0) {
          container.innerHTML = `
            <div style="padding: 24px; text-align: center; color: var(--text-muted);">
              <div style="margin-bottom: 8px;"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg></div>
              <strong>No Digital Signatures Found</strong>
              <p style="font-size: 11.5px; margin-top: 4px;">This document does not contain cryptographic detached PKCS#7 or CMS signatures.</p>
            </div>`;
          return;
        }

        const isAllValid = report.overall_status === 'VALID';
        const isTampered = report.overall_status === 'TAMPERED';

        let badgeStyle = isAllValid ? 'background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4);' : (isTampered ? 'background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4);' : 'background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4);');

        let html = `
          <div style="padding: 12px; border-radius: 8px; margin-bottom: 12px; ${badgeStyle}">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <strong>${isAllValid ? 'ALL SIGNATURES CRYPTOGRAPHICALLY VALID' : (isTampered ? 'TAMPERING DETECTED - FILE WAS MODIFIED' : 'INVALID SIGNATURE')}</strong>
              <span class="badge" style="${badgeStyle}">${report.overall_status}</span>
            </div>
            <div style="font-size: 11.5px; margin-top: 4px; opacity: 0.9;">Total Signatures: ${report.signature_count}</div>
          </div>
        `;

        report.signatures.forEach((sig, i) => {
          const cert = sig.certificate || {};
          html += `
            <div style="padding: 10px; background: rgba(30, 41, 59, 0.5); border: 1px solid var(--studio-border); border-radius: 6px; margin-bottom: 8px; font-size: 12px;">
              <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                <strong>Signature #${sig.index || (i + 1)}</strong>
                <span class="badge ${sig.status === 'VALID' ? 'badge-full' : 'badge-unavail'}">${sig.status}</span>
              </div>
              <div style="color: #cbd5e1; font-size: 11.5px; line-height: 1.5;">
                <div>Subject: <strong>${cert.subject || 'Unknown'}</strong></div>
                <div>Issuer: ${cert.issuer || 'Self-Signed'}</div>
                <div>ByteRange: [${(sig.byte_range || []).join(', ')}]</div>
                ${sig.tamper_detected ? '<div style="color: #ef4444; font-weight: bold; margin-top: 4px;">Digest mismatch: document bytes altered after signing!</div>' : '<div style="color: #10b981; margin-top: 4px;">Document byte stream integrity intact.</div>'}
              </div>
            </div>
          `;
        });

        container.innerHTML = html;
      } catch (err) {
        if (container) container.innerHTML = `<div style="color: #ef4444; padding: 12px;">Verification error: ${err.message}</div>`;
      }
    }

    async applyModalVisualSignature() {
      const target = this._getActiveFile();
      if (!target) return;

      const typedName = document.getElementById('modal-visual-sig-text')?.value.trim() || 'Signed';
      const activePage = (window.PaperplaneEditor && window.PaperplaneEditor.editorState.currentPage) ? window.PaperplaneEditor.editorState.currentPage - 1 : 0;

      try {
        window.showToast?.('Applying visual signature...', 'info');
        const form = new FormData();
        form.append('file', target);
        form.append('signature_data', typedName);
        form.append('signer_name', typedName);
        form.append('page', activePage);
        form.append('rect', JSON.stringify([72, 650, 280, 710]));

        const resp = await fetch('/api/studio/sign/visual', { method: 'POST', body: form });
        if (!resp.ok) throw new Error(`Visual signature failed (${resp.status})`);

        const blob = await resp.blob();
        const newFile = new File([blob], target.name, { type: 'application/pdf' });
        if (window.loadDocumentIntoStudio) await window.loadDocumentIntoStudio(newFile);
        this.currentFile = newFile;
        document.getElementById('digital-sign-modal').hidden = true;
        window.showToast?.('Visual signature placed on document!', 'success');
      } catch (err) {
        window.showToast?.(`Error: ${err.message}`, 'error');
      }
    }

    // =========================================================================
    // 3. SECURITY & REDACTION CONTROLLER
    // =========================================================================

    openSecurityModal(file = null) {
      const target = file || this._getActiveFile();
      if (!target) {
        window.showToast?.('Please open a PDF document in Studio first.', 'warning');
        return;
      }
      this.currentFile = target;
      const modal = document.getElementById('security-modal');
      if (!modal) return;
      modal.hidden = false;
      this._switchSecurityTab('protect');
    }

    _bindSecurityModal() {
      const modal = document.getElementById('security-modal');
      if (!modal) return;

      const closeBtn = document.getElementById('modal-close-security');
      const cancelBtn = document.getElementById('btn-cancel-security');
      if (closeBtn) closeBtn.onclick = () => { modal.hidden = true; };
      if (cancelBtn) cancelBtn.onclick = () => { modal.hidden = true; };

      // Tab switcher
      const tabProtect = document.getElementById('sec-tab-protect');
      const tabUnlock = document.getElementById('sec-tab-unlock');
      const tabAudit = document.getElementById('sec-tab-audit');
      const tabRedact = document.getElementById('sec-tab-redact');

      if (tabProtect) tabProtect.onclick = () => this._switchSecurityTab('protect');
      if (tabUnlock) tabUnlock.onclick = () => this._switchSecurityTab('unlock');
      if (tabAudit) tabAudit.onclick = () => this._switchSecurityTab('audit');
      if (tabRedact) tabRedact.onclick = () => this._switchSecurityTab('redact');

      // Actions
      const applyProtectBtn = document.getElementById('btn-apply-protect');
      if (applyProtectBtn) applyProtectBtn.onclick = () => this.applyProtectPdf();

      const applyUnlockBtn = document.getElementById('btn-apply-unlock');
      if (applyUnlockBtn) applyUnlockBtn.onclick = () => this.applyUnlockPdf();

      const applySanitizeBtn = document.getElementById('btn-apply-sanitize');
      if (applySanitizeBtn) applySanitizeBtn.onclick = () => this.applySanitizePdf();
      const applySanitizeFooterBtn = document.getElementById('btn-apply-sanitize-footer');
      if (applySanitizeFooterBtn) applySanitizeFooterBtn.onclick = () => this.applySanitizePdf();

      const applyRedactBtn = document.getElementById('btn-apply-hardened-redact');
      if (applyRedactBtn) applyRedactBtn.onclick = () => this.applyHardenedRedaction();
      const applyRedactFooterBtn = document.getElementById('btn-apply-hardened-redact-footer');
      if (applyRedactFooterBtn) applyRedactFooterBtn.onclick = () => this.applyHardenedRedaction();

      // Password eye toggles
      document.querySelectorAll('.btn-sec-eye').forEach(btn => {
        btn.onclick = (e) => {
          e.preventDefault();
          const targetId = btn.getAttribute('data-target');
          const input = document.getElementById(targetId);
          if (input) {
            const isPw = input.type === 'password';
            input.type = isPw ? 'text' : 'password';
            btn.setAttribute('aria-label', isPw ? 'Hide password' : 'Show password');
          }
        };
      });
    }

    _switchSecurityTab(tabId) {
      ['protect', 'unlock', 'audit', 'redact'].forEach(t => {
        const tabBtn = document.getElementById(`sec-tab-${t}`);
        const pane = document.getElementById(`sec-pane-${t}`);
        if (tabBtn) tabBtn.classList.toggle('active', t === tabId);
        if (pane) pane.style.display = (t === tabId) ? 'block' : 'none';
      });

      const protectBtn = document.getElementById('btn-apply-protect');
      const unlockBtn = document.getElementById('btn-apply-unlock');
      const sanitizeBtn = document.getElementById('btn-apply-sanitize-footer');
      const redactBtn = document.getElementById('btn-apply-hardened-redact-footer');

      if (protectBtn) protectBtn.style.display = (tabId === 'protect') ? 'inline-flex' : 'none';
      if (unlockBtn) unlockBtn.style.display = (tabId === 'unlock') ? 'inline-flex' : 'none';
      if (sanitizeBtn) sanitizeBtn.style.display = (tabId === 'audit') ? 'inline-flex' : 'none';
      if (redactBtn) redactBtn.style.display = (tabId === 'redact') ? 'inline-flex' : 'none';

      if (tabId === 'audit') {
        this.refreshSecurityAudit();
      }
    }

    async applyProtectPdf() {
      const target = this._getActiveFile();
      if (!target) return;

      const userPw = document.getElementById('sec-user-password')?.value || '';
      const ownerPw = document.getElementById('sec-owner-password')?.value || '';

      if (!userPw && !ownerPw) {
        window.showToast?.('Please specify a password to protect this document.', 'warning');
        return;
      }

      const permissions = {
        allow_printing: document.getElementById('perm-allow-print')?.checked ?? true,
        allow_copying: document.getElementById('perm-allow-copy')?.checked ?? true,
        allow_modifying: document.getElementById('perm-allow-modify')?.checked ?? false,
        allow_annotating: document.getElementById('perm-allow-annotate')?.checked ?? false,
        allow_form_filling: document.getElementById('perm-allow-forms')?.checked ?? true
      };

      try {
        window.showToast?.('Encrypting document with AES-256...', 'info');
        const form = new FormData();
        form.append('file', target);
        form.append('user_password', userPw);
        form.append('owner_password', ownerPw || userPw);
        form.append('permissions', JSON.stringify(permissions));

        const resp = await fetch('/api/studio/security/protect', { method: 'POST', body: form });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || `Protection failed (${resp.status})`);
        }

        const blob = await resp.blob();
        const protName = target.name.replace(/\.pdf$/i, '_protected.pdf');
        downloadBlob(blob, protName);
        window.showToast?.('PDF encrypted with AES-256 and permissions bitmask! Protected file downloaded.', 'success');
      } catch (err) {
        window.showToast?.(`Protection error: ${err.message}`, 'error');
      }
    }

    async applyUnlockPdf() {
      const target = this._getActiveFile();
      if (!target) return;

      const password = document.getElementById('sec-unlock-password')?.value || '';
      if (!password) {
        window.showToast?.('Please enter the password to unlock this document.', 'warning');
        return;
      }

      try {
        window.showToast?.('Authenticating password & decrypting...', 'info');
        const form = new FormData();
        form.append('file', target);
        form.append('password', password);

        const resp = await fetch('/api/studio/security/unlock', { method: 'POST', body: form });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || 'Incorrect password.');
        }

        const blob = await resp.blob();
        const unlName = target.name.replace(/\.pdf$/i, '_unlocked.pdf');
        const newFile = new File([blob], unlName, { type: 'application/pdf' });
        if (window.loadDocumentIntoStudio) await window.loadDocumentIntoStudio(newFile);
        this.currentFile = newFile;
        document.getElementById('security-modal').hidden = true;
        window.showToast?.('PDF successfully unlocked and decrypted!', 'success');
      } catch (err) {
        window.showToast?.(`Unlock failed: ${err.message}`, 'error');
      }
    }

    async refreshSecurityAudit() {
      const target = this._getActiveFile();
      const container = document.getElementById('sec-audit-report');
      if (!target || !(target instanceof Blob || target instanceof File) || target.size === 0) {
        if (container) {
          container.innerHTML = `
            <div style="padding: 20px; text-align: center; color: var(--text-muted);">
              <strong>No Document Loaded</strong>
              <p style="font-size: 11.5px; margin-top: 4px;">Please open or upload a PDF document in Studio first to perform security auditing and sanitization.</p>
            </div>`;
        }
        return;
      }

      if (container) container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; padding: 12px; text-align: center;">Running security audit...</div>';

      try {
        const form = new FormData();
        form.append('file', target);
        const resp = await fetch('/api/studio/security/inspect', { method: 'POST', body: form });
        if (!resp.ok) throw new Error(`Inspection failed (${resp.status})`);
        const info = await resp.json();

        if (!container) return;

        const isEncrypted = info.is_encrypted;
        const perms = info.permissions || {};

        container.innerHTML = `
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12px; color: #cbd5e1; margin-bottom: 12px;">
            <div>Encryption: <strong style="color: ${isEncrypted ? '#10b981' : '#f59e0b'};">${isEncrypted ? (info.encryption_type || 'AES-256') : 'None (Unencrypted)'}</strong></div>
            <div>Password Required: <strong>${info.open_password_required ? 'Yes' : 'No'}</strong></div>
            <div>Active JavaScript: <strong style="color: ${info.has_javascript ? '#ef4444' : '#10b981'};">${info.has_javascript ? 'Detected' : 'Clean'}</strong></div>
            <div>File Attachments: <strong>${info.attachment_count || 0}</strong></div>
            <div>Form Fields: <strong>${info.form_field_count || 0}</strong></div>
            <div>Digitally Signed: <strong>${info.is_digitally_signed ? 'Yes' : 'No'}</strong></div>
          </div>
          <div style="padding: 8px; background: rgba(30, 41, 59, 0.6); border-radius: 6px; font-size: 11.5px; color: #94a3b8;">
            <div style="margin-bottom: 4px; color: #fff; font-weight: 600;">Active User Permissions</div>
            <div>Print: ${perms.can_print ? 'Allowed' : 'Blocked'} · Copy Text: ${perms.can_copy ? 'Allowed' : 'Blocked'} · Modify: ${perms.can_modify ? 'Allowed' : 'Blocked'}</div>
          </div>
        `;
      } catch (err) {
        if (container) container.innerHTML = `<div style="color: #ef4444; padding: 12px;">Audit error: ${err.message}</div>`;
      }
    }

    async applySanitizePdf() {
      const target = this._getActiveFile();
      if (!target) return;

      const opts = {
        remove_metadata: document.getElementById('sanitize-opt-meta')?.checked ?? true,
        remove_attachments: document.getElementById('sanitize-opt-att')?.checked ?? true,
        remove_annotations: document.getElementById('sanitize-opt-annots')?.checked ?? true,
        remove_javascript: document.getElementById('sanitize-opt-js')?.checked ?? true
      };

      try {
        window.showToast?.('Sanitizing document...', 'info');
        const form = new FormData();
        form.append('file', target);
        form.append('options', JSON.stringify(opts));

        const resp = await fetch('/api/studio/security/sanitize', { method: 'POST', body: form });
        if (!resp.ok) throw new Error(`Sanitize failed (${resp.status})`);

        const blob = await resp.blob();
        const newFile = new File([blob], target.name, { type: 'application/pdf' });
        if (window.loadDocumentIntoStudio) await window.loadDocumentIntoStudio(newFile);
        this.currentFile = newFile;
        await this.refreshSecurityAudit();
        window.showToast?.('Document sanitized: metadata, JavaScript, and comments purged!', 'success');
      } catch (err) {
        window.showToast?.(`Sanitization error: ${err.message}`, 'error');
      }
    }

    async applyHardenedRedaction() {
      const target = this._getActiveFile();
      if (!target) return;

      const keyword = document.getElementById('redact-text-target')?.value.trim();
      if (!keyword) {
        window.showToast?.('Please enter a keyword or phrase to redact.', 'warning');
        return;
      }

      if (!confirm(`Permanently and irreversibly obliterate all occurrences of "${keyword}" across document streams? Character glyphs will be destroyed.`)) {
        return;
      }

      try {
        window.showToast?.('Executing hardened irreversible redaction...', 'info');
        const activePage = (window.PaperplaneEditor && window.PaperplaneEditor.editorState.currentPage) ? window.PaperplaneEditor.editorState.currentPage - 1 : 0;
        const form = new FormData();
        form.append('file', target);
        form.append('redactions', JSON.stringify([{ page: activePage, text: keyword }]));

        const resp = await fetch('/api/studio/security/redact', { method: 'POST', body: form });
        if (!resp.ok) throw new Error(`Redaction failed (${resp.status})`);

        const blob = await resp.blob();
        const newFile = new File([blob], target.name, { type: 'application/pdf' });
        if (window.loadDocumentIntoStudio) await window.loadDocumentIntoStudio(newFile);
        this.currentFile = newFile;
        document.getElementById('security-modal').hidden = true;
        window.showToast?.(`Hardened redaction complete: "${keyword}" permanently eradicated!`, 'success');
      } catch (err) {
        window.showToast?.(`Redaction error: ${err.message}`, 'error');
      }
    }
  }

  // Initialize and expose on window
  const controller = new PaperplaneSecurityFormsController();
  window.PaperplaneSecurityForms = controller;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', controller.init);
  } else {
    controller.init();
  }
})();
