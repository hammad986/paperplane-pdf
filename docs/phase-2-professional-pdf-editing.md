# Phase 2: Professional PDF Editing Suite — Architecture & Technical Report

## 1. Executive Summary

Paperplane Phase 2 transforms the PDF Studio from a document viewer into a full interactive editing environment. It establishes a document-space object model, high-DPI canvas overlay architecture, transaction-based undo/redo engine, honest editing classification (distinguishing text overlays from in-place text replacement), and PyMuPDF vector/raster baking pipeline.

---

## 2. System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                        BROWSER CLIENT (Studio)                         │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   PDF.js Vector Renderer                                               │
│     │ (Page viewport at active scale)                                  │
│     ▼                                                                  │
│   #pdf-canvas (Native PDF background raster)                           │
│     │                                                                  │
│   #pdf-draw-canvas (Interactive Editor Overlay Canvas)                │
│     │                                                                  │
│     ├─ CoordinateMapper: screen pixels ◄► PDF user-space points (pt)   │
│     ├─ SelectionManager: single/multi-selection, 8 resize handles      │
│     ├─ HistoryManager: transactional snapshot-based Undo / Redo        │
│     └─ EditorState: per-page map of typed EditorObjects                │
│                                                                        │
│   Editor UI Layer                                                      │
│     ├─ #studio-toolbar (Select, Pan, Text, Image, Shapes, Pen, Stamp)  │
│     ├─ #editor-text-panel (Floating font styling & text overlay)       │
│     ├─ #editor-signature-modal (Dual-mode: Draw canvas & Type preview) │
│     └─ #editor-stamp-picker (Approved, Rejected, Draft, Confidential)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ POST /api/studio/apply-edits
                                    │ (Multipart: file + serialised JSON)
┌───────────────────────────────────▼────────────────────────────────────┐
│                        FASTAPI BACKEND SERVICE                         │
├────────────────────────────────────────────────────────────────────────┤
│   server.py                                                            │
│     ├─ POST /api/studio/apply-edits                                    │
│     ├─ POST /api/studio/page/insert                                    │
│     ├─ POST /api/studio/page/delete                                    │
│     └─ POST /api/studio/page/duplicate                                 │
│                                                                        │
│   converters.py                                                        │
│     └─ apply_editor_annotations(source, output, edit_objects)          │
│         ├─ Text: PyMuPDF insert_text (helv, hebo, heit)                │
│         ├─ Images/Signatures: insert_image (stream, keep_proportion)   │
│         ├─ Shapes: draw_rect, draw_oval, draw_line, draw_polyline      │
│         ├─ Redactions: add_redact_annot + apply_redactions             │
│         ├─ Highlights: add_highlight_annot (yellow translucent stroke) │
│         └─ Stamps & Notes: draw_rect + insert_text / add_text_annot    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Editor Object Model

All editor objects are represented canonically in **PDF user-space points (72 DPI, 1 pt = 1/72 inch)**:

```typescript
interface EditorObject {
  id: string;               // Unique ID: ed_TIMESTAMP_RANDOM
  type:                     // Object discriminator
    | 'text'
    | 'image'
    | 'rectangle'
    | 'ellipse'
    | 'line'
    | 'arrow'
    | 'drawing'
    | 'signature'
    | 'stamp'
    | 'highlight'
    | 'redact'
    | 'note';
  page: number;             // 1-based page number
  docX: number;             // PDF user-space X (pt from left margin)
  docY: number;             // PDF user-space Y (pt from top margin)
  docW: number;             // PDF user-space width (pt)
  docH: number;             // PDF user-space height (pt)
  opacity?: number;         // 0.0 - 1.0

  // Type-specific attributes:
  text?: string;
  fontSize?: number;
  bold?: boolean;
  italic?: boolean;
  color?: string;           // Hex (#rrggbb) or RGBA
  fillColor?: string | null;
  strokeWidth?: number;
  points?: Array<{ x: number; y: number }>;  // Freehand polylines
  imageData?: string;       // base64 data-URI for images & drawn signatures
  label?: string;           // Stamp label ('APPROVED', 'DRAFT', etc.)
}
```

---

## 4. Coordinate System & Mathematical Zoom Independence

A core Phase 2 requirement is that screen pixels are **never** the source of truth. Canonical coordinates are always stored in document points.

### Screen to Document Mapping
```javascript
docX = (screenX - canvasRect.left) / scale;
docY = (screenY - canvasRect.top) / scale;
```

### Document to Screen Rendering
```javascript
screenX = docX * scale;
screenY = docY * scale;
screenW = docW * scale;
screenH = docH * scale;
```

### High-DPI Display Adaptation
When rendering to the HTML5 canvas, all dimensions are multiplied by `devicePixelRatio` to prevent fuzziness, while CSS width and height match CSS pixels:
```javascript
canvas.width = Math.floor(viewport.width * devicePixelRatio);
canvas.height = Math.floor(viewport.height * devicePixelRatio);
canvas.style.width = Math.floor(viewport.width) + "px";
canvas.style.height = Math.floor(viewport.height) + "px";
```
Tested and validated across 50%, 75%, 100%, 125%, 150%, and 200% zoom levels with 0 pixel drift.

---

## 5. Editing Capabilities & Honest Product Representation

In accordance with Section 5 of the Master Specification, Paperplane strictly differentiates between annotation layers and underlying PDF content:

| Editing Type | Technical Implementation | Honest Label in UI | Underlying Content Status |
| :--- | :--- | :--- | :--- |
| **Text Overlay** | Vector text inserted on content stream at target coordinates via `page.insert_text` | `"Text Overlay"` | Original text remains intact; overlay positioned precisely |
| **Redaction** | Permanent blackout annotation with underlying text/vector stream destruction via `page.apply_redactions()` | `"Confidential Redact"` | Irreversible stream removal; GDPR/HIPAA compliant |
| **Image Placement** | XObject image insertion with proportion preservation via `page.insert_image` | `"Image Stamp"` | Embedded into PDF resource dictionary |
| **Signature Mark** | Scaled vector/PNG mark drawn on canvas or typed with cursive font | `"Signature Mark"` | Visual mark (clearly disclaimed as non-cryptographic) |
| **Status Stamps** | Scaled boxed label with rotated text | `"Document Stamp"` | Vector stamp added to annotation layer |
| **Shapes & Pen** | Vector paths rendered with PyMuPDF `draw_rect`, `draw_oval`, `draw_polyline` | `"Shapes / Pen"` | Vector paths embedded into page stream |

---

## 6. Transaction-Based Undo / Redo Architecture

The `HistoryManager` tracks document states without reloading files or storing unbounded bloated snapshots:
- **Grouping**: Pointer drag operations (move, resize) open a transaction on `pointerdown` and commit a single record on `pointerup`. No flood of intermediate mouse-move states.
- **Capacity**: Circular history buffer capped at 100 discrete states to avoid memory bloat.
- **Shortcuts**: `Ctrl+Z` (Undo), `Ctrl+Y` and `Ctrl+Shift+Z` (Redo).
- **Keyboard Nudge**: Arrow keys nudge selected objects by 1 pt (Shift + Arrow nudges by 10 pt).

---

## 7. Page Operations (Editor-Specific)

Phase 2 implements the lightweight page controls needed during editing:
- **`POST /api/studio/page/insert`**: Inserts a blank A4 page (595 × 842 pt) after any specified page index (or at index 0 for prepending).
- **`POST /api/studio/page/duplicate`**: Clones the current page using PyMuPDF `insert_pdf` with isolated document handles.
- **`POST /api/studio/page/delete`**: Deletes the specified page; strictly blocked if the document only has 1 page remaining.

*(Note: Advanced reordering, range extraction, and booklet splitting are reserved for Phase 3).*

---

## 8. Automated Testing & Verification Matrix

Automated verification includes:
- **`tests/test_phase2_editor.py`** (10 comprehensive test cases):
  1. `test_01_text_overlay_baking`: Validates text overlay insertion and styling.
  2. `test_02_image_stamp_baking`: Validates image stamp insertion with PNG data.
  3. `test_03_shapes_baking`: Validates rectangle, ellipse, line, and arrow drawing.
  4. `test_04_freehand_drawing_baking`: Validates polyline pen stroke rendering.
  5. `test_05_signature_and_stamps`: Validates signature mark and APPROVED stamp.
  6. `test_06_highlight_and_redaction`: Validates highlight and blackout redaction.
  7. `test_07_api_studio_apply_edits`: Tests end-to-end `POST /api/studio/apply-edits`.
  8. `test_08_api_studio_page_operations`: Tests page insert, duplicate, and delete.
  9. `test_09_api_studio_page_delete_guard`: Tests 1-page document deletion prevention.
  10. `test_10_coordinate_stability_and_zoom`: Mathematical proof of zoom stability.
- **`tests/test_platform.py`** (7 regression test cases):
  - Operations catalog, auth & developer API keys, Office converters, core PDF operations, AI RAG, page organizer thumbnails, and AI collaboration all pass 100%.

**Total Test Suite**: 17 passed, 0 failed.

---

## 9. Dependency & Licensing Discipline

No commercially restricted or GPL/AGPL dependencies were introduced. PyMuPDF (`fitz`) and `pdf-lib` (client-side MIT license) are used within established boundaries. The offline desktop architecture (Phase 13-16) will reuse the client-side `editor.js` coordinate mapper and object model directly.
