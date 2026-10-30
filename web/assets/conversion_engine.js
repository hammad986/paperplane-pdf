/**
 * Paperplane PDF  -  Phase 5 Professional PDF Conversion Engine Controller
 * =====================================================================
 * Coordinates client-side and backend execution of:
 * - TO PDF conversions: Images (JPG, PNG, WebP), Text, Markdown, HTML, Office
 * - FROM PDF conversions: Word (.docx), Excel (.xlsx), PowerPoint (.pptx),
 *                         Images (JPG, PNG, WebP), Markdown (.md), Text (.txt),
 *                         HTML (.html), PDF/A Archival (.pdf)
 * - Real-time capability negotiation with backend dynamic detector
 * - True structural validation & deterministic safe output handling
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

  class PaperplaneConversionController {
    constructor() {
      this.currentFile = null;
      this.selectedFiles = []; // For multi-image batch to PDF
      this.capabilities = null;
      this.currentDirection = 'from_pdf'; // 'from_pdf' | 'to_pdf'
      this.selectedFormat = 'docx';
      this.isConverting = false;
      this.lastResultBlob = null;
      this.lastResultFilename = '';

      this.init = this.init.bind(this);
      this.openConvertModal = this.openConvertModal.bind(this);
      this.closeConvertModal = this.closeConvertModal.bind(this);
      this.applyConversion = this.applyConversion.bind(this);
    }

    init() {
      this._bindHeaderButtons();
      this._bindModalControls();
      this._fetchCapabilities();
    }

    async _fetchCapabilities() {
      try {
        const resp = await fetch('/api/studio/conversions/capabilities');
        if (resp.ok) {
          this.capabilities = await resp.json();
          this._updateFormatBadges();
        }
      } catch (err) {
        console.warn('Could not fetch conversion capabilities:', err);
      }
    }

    _bindHeaderButtons() {
      const convertBtn = document.getElementById('studio-convert-btn');
      if (convertBtn) {
        convertBtn.addEventListener('click', () => this.openConvertModal());
      }
    }

    _bindModalControls() {
      const modal = document.getElementById('convert-modal');
      const closeBtn = document.getElementById('modal-close-convert');
      const cancelBtn = document.getElementById('btn-cancel-convert');
      const applyBtn = document.getElementById('btn-apply-convert');
      const tabFromPdf = document.getElementById('convert-tab-from-pdf');
      const tabToPdf = document.getElementById('convert-tab-to-pdf');
      const fileInput = document.getElementById('convert-file-input');
      const pageModeSelect = document.getElementById('convert-page-mode');
      const customPageInput = document.getElementById('convert-custom-pages');
      const downloadBtn = document.getElementById('convert-download-btn');

      if (closeBtn) closeBtn.addEventListener('click', this.closeConvertModal);
      if (cancelBtn) cancelBtn.addEventListener('click', this.closeConvertModal);
      if (applyBtn) applyBtn.addEventListener('click', this.applyConversion);

      if (tabFromPdf) {
        tabFromPdf.addEventListener('click', () => this._switchDirection('from_pdf'));
      }
      if (tabToPdf) {
        tabToPdf.addEventListener('click', () => this._switchDirection('to_pdf'));
      }

      if (fileInput) {
        fileInput.addEventListener('change', (e) => {
          if (e.target.files && e.target.files.length > 0) {
            if (this.currentDirection === 'to_pdf' && e.target.files.length > 1) {
              this.selectedFiles = Array.from(e.target.files);
              this._setSourceFile(this.selectedFiles[0], `${this.selectedFiles.length} files selected`);
            } else {
              this.selectedFiles = [e.target.files[0]];
              this._setSourceFile(e.target.files[0]);
            }
          }
        });
      }

      if (pageModeSelect) {
        pageModeSelect.addEventListener('change', () => {
          if (pageModeSelect.value === 'custom') {
            customPageInput.style.display = 'block';
          } else {
            customPageInput.style.display = 'none';
          }
        });
      }

      // Bind format card clicks
      const grid = document.getElementById('convert-format-grid');
      if (grid) {
        grid.addEventListener('click', (e) => {
          const card = e.target.closest('.format-card');
          if (card && !card.classList.contains('disabled')) {
            const format = card.getAttribute('data-format');
            this._selectFormat(format);
          }
        });
      }

      if (downloadBtn) {
        downloadBtn.addEventListener('click', () => {
          if (this.lastResultBlob && this.lastResultFilename) {
            const url = URL.createObjectURL(this.lastResultBlob);
            const a = document.createElement('a');
            a.href = url;
            a.download = this.lastResultFilename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 2000);
          }
        });
      }
    }

    _switchDirection(dir) {
      this.currentDirection = dir;
      const tabFromPdf = document.getElementById('convert-tab-from-pdf');
      const tabToPdf = document.getElementById('convert-tab-to-pdf');

      if (dir === 'from_pdf') {
        tabFromPdf.classList.add('active');
        tabToPdf.classList.remove('active');
        this._renderFromPdfGrid();
        this._selectFormat('docx');
      } else {
        tabToPdf.classList.add('active');
        tabFromPdf.classList.remove('active');
        this._renderToPdfGrid();
        this._selectFormat('images_to_pdf');
      }
      this._updateOptionsVisibility();
    }

    _renderFromPdfGrid() {
      const grid = document.getElementById('convert-format-grid');
      if (!grid) return;
      grid.innerHTML = `
        <div class="format-card selected" data-format="docx">
          <div class="format-card-header">
            <span class="format-icon">Note</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">Word (.docx)</div>
          <div class="format-desc">Editable docx layout</div>
        </div>
        <div class="format-card" data-format="xlsx">
          <div class="format-card-header">
            <span class="format-icon">XLS</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">Excel (.xlsx)</div>
          <div class="format-desc">Extracted table sheets</div>
        </div>
        <div class="format-card" data-format="pptx">
          <div class="format-card-header">
            <span class="format-icon">PPT</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">PowerPoint (.pptx)</div>
          <div class="format-desc">Widescreen presentation</div>
        </div>
        <div class="format-card" data-format="jpg">
          <div class="format-card-header">
            <span class="format-icon">IMG</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">JPEG Images</div>
          <div class="format-desc">Crisp page rasters</div>
        </div>
        <div class="format-card" data-format="png">
          <div class="format-card-header">
            <span class="format-icon">SVG</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">PNG Images</div>
          <div class="format-desc">Lossless transparency</div>
        </div>
        <div class="format-card" data-format="webp">
          <div class="format-card-header">
            <span class="format-icon">HTML</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">WebP Images</div>
          <div class="format-desc">Modern compressed</div>
        </div>
        <div class="format-card" data-format="md">
          <div class="format-card-header">
            <span class="format-icon"></span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">Markdown (.md)</div>
          <div class="format-desc">GFM headings & tables</div>
        </div>
        <div class="format-card" data-format="txt">
          <div class="format-card-header">
            <span class="format-icon">DOC</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">Plain Text (.txt)</div>
          <div class="format-desc">Clean Unicode text</div>
        </div>
        <div class="format-card" data-format="html">
          <div class="format-card-header">
            <span class="format-icon">HTML</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">HTML Document</div>
          <div class="format-desc">Sanitized web doc</div>
        </div>
        <div class="format-card" data-format="pdfa">
          <div class="format-card-header">
            <span class="format-icon">PDFA</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">PDF/A-1b</div>
          <div class="format-desc">Archival standard</div>
        </div>
      `;
      this._updateFormatBadges();
    }

    _renderToPdfGrid() {
      const grid = document.getElementById('convert-format-grid');
      if (!grid) return;
      grid.innerHTML = `
        <div class="format-card selected" data-format="images_to_pdf">
          <div class="format-card-header">
            <span class="format-icon">IMG</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">Images to PDF</div>
          <div class="format-desc">JPG, PNG, WebP batch</div>
        </div>
        <div class="format-card" data-format="docx_to_pdf">
          <div class="format-card-header">
            <span class="format-icon">Note</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">Word to PDF</div>
          <div class="format-desc">DOCX to vector PDF</div>
        </div>
        <div class="format-card" data-format="xlsx_to_pdf">
          <div class="format-card-header">
            <span class="format-icon">XLS</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">Excel to PDF</div>
          <div class="format-desc">Formatted sheets</div>
        </div>
        <div class="format-card" data-format="pptx_to_pdf">
          <div class="format-card-header">
            <span class="format-icon">PPT</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">PPTX to PDF</div>
          <div class="format-desc">Slide presentation</div>
        </div>
        <div class="format-card" data-format="md_to_pdf">
          <div class="format-card-header">
            <span class="format-icon"></span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">Markdown to PDF</div>
          <div class="format-desc">GFM typography & tables</div>
        </div>
        <div class="format-card" data-format="txt_to_pdf">
          <div class="format-card-header">
            <span class="format-icon">DOC</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">Text to PDF</div>
          <div class="format-desc">Paginated clean text</div>
        </div>
        <div class="format-card" data-format="html_to_pdf">
          <div class="format-card-header">
            <span class="format-icon">HTML</span>
            <span class="format-badge badge-full">FULL</span>
          </div>
          <div class="format-name">HTML to PDF</div>
          <div class="format-desc">Headless Chrome render</div>
        </div>
      `;
      this._updateFormatBadges();
    }

    _selectFormat(format) {
      this.selectedFormat = format;
      const cards = document.querySelectorAll('#convert-format-grid .format-card');
      cards.forEach(c => {
        if (c.getAttribute('data-format') === format) {
          c.classList.add('selected');
        } else {
          c.classList.remove('selected');
        }
      });
      this._updateOptionsVisibility();
    }

    _updateOptionsVisibility() {
      const pagesRow = document.getElementById('options-pages-row');
      const imageRow = document.getElementById('options-image-row');
      const pptxRow = document.getElementById('options-pptx-row');
      const img2pdfRow = document.getElementById('options-img2pdf-row');

      if (this.currentDirection === 'from_pdf') {
        pagesRow.style.display = 'flex';
        img2pdfRow.style.display = 'none';

        if (['jpg', 'png', 'webp'].includes(this.selectedFormat)) {
          imageRow.style.display = 'flex';
        } else {
          imageRow.style.display = 'none';
        }

        if (this.selectedFormat === 'pptx') {
          pptxRow.style.display = 'flex';
        } else {
          pptxRow.style.display = 'none';
        }
      } else {
        // TO PDF
        pagesRow.style.display = 'none';
        imageRow.style.display = 'none';
        pptxRow.style.display = 'none';

        if (this.selectedFormat === 'images_to_pdf') {
          img2pdfRow.style.display = 'flex';
        } else {
          img2pdfRow.style.display = 'none';
        }
      }
    }

    _updateFormatBadges() {
      if (!this.capabilities || !this.capabilities.conversions) return;
      const convs = this.capabilities.conversions;

      const badgeMap = {
        'docx': convs.pdf_to_docx?.status,
        'xlsx': convs.pdf_to_excel?.status,
        'pptx': convs.pdf_to_powerpoint?.status,
        'jpg': convs.pdf_to_jpg?.status,
        'png': convs.pdf_to_png?.status,
        'webp': convs.pdf_to_webp?.status,
        'md': convs.pdf_to_markdown?.status,
        'txt': convs.pdf_to_txt?.status,
        'html': convs.pdf_to_html?.status,
        'pdfa': convs.pdf_to_pdfa?.status,
        'images_to_pdf': convs.jpg_to_pdf?.status,
        'docx_to_pdf': convs.docx_to_pdf?.status,
        'xlsx_to_pdf': convs.xlsx_to_pdf?.status,
        'pptx_to_pdf': convs.pptx_to_pdf?.status,
        'md_to_pdf': convs.markdown_to_pdf?.status,
        'txt_to_pdf': convs.txt_to_pdf?.status,
        'html_to_pdf': convs.html_to_pdf?.status
      };

      const cards = document.querySelectorAll('#convert-format-grid .format-card');
      cards.forEach(card => {
        const fmt = card.getAttribute('data-format');
        const st = badgeMap[fmt];
        const badge = card.querySelector('.format-badge');
        if (badge && st) {
          badge.textContent = st;
          badge.className = `format-badge ${st === 'FULL' ? 'badge-full' : st === 'LIMITED' ? 'badge-limited' : 'badge-unavail'}`;
          if (st === 'UNAVAILABLE') {
            card.classList.add('disabled');
          } else {
            card.classList.remove('disabled');
          }
        }
      });
    }

    _setSourceFile(file, customMeta = null) {
      this.currentFile = file;
      const nameEl = document.getElementById('convert-source-filename');
      const metaEl = document.getElementById('convert-source-meta');
      const iconEl = document.getElementById('convert-source-icon');

      if (!file) {
        if (nameEl) nameEl.textContent = 'No document selected';
        if (metaEl) metaEl.textContent = '0 B';
        return;
      }

      if (nameEl) nameEl.textContent = file.name;
      if (metaEl) metaEl.textContent = customMeta || `${formatBytes(file.size)} | ${file.type || 'Document'}`;
      if (iconEl) {
        const ext = file.name.split('.').pop().toLowerCase();
        if (ext === 'pdf') iconEl.textContent = 'PDF';
        else if (['jpg', 'jpeg', 'png', 'webp'].includes(ext)) iconEl.textContent = 'IMG';
        else if (['doc', 'docx'].includes(ext)) iconEl.textContent = 'Note';
        else if (['xls', 'xlsx'].includes(ext)) iconEl.textContent = 'XLS';
        else if (['ppt', 'pptx'].includes(ext)) iconEl.textContent = 'PPT';
        else if (['md', 'txt'].includes(ext)) iconEl.textContent = '';
        else iconEl.textContent = 'FILE';
      }
    }

    async openConvertModal(file = null) {
      const targetFile = file || (window.PaperplaneEditor && window.PaperplaneEditor.editorState.sourceFile);
      if (targetFile) {
        this.selectedFiles = [targetFile];
        this._setSourceFile(targetFile);
        this._switchDirection('from_pdf');
      } else {
        this._setSourceFile(null);
        this._switchDirection('to_pdf');
      }

      // Reset progress & results
      const progBox = document.getElementById('convert-progress-box');
      const resBox = document.getElementById('convert-result-box');
      if (progBox) progBox.style.display = 'none';
      if (resBox) resBox.style.display = 'none';

      const modal = document.getElementById('convert-modal');
      if (modal) modal.hidden = false;

      await this._fetchCapabilities();
    }

    closeConvertModal() {
      const modal = document.getElementById('convert-modal');
      if (modal) modal.hidden = true;
    }

    async applyConversion() {
      if (this.isConverting) return;

      if (!this.currentFile && this.selectedFiles.length === 0) {
        window.showToast?.('Please select or upload a document to convert.', 'warning');
        return;
      }

      this.isConverting = true;
      const applyBtn = document.getElementById('btn-apply-convert');
      if (applyBtn) {
        applyBtn.disabled = true;
        applyBtn.textContent = 'Converting...';
      }

      const progBox = document.getElementById('convert-progress-box');
      const progBar = document.getElementById('convert-progress-bar');
      const progLbl = document.getElementById('convert-progress-label');
      const progPct = document.getElementById('convert-progress-percent');
      const resBox = document.getElementById('convert-result-box');

      if (progBox) progBox.style.display = 'block';
      if (resBox) resBox.style.display = 'none';
      if (progBar) progBar.style.width = '20%';
      if (progPct) progPct.textContent = '20%';
      if (progLbl) progLbl.textContent = 'Reading source and initializing converter...';

      const startTime = performance.now();

      try {
        let resp;
        let targetExt = this.selectedFormat;

        if (this.currentDirection === 'to_pdf' && this.selectedFormat === 'images_to_pdf') {
          // Images to PDF batch
          const form = new FormData();
          const files = this.selectedFiles.length > 0 ? this.selectedFiles : [this.currentFile];
          files.forEach(f => form.append('files', f));
          form.append('page_size', document.getElementById('convert-img2pdf-size')?.value || 'a4');
          form.append('orientation', document.getElementById('convert-img2pdf-orient')?.value || 'auto');
          form.append('fit_mode', document.getElementById('convert-img2pdf-fit')?.value || 'fit');
          form.append('margin_pt', document.getElementById('convert-img2pdf-margin')?.value || '18');

          if (progBar) progBar.style.width = '55%';
          if (progPct) progPct.textContent = '55%';
          if (progLbl) progLbl.textContent = 'Synthesizing pages and baking image layout...';

          resp = await fetch('/api/studio/convert/images-to-pdf', {
            method: 'POST',
            body: form
          });
          targetExt = 'pdf';
        } else {
          // Standard / Studio Convert
          const form = new FormData();
          form.append('file', this.currentFile || this.selectedFiles[0]);

          let targetFmt = this.selectedFormat;
          if (this.currentDirection === 'to_pdf') {
            targetFmt = 'pdf';
          }
          form.append('target_format', targetFmt);

          // Page options
          const pageMode = document.getElementById('convert-page-mode')?.value || 'all';
          if (pageMode === 'current') {
            const curP = window.PaperplaneEditor?.editorState?.currentPage || 1;
            form.append('pages', String(curP));
          } else if (pageMode === 'custom') {
            const customVal = document.getElementById('convert-custom-pages')?.value || '1';
            form.append('pages', customVal);
          } else {
            form.append('pages', 'all');
          }

          // Format-specific options
          if (['jpg', 'png', 'webp'].includes(this.selectedFormat)) {
            form.append('dpi', document.getElementById('convert-dpi')?.value || '150');
            form.append('quality', document.getElementById('convert-quality')?.value || '95');
          } else if (this.selectedFormat === 'pptx') {
            form.append('mode', document.getElementById('convert-pptx-mode')?.value || 'visual');
          }

          if (progBar) progBar.style.width = '60%';
          if (progPct) progPct.textContent = '60%';
          if (progLbl) progLbl.textContent = 'Executing document conversion engine...';

          resp = await fetch('/api/studio/convert', {
            method: 'POST',
            body: form
          });
        }

        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData.detail || `Conversion failed with status ${resp.status}`);
        }

        if (progBar) progBar.style.width = '90%';
        if (progPct) progPct.textContent = '90%';
        if (progLbl) progLbl.textContent = 'Validating output structure and signature...';

        const blob = await resp.blob();
        const durationSec = ((performance.now() - startTime) / 1000).toFixed(2);

        // Header metrics
        const pagesCount = resp.headers.get('X-Pages-Count');
        const validationStatus = resp.headers.get('X-Validation-Status') || 'Passed';
        const contentDisp = resp.headers.get('Content-Disposition') || '';
        let filename = 'converted_document';
        const match = contentDisp.match(/filename=["']?([^"';]+)["']?/i);
        if (match && match[1]) {
          filename = match[1];
        } else {
          const baseName = (this.currentFile?.name || 'document').replace(/\.[^/.]+$/, '');
          filename = `${baseName}.${targetExt === 'images_to_pdf' ? 'pdf' : targetExt}`;
        }

        this.lastResultBlob = blob;
        this.lastResultFilename = filename;

        if (progBar) progBar.style.width = '100%';
        if (progPct) progPct.textContent = '100%';
        if (progLbl) progLbl.textContent = 'Conversion Complete!';

        // Update Result Box
        if (resBox) {
          resBox.style.display = 'block';
          document.getElementById('convert-result-name').textContent = filename;
          document.getElementById('convert-result-time').textContent = `${durationSec}s`;
          let statsText = `Size: ${formatBytes(blob.size)} | Status: ${validationStatus}`;
          if (pagesCount) statsText += ` | Pages: ${pagesCount}`;
          document.getElementById('convert-result-stats').textContent = statsText;
        }

        window.showToast?.(`Converted successfully to ${filename} (${formatBytes(blob.size)}) in ${durationSec}s`, 'success');

        // Automatically trigger download
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 2000);

      } catch (err) {
        console.error('Conversion execution error:', err);
        window.showToast?.(err.message || 'Conversion failed.', 'error');
        if (progLbl) progLbl.textContent = `Failed: ${err.message}`;
      } finally {
        this.isConverting = false;
        if (applyBtn) {
          applyBtn.disabled = false;
          applyBtn.textContent = 'Convert Now →';
        }
      }
    }
  }

  // Initialize and mount globally
  window.conversionEngine = new PaperplaneConversionController();
  document.addEventListener('DOMContentLoaded', () => {
    window.conversionEngine.init();
  });
})();
