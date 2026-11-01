// =============================================================================
// Paperplane PDF  -  Phase 2 Professional Editor Engine
// =============================================================================
// Architecture:
//   EditorState         -  per-page arrays of EditorObject records
//   HistoryManager      -  undo/redo stack with transaction grouping
//   SelectionManager    -  single/multi-select with handles
//   EditCanvasManager   -  pointer-to-doc coordinate mapping, overlays
//   Tool implementations per object type
//
// Coordinate Convention
// ---------------------
// All stored coordinates use PDF-page-space (Y from top = canvas convention).
// "docX/docY/docW/docH" are in PDF user-space points at scale=1.0.
// Screen-to-doc conversion accounts for: zoom, devicePixelRatio, scroll.
//
// Editing Capabilities (honest labelling):
//   TEXT OVERLAY  -  adds new text objects on top of the page.
//                  This is NOT in-place editing of existing PDF content.
//   IMAGE STAMP    -  inserts images as new objects.
//   SHAPES         -  rectangles, ellipses, lines, arrows.
//   FREEHAND       -  pen strokes.
//   SIGNATURE MARK  -  hand-drawn or typed signatures (NOT cryptographic signing).
//   HIGHLIGHT / REDACT / STAMP  -  annotation objects.
//
// =============================================================================

'use strict';

// ---------------------------------------------------------------------------
// EditorObject schema
// ---------------------------------------------------------------------------
// {
//   id:        string  (uuid)
//   type:      'text'|'image'|'rectangle'|'ellipse'|'line'|'arrow'|
//              'drawing'|'highlight'|'redact'|'signature'|'stamp'|'note'
//   page:      number  (1-based)
//   docX:      number  (pt from left)
//   docY:      number  (pt from top)
//   docW:      number  (pt width)
//   docH:      number  (pt height)
//   -- Text-specific --
//   text:      string
//   fontSize:  number
//   bold:      boolean
//   italic:    boolean
//   underline: boolean
//   color:     string (#rrggbb)
//   align:     'left'|'center'|'right'
//   -- Image-specific --
//   imageData: string  (data-URI)
//   -- Shape-specific --
//   strokeWidth: number
//   fillColor:   string|null
//   -- Drawing-specific --
//   points:    [{x,y}...]
//   -- Signature-specific --
//   imageData: string  (data-URI of drawn sig or null)
//   -- Stamp-specific --
//   label:     string  (APPROVED|DRAFT|CONFIDENTIAL|REVIEWED|REJECTED)
// }

const EDITOR_VERSION = '2.0.0';

// Maximum undo history steps
const MAX_HISTORY = 100;

// ---------------------------------------------------------------------------
// Utility: ID generator
// ---------------------------------------------------------------------------
function genId() {
  return `ed_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

// ---------------------------------------------------------------------------
// Utility: Deep clone
// ---------------------------------------------------------------------------
function cloneDeep(obj) {
  return JSON.parse(JSON.stringify(obj));
}

// ---------------------------------------------------------------------------
// EditorState  -  per-document, per-page edit object storage
// ---------------------------------------------------------------------------
class EditorState {
  constructor() {
    // Map<pageNum(1-based), EditorObject[]>
    this._pages = new Map();
    this._dirty = false;
    this._sourceFile = null;  // File | null  -  the currently loaded PDF
    this._sourceName = 'document.pdf';
    this._totalPages = 0;
  }

  get dirty() { return this._dirty; }
  get sourceFile() { return this._sourceFile; }
  get sourceName() { return this._sourceName; }
  get totalPages() { return this._totalPages; }

  setSource(file, name, totalPages) {
    this._sourceFile = file;
    this._sourceName = name || (file && file.name) || 'document.pdf';
    this._totalPages = totalPages || 0;
    this._dirty = false;
  }

  getObjects(page) {
    return this._pages.get(page) || [];
  }

  getAllObjects() {
    const result = [];
    this._pages.forEach((objs) => result.push(...objs));
    return result;
  }

  addObject(obj) {
    const page = obj.page;
    if (!this._pages.has(page)) this._pages.set(page, []);
    this._pages.get(page).push(obj);
    this._dirty = true;
    return obj;
  }

  updateObject(id, updates) {
    this._pages.forEach((objs) => {
      const o = objs.find(x => x.id === id);
      if (o) Object.assign(o, updates);
    });
    this._dirty = true;
  }

  removeObject(id) {
    this._pages.forEach((objs, page) => {
      const idx = objs.findIndex(x => x.id === id);
      if (idx !== -1) {
        objs.splice(idx, 1);
        this._dirty = true;
      }
    });
  }

  removeObjects(ids) {
    ids.forEach(id => this.removeObject(id));
  }

  bringForward(id) {
    this._pages.forEach((objs) => {
      const idx = objs.findIndex(x => x.id === id);
      if (idx !== -1 && idx < objs.length - 1) {
        [objs[idx], objs[idx + 1]] = [objs[idx + 1], objs[idx]];
        this._dirty = true;
      }
    });
  }

  sendBackward(id) {
    this._pages.forEach((objs) => {
      const idx = objs.findIndex(x => x.id === id);
      if (idx > 0) {
        [objs[idx - 1], objs[idx]] = [objs[idx], objs[idx - 1]];
        this._dirty = true;
      }
    });
  }

  getObject(id) {
    for (const objs of this._pages.values()) {
      const o = objs.find(x => x.id === id);
      if (o) return o;
    }
    return null;
  }

  clearPage(page) {
    this._pages.set(page, []);
    this._dirty = true;
  }

  clearAll() {
    this._pages.clear();
    this._dirty = false;
  }

  serialize() {
    // Returns flat array of all objects suitable for the API
    return this.getAllObjects();
  }

  markClean() { this._dirty = false; }
}

// ---------------------------------------------------------------------------
// HistoryManager  -  undo/redo with transaction grouping
// ---------------------------------------------------------------------------
class HistoryManager {
  constructor(editorState) {
    this._state = editorState;
    this._undoStack = [];
    this._redoStack = [];
    this._currentTransaction = null;
  }

  _snapshot() {
    // Capture entire editor state as JSON
    const data = {};
    this._state._pages.forEach((objs, page) => {
      data[page] = cloneDeep(objs);
    });
    return data;
  }

  _restore(snapshot) {
    this._state._pages.clear();
    Object.entries(snapshot).forEach(([page, objs]) => {
      this._state._pages.set(Number(page), objs);
    });
    this._state._dirty = true;
  }

  beginTransaction(label = '') {
    if (this._currentTransaction) return;  // nested  -  ignore
    this._currentTransaction = { label, before: this._snapshot() };
  }

  commitTransaction() {
    if (!this._currentTransaction) return;
    const after = this._snapshot();
    this._undoStack.push({ ...this._currentTransaction, after });
    if (this._undoStack.length > MAX_HISTORY) this._undoStack.shift();
    this._redoStack = [];
    this._currentTransaction = null;
  }

  rollbackTransaction() {
    if (!this._currentTransaction) return;
    this._restore(this._currentTransaction.before);
    this._currentTransaction = null;
  }

  // Record a single discrete action (auto-wraps in a transaction)
  record(label, fn) {
    const before = this._snapshot();
    fn();
    const after = this._snapshot();
    this._undoStack.push({ label, before, after });
    if (this._undoStack.length > MAX_HISTORY) this._undoStack.shift();
    this._redoStack = [];
  }

  undo() {
    const entry = this._undoStack.pop();
    if (!entry) return false;
    this._redoStack.push(entry);
    this._restore(entry.before);
    return true;
  }

  redo() {
    const entry = this._redoStack.pop();
    if (!entry) return false;
    this._undoStack.push(entry);
    this._restore(entry.after);
    return true;
  }

  canUndo() { return this._undoStack.length > 0; }
  canRedo() { return this._redoStack.length > 0; }
  clear() { this._undoStack = []; this._redoStack = []; }
}

// ---------------------------------------------------------------------------
// SelectionManager  -  select, move, resize with handles
// ---------------------------------------------------------------------------
const HANDLE_SIZE = 9;
const HANDLE_HALF = HANDLE_SIZE / 2;

class SelectionManager {
  constructor() {
    this._selected = new Set();  // Set of EditorObject IDs
    this._clipboard = [];        // clipboard for copy/paste
  }

  get selectedIds() { return [...this._selected]; }
  get hasSelection() { return this._selected.size > 0; }
  get count() { return this._selected.size; }

  select(id) { this._selected.clear(); this._selected.add(id); }
  addToSelection(id) { this._selected.add(id); }
  toggle(id) {
    if (this._selected.has(id)) this._selected.delete(id);
    else this._selected.add(id);
  }
  deselect() { this._selected.clear(); }
  isSelected(id) { return this._selected.has(id); }

  copy(editorState) {
    this._clipboard = this._selected.size > 0
      ? this.selectedIds.map(id => cloneDeep(editorState.getObject(id))).filter(Boolean)
      : [];
  }

  paste(editorState, history, page, offsetX = 16, offsetY = 16) {
    if (!this._clipboard.length) return;
    history.beginTransaction('Paste');
    const newIds = [];
    this._clipboard.forEach(obj => {
      const newObj = cloneDeep(obj);
      newObj.id = genId();
      newObj.page = page;
      newObj.docX += offsetX;
      newObj.docY += offsetY;
      editorState.addObject(newObj);
      newIds.push(newObj.id);
    });
    history.commitTransaction();
    this._selected = new Set(newIds);
  }

  // Returns 8 handle positions for a bounding rect in screen coordinates
  static getHandles(sx, sy, sw, sh) {
    return [
      { id: 'nw', x: sx,          y: sy          },
      { id: 'n',  x: sx + sw / 2, y: sy          },
      { id: 'ne', x: sx + sw,     y: sy          },
      { id: 'w',  x: sx,          y: sy + sh / 2 },
      { id: 'e',  x: sx + sw,     y: sy + sh / 2 },
      { id: 'sw', x: sx,          y: sy + sh     },
      { id: 's',  x: sx + sw / 2, y: sy + sh     },
      { id: 'se', x: sx + sw,     y: sy + sh     },
    ];
  }

  // Hit-test a screen point against object handles; returns handle id or null
  static hitTestHandle(px, py, sx, sy, sw, sh) {
    for (const h of SelectionManager.getHandles(sx, sy, sw, sh)) {
      if (Math.abs(px - h.x) <= HANDLE_HALF + 2 && Math.abs(py - h.y) <= HANDLE_HALF + 2) {
        return h.id;
      }
    }
    return null;
  }
}

// ---------------------------------------------------------------------------
// CoordinateMapper  -  document ↔ screen coordinate conversion
// ---------------------------------------------------------------------------
class CoordinateMapper {
  constructor() {
    this.scale = 1.0;
    this.dpr = window.devicePixelRatio || 1;
    this.pageWidth = 595;   // PDF user-space width (pt)
    this.pageHeight = 842;  // PDF user-space height (pt)
  }

  // Update from current PDF.js viewport
  update(scale, pageWidth, pageHeight) {
    this.scale = scale;
    this.pageWidth = pageWidth;
    this.pageHeight = pageHeight;
    this.dpr = window.devicePixelRatio || 1;
  }

  // Convert CSS canvas client event coords → document (PDF) coords
  screenToDoc(screenX, screenY, canvasEl) {
    const rect = canvasEl.getBoundingClientRect();
    // Position within canvas CSS size
    const cx = screenX - rect.left;
    const cy = screenY - rect.top;
    // CSS size → doc coordinates: divide by scale
    const docX = cx / this.scale;
    const docY = cy / this.scale;
    return { x: docX, y: docY };
  }

  // Convert document coords → CSS screen coords (for rendering overlays)
  docToScreen(docX, docY) {
    return { x: docX * this.scale, y: docY * this.scale };
  }

  // Convert doc dimensions → screen dimensions
  docSizeToScreen(docW, docH) {
    return { w: docW * this.scale, h: docH * this.scale };
  }

  // Convert screen dimensions → doc dimensions
  screenSizeToDoc(sw, sh) {
    return { w: sw / this.scale, h: sh / this.scale };
  }
}

// ---------------------------------------------------------------------------
// SignaturePad  -  canvas-based signature drawing + typed mode
// ---------------------------------------------------------------------------
class SignaturePad {
  constructor(canvasEl) {
    this._canvas = canvasEl;
    this._ctx = canvasEl.getContext('2d');
    this._drawing = false;
    this._paths = [];
    this._currentPath = [];
    this._mode = 'draw';  // 'draw' | 'type'
    this._typedText = '';
    this._dpr = window.devicePixelRatio || 1;
    this._setupCanvas();
    this._attachEvents();
  }

  _setupCanvas() {
    const el = this._canvas;
    const w = el.offsetWidth || 480;
    const h = el.offsetHeight || 160;
    el.width = w * this._dpr;
    el.height = h * this._dpr;
    el.style.width = w + 'px';
    el.style.height = h + 'px';
    this._ctx.scale(this._dpr, this._dpr);
    this._clear();
  }

  _clear() {
    const ctx = this._ctx;
    const w = this._canvas.offsetWidth;
    const h = this._canvas.offsetHeight;
    ctx.clearRect(0, 0, w, h);
    // Light background
    ctx.fillStyle = '#f9fafb';
    ctx.fillRect(0, 0, w, h);
    // Baseline guide
    ctx.strokeStyle = '#d1d5db';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(16, h * 0.75);
    ctx.lineTo(w - 16, h * 0.75);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  _redraw() {
    this._clear();
    if (this._mode === 'type') {
      this._drawTyped();
      return;
    }
    const ctx = this._ctx;
    ctx.strokeStyle = '#1a1a2e';
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    this._paths.forEach(path => {
      if (path.length < 2) return;
      ctx.beginPath();
      ctx.moveTo(path[0].x, path[0].y);
      path.slice(1).forEach(pt => ctx.lineTo(pt.x, pt.y));
      ctx.stroke();
    });
    if (this._currentPath.length >= 2) {
      ctx.beginPath();
      ctx.moveTo(this._currentPath[0].x, this._currentPath[0].y);
      this._currentPath.slice(1).forEach(pt => ctx.lineTo(pt.x, pt.y));
      ctx.stroke();
    }
  }

  _drawTyped() {
    const ctx = this._ctx;
    const w = this._canvas.offsetWidth;
    const h = this._canvas.offsetHeight;
    this._clear();
    if (!this._typedText) return;
    ctx.fillStyle = '#1a1a2e';
    ctx.font = `italic ${Math.min(42, h * 0.45)}px Georgia, serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(this._typedText, w / 2, h / 2);
  }

  _getPos(e) {
    const rect = this._canvas.getBoundingClientRect();
    const src = e.touches ? e.touches[0] : e;
    return { x: src.clientX - rect.left, y: src.clientY - rect.top };
  }

  _attachEvents() {
    const el = this._canvas;
    const onStart = e => {
      if (this._mode !== 'draw') return;
      e.preventDefault();
      this._drawing = true;
      const pt = this._getPos(e);
      this._currentPath = [pt];
    };
    const onMove = e => {
      if (!this._drawing) return;
      e.preventDefault();
      const pt = this._getPos(e);
      this._currentPath.push(pt);
      this._redraw();
    };
    const onEnd = e => {
      if (!this._drawing) return;
      this._drawing = false;
      if (this._currentPath.length > 1) {
        this._paths.push([...this._currentPath]);
      }
      this._currentPath = [];
      this._redraw();
    };
    el.addEventListener('mousedown', onStart);
    el.addEventListener('mousemove', onMove);
    el.addEventListener('mouseup', onEnd);
    el.addEventListener('mouseleave', onEnd);
    el.addEventListener('touchstart', onStart, { passive: false });
    el.addEventListener('touchmove', onMove, { passive: false });
    el.addEventListener('touchend', onEnd);
  }

  setMode(mode) {
    this._mode = mode;
    this._redraw();
  }

  setTypedText(text) {
    this._typedText = text;
    if (this._mode === 'type') this._redraw();
  }

  clear() {
    this._paths = [];
    this._currentPath = [];
    this._typedText = '';
    this._clear();
  }

  isEmpty() {
    if (this._mode === 'draw') return this._paths.length === 0;
    return !this._typedText.trim();
  }

  // Returns a data-URI PNG of the signature at 2x resolution
  toDataURL() {
    this._redraw();
    return this._canvas.toDataURL('image/png');
  }

  // Returns an array of {x,y} stroke points (draw mode only) for freehand serialisation
  getStrokes() {
    const all = [];
    this._paths.forEach(p => all.push(...p));
    return all;
  }
}

// ---------------------------------------------------------------------------
// EditCanvasManager  -  overlay canvas handling, object rendering, interaction
// ---------------------------------------------------------------------------
class EditCanvasManager {
  constructor(opts) {
    // Required elements
    this._pdfCanvas = opts.pdfCanvas;          // #pdf-canvas
    this._editCanvas = opts.editCanvas;         // #pdf-edit-overlay (new canvas)
    this._wrapperEl = opts.wrapperEl;          // .page-render-wrapper

    this._editorState = opts.editorState;
    this._history = opts.history;
    this._selection = opts.selection;
    this._mapper = opts.mapper;
    this._currentPage = 1;
    this._activeTool = 'select';
    this._activeColor = '#ff4b26';
    this._activeFontSize = 16;
    this._activeStrokeWidth = 2.5;
    this._activeFill = null;
    this._activeFontFamily = 'sans-serif';
    this._activeBold = false;
    this._activeItalic = false;

    // Interaction state
    this._interacting = false;
    this._dragStart = null;    // {docX, docY}
    this._dragHandle = null;   // resize handle id
    this._dragObj = null;      // object being moved/resized
    this._freehandPoints = []; // current pen stroke
    this._tempShape = null;    // shape preview while dragging

    this._onChange = opts.onChange || (() => {});
    this._onUnsaved = opts.onUnsaved || (() => {});

    this._setupCanvas();
    this._attachEvents();
  }

  // -------------------------------------------------------------------------
  // Canvas setup
  // -------------------------------------------------------------------------
  _setupCanvas() {
    const w = this._pdfCanvas.offsetWidth || this._pdfCanvas.width;
    const h = this._pdfCanvas.offsetHeight || this._pdfCanvas.height;
    this._editCanvas.style.width = `${w}px`;
    this._editCanvas.style.height = `${h}px`;
    this._editCanvas.width = this._pdfCanvas.width;
    this._editCanvas.height = this._pdfCanvas.height;
    this._editCanvas.style.pointerEvents = 'auto';
    this._editCanvas.style.cursor = 'default';
  }

  syncSize() {
    this._setupCanvas();
    this.redraw();
  }

  setPage(pageNum) {
    this._currentPage = pageNum;
    this._selection.deselect();
    this.redraw();
  }

  setTool(tool) {
    this._activeTool = tool;
    const cursors = {
      select: 'default',
      text: 'text',
      image: 'crosshair',
      rectangle: 'crosshair',
      ellipse: 'crosshair',
      line: 'crosshair',
      arrow: 'crosshair',
      drawing: 'crosshair',
      highlight: 'crosshair',
      redact: 'crosshair',
      signature: 'crosshair',
      stamp: 'crosshair',
      note: 'cell',
      pan: 'grab',
    };
    this._editCanvas.style.cursor = cursors[tool] || 'default';
    if (tool !== 'select') this._selection.deselect();
    this.redraw();
  }

  setColor(c) { this._activeColor = c; }
  setFontSize(s) { this._activeFontSize = s; }
  setStrokeWidth(w) { this._activeStrokeWidth = w; }
  setFill(f) { this._activeFill = f; }
  setBold(b) { this._activeBold = b; }
  setItalic(i) { this._activeItalic = i; }

  // -------------------------------------------------------------------------
  // Coordinate helpers
  // -------------------------------------------------------------------------
  _eventToDoc(e) {
    // Pointer → document coords using CoordinateMapper
    const src = e.touches ? e.touches[0] : e;
    return this._mapper.screenToDoc(src.clientX, src.clientY, this._editCanvas);
  }

  _docToScreen(docX, docY) {
    return this._mapper.docToScreen(docX, docY);
  }

  // Convert canvas rendering context to scaled coords
  _ctx() {
    const ctx = this._editCanvas.getContext('2d');
    return ctx;
  }

  // -------------------------------------------------------------------------
  // Object rendering
  // -------------------------------------------------------------------------
  redraw() {
    const canvas = this._editCanvas;
    const ctx = this._ctx();
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const dpr = window.devicePixelRatio || 1;
    ctx.save();
    ctx.scale(dpr, dpr);

    const objects = this._editorState.getObjects(this._currentPage);

    objects.forEach(obj => {
      this._renderObject(ctx, obj, this._selection.isSelected(obj.id));
    });

    // Draw temp shape preview
    if (this._tempShape) {
      this._renderTempShape(ctx, this._tempShape);
    }

    // Draw current freehand stroke
    if (this._freehandPoints.length > 1) {
      ctx.strokeStyle = this._activeColor;
      ctx.lineWidth = this._activeStrokeWidth;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.beginPath();
      const s0 = this._docToScreen(this._freehandPoints[0].x, this._freehandPoints[0].y);
      ctx.moveTo(s0.x, s0.y);
      this._freehandPoints.slice(1).forEach(p => {
        const sp = this._docToScreen(p.x, p.y);
        ctx.lineTo(sp.x, sp.y);
      });
      ctx.stroke();
    }

    ctx.restore();
  }

  _renderObject(ctx, obj, selected) {
    const s = this._docToScreen(obj.docX, obj.docY);
    const sz = this._mapper.docSizeToScreen(obj.docW || 100, obj.docH || 30);
    const sx = s.x, sy = s.y, sw = sz.w, sh = sz.h;

    ctx.save();

    switch (obj.type) {
      case 'text':
        this._renderText(ctx, obj, sx, sy, sw, sh);
        break;
      case 'image':
        this._renderImage(ctx, obj, sx, sy, sw, sh);
        break;
      case 'rectangle':
      case 'shape':
        this._renderRect(ctx, obj, sx, sy, sw, sh);
        break;
      case 'ellipse':
      case 'circle':
        this._renderEllipse(ctx, obj, sx, sy, sw, sh);
        break;
      case 'line':
        this._renderLine(ctx, obj, sx, sy, sw, sh);
        break;
      case 'arrow':
        this._renderArrow(ctx, obj, sx, sy, sw, sh);
        break;
      case 'drawing':
      case 'freehand':
      case 'pen':
        this._renderFreehand(ctx, obj);
        break;
      case 'highlight':
        this._renderHighlight(ctx, obj, sx, sy, sw, sh);
        break;
      case 'redact':
        this._renderRedact(ctx, obj, sx, sy, sw, sh);
        break;
      case 'signature':
        this._renderSignature(ctx, obj, sx, sy, sw, sh);
        break;
      case 'stamp':
        this._renderStamp(ctx, obj, sx, sy, sw, sh);
        break;
      case 'note':
        this._renderNote(ctx, obj, sx, sy, sw, sh);
        break;
    }

    // Selection overlay
    if (selected) {
      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 3]);
      ctx.strokeRect(sx - 2, sy - 2, sw + 4, sh + 4);
      ctx.setLineDash([]);

      // Resize handles
      SelectionManager.getHandles(sx, sy, sw, sh).forEach(h => {
        ctx.fillStyle = '#ffffff';
        ctx.strokeStyle = '#3b82f6';
        ctx.lineWidth = 1.5;
        ctx.fillRect(h.x - HANDLE_HALF, h.y - HANDLE_HALF, HANDLE_SIZE, HANDLE_SIZE);
        ctx.strokeRect(h.x - HANDLE_HALF, h.y - HANDLE_HALF, HANDLE_SIZE, HANDLE_SIZE);
      });
    }

    ctx.restore();
  }

  _renderText(ctx, obj, sx, sy, sw, sh) {
    const fs = (obj.fontSize || 16) * this._mapper.scale;
    let font = '';
    if (obj.italic) font += 'italic ';
    if (obj.bold) font += 'bold ';
    font += `${fs}px ${obj.fontFamily || 'Plus Jakarta Sans, sans-serif'}`;
    ctx.font = font;
    ctx.fillStyle = obj.color || '#142023';
    ctx.globalAlpha = obj.opacity != null ? obj.opacity : 1;
    ctx.textBaseline = 'top';
    // Draw label badge "TEXT OVERLAY" above object in edit mode
    const lines = (obj.text || '').split('\n');
    let lineY = sy + 2;
    lines.forEach(line => {
      ctx.fillText(line, sx + 3, lineY);
      lineY += fs * 1.25;
    });
    // Underline
    if (obj.underline) {
      const tw = ctx.measureText(obj.text || '').width;
      ctx.strokeStyle = obj.color || '#142023';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(sx + 3, sy + fs + 3);
      ctx.lineTo(sx + 3 + tw, sy + fs + 3);
      ctx.stroke();
    }
  }

  _renderImage(ctx, obj, sx, sy, sw, sh) {
    if (obj._imgEl) {
      ctx.drawImage(obj._imgEl, sx, sy, sw, sh);
    } else if (obj.imageData) {
      const img = new Image();
      img.onload = () => { obj._imgEl = img; this.redraw(); };
      img.src = obj.imageData;
      ctx.fillStyle = 'rgba(59,130,246,0.1)';
      ctx.fillRect(sx, sy, sw, sh);
      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 3]);
      ctx.strokeRect(sx, sy, sw, sh);
      ctx.setLineDash([]);
      ctx.fillStyle = '#3b82f6';
      ctx.font = `12px sans-serif`;
      ctx.fillText('Loading image…', sx + 6, sy + 20);
    }
  }

  _renderRect(ctx, obj, sx, sy, sw, sh) {
    ctx.globalAlpha = obj.opacity != null ? obj.opacity : 1;
    if (obj.fillColor) {
      ctx.fillStyle = obj.fillColor;
      ctx.fillRect(sx, sy, sw, sh);
    }
    ctx.strokeStyle = obj.color || '#142023';
    ctx.lineWidth = (obj.strokeWidth || 2) * this._mapper.scale;
    ctx.strokeRect(sx, sy, sw, sh);
  }

  _renderEllipse(ctx, obj, sx, sy, sw, sh) {
    ctx.globalAlpha = obj.opacity != null ? obj.opacity : 1;
    ctx.beginPath();
    ctx.ellipse(sx + sw / 2, sy + sh / 2, sw / 2, sh / 2, 0, 0, Math.PI * 2);
    if (obj.fillColor) { ctx.fillStyle = obj.fillColor; ctx.fill(); }
    ctx.strokeStyle = obj.color || '#142023';
    ctx.lineWidth = (obj.strokeWidth || 2) * this._mapper.scale;
    ctx.stroke();
  }

  _renderLine(ctx, obj, sx, sy, sw, sh) {
    ctx.strokeStyle = obj.color || '#142023';
    ctx.lineWidth = (obj.strokeWidth || 2) * this._mapper.scale;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(sx + sw, sy + sh);
    ctx.stroke();
  }

  _renderArrow(ctx, obj, sx, sy, sw, sh) {
    this._renderLine(ctx, obj, sx, sy, sw, sh);
    // Arrowhead
    const ex = sx + sw, ey = sy + sh;
    const dx = ex - sx, dy = ey - sy;
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    const ux = dx / len, uy = dy / len;
    const hl = 12 * this._mapper.scale;
    const ax = ex - ux * hl - uy * hl * 0.4;
    const ay = ey - uy * hl + ux * hl * 0.4;
    const bx = ex - ux * hl + uy * hl * 0.4;
    const by = ey - uy * hl - ux * hl * 0.4;
    ctx.fillStyle = obj.color || '#142023';
    ctx.beginPath();
    ctx.moveTo(ex, ey);
    ctx.lineTo(ax, ay);
    ctx.lineTo(bx, by);
    ctx.closePath();
    ctx.fill();
  }

  _renderFreehand(ctx, obj) {
    const pts = obj.points || [];
    if (pts.length < 2) return;
    ctx.globalAlpha = obj.opacity != null ? obj.opacity : 1;
    ctx.strokeStyle = obj.color || '#ff4b26';
    ctx.lineWidth = (obj.strokeWidth || 2.5) * this._mapper.scale;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    const s0 = this._docToScreen(pts[0].x, pts[0].y);
    ctx.moveTo(s0.x, s0.y);
    pts.slice(1).forEach(p => {
      const sp = this._docToScreen(p.x, p.y);
      ctx.lineTo(sp.x, sp.y);
    });
    ctx.stroke();
  }

  _renderHighlight(ctx, obj, sx, sy, sw, sh) {
    ctx.globalAlpha = 0.4;
    ctx.fillStyle = obj.color || '#FFF176';
    ctx.fillRect(sx, sy, sw, sh);
    ctx.globalAlpha = 1;
  }

  _renderRedact(ctx, obj, sx, sy, sw, sh) {
    ctx.fillStyle = '#000000';
    ctx.fillRect(sx, sy, sw, sh);
  }

  _renderSignature(ctx, obj, sx, sy, sw, sh) {
    if (obj._imgEl) {
      ctx.drawImage(obj._imgEl, sx, sy, sw, sh);
    } else if (obj.imageData) {
      const img = new Image();
      img.onload = () => { obj._imgEl = img; this.redraw(); };
      img.src = obj.imageData;
    } else if (obj.text) {
      ctx.fillStyle = obj.color || '#1a1a2e';
      ctx.font = `italic ${(obj.fontSize || 26) * this._mapper.scale}px Georgia, serif`;
      ctx.fillText(obj.text, sx + 4, sy + sh * 0.7);
    }
    // Border
    ctx.strokeStyle = 'rgba(59,130,246,0.35)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.strokeRect(sx, sy, sw, sh);
    ctx.setLineDash([]);
    // Label
    ctx.fillStyle = 'rgba(59,130,246,0.7)';
    ctx.font = `10px sans-serif`;
    ctx.fillText('Signature Mark', sx + 2, sy - 4);
  }

  _renderStamp(ctx, obj, sx, sy, sw, sh) {
    const color = obj.color || '#ef4444';
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5 * this._mapper.scale;
    ctx.strokeRect(sx, sy, sw, sh);
    const fs = Math.min((obj.fontSize || 24) * this._mapper.scale, sh * 0.65);
    ctx.fillStyle = color;
    ctx.font = `bold ${fs}px Plus Jakarta Sans, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(obj.label || obj.text || 'STAMP', sx + sw / 2, sy + sh / 2);
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
  }

  _renderNote(ctx, obj, sx, sy, sw, sh) {
    ctx.fillStyle = '#fef3c7';
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = 1.5;
    ctx.fillRect(sx, sy, sw, sh);
    ctx.strokeRect(sx, sy, sw, sh);
    // Icon
    ctx.font = `${Math.min(20, sh * 0.5) * this._mapper.scale}px sans-serif`;
    ctx.fillStyle = '#92400e';
    ctx.fillText('Note', sx + 3, sy + 3);
    if (obj.text) {
      ctx.fillStyle = '#78350f';
      ctx.font = `11px sans-serif`;
      ctx.fillText(obj.text.slice(0, 30), sx + 6, sy + sh * 0.55);
    }
  }

  _renderTempShape(ctx, shape) {
    const { type, sx, sy, sw, sh } = shape;
    ctx.globalAlpha = 0.6;
    ctx.strokeStyle = this._activeColor;
    ctx.lineWidth = this._activeStrokeWidth * this._mapper.scale;
    ctx.setLineDash([5, 3]);
    if (this._activeFill) { ctx.fillStyle = this._activeFill; }
    switch (type) {
      case 'rectangle':
        if (this._activeFill) ctx.fillRect(sx, sy, sw, sh);
        ctx.strokeRect(sx, sy, sw, sh);
        break;
      case 'ellipse':
        ctx.beginPath();
        ctx.ellipse(sx + sw / 2, sy + sh / 2, Math.abs(sw) / 2, Math.abs(sh) / 2, 0, 0, Math.PI * 2);
        if (this._activeFill) ctx.fill();
        ctx.stroke();
        break;
      case 'line':
      case 'arrow':
        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.lineTo(sx + sw, sy + sh);
        ctx.stroke();
        break;
      case 'highlight':
        ctx.globalAlpha = 0.35;
        ctx.fillStyle = this._activeColor;
        ctx.fillRect(sx, sy, sw, sh);
        break;
      case 'redact':
        ctx.fillStyle = '#000';
        ctx.fillRect(sx, sy, sw, sh);
        break;
    }
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
  }

  // -------------------------------------------------------------------------
  // Hit testing
  // -------------------------------------------------------------------------
  _hitTestObjects(docX, docY) {
    // Test in reverse order (topmost first)
    const objects = this._editorState.getObjects(this._currentPage);
    for (let i = objects.length - 1; i >= 0; i--) {
      const obj = objects[i];
      const px = docX, py = docY;
      // Inflate slightly for easier clicking
      if (px >= obj.docX - 3 && px <= obj.docX + (obj.docW || 100) + 3 &&
          py >= obj.docY - 3 && py <= obj.docY + (obj.docH || 30) + 3) {
        return obj;
      }
    }
    return null;
  }

  _hitTestHandleOnSelected(docX, docY) {
    if (!this._selection.hasSelection) return null;
    const ids = this._selection.selectedIds;
    for (const id of ids) {
      const obj = this._editorState.getObject(id);
      if (!obj) continue;
      const s = this._docToScreen(obj.docX, obj.docY);
      const sz = this._mapper.docSizeToScreen(obj.docW || 100, obj.docH || 30);
      // Convert docX/docY to screen for handle testing
      const sdx = docX * this._mapper.scale;
      const sdy = docY * this._mapper.scale;
      const h = SelectionManager.hitTestHandle(sdx, sdy, s.x, s.y, sz.w, sz.h);
      if (h) return { handleId: h, objId: id };
    }
    return null;
  }

  // -------------------------------------------------------------------------
  // Pointer event handlers
  // -------------------------------------------------------------------------
  _attachEvents() {
    const el = this._editCanvas;

    el.addEventListener('mousedown', e => this._onPointerDown(e));
    el.addEventListener('mousemove', e => this._onPointerMove(e));
    el.addEventListener('mouseup', e => this._onPointerUp(e));
    el.addEventListener('mouseleave', e => this._onPointerUp(e));
    el.addEventListener('touchstart', e => { e.preventDefault(); this._onPointerDown(e.touches[0]); }, { passive: false });
    el.addEventListener('touchmove', e => { e.preventDefault(); this._onPointerMove(e.touches[0]); }, { passive: false });
    el.addEventListener('touchend', e => this._onPointerUp(e.changedTouches[0]));

    // Keyboard: Delete, Backspace → delete selected
    document.addEventListener('keydown', e => this._onKeyDown(e));
  }

  _onPointerDown(e) {
    const doc = this._eventToDoc(e);

    if (this._activeTool === 'pan') return;

    if (this._activeTool === 'select') {
      // Check resize handles first
      const handleHit = this._hitTestHandleOnSelected(doc.x, doc.y);
      if (handleHit) {
        this._interacting = true;
        this._dragHandle = handleHit.handleId;
        this._dragObj = this._editorState.getObject(handleHit.objId);
        this._dragStart = doc;
        this._history.beginTransaction('Resize');
        return;
      }

      // Hit-test objects
      const hit = this._hitTestObjects(doc.x, doc.y);
      if (hit) {
        if (e.shiftKey) {
          this._selection.toggle(hit.id);
        } else {
          this._selection.select(hit.id);
        }
        this._interacting = true;
        this._dragHandle = null;
        this._dragObj = hit;
        this._dragStart = { ...doc, objX: hit.docX, objY: hit.docY };
        this._history.beginTransaction('Move');
      } else {
        this._selection.deselect();
      }
      this.redraw();
      return;
    }

    // Drawing tools  -  start
    this._interacting = true;
    this._dragStart = doc;

    if (this._activeTool === 'drawing') {
      this._freehandPoints = [{ x: doc.x, y: doc.y }];
    } else if (this._activeTool === 'text') {
      // Handled on pointerUp for click-to-place
    } else if (this._activeTool === 'note') {
      // Handled on pointerUp
    }
    this.redraw();
  }

  _onPointerMove(e) {
    if (!this._interacting) return;
    const doc = this._eventToDoc(e);

    if (this._activeTool === 'select' && this._dragObj) {
      if (this._dragHandle) {
        // Resize
        this._applyResize(doc);
      } else {
        // Move
        const dx = doc.x - this._dragStart.x;
        const dy = doc.y - this._dragStart.y;
        this._editorState.updateObject(this._dragObj.id, {
          docX: this._dragStart.objX + dx,
          docY: this._dragStart.objY + dy,
        });
      }
      this.redraw();
      return;
    }

    if (this._activeTool === 'drawing') {
      this._freehandPoints.push({ x: doc.x, y: doc.y });
      this.redraw();
      return;
    }

    // Shape preview
    const shapeTools = ['rectangle', 'ellipse', 'line', 'arrow', 'highlight', 'redact'];
    if (shapeTools.includes(this._activeTool)) {
      const sw = (doc.x - this._dragStart.x) * this._mapper.scale;
      const sh = (doc.y - this._dragStart.y) * this._mapper.scale;
      const s = this._docToScreen(this._dragStart.x, this._dragStart.y);
      this._tempShape = { type: this._activeTool, sx: s.x, sy: s.y, sw, sh };
      this.redraw();
    }
  }

  _onPointerUp(e) {
    if (!this._interacting) return;
    const doc = e ? this._eventToDoc(e) : this._dragStart;
    this._interacting = false;

    if (this._activeTool === 'select') {
      if (this._dragObj) {
        this._history.commitTransaction();
        this._dragObj = null;
        this._dragHandle = null;
      }
      this.redraw();
      this._onUnsaved();
      return;
    }

    if (this._activeTool === 'drawing') {
      if (this._freehandPoints.length > 1) {
        const bounds = this._pathBounds(this._freehandPoints);
        const obj = {
          id: genId(),
          type: 'drawing',
          page: this._currentPage,
          docX: bounds.minX,
          docY: bounds.minY,
          docW: bounds.maxX - bounds.minX,
          docH: bounds.maxY - bounds.minY,
          color: this._activeColor,
          strokeWidth: this._activeStrokeWidth,
          points: [...this._freehandPoints],
          opacity: 1,
        };
        this._history.record('Freehand stroke', () => this._editorState.addObject(obj));
        this._selection.select(obj.id);
      }
      this._freehandPoints = [];
      this._tempShape = null;
      this.redraw();
      this._onUnsaved();
      return;
    }

    if (this._activeTool === 'text') {
      this._showTextDialog(doc);
      return;
    }

    if (this._activeTool === 'note') {
      this._showNoteDialog(doc);
      return;
    }

    if (this._activeTool === 'signature') {
      this._showSignatureDialog(doc);
      return;
    }

    if (this._activeTool === 'stamp') {
      this._showStampPicker(doc);
      return;
    }

    if (this._activeTool === 'image') {
      this._triggerImageInsert(doc);
      return;
    }

    // Shape tools
    const shapeTools = ['rectangle', 'ellipse', 'line', 'arrow', 'highlight', 'redact'];
    if (shapeTools.includes(this._activeTool)) {
      const docW = doc.x - this._dragStart.x;
      const docH = doc.y - this._dragStart.y;
      if (Math.abs(docW) < 4 && Math.abs(docH) < 4) {
        this._tempShape = null;
        this.redraw();
        return;
      }
      const obj = {
        id: genId(),
        type: this._activeTool,
        page: this._currentPage,
        docX: Math.min(this._dragStart.x, doc.x),
        docY: Math.min(this._dragStart.y, doc.y),
        docW: Math.abs(docW),
        docH: Math.abs(docH),
        color: this._activeColor,
        fillColor: this._activeFill,
        strokeWidth: this._activeStrokeWidth,
        opacity: this._activeTool === 'highlight' ? 0.4 : 1,
      };
      this._history.record(`Add ${this._activeTool}`, () => this._editorState.addObject(obj));
      this._selection.select(obj.id);
    }

    this._tempShape = null;
    this.redraw();
    this._onUnsaved();
  }

  _applyResize(doc) {
    if (!this._dragObj || !this._dragHandle) return;
    const obj = this._editorState.getObject(this._dragObj.id);
    if (!obj) return;

    const dx = doc.x - this._dragStart.x;
    const dy = doc.y - this._dragStart.y;
    const handle = this._dragHandle;

    let { docX, docY, docW, docH } = obj;
    const origX = this._dragStart.objX !== undefined ? this._dragStart.objX : docX;
    const origY = this._dragStart.objY !== undefined ? this._dragStart.objY : docY;

    // Note: objX/objY not stored in dragStart for resize; use current
    switch (handle) {
      case 'se': obj.docW = Math.max(20, docW + dx); obj.docH = Math.max(10, docH + dy); break;
      case 'sw': obj.docX = docX + dx; obj.docW = Math.max(20, docW - dx); obj.docH = Math.max(10, docH + dy); break;
      case 'ne': obj.docW = Math.max(20, docW + dx); obj.docY = docY + dy; obj.docH = Math.max(10, docH - dy); break;
      case 'nw': obj.docX = docX + dx; obj.docY = docY + dy; obj.docW = Math.max(20, docW - dx); obj.docH = Math.max(10, docH - dy); break;
      case 'n': obj.docY = docY + dy; obj.docH = Math.max(10, docH - dy); break;
      case 's': obj.docH = Math.max(10, docH + dy); break;
      case 'e': obj.docW = Math.max(20, docW + dx); break;
      case 'w': obj.docX = docX + dx; obj.docW = Math.max(20, docW - dx); break;
    }
    this._dragStart = { ...doc };
    this._editorState._dirty = true;
  }

  _onKeyDown(e) {
    const active = document.activeElement;
    // Don't intercept when typing in inputs
    if (active && ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName)) return;
    // Don't intercept when a dialog modal is open
    const modalOpen = document.querySelector('.editor-dialog-overlay:not([hidden])');
    if (modalOpen) return;

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault();
      if (e.shiftKey) {
        if (this._history.redo()) { this.redraw(); this._onUnsaved(); }
      } else {
        if (this._history.undo()) { this.redraw(); this._onUnsaved(); }
      }
      return;
    }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
      e.preventDefault();
      if (this._history.redo()) { this.redraw(); this._onUnsaved(); }
      return;
    }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') {
      e.preventDefault();
      this._selection.copy(this._editorState);
      return;
    }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') {
      e.preventDefault();
      this._selection.paste(this._editorState, this._history, this._currentPage);
      this.redraw();
      this._onUnsaved();
      return;
    }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
      e.preventDefault();
      // Select all on current page
      const objs = this._editorState.getObjects(this._currentPage);
      objs.forEach(o => this._selection.addToSelection(o.id));
      this.redraw();
      return;
    }

    if ((e.key === 'Delete' || e.key === 'Backspace') && this._selection.hasSelection) {
      e.preventDefault();
      const ids = this._selection.selectedIds;
      this._history.record('Delete objects', () => {
        this._editorState.removeObjects(ids);
      });
      this._selection.deselect();
      this.redraw();
      this._onUnsaved();
      return;
    }

    // Arrow key nudge selected objects
    if (['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key) && this._selection.hasSelection) {
      e.preventDefault();
      const step = e.shiftKey ? 10 : 1;
      const dx = e.key === 'ArrowLeft' ? -step : e.key === 'ArrowRight' ? step : 0;
      const dy = e.key === 'ArrowUp' ? -step : e.key === 'ArrowDown' ? step : 0;
      this._history.record('Nudge', () => {
        this._selection.selectedIds.forEach(id => {
          const obj = this._editorState.getObject(id);
          if (obj) { obj.docX += dx; obj.docY += dy; obj._dirty = true; }
        });
        this._editorState._dirty = true;
      });
      this.redraw();
      this._onUnsaved();
    }
  }

  // -------------------------------------------------------------------------
  // Dialog helpers  -  text
  // -------------------------------------------------------------------------
  _showTextDialog(doc) {
    // Show the Phase 2 text insertion panel
    const panel = document.getElementById('editor-text-panel');
    if (!panel) {
      // Fallback: minimal prompt if panel doesn't exist yet
      const text = prompt('Enter text to add (Text Overlay  -  not in-place PDF edit):');
      if (!text) { this._interacting = false; return; }
      const obj = {
        id: genId(),
        type: 'text',
        page: this._currentPage,
        docX: doc.x,
        docY: doc.y,
        docW: 200,
        docH: 32,
        text,
        fontSize: this._activeFontSize,
        bold: this._activeBold,
        italic: this._activeItalic,
        underline: false,
        color: this._activeColor,
        opacity: 1,
      };
      this._history.record('Add text overlay', () => this._editorState.addObject(obj));
      this._selection.select(obj.id);
      this.redraw();
      this._onUnsaved();
      return;
    }
    // Show floating panel positioned near click
    panel.dataset.pendingDoc = JSON.stringify(doc);
    panel.hidden = false;
    const textInput = panel.querySelector('#editor-text-input');
    if (textInput) { textInput.value = ''; textInput.focus(); }
  }

  _showNoteDialog(doc) {
    const text = prompt('Enter sticky note text:');
    if (!text) { this._interacting = false; return; }
    const obj = {
      id: genId(),
      type: 'note',
      page: this._currentPage,
      docX: doc.x,
      docY: doc.y,
      docW: 140,
      docH: 80,
      text,
      color: '#f59e0b',
      opacity: 1,
    };
    this._history.record('Add note', () => this._editorState.addObject(obj));
    this._selection.select(obj.id);
    this.redraw();
    this._onUnsaved();
  }

  _showSignatureDialog(doc) {
    // Open the signature modal
    const modal = document.getElementById('editor-signature-modal');
    if (!modal) return;
    modal.dataset.pendingDoc = JSON.stringify(doc);
    modal.hidden = false;
  }

  _showStampPicker(doc) {
    const modal = document.getElementById('editor-stamp-picker');
    if (!modal) return;
    modal.dataset.pendingDoc = JSON.stringify(doc);
    modal.hidden = false;
  }

  _triggerImageInsert(doc) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/png,image/jpeg,image/webp,image/gif';
    input.onchange = () => {
      const file = input.files[0];
      if (!file) return;
      if (file.size > 10 * 1024 * 1024) {
        window.showToast('Image too large. Please use an image under 10 MB.', 'error');
        return;
      }
      const reader = new FileReader();
      reader.onload = ev => {
        const dataURL = ev.target.result;
        const img = new Image();
        img.onload = () => {
          const aspectW = img.naturalWidth;
          const aspectH = img.naturalHeight;
          const maxW = 200;
          const scale = maxW / aspectW;
          const docW = maxW;
          const docH = aspectH * scale;
          const obj = {
            id: genId(),
            type: 'image',
            page: this._currentPage,
            docX: doc.x,
            docY: doc.y,
            docW,
            docH,
            imageData: dataURL,
            opacity: 1,
          };
          this._history.record('Insert image', () => this._editorState.addObject(obj));
          this._selection.select(obj.id);
          this.redraw();
          this._onUnsaved();
        };
        img.src = dataURL;
      };
      reader.readAsDataURL(file);
    };
    input.click();
  }

  // -------------------------------------------------------------------------
  // Public API  -  called from the UI controller
  // -------------------------------------------------------------------------
  placeTextObject(text, options = {}) {
    const panel = document.getElementById('editor-text-panel');
    const docRaw = panel?.dataset.pendingDoc;
    const doc = docRaw ? JSON.parse(docRaw) : { x: 72, y: 72 };
    if (!text) return;
    const obj = {
      id: genId(),
      type: 'text',
      page: this._currentPage,
      docX: doc.x,
      docY: doc.y,
      docW: Math.max(200, text.length * (options.fontSize || 16) * 0.65),
      docH: (options.fontSize || 16) * 1.8,
      text,
      fontSize: options.fontSize || this._activeFontSize,
      bold: options.bold || this._activeBold,
      italic: options.italic || this._activeItalic,
      underline: options.underline || false,
      color: options.color || this._activeColor,
      opacity: 1,
    };
    this._history.record('Add text overlay', () => this._editorState.addObject(obj));
    this._selection.select(obj.id);
    if (panel) panel.hidden = true;
    this.redraw();
    this._onUnsaved();
  }

  placeSignature(sigDataURL, sigText, doc) {
    const finalDoc = doc || { x: 72, y: 500 };
    const obj = {
      id: genId(),
      type: 'signature',
      page: this._currentPage,
      docX: finalDoc.x,
      docY: finalDoc.y,
      docW: 180,
      docH: 70,
      imageData: sigDataURL || null,
      text: sigText || null,
      fontSize: 26,
      color: '#1a1a2e',
      opacity: 1,
    };
    this._history.record('Place signature mark', () => this._editorState.addObject(obj));
    this._selection.select(obj.id);
    this.redraw();
    this._onUnsaved();
  }

  placeStamp(label, color) {
    const modal = document.getElementById('editor-stamp-picker');
    const docRaw = modal?.dataset.pendingDoc;
    const doc = docRaw ? JSON.parse(docRaw) : { x: 100, y: 100 };
    const obj = {
      id: genId(),
      type: 'stamp',
      page: this._currentPage,
      docX: doc.x,
      docY: doc.y,
      docW: 160,
      docH: 55,
      label,
      text: label,
      color: color || '#ef4444',
      fontSize: 28,
      opacity: 1,
    };
    this._history.record('Place stamp', () => this._editorState.addObject(obj));
    this._selection.select(obj.id);
    if (modal) modal.hidden = true;
    this.redraw();
    this._onUnsaved();
  }

  deleteSelected() {
    if (!this._selection.hasSelection) return;
    const ids = this._selection.selectedIds;
    this._history.record('Delete', () => this._editorState.removeObjects(ids));
    this._selection.deselect();
    this.redraw();
    this._onUnsaved();
  }

  duplicateSelected() {
    if (!this._selection.hasSelection) return;
    const newIds = [];
    this._history.record('Duplicate', () => {
      this._selection.selectedIds.forEach(id => {
        const obj = this._editorState.getObject(id);
        if (!obj) return;
        const dup = cloneDeep(obj);
        dup.id = genId();
        dup.docX += 12;
        dup.docY += 12;
        this._editorState.addObject(dup);
        newIds.push(dup.id);
      });
    });
    this._selection._selected = new Set(newIds);
    this.redraw();
    this._onUnsaved();
  }

  bringForward() {
    this._selection.selectedIds.forEach(id => this._editorState.bringForward(id));
    this.redraw();
    this._onUnsaved();
  }

  sendBackward() {
    this._selection.selectedIds.forEach(id => this._editorState.sendBackward(id));
    this.redraw();
    this._onUnsaved();
  }

  // -------------------------------------------------------------------------
  // Freehand path bounding box
  // -------------------------------------------------------------------------
  _pathBounds(pts) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    pts.forEach(p => {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    });
    return { minX: minX - 2, minY: minY - 2, maxX: maxX + 2, maxY: maxY + 2 };
  }
}

// ---------------------------------------------------------------------------
// PaperplaneEditorController  -  top-level Phase 2 editor coordinator
// ---------------------------------------------------------------------------
class PaperplaneEditorController {
  constructor() {
    this.editorState = new EditorState();
    this.history = new HistoryManager(this.editorState);
    this.selection = new SelectionManager();
    this.mapper = new CoordinateMapper();
    this.canvas = null;     // EditCanvasManager, created on studio load
    this.sigPad = null;     // SignaturePad instance
    this._activeTool = 'pan';
    this._unsaved = false;
  }

  // Called when studio loads a PDF and PDF.js renders a page
  onPageRendered(pdfCanvas, editCanvasEl, wrapperEl, scale, pageNum, pageWidth, pageHeight) {
    this.mapper.update(scale, pageWidth, pageHeight);

    if (!this.canvas) {
      this.canvas = new EditCanvasManager({
        pdfCanvas,
        editCanvas: editCanvasEl,
        wrapperEl,
        editorState: this.editorState,
        history: this.history,
        selection: this.selection,
        mapper: this.mapper,
        onChange: () => this._onStateChange(),
        onUnsaved: () => this._markUnsaved(),
      });
    } else {
      this.mapper.update(scale, pageWidth, pageHeight);
      this.canvas.syncSize();
    }

    this.canvas.setPage(pageNum);
    this.canvas.setTool(this._activeTool);
    this._updateHistoryButtons();
    this._updateUnsavedIndicator();
  }

  setTool(tool) {
    this._activeTool = tool;
    if (this.canvas) this.canvas.setTool(tool);
  }

  setColor(c) { if (this.canvas) this.canvas.setColor(c); }
  setFontSize(s) { if (this.canvas) this.canvas.setFontSize(s); }
  setStrokeWidth(w) { if (this.canvas) this.canvas.setStrokeWidth(w); }
  setFill(f) { if (this.canvas) this.canvas.setFill(f); }

  undo() {
    if (this.history.undo()) {
      if (this.canvas) this.canvas.redraw();
      this._markUnsaved();
      this._updateHistoryButtons();
    }
  }

  redo() {
    if (this.history.redo()) {
      if (this.canvas) this.canvas.redraw();
      this._markUnsaved();
      this._updateHistoryButtons();
    }
  }

  clearPage(page) {
    const p = page || (this.canvas ? this.canvas._currentPage : 1);
    this.history.record('Clear page', () => this.editorState.clearPage(p));
    if (this.canvas) this.canvas.redraw();
    this._markUnsaved();
  }

  clearAll() {
    this.history.record('Clear all edits', () => this.editorState.clearAll());
    if (this.canvas) this.canvas.redraw();
    this._markUnsaved();
  }

  loadDocument(file, name, totalPages) {
    this.editorState.clearAll();
    this.editorState.setSource(file, name, totalPages);
    this.history.clear();
    this.selection.deselect();
    this._unsaved = false;
    this._updateUnsavedIndicator();
  }

  _onStateChange() {
    this._updateHistoryButtons();
  }

  _markUnsaved() {
    this._unsaved = this.editorState.dirty;
    this._updateUnsavedIndicator();
  }

  _updateUnsavedIndicator() {
    const badge = document.getElementById('editor-unsaved-badge');
    if (badge) badge.hidden = !this._unsaved;
  }

  _updateHistoryButtons() {
    const undoBtn = document.getElementById('editor-undo-btn');
    const redoBtn = document.getElementById('editor-redo-btn');
    if (undoBtn) undoBtn.disabled = !this.history.canUndo();
    if (redoBtn) redoBtn.disabled = !this.history.canRedo();
  }

  // -------------------------------------------------------------------------
  // Export  -  bake all edits and download
  // -------------------------------------------------------------------------
  async exportPDF() {
    const file = this.editorState.sourceFile;
    if (!file) {
      window.showToast('No PDF loaded. Open a document first.', 'error');
      return null;
    }
    const objects = this.editorState.serialize();
    // Strip non-serialisable image element references
    const clean = objects.map(o => {
      const c = { ...o };
      delete c._imgEl;
      return c;
    });

    const form = new FormData();
    form.append('file', file, this.editorState.sourceName || 'document.pdf');
    form.append('edits', JSON.stringify(clean));

    const btn = document.getElementById('save-studio-btn');
    const origText = btn?.innerHTML;
    if (btn) { btn.disabled = true; btn.innerHTML = 'Exporting…'; }

    try {
      const resp = await fetch('/api/studio/apply-edits', {
        method: 'POST',
        credentials: 'same-origin',
        body: form,
      });

      if (!resp.ok) {
        let errMsg = `Export failed (HTTP ${resp.status})`;
        try { const j = await resp.json(); errMsg = j.detail || errMsg; } catch {}
        throw new Error(errMsg);
      }

      const blob = await resp.blob();
      if (blob.size < 100) throw new Error('Server returned an empty PDF. Please try again.');

      // Validate PDF header
      const headerBuffer = await blob.slice(0, 5).arrayBuffer();
      const headerView = new Uint8Array(headerBuffer);
      const pdfSig = [0x25, 0x50, 0x44, 0x46, 0x2D]; // %PDF-
      const valid = pdfSig.every((b, i) => headerView[i] === b);
      if (!valid) throw new Error('Output file does not have a valid PDF header. Export aborted.');

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `edited_${this.editorState.sourceName || 'document.pdf'}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 10000);

      this.editorState.markClean();
      this._unsaved = false;
      this._updateUnsavedIndicator();
      window.showToast('Edited PDF exported successfully!', 'success');
      return blob;
    } catch (err) {
      window.showToast(`Export error: ${err.message}`, 'error');
      throw err;
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = origText; }
    }
  }

  // -------------------------------------------------------------------------
  // Page operations (delegates to server)
  // -------------------------------------------------------------------------
  async _pageMutate(endpoint, extraFields) {
    const file = this.editorState.sourceFile;
    if (!file) { window.showToast('No PDF loaded.', 'error'); return null; }

    const form = new FormData();
    form.append('file', file, this.editorState.sourceName || 'document.pdf');
    Object.entries(extraFields).forEach(([k, v]) => form.append(k, v));

    const resp = await fetch(endpoint, {
      method: 'POST',
      credentials: 'same-origin',
      body: form
    });
    if (!resp.ok) {
      let msg = `Page operation failed (${resp.status})`;
      try { const j = await resp.json(); msg = j.detail || msg; } catch {}
      window.showToast(msg, 'error');
      return null;
    }
    const blob = await resp.blob();
    const newFile = new File([blob], this.editorState.sourceName, { type: 'application/pdf' });
    return newFile;
  }

  async insertBlankPage(afterPage) {
    if (window.PaperplanePageOrganizer && window.PaperplanePageOrganizer.insertBlank) {
      return await window.PaperplanePageOrganizer.insertBlank(afterPage);
    }
    const newFile = await this._pageMutate('/api/studio/page/insert', { after_page: afterPage });
    if (newFile) {
      this.editorState.setSource(newFile, this.editorState.sourceName, this.editorState.totalPages + 1);
      window.showToast(`Blank page inserted after page ${afterPage}.`, 'success');
      return newFile;
    }
    return null;
  }

  async deletePage(pageNumber) {
    if (window.PaperplanePageOrganizer && window.PaperplanePageOrganizer.deletePages) {
      return await window.PaperplanePageOrganizer.deletePages([pageNumber]);
    }
    if (this.editorState.totalPages <= 1) {
      window.showToast('Cannot delete the only page.', 'error');
      return null;
    }
    const newFile = await this._pageMutate('/api/studio/page/delete', { page_number: pageNumber });
    if (newFile) {
      this.editorState.setSource(newFile, this.editorState.sourceName, this.editorState.totalPages - 1);
      window.showToast(`Page ${pageNumber} deleted.`, 'success');
      return newFile;
    }
    return null;
  }

  async duplicatePage(pageNumber) {
    if (window.PaperplanePageOrganizer && window.PaperplanePageOrganizer.duplicatePages) {
      return await window.PaperplanePageOrganizer.duplicatePages([pageNumber]);
    }
    const newFile = await this._pageMutate('/api/studio/page/duplicate', { page_number: pageNumber });
    if (newFile) {
      this.editorState.setSource(newFile, this.editorState.sourceName, this.editorState.totalPages + 1);
      window.showToast(`Page ${pageNumber} duplicated.`, 'success');
      return newFile;
    }
    return null;
  }

  async reorderPages(newOrder) {
    if (window.PaperplanePageOrganizer) {
      return await window.PaperplanePageOrganizer.reorder(newOrder);
    }
  }

  async rotatePages(pages, degrees) {
    if (window.PaperplanePageOrganizer) {
      return await window.PaperplanePageOrganizer.rotate(pages, degrees);
    }
  }

  async cropPage(pageNum, cropBox) {
    if (window.PaperplanePageOrganizer) {
      return await window.PaperplanePageOrganizer.applyCrop(pageNum, cropBox);
    }
  }

  async resizePages(pages, options) {
    if (window.PaperplanePageOrganizer) {
      return await window.PaperplanePageOrganizer.applyResize(pages, options);
    }
  }

  async extractPages(pages) {
    if (window.PaperplanePageOrganizer) {
      return await window.PaperplanePageOrganizer.extract(pages);
    }
  }
}

// ---------------------------------------------------------------------------
// Export as singleton attached to window
// ---------------------------------------------------------------------------
window.PaperplaneEditor = new PaperplaneEditorController();
window.EditorClasses = {
  EditorState,
  HistoryManager,
  SelectionManager,
  CoordinateMapper,
  SignaturePad,
  EditCanvasManager,
  PaperplaneEditorController,
};
