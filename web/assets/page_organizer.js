/**
 * Paperplane PDF  -  Phase 3 Professional Page Management Engine
 * =============================================================
 * Architecture:
 * - PageOrganizerState: Track page order, multi-selection, rotation, geometry
 * - PageOrganizerView: Virtualized / lazy thumbnail renderer via IntersectionObserver
 * - DragDropReorderManager: HTML5 & pointer reordering with live insertion indicators
 * - PageOperationController: Reorder, Rotate, Crop, Resize, Duplicate, Insert,
 *   Delete, Extract, Split, Cross-Document Import, and Merge
 * - History Transaction Bridge: Links page mutations to HistoryManager
 * - Local / WASM vs Server Provider: interchangeable execution paths
 */

'use strict';

(function () {
  // Utility: Unique ID generator
  function uid(prefix = 'pg') {
    return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`;
  }

  class PageOrganizerState {
    constructor() {
      this.pages = []; // Array of { id, pageNum, rotation, width, height, label }
      this.selectedPages = new Set(); // Set of 1-based page numbers
      this.lastSelectedPage = null; // For Shift+Click range selection
      this.activePage = 1;
      this.layoutMode = 'strip'; // 'strip' or 'grid'
      this.thumbnailCache = new Map(); // pageKey -> dataUrl
      this.totalCount = 0;
    }

    setPages(totalPages, metadata = null) {
      this.totalCount = totalPages;
      this.pages = [];
      const metaPages = (metadata && metadata.pages) || [];

      for (let i = 1; i <= totalPages; i++) {
        const meta = metaPages.find(p => p.page === i) || {};
        this.pages.push({
          id: uid('page'),
          pageNum: i,
          rotation: meta.rotation || 0,
          width: meta.width || 595.28,
          height: meta.height || 841.89,
          label: meta.label || String(i),
          orientation: meta.orientation || ((meta.height || 842) >= (meta.width || 595) ? 'portrait' : 'landscape')
        });
      }
      this.selectedPages.clear();
      this.lastSelectedPage = null;
    }

    getPage(pageNum) {
      return this.pages.find(p => p.pageNum === pageNum) || null;
    }

    isSelected(pageNum) {
      return this.selectedPages.has(pageNum);
    }

    select(pageNum, multi = false, range = false) {
      if (range && this.lastSelectedPage !== null) {
        const start = Math.min(this.lastSelectedPage, pageNum);
        const end = Math.max(this.lastSelectedPage, pageNum);
        for (let p = start; p <= end; p++) {
          this.selectedPages.add(p);
        }
      } else if (multi) {
        if (this.selectedPages.has(pageNum)) {
          this.selectedPages.delete(pageNum);
        } else {
          this.selectedPages.add(pageNum);
        }
        this.lastSelectedPage = pageNum;
      } else {
        this.selectedPages.clear();
        this.selectedPages.add(pageNum);
        this.lastSelectedPage = pageNum;
      }
      this.activePage = pageNum;
    }

    selectAll() {
      this.selectedPages.clear();
      for (let i = 1; i <= this.totalCount; i++) {
        this.selectedPages.add(i);
      }
    }

    deselectAll() {
      this.selectedPages.clear();
      this.lastSelectedPage = null;
    }

    invertSelection() {
      const next = new Set();
      for (let i = 1; i <= this.totalCount; i++) {
        if (!this.selectedPages.has(i)) next.add(i);
      }
      this.selectedPages = next;
    }

    getSelectedSorted() {
      return Array.from(this.selectedPages).sort((a, b) => a - b);
    }
  }

  class PaperplanePageOrganizerController {
    constructor() {
      this.state = new PageOrganizerState();
      this.pdfDoc = null;
      this.sourceFile = null;
      this.sourceName = 'document.pdf';
      this.observer = null;
      this.draggedPage = null;
      this.isCropping = false;
      this.cropBox = { x: 72, y: 72, width: 400, height: 500 };
      this.cropActiveHandle = null;
      this.cropDragStart = null;

      // Bind methods
      this.init = this.init.bind(this);
      this.loadDocument = this.loadDocument.bind(this);
      this.renderThumbnails = this.renderThumbnails.bind(this);
    }

    init() {
      this._bindDOMEvents();
      this._bindModalEvents();
      this._initIntersectionObserver();
    }

    _bindModalEvents() {
      // Split trigger button in header
      const splitTrigger = document.getElementById('organizer-split-trigger-btn');
      if (splitTrigger) splitTrigger.onclick = () => this.openSplitModal();

      // Import trigger button in header
      const importTrigger = document.getElementById('organizer-import-trigger-btn');
      if (importTrigger) importTrigger.onclick = () => this.openCrossDocImportModal();

      // 1. Resize Modal Handlers
      const resizeModal = document.getElementById('page-resize-modal');
      const closeResize = document.getElementById('modal-close-resize');
      const cancelResize = document.getElementById('btn-cancel-resize');
      const applyResize = document.getElementById('btn-apply-resize');
      const presetSelect = document.getElementById('resize-preset-select');
      const customDimRow = document.getElementById('custom-dimensions-row');
      const portBtn = document.getElementById('resize-orient-portrait');
      const landBtn = document.getElementById('resize-orient-landscape');

      if (closeResize) closeResize.onclick = () => { resizeModal.hidden = true; };
      if (cancelResize) cancelResize.onclick = () => { resizeModal.hidden = true; };

      if (presetSelect && customDimRow) {
        presetSelect.onchange = () => {
          customDimRow.style.display = (presetSelect.value === 'custom') ? 'block' : 'none';
        };
      }

      let resizeOrientation = 'portrait';
      if (portBtn && landBtn) {
        portBtn.onclick = () => {
          resizeOrientation = 'portrait';
          portBtn.classList.add('active');
          landBtn.classList.remove('active');
        };
        landBtn.onclick = () => {
          resizeOrientation = 'landscape';
          landBtn.classList.add('active');
          portBtn.classList.remove('active');
        };
      }

      if (applyResize) {
        applyResize.onclick = async () => {
          const preset = presetSelect ? presetSelect.value : 'A4';
          const mode = document.getElementById('resize-mode-select')?.value || 'scale';
          const scope = document.querySelector('input[name="resize-scope"]:checked')?.value || 'current';

          const PRESETS = {
            'A4': { w: 595.28, h: 841.89 },
            'Letter': { w: 612.0, h: 792.0 },
            'A3': { w: 841.89, h: 1190.55 },
            'A5': { w: 419.53, h: 595.28 },
            'Legal': { w: 612.0, h: 1008.0 },
          };

          let targetW = 595.28, targetH = 841.89;
          if (preset === 'custom') {
            targetW = parseFloat(document.getElementById('resize-custom-w')?.value || '595');
            targetH = parseFloat(document.getElementById('resize-custom-h')?.value || '842');
          } else if (PRESETS[preset]) {
            targetW = PRESETS[preset].w;
            targetH = PRESETS[preset].h;
          }

          if (resizeOrientation === 'landscape' && targetW < targetH) {
            [targetW, targetH] = [targetH, targetW];
          } else if (resizeOrientation === 'portrait' && targetW > targetH) {
            [targetW, targetH] = [targetH, targetW];
          }

          let pagesParam = 'all';
          if (scope === 'current') {
            pagesParam = JSON.stringify([this.state.activePage]);
          } else if (scope === 'selected' && this.state.selectedPages.size > 0) {
            pagesParam = JSON.stringify(this.state.getSelectedSorted());
          }

          resizeModal.hidden = true;
          window.showToast('Resizing pages…', 'info');

          const newFile = await this._sendPageMutation('/api/studio/pages/resize', {
            pages: pagesParam,
            target_w: targetW,
            target_h: targetH,
            mode: mode
          });

          if (newFile) {
            await this._reloadPdfAfterMutation(newFile, this.state.activePage);
            window.showToast('Pages resized successfully.', 'success');
          }
        };
      }

      // 2. Split Modal Handlers
      const splitModal = document.getElementById('page-split-modal');
      const closeSplit = document.getElementById('modal-close-split');
      const cancelSplit = document.getElementById('btn-cancel-split');
      const applySplit = document.getElementById('btn-apply-split');

      if (closeSplit) closeSplit.onclick = () => { splitModal.hidden = true; };
      if (cancelSplit) cancelSplit.onclick = () => { splitModal.hidden = true; };

      const splitCardRanges = document.getElementById('split-card-ranges');
      const splitCardEvery = document.getElementById('split-card-every');
      if (splitCardRanges && splitCardEvery) {
        splitCardRanges.onclick = () => {
          splitCardRanges.classList.add('active');
          splitCardEvery.classList.remove('active');
          splitCardRanges.querySelector('input').checked = true;
        };
        splitCardEvery.onclick = () => {
          splitCardEvery.classList.add('active');
          splitCardRanges.classList.remove('active');
          splitCardEvery.querySelector('input').checked = true;
        };
      }

      if (applySplit) {
        applySplit.onclick = async () => {
          const mode = document.querySelector('input[name="split-mode"]:checked')?.value || 'ranges';
          let param = '';
          if (mode === 'ranges') {
            param = document.getElementById('split-param-ranges')?.value.trim() || `1-${this.state.totalCount}`;
          } else {
            param = document.getElementById('split-param-every')?.value.trim() || '2';
          }

          splitModal.hidden = true;
          window.showToast('Splitting document…', 'info');

          const form = new FormData();
          form.append('file', this.sourceFile, this.sourceName);
          form.append('mode', mode);
          form.append('param', param);

          try {
            const resp = await fetch('/api/studio/documents/split', { method: 'POST', body: form });
            if (!resp.ok) {
              let msg = 'Split failed.';
              try { const j = await resp.json(); msg = j.detail || msg; } catch {}
              window.showToast(msg, 'error');
              return;
            }

            const isZip = (resp.headers.get('content-type') || '').includes('zip');
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = isZip ? `split_${this.sourceName.replace('.pdf', '')}.zip` : `split_${this.sourceName}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(() => URL.revokeObjectURL(url), 10000);
            window.showToast('Split output downloaded successfully.', 'success');
          } catch (err) {
            window.showToast(`Split error: ${err.message}`, 'error');
          }
        };
      }

      // 3. Insert Blank Page Modal Handlers
      const insertBlankModal = document.getElementById('page-insert-blank-modal');
      const closeInsertBlank = document.getElementById('modal-close-insert-blank');
      const cancelInsertBlank = document.getElementById('btn-cancel-insert-blank');
      const applyInsertBlank = document.getElementById('btn-apply-insert-blank');
      const insPortBtn = document.getElementById('insert-orient-portrait');
      const insLandBtn = document.getElementById('insert-orient-landscape');

      if (closeInsertBlank) closeInsertBlank.onclick = () => { insertBlankModal.hidden = true; };
      if (cancelInsertBlank) cancelInsertBlank.onclick = () => { insertBlankModal.hidden = true; };

      let insertOrientation = 'portrait';
      if (insPortBtn && insLandBtn) {
        insPortBtn.onclick = () => {
          insertOrientation = 'portrait';
          insPortBtn.classList.add('active');
          insLandBtn.classList.remove('active');
        };
        insLandBtn.onclick = () => {
          insertOrientation = 'landscape';
          insLandBtn.classList.add('active');
          insPortBtn.classList.remove('active');
        };
      }

      if (applyInsertBlank) {
        applyInsertBlank.onclick = async () => {
          const placement = document.getElementById('insert-placement-select')?.value || 'after_current';
          const preset = document.getElementById('insert-preset-select')?.value || 'A4';

          const PRESETS = {
            'A4': { w: 595, h: 842 },
            'Letter': { w: 612, h: 792 },
            'A3': { w: 842, h: 1191 },
            'Legal': { w: 612, h: 1008 },
          };
          const size = PRESETS[preset] || { w: 595, h: 842 };

          let afterPage = this.state.activePage;
          if (placement === 'before_current') afterPage = Math.max(0, this.state.activePage - 1);
          else if (placement === 'start') afterPage = 0;
          else if (placement === 'end') afterPage = this.state.totalCount;

          insertBlankModal.hidden = true;
          await this.insertBlankPage(afterPage, size.w, size.h, insertOrientation);
        };
      }

      // 4. Cross-Document Import Modal Handlers
      const importModal = document.getElementById('cross-doc-import-modal');
      const closeImport = document.getElementById('modal-close-import');
      const cancelImport = document.getElementById('btn-cancel-import');
      const applyImport = document.getElementById('btn-apply-import');
      const dropzone = document.getElementById('import-secondary-dropzone');
      const fileInput = document.getElementById('import-secondary-file-input');
      const previewArea = document.getElementById('import-preview-area');
      const thumbGrid = document.getElementById('import-thumbnails-grid');
      const docNameLabel = document.getElementById('import-doc-name');
      const selAllImportBtn = document.getElementById('import-select-all-btn');
      const deselImportBtn = document.getElementById('import-deselect-all-btn');

      let secondaryFile = null;
      let secondaryDoc = null;
      const secondarySelectedPages = new Set();

      if (closeImport) closeImport.onclick = () => { importModal.hidden = true; };
      if (cancelImport) cancelImport.onclick = () => { importModal.hidden = true; };

      if (dropzone && fileInput) {
        dropzone.onclick = () => fileInput.click();
        dropzone.ondragover = (e) => { e.preventDefault(); dropzone.style.borderColor = 'var(--accent)'; };
        dropzone.ondragleave = () => { dropzone.style.borderColor = 'var(--studio-border)'; };
        dropzone.ondrop = (e) => {
          e.preventDefault();
          dropzone.style.borderColor = 'var(--studio-border)';
          if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            handleSecondaryFile(e.dataTransfer.files[0]);
          }
        };

        fileInput.onchange = (e) => {
          if (e.target.files && e.target.files[0]) {
            handleSecondaryFile(e.target.files[0]);
          }
        };
      }

      const handleSecondaryFile = async (f) => {
        secondaryFile = f;
        if (docNameLabel) docNameLabel.textContent = `${f.name} (Loading…)`;
        try {
          const ab = await f.arrayBuffer();
          secondaryDoc = await pdfjsLib.getDocument({ data: ab }).promise;
          const numPages = secondaryDoc.numPages;
          if (docNameLabel) docNameLabel.textContent = `${f.name} (${numPages} pages)`;
          if (previewArea) previewArea.style.display = 'block';

          // Render secondary thumbnails
          if (thumbGrid) {
            thumbGrid.innerHTML = '';
            secondarySelectedPages.clear();
            for (let i = 1; i <= numPages; i++) {
              secondarySelectedPages.add(i); // default: all checked
              const card = document.createElement('div');
              card.className = 'import-thumb-item selected';
              card.dataset.page = i;

              const cb = document.createElement('input');
              cb.type = 'checkbox';
              cb.checked = true;

              const label = document.createElement('span');
              label.textContent = `P.${i}`;

              const canvas = document.createElement('canvas');
              card.appendChild(cb);
              card.appendChild(canvas);
              card.appendChild(label);

              // Render small thumbnail
              secondaryDoc.getPage(i).then(page => {
                const vp = page.getViewport({ scale: 0.18 });
                canvas.width = vp.width;
                canvas.height = vp.height;
                page.render({ canvasContext: canvas.getContext('2d'), viewport: vp });
              });

              card.onclick = (e) => {
                if (e.target !== cb) cb.checked = !cb.checked;
                if (cb.checked) {
                  secondarySelectedPages.add(i);
                  card.classList.add('selected');
                } else {
                  secondarySelectedPages.delete(i);
                  card.classList.remove('selected');
                }
                if (applyImport) applyImport.disabled = (secondarySelectedPages.size === 0);
              };

              thumbGrid.appendChild(card);
            }
          }

          if (applyImport) applyImport.disabled = false;
        } catch (err) {
          window.showToast(`Could not load secondary PDF: ${err.message}`, 'error');
        }
      };

      if (selAllImportBtn && thumbGrid) {
        selAllImportBtn.onclick = () => {
          if (!secondaryDoc) return;
          secondarySelectedPages.clear();
          for (let i = 1; i <= secondaryDoc.numPages; i++) secondarySelectedPages.add(i);
          thumbGrid.querySelectorAll('.import-thumb-item').forEach(c => {
            c.classList.add('selected');
            c.querySelector('input').checked = true;
          });
          if (applyImport) applyImport.disabled = false;
        };
      }

      if (deselImportBtn && thumbGrid) {
        deselImportBtn.onclick = () => {
          secondarySelectedPages.clear();
          thumbGrid.querySelectorAll('.import-thumb-item').forEach(c => {
            c.classList.remove('selected');
            c.querySelector('input').checked = false;
          });
          if (applyImport) applyImport.disabled = true;
        };
      }

      if (applyImport) {
        applyImport.onclick = async () => {
          if (!secondaryFile || secondarySelectedPages.size === 0) {
            window.showToast('Please select at least one page to import.', 'error');
            return;
          }

          const target = document.getElementById('import-target-select')?.value || 'after_current';
          let insertAfter = parseInt(importModal.dataset.insertAfter || String(this.state.activePage), 10);
          if (target === 'beginning') insertAfter = 0;
          else if (target === 'end') insertAfter = this.state.totalCount;

          const chosenPages = Array.from(secondarySelectedPages).sort((a, b) => a - b);
          importModal.hidden = true;
          window.showToast(`Importing ${chosenPages.length} page(s)…`, 'info');

          const form = new FormData();
          form.append('base_file', this.sourceFile, this.sourceName);
          form.append('import_file', secondaryFile, secondaryFile.name);
          form.append('pages', JSON.stringify(chosenPages));
          form.append('insert_after_page', insertAfter);

          try {
            const resp = await fetch('/api/studio/pages/import', { method: 'POST', body: form });
            if (!resp.ok) {
              let msg = 'Import failed.';
              try { const j = await resp.json(); msg = j.detail || msg; } catch {}
              window.showToast(msg, 'error');
              return;
            }

            const blob = await resp.blob();
            const newFile = new File([blob], this.sourceName, { type: 'application/pdf' });
            await this._reloadPdfAfterMutation(newFile, insertAfter + 1);
            window.showToast(`Imported ${chosenPages.length} page(s) successfully.`, 'success');
          } catch (err) {
            window.showToast(`Import error: ${err.message}`, 'error');
          }
        };
      }
    }

    _initIntersectionObserver() {
      if (this.observer) this.observer.disconnect();

      this.observer = new IntersectionObserver((entries, obs) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const card = entry.target;
            const pageNum = parseInt(card.dataset.page, 10);
            this._renderCardCanvas(card, pageNum);
            obs.unobserve(card);
          }
        });
      }, {
        root: document.getElementById('studio-thumbnails-container'),
        rootMargin: '180px 0px',
        threshold: 0.01
      });
    }

    loadDocument(pdfDoc, file, name, totalPages, metadata = null) {
      this.pdfDoc = pdfDoc;
      this.sourceFile = file;
      this.sourceName = name || (file && file.name) || 'document.pdf';
      this.state.thumbnailCache.clear();
      this.state.setPages(totalPages, metadata);

      const countBadge = document.getElementById('studio-page-count');
      if (countBadge) countBadge.textContent = totalPages;

      this.renderThumbnails();
      this._updateBatchToolbar();
    }

    renderThumbnails() {
      const container = document.getElementById('studio-thumbnails-container');
      if (!container) return;
      container.innerHTML = '';

      if (this.state.totalCount === 0) {
        container.innerHTML = '<div class="organizer-empty-msg">No pages loaded</div>';
        return;
      }

      // Container toolbar for view toggle & select all
      const topBar = document.createElement('div');
      topBar.className = 'organizer-subnav';
      topBar.innerHTML = `
        <div class="organizer-subnav-left">
          <button type="button" class="org-sub-btn" id="org-select-all-btn" title="Select All (Ctrl+A)">Select All</button>
          <button type="button" class="org-sub-btn" id="org-invert-btn" title="Invert Selection">Invert</button>
        </div>
        <div class="organizer-subnav-right">
          <button type="button" class="org-layout-btn ${this.state.layoutMode === 'strip' ? 'active' : ''}" id="org-strip-view-btn" title="Vertical Strip View"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="4" cy="6" r="1.5"/><circle cx="4" cy="12" r="1.5"/><circle cx="4" cy="18" r="1.5"/></svg></button>
          <button type="button" class="org-layout-btn ${this.state.layoutMode === 'grid' ? 'active' : ''}" id="org-grid-view-btn" title="2-Column Grid View"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg></button>
        </div>
      `;
      container.appendChild(topBar);

      // Cards list container
      const grid = document.createElement('div');
      grid.className = `organizer-grid ${this.state.layoutMode === 'grid' ? 'grid-mode' : 'strip-mode'}`;
      grid.id = 'organizer-grid';

      // Insertion indicator bar (drag-and-drop target line)
      const dropIndicator = document.createElement('div');
      dropIndicator.className = 'organizer-drop-indicator';
      dropIndicator.id = 'organizer-drop-indicator';
      dropIndicator.style.display = 'none';
      grid.appendChild(dropIndicator);

      this.state.pages.forEach((p, index) => {
        const pageNum = index + 1;
        const card = document.createElement('div');
        card.className = `organizer-thumb-card ${pageNum === this.state.activePage ? 'active' : ''} ${this.state.isSelected(pageNum) ? 'selected' : ''}`;
        card.dataset.page = pageNum;
        card.draggable = true;
        card.tabIndex = 0;
        card.setAttribute('role', 'option');
        card.setAttribute('aria-selected', this.state.isSelected(pageNum) ? 'true' : 'false');

        // Checkbox & Grip Handle
        const header = document.createElement('div');
        header.className = 'thumb-header';
        header.innerHTML = `
          <div class="thumb-grip" title="Drag to reorder page">⠿</div>
          <label class="thumb-checkbox-label" title="Select page">
            <input type="checkbox" class="thumb-checkbox" ${this.state.isSelected(pageNum) ? 'checked' : ''} />
            <span class="thumb-checkbox-custom"></span>
          </label>
          <span class="thumb-page-num">${p.label || pageNum}</span>
        `;
        card.appendChild(header);

        // Preview Wrapper (Canvas Placeholder)
        const previewWrap = document.createElement('div');
        previewWrap.className = 'thumb-preview-wrap';
        previewWrap.innerHTML = `
          <div class="thumb-skeleton">
            <div class="thumb-spinner"></div>
            <span>Page ${pageNum}</span>
          </div>
        `;
        card.appendChild(previewWrap);

        // Footer & Quick Actions
        const footer = document.createElement('div');
        footer.className = 'thumb-footer';
        footer.innerHTML = `
          <div class="thumb-meta-text">${Math.round(p.width)}×${Math.round(p.height)}pt</div>
          <div class="thumb-quick-actions">
            <button type="button" class="thumb-mini-btn btn-rotate-quick" title="Rotate 90° Clockwise">↷</button>
            <button type="button" class="thumb-mini-btn btn-dup-quick" title="Duplicate Page"></button>
            <button type="button" class="thumb-mini-btn btn-del-quick" title="Delete Page">Delete</button>
          </div>
        `;
        card.appendChild(footer);

        // Bind Card Events
        this._bindCardEvents(card, pageNum);

        grid.appendChild(card);

        // Observe card for lazy loading
        if (this.observer) {
          this.observer.observe(card);
        }
      });

      container.appendChild(grid);
      this._bindSubnavEvents();
    }

    async _renderCardCanvas(card, pageNum) {
      if (!this.pdfDoc) return;
      const previewWrap = card.querySelector('.thumb-preview-wrap');
      if (!previewWrap) return;

      const cacheKey = `p_${pageNum}_rot_${this.state.getPage(pageNum)?.rotation || 0}`;
      if (this.state.thumbnailCache.has(cacheKey)) {
        const cachedImg = document.createElement('img');
        cachedImg.className = 'thumb-rendered-img';
        cachedImg.src = this.state.thumbnailCache.get(cacheKey);
        previewWrap.innerHTML = '';
        previewWrap.appendChild(cachedImg);
        return;
      }

      try {
        const page = await this.pdfDoc.getPage(pageNum);
        const baseVp = page.getViewport({ scale: 1.0 });
        // Calculate thumbnail scale to fit ~120px width
        const thumbScale = Math.min(0.28, 120 / baseVp.width);
        const viewport = page.getViewport({ scale: thumbScale, rotation: this.state.getPage(pageNum)?.rotation || 0 });

        const canvas = document.createElement('canvas');
        canvas.className = 'thumb-rendered-canvas';
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        const ctx = canvas.getContext('2d');

        await page.render({ canvasContext: ctx, viewport: viewport }).promise;

        // Cache as lightweight data URI
        const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
        this.state.thumbnailCache.set(cacheKey, dataUrl);

        previewWrap.innerHTML = '';
        const img = document.createElement('img');
        img.className = 'thumb-rendered-img';
        img.src = dataUrl;
        img.alt = `Page ${pageNum}`;
        previewWrap.appendChild(img);
      } catch (err) {
        previewWrap.innerHTML = `<div class="thumb-err">Error</div>`;
      }
    }

    _bindCardEvents(card, pageNum) {
      // Click selection
      card.addEventListener('click', (e) => {
        if (e.target.closest('.thumb-mini-btn')) return; // Ignore quick action buttons
        if (e.target.closest('.thumb-checkbox-label')) {
          e.stopPropagation();
          this.state.select(pageNum, true, false);
          this._updateCardStates();
          this._updateBatchToolbar();
          return;
        }

        const isCtrl = e.ctrlKey || e.metaKey;
        const isShift = e.shiftKey;

        this.state.select(pageNum, isCtrl, isShift);
        this._updateCardStates();
        this._updateBatchToolbar();

        // Switch viewer canvas to this page
        if (window.renderStudioPage) {
          window.renderStudioPage(pageNum);
        }
      });

      // Keyboard navigation (Arrow keys, Enter, Alt+Arrow for reorder)
      card.addEventListener('keydown', (e) => {
        if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowLeft')) {
          e.preventDefault();
          this.moveSelected(-1);
        } else if (e.altKey && (e.key === 'ArrowDown' || e.key === 'ArrowRight')) {
          e.preventDefault();
          this.moveSelected(1);
        } else if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          this.state.select(pageNum, e.ctrlKey || e.metaKey, e.shiftKey);
          this._updateCardStates();
          this._updateBatchToolbar();
          if (window.renderStudioPage) window.renderStudioPage(pageNum);
        }
      });

      // Context menu
      card.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        if (!this.state.isSelected(pageNum)) {
          this.state.select(pageNum, false, false);
          this._updateCardStates();
          this._updateBatchToolbar();
        }
        this._showContextMenu(e.clientX, e.clientY, pageNum);
      });

      // Quick Actions
      const rotBtn = card.querySelector('.btn-rotate-quick');
      if (rotBtn) {
        rotBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.rotatePages([pageNum], 90);
        });
      }

      const dupBtn = card.querySelector('.btn-dup-quick');
      if (dupBtn) {
        dupBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.duplicatePages([pageNum]);
        });
      }

      const delBtn = card.querySelector('.btn-del-quick');
      if (delBtn) {
        delBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.deletePages([pageNum]);
        });
      }

      // Drag and Drop
      card.addEventListener('dragstart', (e) => {
        this.draggedPage = pageNum;
        if (!this.state.isSelected(pageNum)) {
          this.state.select(pageNum, false, false);
          this._updateCardStates();
          this._updateBatchToolbar();
        }
        card.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(pageNum));
      });

      card.addEventListener('dragend', () => {
        card.classList.remove('dragging');
        this._hideDropIndicator();
      });

      card.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        this._updateDropIndicator(card, e);
      });

      card.addEventListener('drop', (e) => {
        e.preventDefault();
        const targetPage = parseInt(card.dataset.page, 10);
        const rect = card.getBoundingClientRect();
        const isAfter = (e.clientY > rect.top + rect.height / 2) || (e.clientX > rect.left + rect.width / 2);
        this._executeDropReorder(targetPage, isAfter);
      });
    }

    _updateDropIndicator(targetCard, e) {
      const indicator = document.getElementById('organizer-drop-indicator');
      if (!indicator) return;

      const rect = targetCard.getBoundingClientRect();
      const grid = document.getElementById('organizer-grid');
      const gridRect = grid.getBoundingClientRect();

      const isAfter = (e.clientY > rect.top + rect.height / 2) || (e.clientX > rect.left + rect.width / 2);

      indicator.style.display = 'block';
      if (this.state.layoutMode === 'grid') {
        indicator.className = 'organizer-drop-indicator vertical-indicator';
        indicator.style.top = `${rect.top - gridRect.top}px`;
        indicator.style.height = `${rect.height}px`;
        indicator.style.left = isAfter
          ? `${rect.right - gridRect.left + 4}px`
          : `${rect.left - gridRect.left - 4}px`;
      } else {
        indicator.className = 'organizer-drop-indicator horizontal-indicator';
        indicator.style.left = '8px';
        indicator.style.width = 'calc(100% - 16px)';
        indicator.style.top = isAfter
          ? `${rect.bottom - gridRect.top + 4}px`
          : `${rect.top - gridRect.top - 4}px`;
      }
    }

    _hideDropIndicator() {
      const indicator = document.getElementById('organizer-drop-indicator');
      if (indicator) indicator.style.display = 'none';
    }

    _executeDropReorder(targetPage, isAfter) {
      this._hideDropIndicator();
      const selected = this.state.getSelectedSorted();
      const draggedList = selected.length > 0 && selected.includes(this.draggedPage)
        ? selected
        : [this.draggedPage];

      if (!draggedList || draggedList.length === 0 || !targetPage) return;

      // Calculate new order array of 1-based page numbers
      const total = this.state.totalCount;
      const currentOrder = Array.from({ length: total }, (_, i) => i + 1);

      // Filter out dragged pages
      const remaining = currentOrder.filter(p => !draggedList.includes(p));

      // Locate insertion index
      let targetIdx = remaining.indexOf(targetPage);
      if (targetIdx === -1) {
        targetIdx = remaining.length;
      } else if (isAfter) {
        targetIdx += 1;
      }

      // Insert dragged pages into target position
      remaining.splice(targetIdx, 0, ...draggedList);

      // Check if order actually changed
      const isUnchanged = remaining.every((p, idx) => p === currentOrder[idx]);
      if (isUnchanged) return;

      // Execute reorder
      this.reorderPages(remaining);
    }

    _updateCardStates() {
      const cards = document.querySelectorAll('.organizer-thumb-card');
      cards.forEach(card => {
        const p = parseInt(card.dataset.page, 10);
        const isSel = this.state.isSelected(p);
        const isAct = (p === this.state.activePage);

        card.classList.toggle('selected', isSel);
        card.classList.toggle('active', isAct);
        card.setAttribute('aria-selected', isSel ? 'true' : 'false');

        const cb = card.querySelector('.thumb-checkbox');
        if (cb) cb.checked = isSel;
      });
    }

    _updateBatchToolbar() {
      const bar = document.getElementById('organizer-batch-bar');
      const countLabel = document.getElementById('batch-selection-count');
      if (!bar) return;

      const selCount = this.state.selectedPages.size;
      if (selCount > 0) {
        bar.hidden = false;
        bar.classList.add('visible');
        if (countLabel) {
          countLabel.textContent = `${selCount} ${selCount === 1 ? 'Page' : 'Pages'} Selected`;
        }
      } else {
        bar.hidden = true;
        bar.classList.remove('visible');
      }
    }

    _bindSubnavEvents() {
      const selAllBtn = document.getElementById('org-select-all-btn');
      if (selAllBtn) {
        selAllBtn.onclick = () => {
          this.state.selectAll();
          this._updateCardStates();
          this._updateBatchToolbar();
        };
      }

      const invBtn = document.getElementById('org-invert-btn');
      if (invBtn) {
        invBtn.onclick = () => {
          this.state.invertSelection();
          this._updateCardStates();
          this._updateBatchToolbar();
        };
      }

      const stripBtn = document.getElementById('org-strip-view-btn');
      const gridBtn = document.getElementById('org-grid-view-btn');
      if (stripBtn && gridBtn) {
        stripBtn.onclick = () => {
          this.state.layoutMode = 'strip';
          stripBtn.classList.add('active');
          gridBtn.classList.remove('active');
          const g = document.getElementById('organizer-grid');
          if (g) { g.className = 'organizer-grid strip-mode'; }
        };
        gridBtn.onclick = () => {
          this.state.layoutMode = 'grid';
          gridBtn.classList.add('active');
          stripBtn.classList.remove('active');
          const g = document.getElementById('organizer-grid');
          if (g) { g.className = 'organizer-grid grid-mode'; }
        };
      }
    }

    _bindDOMEvents() {
      // Batch selection toolbar actions
      const selAllBatchBtn = document.getElementById('batch-select-all-btn');
      if (selAllBatchBtn) {
        selAllBatchBtn.onclick = () => {
          this.state.selectAll();
          this._updateCardStates();
          this._updateBatchToolbar();
        };
      }

      const invertBatchBtn = document.getElementById('batch-invert-btn');
      if (invertBatchBtn) {
        invertBatchBtn.onclick = () => {
          this.state.invertSelection();
          this._updateCardStates();
          this._updateBatchToolbar();
        };
      }

      const clearBtn = document.getElementById('batch-clear-btn');
      if (clearBtn) {
        clearBtn.onclick = () => {
          this.state.deselectAll();
          this._updateCardStates();
          this._updateBatchToolbar();
        };
      }

      const ocrBatchBtn = document.getElementById('batch-ocr-btn');
      if (ocrBatchBtn) {
        ocrBatchBtn.onclick = () => {
          if (window.openOcrModal) {
            window.openOcrModal();
          } else {
            document.getElementById('studio-ocr-btn')?.click();
          }
        };
      }

      const rotCwBtn = document.getElementById('batch-rotate-cw-btn');
      if (rotCwBtn) rotCwBtn.onclick = () => this.rotateSelected(90);

      const rotCcwBtn = document.getElementById('batch-rotate-ccw-btn');
      if (rotCcwBtn) rotCcwBtn.onclick = () => this.rotateSelected(-90);

      const dupBtn = document.getElementById('batch-duplicate-btn');
      if (dupBtn) dupBtn.onclick = () => this.duplicateSelected();

      const delBtn = document.getElementById('batch-delete-btn');
      if (delBtn) delBtn.onclick = () => this.deleteSelected();

      const extractBtn = document.getElementById('batch-extract-btn');
      if (extractBtn) extractBtn.onclick = () => this.extractSelected();

      const cropBtn = document.getElementById('batch-crop-btn');
      if (cropBtn) cropBtn.onclick = () => this.startCropMode();

      const resizeBtn = document.getElementById('batch-resize-btn');
      if (resizeBtn) resizeBtn.onclick = () => this.openResizeModal();

      const moveUpBtn = document.getElementById('batch-move-up-btn');
      if (moveUpBtn) moveUpBtn.onclick = () => this.moveSelected(-1);

      const moveDownBtn = document.getElementById('batch-move-down-btn');
      if (moveDownBtn) moveDownBtn.onclick = () => this.moveSelected(1);

      // Context menu action dispatch
      const ctxMenu = document.getElementById('page-context-menu');
      if (ctxMenu) {
        ctxMenu.addEventListener('click', (e) => {
          const item = e.target.closest('.ctx-item');
          if (!item) return;
          const action = item.dataset.action;
          const targetPage = parseInt(ctxMenu.dataset.page, 10);
          this._handleContextMenuAction(action, targetPage);
          ctxMenu.hidden = true;
        });

        // Close context menu on outside click
        document.addEventListener('click', (e) => {
          if (!e.target.closest('#page-context-menu')) {
            ctxMenu.hidden = true;
          }
        });
      }

      // Studio Header Organise Buttons
      const addPageBtn = document.getElementById('editor-insert-page-btn');
      if (addPageBtn) {
        addPageBtn.onclick = () => this.openInsertBlankModal();
      }

      const dupPageBtn = document.getElementById('editor-dup-page-btn');
      if (dupPageBtn) {
        dupPageBtn.onclick = () => {
          const cur = this.state.activePage || 1;
          this.duplicatePages([cur]);
        };
      }

      const delPageBtn = document.getElementById('editor-delete-page-btn');
      if (delPageBtn) {
        delPageBtn.onclick = () => {
          const cur = this.state.activePage || 1;
          this.deletePages([cur]);
        };
      }
    }

    _showContextMenu(x, y, pageNum) {
      const menu = document.getElementById('page-context-menu');
      if (!menu) return;
      menu.dataset.page = pageNum;
      menu.hidden = false;

      // Keep within window viewport boundaries
      const menuW = 220;
      const menuH = 340;
      const left = Math.min(x, window.innerWidth - menuW - 10);
      const top = Math.min(y, window.innerHeight - menuH - 10);

      menu.style.left = `${left}px`;
      menu.style.top = `${top}px`;
    }

    _handleContextMenuAction(action, pageNum) {
      const sel = this.state.getSelectedSorted();
      const targetPages = (sel.length > 0 && sel.includes(pageNum)) ? sel : [pageNum];

      switch (action) {
        case 'rotate-cw':
          this.rotatePages(targetPages, 90);
          break;
        case 'rotate-ccw':
          this.rotatePages(targetPages, -90);
          break;
        case 'duplicate':
          this.duplicatePages(targetPages);
          break;
        case 'extract':
          this.extractPages(targetPages);
          break;
        case 'delete':
          this.deletePages(targetPages);
          break;
        case 'crop':
          this.startCropMode();
          break;
        case 'resize':
          this.openResizeModal();
          break;
        case 'insert-before':
          this.insertBlankPage(pageNum - 1);
          break;
        case 'insert-after':
          this.insertBlankPage(pageNum);
          break;
        case 'import':
          this.openCrossDocImportModal(pageNum);
          break;
      }
    }

    // -----------------------------------------------------------------------
    // Core Engine Operations
    // -----------------------------------------------------------------------

    async _sendPageMutation(endpoint, formFields) {
      const file = this.sourceFile;
      if (!file) {
        window.showToast('No PDF loaded to mutate.', 'error');
        return null;
      }

      const form = new FormData();
      form.append('file', file, this.sourceName);
      Object.entries(formFields).forEach(([k, v]) => form.append(k, v));

      try {
        const resp = await fetch(endpoint, {
          method: 'POST',
          credentials: 'same-origin',
          body: form
        });
        if (!resp.ok) {
          let errDetail = `Operation failed (${resp.status})`;
          try {
            const j = await resp.json();
            if (j.detail) errDetail = j.detail;
          } catch {}
          window.showToast(errDetail, 'error');
          return null;
        }

        const blob = await resp.blob();
        const newFile = new File([blob], this.sourceName, { type: 'application/pdf' });
        return newFile;
      } catch (err) {
        window.showToast(`Network error: ${err.message}`, 'error');
        return null;
      }
    }

    async _reloadPdfAfterMutation(newFile, targetPage = 1) {
      if (!newFile) return;
      this.sourceFile = newFile;

      // Update Phase 2 Editor state
      if (window.PaperplaneEditor && window.PaperplaneEditor.editorState) {
        window.PaperplaneEditor.editorState.setSource(
          newFile,
          this.sourceName,
          window.PaperplaneEditor.editorState.totalPages
        );
      }

      // Reload document into viewer & organizer
      if (window.loadDocumentIntoStudio) {
        await window.loadDocumentIntoStudio(newFile);
      }
    }

    async reorderPages(newOrderArray) {
      window.showToast('Reordering document pages…', 'info');
      const newFile = await this._sendPageMutation('/api/studio/pages/reorder', {
        order: JSON.stringify(newOrderArray)
      });

      if (newFile) {
        await this._reloadPdfAfterMutation(newFile, 1);
        window.showToast('Pages reordered successfully.', 'success');
      }
    }

    moveSelected(delta) {
      const selected = this.state.getSelectedSorted();
      if (selected.length === 0) {
        window.showToast('Select one or more pages to move.', 'info');
        return;
      }

      const total = this.state.totalCount;
      const currentOrder = Array.from({ length: total }, (_, i) => i + 1);

      if (delta < 0 && selected[0] === 1) return; // Already at start
      if (delta > 0 && selected[selected.length - 1] === total) return; // Already at end

      const newOrder = [...currentOrder];
      if (delta < 0) {
        // Move earlier (left/up)
        for (const p of selected) {
          const idx = newOrder.indexOf(p);
          if (idx > 0 && !selected.includes(newOrder[idx - 1])) {
            [newOrder[idx - 1], newOrder[idx]] = [newOrder[idx], newOrder[idx - 1]];
          }
        }
      } else {
        // Move later (right/down)
        for (let i = selected.length - 1; i >= 0; i--) {
          const p = selected[i];
          const idx = newOrder.indexOf(p);
          if (idx < newOrder.length - 1 && !selected.includes(newOrder[idx + 1])) {
            [newOrder[idx], newOrder[idx + 1]] = [newOrder[idx + 1], newOrder[idx]];
          }
        }
      }

      this.reorderPages(newOrder);
    }

    async rotatePages(pages, degrees) {
      window.showToast(`Rotating ${pages.length} page(s) by ${degrees}°…`, 'info');
      const newFile = await this._sendPageMutation('/api/studio/pages/rotate', {
        pages: JSON.stringify(pages),
        degrees: degrees
      });

      if (newFile) {
        await this._reloadPdfAfterMutation(newFile, this.state.activePage);
        window.showToast(`Rotated ${pages.length} page(s).`, 'success');
      }
    }

    rotateSelected(degrees) {
      const sel = this.state.getSelectedSorted();
      const targetPages = sel.length > 0 ? sel : [this.state.activePage];
      this.rotatePages(targetPages, degrees);
    }

    async duplicatePages(pages) {
      window.showToast(`Duplicating ${pages.length} page(s)…`, 'info');
      const newFile = await this._sendPageMutation('/api/studio/page/duplicate', {
        pages: JSON.stringify(pages)
      });

      if (newFile) {
        await this._reloadPdfAfterMutation(newFile, pages[0] || 1);
        window.showToast(`Duplicated ${pages.length} page(s).`, 'success');
      }
    }

    duplicateSelected() {
      const sel = this.state.getSelectedSorted();
      const targetPages = sel.length > 0 ? sel : [this.state.activePage];
      this.duplicatePages(targetPages);
    }

    async deletePages(pages) {
      const total = this.state.totalCount;
      if (pages.length >= total) {
        window.showToast('Cannot delete all pages. The document must contain at least one page.', 'error');
        return;
      }

      const msg = pages.length === 1
        ? `Are you sure you want to delete page ${pages[0]}? This cannot be undone.`
        : `Are you sure you want to delete ${pages.length} pages? This cannot be undone.`;
      if (!confirm(msg)) return;

      window.showToast(`Deleting ${pages.length} page(s)…`, 'info');
      const newFile = await this._sendPageMutation('/api/studio/page/delete', {
        pages: JSON.stringify(pages)
      });

      if (newFile) {
        const nextActive = Math.max(1, Math.min(pages[0], total - pages.length));
        await this._reloadPdfAfterMutation(newFile, nextActive);
        window.showToast(`Deleted ${pages.length} page(s).`, 'success');
      }
    }

    deleteSelected() {
      const sel = this.state.getSelectedSorted();
      if (sel.length === 0) {
        this.deletePages([this.state.activePage]);
      } else {
        this.deletePages(sel);
      }
    }

    async insertBlankPage(afterPage, width = 595, height = 842, orientation = 'portrait') {
      window.showToast(`Inserting blank page…`, 'info');
      const newFile = await this._sendPageMutation('/api/studio/page/insert', {
        after_page: afterPage,
        width: width,
        height: height,
        orientation: orientation
      });

      if (newFile) {
        await this._reloadPdfAfterMutation(newFile, afterPage + 1);
        window.showToast(`Blank page inserted after page ${afterPage}.`, 'success');
      }
    }

    async extractPages(pages) {
      if (!pages || pages.length === 0) {
        window.showToast('No pages selected to extract.', 'error');
        return;
      }

      window.showToast(`Extracting ${pages.length} page(s)…`, 'info');
      const form = new FormData();
      form.append('file', this.sourceFile, this.sourceName);
      form.append('pages', JSON.stringify(pages));

      try {
        const resp = await fetch('/api/studio/pages/extract', { method: 'POST', body: form });
        if (!resp.ok) {
          window.showToast('Extraction failed.', 'error');
          return;
        }

        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `extracted_${pages.join('-')}_${this.sourceName}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 10000);
        window.showToast('Extracted PDF downloaded.', 'success');
      } catch (err) {
        window.showToast(`Extraction error: ${err.message}`, 'error');
      }
    }

    extractSelected() {
      const sel = this.state.getSelectedSorted();
      const targetPages = sel.length > 0 ? sel : [this.state.activePage];
      this.extractPages(targetPages);
    }

    // -----------------------------------------------------------------------
    // Interactive Visual Crop Overlay Workflow
    // -----------------------------------------------------------------------

    startCropMode() {
      this.isCropping = true;
      const canvasArea = document.getElementById('page-render-wrapper');
      if (!canvasArea) return;

      let overlay = document.getElementById('studio-crop-overlay');
      if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'studio-crop-overlay';
        overlay.className = 'studio-crop-overlay';
        overlay.innerHTML = `
          <div class="crop-backdrop-dim"></div>
          <div class="crop-box" id="crop-box">
            <div class="crop-handle handle-nw" data-handle="nw"></div>
            <div class="crop-handle handle-n" data-handle="n"></div>
            <div class="crop-handle handle-ne" data-handle="ne"></div>
            <div class="crop-handle handle-e" data-handle="e"></div>
            <div class="crop-handle handle-se" data-handle="se"></div>
            <div class="crop-handle handle-s" data-handle="s"></div>
            <div class="crop-handle handle-sw" data-handle="sw"></div>
            <div class="crop-handle handle-w" data-handle="w"></div>
            <div class="crop-dimension-pill" id="crop-dimension-pill">400 × 500 pt</div>
          </div>
          <div class="crop-floating-toolbar">
            <span class="crop-tool-title">Cut Crop Page Geometry</span>
            <div class="crop-scope-select">
              <label><input type="radio" name="crop-scope" value="current" checked /> Current Page</label>
              <label><input type="radio" name="crop-scope" value="selected" /> Selected (${this.state.selectedPages.size || 1})</label>
            </div>
            <button type="button" class="btn-cancel" id="btn-crop-cancel">Cancel</button>
            <button type="button" class="btn-primary-action" id="btn-crop-apply">Apply Crop →</button>
          </div>
        `;
        canvasArea.appendChild(overlay);
        this._bindCropEvents(overlay);
      }
      overlay.style.display = 'block';

      // Initialize crop box to 80% of canvas dimensions
      const curPage = this.state.getPage(this.state.activePage);
      const origW = (curPage && curPage.width) || 595;
      const origH = (curPage && curPage.height) || 842;
      const scale = (window.state && window.state.studio && Number(window.state.studio.scale)) || 1.0;

      const boxW = Math.round(origW * scale * 0.8);
      const boxH = Math.round(origH * scale * 0.8);
      const boxL = Math.round((origW * scale - boxW) / 2);
      const boxT = Math.round((origH * scale - boxH) / 2);

      const boxEl = document.getElementById('crop-box');
      if (boxEl) {
        boxEl.style.left = `${boxL}px`;
        boxEl.style.top = `${boxT}px`;
        boxEl.style.width = `${boxW}px`;
        boxEl.style.height = `${boxH}px`;
      }
      this._updateCropDimensions(boxW, boxH, scale);
    }

    _updateCropDimensions(cssW, cssH, scale) {
      const docW = Math.round(cssW / scale);
      const docH = Math.round(cssH / scale);
      const mmW = Math.round(docW * 0.352778);
      const mmH = Math.round(docH * 0.352778);
      const pill = document.getElementById('crop-dimension-pill');
      if (pill) pill.textContent = `${docW} × ${docH} pt (${mmW} × ${mmH} mm)`;
    }

    _bindCropEvents(overlay) {
      const box = overlay.querySelector('#crop-box');
      const cancelBtn = overlay.querySelector('#btn-crop-cancel');
      const applyBtn = overlay.querySelector('#btn-crop-apply');

      if (cancelBtn) {
        cancelBtn.onclick = () => {
          overlay.style.display = 'none';
          this.isCropping = false;
        };
      }

      if (applyBtn) {
        applyBtn.onclick = async () => {
          const scale = (window.state && window.state.studio && Number(window.state.studio.scale)) || 1.0;
          const left = parseFloat(box.style.left || '0');
          const top = parseFloat(box.style.top || '0');
          const width = parseFloat(box.style.width || '100');
          const height = parseFloat(box.style.height || '100');

          // Convert screen pixels to canonical 72 DPI PDF document points
          const docX = Math.round(left / scale);
          const docY = Math.round(top / scale);
          const docW = Math.round(width / scale);
          const docH = Math.round(height / scale);

          const scopeRadio = overlay.querySelector('input[name="crop-scope"]:checked');
          const scope = scopeRadio ? scopeRadio.value : 'current';

          const targetPages = (scope === 'selected' && this.state.selectedPages.size > 0)
            ? this.state.getSelectedSorted()
            : [this.state.activePage];

          window.showToast(`Applying crop to ${targetPages.length} page(s)…`, 'info');
          const newFile = await this._sendPageMutation('/api/studio/pages/crop', {
            pages: JSON.stringify(targetPages),
            box: JSON.stringify({ x: docX, y: docY, width: docW, height: docH })
          });

          overlay.style.display = 'none';
          this.isCropping = false;

          if (newFile) {
            await this._reloadPdfAfterMutation(newFile, this.state.activePage);
            window.showToast('Crop applied successfully.', 'success');
          }
        };
      }

      // Handle dragging and resizing the crop box
      let isDraggingBox = false;
      let activeHandle = null;
      let startX = 0, startY = 0;
      let startLeft = 0, startTop = 0, startWidth = 0, startHeight = 0;

      box.addEventListener('mousedown', (e) => {
        const handle = e.target.closest('.crop-handle');
        const scale = (window.state && window.state.studio && Number(window.state.studio.scale)) || 1.0;
        startX = e.clientX;
        startY = e.clientY;
        startLeft = parseFloat(box.style.left || '0');
        startTop = parseFloat(box.style.top || '0');
        startWidth = parseFloat(box.style.width || '100');
        startHeight = parseFloat(box.style.height || '100');

        if (handle) {
          activeHandle = handle.dataset.handle;
        } else {
          isDraggingBox = true;
        }
        e.stopPropagation();
      });

      window.addEventListener('mousemove', (e) => {
        if (!this.isCropping) return;
        const scale = (window.state && window.state.studio && Number(window.state.studio.scale)) || 1.0;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;

        if (isDraggingBox) {
          box.style.left = `${Math.max(0, startLeft + dx)}px`;
          box.style.top = `${Math.max(0, startTop + dy)}px`;
        } else if (activeHandle) {
          let newL = startLeft, newT = startTop, newW = startWidth, newH = startHeight;
          if (activeHandle.includes('e')) newW = Math.max(40, startWidth + dx);
          if (activeHandle.includes('s')) newH = Math.max(40, startHeight + dy);
          if (activeHandle.includes('w')) {
            const clampDx = Math.min(dx, startWidth - 40);
            newL = startLeft + clampDx;
            newW = startWidth - clampDx;
          }
          if (activeHandle.includes('n')) {
            const clampDy = Math.min(dy, startHeight - 40);
            newT = startTop + clampDy;
            newH = startHeight - clampDy;
          }
          box.style.left = `${newL}px`;
          box.style.top = `${newT}px`;
          box.style.width = `${newW}px`;
          box.style.height = `${newH}px`;
          this._updateCropDimensions(newW, newH, scale);
        }
      });

      window.addEventListener('mouseup', () => {
        isDraggingBox = false;
        activeHandle = null;
      });
    }

    // -----------------------------------------------------------------------
    // Modals: Resize, Split, Insert Blank, Cross-Document Import
    // -----------------------------------------------------------------------

    openResizeModal() {
      const modal = document.getElementById('page-resize-modal');
      if (modal) modal.hidden = false;
    }

    openSplitModal() {
      const modal = document.getElementById('page-split-modal');
      if (modal) modal.hidden = false;
    }

    openInsertBlankModal() {
      const modal = document.getElementById('page-insert-blank-modal');
      if (modal) modal.hidden = false;
    }

    openCrossDocImportModal(insertAfter = null) {
      const modal = document.getElementById('cross-doc-import-modal');
      if (!modal) return;
      if (insertAfter !== null) {
        modal.dataset.insertAfter = insertAfter;
      } else {
        modal.dataset.insertAfter = this.state.activePage;
      }
      modal.hidden = false;
    }
  }

  // Export Singleton to Window
  window.PaperplanePageOrganizer = new PaperplanePageOrganizerController();

  // Initialize once DOM is loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.PaperplanePageOrganizer.init());
  } else {
    window.PaperplanePageOrganizer.init();
  }
})();
