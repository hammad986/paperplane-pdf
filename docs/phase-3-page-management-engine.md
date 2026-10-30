# Paperplane PDF — Phase 3: Professional Page Management Engine

## Architecture & System Overview

Phase 3 implements an enterprise-grade, workstation-class **Page Management Engine** for the Paperplane PDF platform. Designed to operate symmetrically across **Paperplane Web** (client-side WASM/PDF.js with cloud-capable server endpoints) and **Paperplane Desktop** (local-first native Python/PyMuPDF execution without mandatory cloud dependencies), this engine provides precise, non-destructive, structural PDF manipulation.

---

## 1. Page State Model & Coordinate System

### 1.1 State Separation Architecture
To ensure scalability, serializability, and clean separation of concerns, the engine separates:
- **`PageOrganizerState`**: Canonical representation of the document's page order, labels, dimensions, orientation, rotation angles, and selection set (`Set<number>`).
- **`DocumentState` (`EditorState`)**: Annotation and editor overlay objects per page (from Phase 2).
- **`ViewerState`**: Zoom level, scroll position, and active page index.
- **`HistoryManager`**: Undo/Redo transaction stack recording atomic page-level operations (`reorder`, `rotate`, `crop`, `resize`, `delete`, `insert`).

### 1.2 Document Coordinate Integrity
- All page geometry operations (crop boxes, dimensions, offsets) are stored and computed in **canonical PDF user-space points (72 DPI)**, where `1 pt = 1/72 inch`.
- Canonical A4 dimensions: `595.28 × 841.89 pt`.
- Canonical US Letter dimensions: `612.0 × 792.0 pt`.
- Conversions between screen pixels and document coordinates strictly account for `zoom`, `devicePixelRatio`, and page rotation matrix, preventing distortion at 100%, 150%, 200%, or 4K/high-DPI resolutions.

---

## 2. Page Organizer UI & Interaction Model

### 2.1 Thumbnail Virtualization & Lazy Rendering
- Built with `IntersectionObserver` observing thumbnail card containers.
- Viewport threshold triggers on-demand rendering of low-resolution thumbnail canvases (~120px max width) via PDF.js worker.
- Rendered thumbnails are cached in memory as JPEG Data URIs (`p_{num}_rot_{angle}`), reducing DOM memory footprint for documents with 100 to 1,000+ pages.
- Switchable layout modes:
  - **Vertical Strip Mode** (`☰`): Compact single-column sidebar with quick actions.
  - **2-Column Grid Mode** (`☷`): Scalable overview for document-level reorganization.

### 2.2 Selection Engine
- **Click**: Single page selection and active view navigation.
- **Ctrl / Cmd + Click**: Toggle individual page into/out of selection set.
- **Shift + Click**: Range selection from `lastSelectedPage` to clicked page index.
- **Select All (`Ctrl+A`) / Invert**: Bulk selection utilities.
- Operates on stable 1-based page indices rather than volatile DOM references.

### 2.3 Drag-and-Drop Reordering
- HTML5 Drag-and-Drop with animated live insertion indicator bar (`.organizer-drop-indicator`).
- Supports single-page and contiguous multi-page relocation.
- Non-drag keyboard alternative: `Alt + ArrowUp` / `Alt + ArrowLeft` to move page earlier, `Alt + ArrowDown` / `Alt + ArrowRight` to move page later.
- Operations commit as a single atomic history transaction.

---

## 3. Core Page Operations & Endpoints

| Operation | Frontend Trigger | Backend Endpoint / Converter | Key Guarantees |
|---|---|---|---|
| **Reorder** | Drag-drop thumbnail, keyboard reorder (`Alt+Arrows`) | `POST /api/studio/pages/reorder`<br>`converters.reorder_pdf_pages()` | PyMuPDF `doc.select()`; preserves fonts, vector streams, annotations; zero rasterization. |
| **Rotate** | Mini thumbnail button `↷`, batch bar, context menu | `POST /api/studio/pages/rotate`<br>`converters.rotate_pdf_pages()` | Modifies PDF page `/Rotate` dictionary (+90°, 180°, 270°); persists on export. |
| **Crop** | Canvas Crop Overlay, Batch Bar | `POST /api/studio/pages/crop`<br>`converters.crop_pdf_pages()` | Updates `/CropBox` in 72 DPI PDF user points; non-destructive to underlying vector data. |
| **Resize** | Resize Modal, Preset Picker (A4, Letter, A3, Legal, Custom) | `POST /api/studio/pages/resize`<br>`converters.resize_pdf_pages()` | Supports `scale` (matrix scale), `center` (bleed/canvas expansion), and `crop` modes. |
| **Duplicate** | Batch Bar `📋 Duplicate`, Context Menu | `POST /api/studio/page/duplicate` | Multi-page and single-page duplication; genuine duplicate PDF page trees. |
| **Insert Blank** | Header `+ Blank`, Context Menu | `POST /api/studio/page/insert` | Configurable dimensions (surrounding page or preset), portrait/landscape, placement. |
| **Delete** | Batch Bar `🗑️ Delete`, Context Menu | `POST /api/studio/page/delete` | Safeguard: Blocks deleting the only page or all pages (`HTTP 400`). |
| **Extract** | Batch Bar `📤 Extract`, Context Menu | `POST /api/studio/pages/extract`<br>`converters.extract_pdf_pages()` | Exports specified pages in exact requested order to a standalone valid PDF. |
| **Split** | Header `✂️ Split`, Split Modal | `POST /api/studio/documents/split`<br>`converters.split_pdf_document()` | Split by custom ranges (`1-2, 3-5`) or every N pages; packages multi-file outputs as ZIP. |
| **Import / Merge** | Header `📥 Import`, Dropzone Modal | `POST /api/studio/pages/import`<br>`POST /api/studio/documents/merge` | Cross-document page grafting (`doc.insert_pdf()`); multi-document drag-and-drop merging. |
| **Metadata** | Organizer initialization | `POST /api/studio/pages/metadata`<br>`converters.get_pdf_metadata_pages()` | Returns per-page width, height, rotation, orientation, and logical page labels. |

---

## 4. In-Place Save & Memory Management

### 4.1 PyMuPDF In-Place File Safety
When saving mutations where `output_path == input_path`, PyMuPDF forbids direct non-incremental writes to open file handles. The engine employs an atomic write-and-replace strategy:
```python
temp_out = output.with_name(f"{output.stem}_tmp_{os.getpid()}_{uuid.uuid4().hex[:6]}.pdf")
doc.save(str(temp_out), garbage=3, deflate=True)
doc.close()
temp_out.replace(output)
```
This guarantees zero file truncation, zero lock contention, and automatic garbage collection of orphaned PDF xref entries.

### 4.2 Resource Cleanup
All endpoint operations run within temporary directories (`tempfile.mkdtemp()`) protected by `try ... finally: shutil.rmtree(temp_dir, ignore_errors=True)`.

---

## 5. Automated Test Suite Matrix

Phase 3 is validated by a rigorous 20-test automated suite (`tests/test_phase3_page_engine.py`) alongside existing Phase 1 and Phase 2 test suites.

**Test Summary (37 / 37 PASSING):**
- `tests/test_phase3_page_engine.py`: 20 tests (reorder single/multi, rotate 90/180/270, crop persistence, resize scale/center/crop, extract preservation, cross-document page import, multi-doc merge, split every N & ranges with ZIP, delete safety guard, blank page insertion with geometry, metadata extraction).
- `tests/test_phase2_editor.py`: 10 tests (text overlay, image stamps, shapes, freehand drawing, signatures, highlight/redaction, apply edits, page delete guard, coordinate stability).
- `tests/test_platform.py`: 7 tests (operations catalog, auth & developer keys, office converters, core operations, AI RAG, thumbnails, collaboration).

---

## 6. Local-First & Desktop Architecture Alignment

To prepare for **Phase 13 (Desktop Architecture)** and **Phase 14 (Windows Local PDF Engine)**:
- All core converters in `converters.py` depend solely on PyMuPDF (`fitz`), Pillow, and PyPDF.
- Converters are decoupled from HTTP request/response abstractions; they operate on standard Python `Path` objects.
- In the future desktop workstation, the same converter routines will be invoked directly via local IPC / subprocess without any cloud network hop.
