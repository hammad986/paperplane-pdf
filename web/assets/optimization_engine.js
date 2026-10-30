/**
 * Paperplane PDF  -  Phase 4 Compression, Repair & OCR Engine Controller
 * ====================================================================
 * Coordinates client-side and backend execution of:
 * - Real Tesseract-backed OCR with searchable text-layer injection
 * - Measurable multi-preset compression & target file size optimization
 * - Structural PDF repair, syntax validation, and surviving page salvage
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

  class PaperplaneOptimizationController {
    constructor() {
      this.currentFile = null;
      this.installedLanguages = [];
      this.isProcessing = false;

      this.init = this.init.bind(this);
      this.openCompressModal = this.openCompressModal.bind(this);
      this.openOcrModal = this.openOcrModal.bind(this);
      this.openRepairModal = this.openRepairModal.bind(this);
    }

    init() {
      this._bindHeaderButtons();
      this._bindCompressModal();
      this._bindOcrModal();
      this._bindRepairModal();
      this._fetchInstalledLanguages();
    }

    async _fetchInstalledLanguages() {
      try {
        const resp = await fetch('/api/studio/ocr/languages');
        if (resp.ok) {
          const data = await resp.json();
          if (data && data.languages) {
            this.installedLanguages = data.languages;
            const select = document.getElementById('ocr-language-select');
            if (select) {
              select.innerHTML = '';
              data.languages.forEach(l => {
                const opt = document.createElement('option');
                opt.value = l.code;
                opt.textContent = `${l.name} (${l.code})`;
                if (l.code === 'eng') opt.selected = true;
                select.appendChild(opt);
              });
            }
          }
        }
      } catch (err) {
        console.warn('Failed to query installed OCR languages:', err);
      }
    }

    _bindHeaderButtons() {
      const compBtn = document.getElementById('studio-compress-btn');
      if (compBtn) compBtn.onclick = () => this.openCompressModal();

      const ocrBtn = document.getElementById('studio-ocr-btn');
      if (ocrBtn) ocrBtn.onclick = () => this.openOcrModal();

      const repBtn = document.getElementById('studio-repair-btn');
      if (repBtn) repBtn.onclick = () => this.openRepairModal();

      const batchOcrBtn = document.getElementById('batch-ocr-btn');
      if (batchOcrBtn) {
        batchOcrBtn.onclick = () => {
          let selected = [];
          if (window.PaperplanePageOrganizer && window.PaperplanePageOrganizer.state) {
            selected = window.PaperplanePageOrganizer.state.getSelectedSorted();
          }
          this.openOcrModal(null, selected);
        };
      }
    }

    // -------------------------------------------------------------------------
    // 1. COMPRESSION MODAL & ENGINE
    // -------------------------------------------------------------------------

    async openCompressModal(file = null) {
      const targetFile = file || (window.PaperplaneEditor && window.PaperplaneEditor.editorState.sourceFile);
      if (!targetFile) {
        window.showToast('Please open a PDF document in Studio first.', 'warning');
        return;
      }
      this.currentFile = targetFile;

      const modal = document.getElementById('compress-modal');
      if (!modal) return;

      // Reset UI stats
      document.getElementById('compress-stat-size').textContent = formatBytes(targetFile.size);
      document.getElementById('compress-stat-pages').textContent = '...';
      document.getElementById('compress-stat-images').textContent = '...';
      document.getElementById('compress-stat-raster').textContent = '...';
      document.getElementById('compress-stat-opp').textContent = 'Analyzing document structure...';
      document.getElementById('compress-analysis-badge').textContent = 'Scanning...';
      modal.hidden = false;

      // Run structural analysis
      try {
        const form = new FormData();
        form.append('file', targetFile);
        const resp = await fetch('/api/studio/compress/analyze', { method: 'POST', body: form });
        if (resp.ok) {
          const data = await resp.json();
          const a = data.analysis;
          document.getElementById('compress-stat-pages').textContent = a.page_count;
          document.getElementById('compress-stat-images').textContent = a.total_images;
          document.getElementById('compress-stat-raster').textContent = `${a.raster_percentage}%`;
          document.getElementById('compress-stat-opp').textContent = `${a.opportunity} (Est. ${a.estimated_reduction})`;
          document.getElementById('compress-analysis-badge').textContent = `${a.raster_percentage > 50 ? 'Raster Heavy' : 'Vector Heavy'}`;
        }
      } catch (err) {
        document.getElementById('compress-stat-opp').textContent = 'Could not run structural analysis.';
      }
    }

    _bindCompressModal() {
      const modal = document.getElementById('compress-modal');
      const closeBtn = document.getElementById('modal-close-compress');
      const cancelBtn = document.getElementById('btn-cancel-compress');
      const applyBtn = document.getElementById('btn-apply-compress');

      if (closeBtn) closeBtn.onclick = () => { modal.hidden = true; };
      if (cancelBtn) cancelBtn.onclick = () => { modal.hidden = true; };

      // Preset radio selection card toggle
      const cards = modal ? modal.querySelectorAll('.split-mode-card') : [];
      cards.forEach(card => {
        card.addEventListener('click', () => {
          cards.forEach(c => c.classList.remove('active'));
          card.classList.add('active');
          const radio = card.querySelector('input[type="radio"]');
          if (radio) radio.checked = true;
        });
      });

      if (applyBtn) {
        applyBtn.onclick = async () => {
          if (!this.currentFile) return;
          const chosenRadio = modal.querySelector('input[name="compress-preset"]:checked');
          const preset = chosenRadio ? chosenRadio.value : 'balanced';

          const targetSizeVal = parseFloat(document.getElementById('compress-target-size')?.value || '0');
          const targetUnit = document.getElementById('compress-target-unit')?.value || 'MB';
          let targetKb = null;
          if (targetSizeVal > 0) {
            targetKb = targetUnit === 'MB' ? Math.round(targetSizeVal * 1024) : Math.round(targetSizeVal);
          }

          modal.hidden = true;
          window.showToast(`Compressing PDF with ${preset} preset…`, 'info');

          try {
            const form = new FormData();
            form.append('file', this.currentFile);
            form.append('preset', preset);
            if (targetKb) form.append('target_size_kb', targetKb);

            const resp = await fetch('/api/studio/compress', { method: 'POST', body: form });
            if (!resp.ok) {
              const err = await resp.json().catch(() => ({}));
              throw new Error(err.detail || `Compression failed (${resp.status})`);
            }

            const origSize = parseInt(resp.headers.get('X-Original-Size') || '0', 10);
            const outSize = parseInt(resp.headers.get('X-Output-Size') || '0', 10);
            const pct = resp.headers.get('X-Percent-Saved') || '0';
            const savedStr = formatBytes(origSize - outSize);

            const blob = await resp.blob();
            const newFile = new File([blob], this.currentFile.name, { type: 'application/pdf' });

            if (window.loadDocumentIntoStudio) {
              await window.loadDocumentIntoStudio(newFile);
            }
            window.showToast(`Compressed! Saved ${savedStr} (${pct}% reduction).`, 'success');
          } catch (err) {
            window.showToast(`Compression error: ${err.message}`, 'error');
          }
        };
      }
    }

    // -------------------------------------------------------------------------
    // 2. OCR MODAL & ENGINE
    // -------------------------------------------------------------------------

    openOcrModal(file = null, selectedPages = null) {
      const targetFile = file || (window.PaperplaneEditor && window.PaperplaneEditor.editorState.sourceFile);
      if (!targetFile) {
        window.showToast('Please open a PDF document in Studio first.', 'warning');
        return;
      }
      this.currentFile = targetFile;
      this.selectedOcrPages = selectedPages || [];

      const modal = document.getElementById('ocr-modal');
      if (!modal) return;

      const scopeSelectedBtn = document.getElementById('ocr-scope-selected');
      if (scopeSelectedBtn) {
        if (this.selectedOcrPages.length > 0) {
          scopeSelectedBtn.textContent = `Selected Pages (${this.selectedOcrPages.length})`;
          scopeSelectedBtn.disabled = false;
        } else {
          scopeSelectedBtn.textContent = `Selected Pages (0)`;
          scopeSelectedBtn.disabled = true;
        }
      }

      const progressBox = document.getElementById('ocr-progress-box');
      if (progressBox) progressBox.style.display = 'none';

      modal.hidden = false;
    }

    _bindOcrModal() {
      const modal = document.getElementById('ocr-modal');
      const closeBtn = document.getElementById('modal-close-ocr');
      const cancelBtn = document.getElementById('btn-cancel-ocr');
      const applyBtn = document.getElementById('btn-apply-ocr');

      if (closeBtn) closeBtn.onclick = () => { modal.hidden = true; };
      if (cancelBtn) cancelBtn.onclick = () => { modal.hidden = true; };

      const scopeScanned = document.getElementById('ocr-scope-scanned');
      const scopeAll = document.getElementById('ocr-scope-all');
      const scopeSelected = document.getElementById('ocr-scope-selected');
      let chosenScope = 'scanned_only';

      const setScope = (btn, scopeVal, hint) => {
        [scopeScanned, scopeAll, scopeSelected].forEach(b => b && b.classList.remove('active'));
        if (btn) btn.classList.add('active');
        chosenScope = scopeVal;
        const hintEl = document.getElementById('ocr-scope-hint');
        if (hintEl) hintEl.textContent = hint;
      };

      if (scopeScanned) scopeScanned.onclick = () => setScope(scopeScanned, 'scanned_only', 'Smart hybrid detection: skips pages that already possess clean native text.');
      if (scopeAll) scopeAll.onclick = () => setScope(scopeAll, 'all', 'Forces recognition on every page regardless of existing text.');
      if (scopeSelected) scopeSelected.onclick = () => setScope(scopeSelected, 'selected', `Processes only the ${this.selectedOcrPages.length} currently selected page(s).`);

      if (applyBtn) {
        applyBtn.onclick = async () => {
          if (!this.currentFile) return;

          const lang = document.getElementById('ocr-language-select')?.value || 'eng';
          const dpi = parseInt(document.getElementById('ocr-dpi-select')?.value || '150', 10);

          const progressBox = document.getElementById('ocr-progress-box');
          const progressStatus = document.getElementById('ocr-progress-status');
          const progressPct = document.getElementById('ocr-progress-pct');
          const progressBar = document.getElementById('ocr-progress-bar');

          if (progressBox) progressBox.style.display = 'block';
          if (progressStatus) progressStatus.textContent = `Running OCR engine (${lang.toUpperCase()})...`;
          if (progressPct) progressPct.textContent = '35%';
          if (progressBar) progressBar.style.width = '35%';
          applyBtn.disabled = true;

          try {
            const form = new FormData();
            form.append('file', this.currentFile);
            form.append('language', lang);
            form.append('dpi', dpi);

            if (chosenScope === 'selected' && this.selectedOcrPages.length > 0) {
              form.append('pages', JSON.stringify(this.selectedOcrPages));
              form.append('mode', 'selected');
            } else {
              form.append('pages', 'all');
              form.append('mode', chosenScope);
            }

            if (progressBar) progressBar.style.width = '60%';
            if (progressPct) progressPct.textContent = '60%';

            const resp = await fetch('/api/studio/ocr', { method: 'POST', body: form });
            if (!resp.ok) {
              const err = await resp.json().catch(() => ({}));
              throw new Error(err.detail || `OCR failed (${resp.status})`);
            }

            if (progressBar) progressBar.style.width = '100%';
            if (progressPct) progressPct.textContent = '100%';

            const ocrdCount = resp.headers.get('X-Pages-OCRed') || '0';
            const charsCount = resp.headers.get('X-Extracted-Chars') || '0';
            const elapsed = resp.headers.get('X-Elapsed-Seconds') || '0';

            const blob = await resp.blob();
            const newFile = new File([blob], this.currentFile.name, { type: 'application/pdf' });

            modal.hidden = true;
            if (window.loadDocumentIntoStudio) {
              await window.loadDocumentIntoStudio(newFile);
            }
            window.showToast(`OCR completed in ${elapsed}s! ${ocrdCount} page(s) recognized (${charsCount} characters). Text is now searchable via Ctrl+F.`, 'success');
          } catch (err) {
            window.showToast(`OCR error: ${err.message}`, 'error');
          } finally {
            applyBtn.disabled = false;
            if (progressBar) progressBar.style.width = '0%';
          }
        };
      }
    }

    // -------------------------------------------------------------------------
    // 3. REPAIR MODAL & ENGINE
    // -------------------------------------------------------------------------

    openRepairModal(file = null) {
      const targetFile = file || (window.PaperplaneEditor && window.PaperplaneEditor.editorState.sourceFile);
      if (!targetFile) {
        window.showToast('Please open a PDF document in Studio first.', 'warning');
        return;
      }
      this.currentFile = targetFile;

      const modal = document.getElementById('repair-modal');
      if (!modal) return;

      const repBox = document.getElementById('repair-report-box');
      if (repBox) repBox.style.display = 'none';

      modal.hidden = false;
    }

    _bindRepairModal() {
      const modal = document.getElementById('repair-modal');
      const closeBtn = document.getElementById('modal-close-repair');
      const cancelBtn = document.getElementById('btn-cancel-repair');
      const applyBtn = document.getElementById('btn-apply-repair');

      if (closeBtn) closeBtn.onclick = () => { modal.hidden = true; };
      if (cancelBtn) cancelBtn.onclick = () => { modal.hidden = true; };

      const cards = modal ? modal.querySelectorAll('.split-mode-card') : [];
      cards.forEach(card => {
        card.addEventListener('click', () => {
          cards.forEach(c => c.classList.remove('active'));
          card.classList.add('active');
          const radio = card.querySelector('input[type="radio"]');
          if (radio) radio.checked = true;
          if (radio && radio.value === 'validate_only') {
            applyBtn.textContent = 'Run Health Check →';
          } else {
            applyBtn.textContent = 'Execute Repair →';
          }
        });
      });

      if (applyBtn) {
        applyBtn.onclick = async () => {
          if (!this.currentFile) return;
          const chosenRadio = modal.querySelector('input[name="repair-mode"]:checked');
          const mode = chosenRadio ? chosenRadio.value : 'automatic';

          applyBtn.disabled = true;
          window.showToast(mode === 'validate_only' ? 'Inspecting PDF syntax...' : 'Executing document repair...', 'info');

          try {
            const form = new FormData();
            form.append('file', this.currentFile);
            form.append('mode', mode);

            const resp = await fetch('/api/studio/repair', { method: 'POST', body: form });
            if (!resp.ok) {
              const err = await resp.json().catch(() => ({}));
              throw new Error(err.detail || `Repair failed (${resp.status})`);
            }

            if (mode === 'validate_only') {
              const res = await resp.json();
              const report = res.report;
              const repBox = document.getElementById('repair-report-box');
              const badge = document.getElementById('repair-report-badge');
              const msg = document.getElementById('repair-report-msg');
              const issues = document.getElementById('repair-issues-list');

              if (repBox) repBox.style.display = 'block';
              if (badge) {
                badge.textContent = report.valid ? 'Healthy' : 'Issues Found';
                badge.style.background = report.valid ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)';
                badge.style.color = report.valid ? '#22c55e' : '#ef4444';
              }
              if (msg) msg.textContent = report.message;
              if (issues) {
                issues.innerHTML = (report.detected_issues || []).map(i => `• ${i}`).join('<br>');
              }
              window.showToast(report.valid ? 'Document structure is healthy!' : 'Structural issues detected.', report.valid ? 'success' : 'warning');
            } else {
              const recovered = resp.headers.get('X-Recovered-Pages') || 'all';
              const blob = await resp.blob();
              const newFile = new File([blob], this.currentFile.name, { type: 'application/pdf' });

              modal.hidden = true;
              if (window.loadDocumentIntoStudio) {
                await window.loadDocumentIntoStudio(newFile);
              }
              window.showToast(`Document repaired! ${recovered} page(s) salvaged and restored.`, 'success');
            }
          } catch (err) {
            window.showToast(`Repair error: ${err.message}`, 'error');
          } finally {
            applyBtn.disabled = false;
          }
        };
      }
    }
  }

  // Export Singleton
  window.PaperplaneOptimization = new PaperplaneOptimizationController();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.PaperplaneOptimization.init());
  } else {
    window.PaperplaneOptimization.init();
  }
})();
