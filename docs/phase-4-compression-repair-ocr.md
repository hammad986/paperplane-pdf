# Paperplane PDF — Phase 4: Compression, Repair & OCR Engine

## Overview & Architectural Principles

Phase 4 implements three distinct, workstation-grade engines for the Paperplane PDF platform:
1. **OCR Engine**: Genuine, C++ embedded Tesseract optical character recognition that injects a selectable, searchable invisible text layer into scanned and image-only pages.
2. **Compression Engine**: Multi-preset (`extreme`, `high`, `balanced`, `high_quality`, `lossless`) and target-file-size optimization with measurable byte metrics.
3. **Repair Engine**: Three-tier recovery pipeline (`validate_only`, `automatic`, `advanced`) capable of repairing corrupted xref tables, broken stream lengths, and salvaging surviving pages from truncated documents.

Both Paperplane Web and the future offline Paperplane Desktop workstation utilize these engines identically without mandatory cloud processing or telemetry.

---

## 1. OCR Engine Architecture

### 1.1 Critical Mandate: Zero Fake OCR
- The system never resaves an unmodified file, never copies non-existent text, and never creates an empty placeholder text layer.
- Scanned pages receive genuine searchable and selectable text at exact word coordinates using PDF standard `render_mode=3` ("Neither fill nor stroke text").
- The original scanned bitmap/rendering is 100% visually preserved, while enabling native `Ctrl+F` in-document search, text selection, and clipboard copy.

### 1.2 Pipeline & Preprocessing
1. **Page Classification**:
   - Inspects existing text stream length and embedded images.
   - Categorizes each page as `scanned` (images present, text < 30 chars), `text` (clean vector text, no full scans), or `hybrid` (mixed content).
2. **Preprocessing**:
   - Controlled DPI rendering (default 150 DPI for balanced performance; 200–300 DPI for high-fidelity accuracy).
   - Auto-contrast enhancement and sharpness normalization via Pillow.
3. **Recognition**:
   - Direct C++ binding to Tesseract via PyMuPDF (`page.get_textpage_ocr(language=..., dpi=..., tessdata=...)`).
   - Extracts word bounding boxes (`(x0, y0, x1, y1, word)`).
4. **Text Layer Injection**:
   - Injects invisible text glyphs at calculated baseline coordinates (`fitz.Point(x0, y1)`).
5. **Quality & Diagnostic Report**:
   - Returns pages processed, pages OCR'd, pages already searchable, extracted character count, elapsed time, and input/output sizes.

### 1.3 Language Discovery & Management
- Installed language models are dynamically discovered by scanning `tessdata/*.traineddata`.
- Default installed models:
  - `eng`: English (4.1 MB fast model)
  - `fra`: French (1.1 MB fast model)
  - `deu`: German (1.5 MB fast model)
  - `spa`: Spanish (2.3 MB fast model)
- If an uninstalled language is requested (e.g. `ara`, `hin`, `jpn`), the engine cleanly errors with `"Required OCR language data for '{lang}' is not installed."` No silent fallback.

---

## 2. Compression Engine Architecture

### 2.1 Presets & Semantics
| Preset | Target Image Dimensions | JPEG Quality | Stream Deflation | Unused Objects | Semantics |
|---|---|---|---|---|---|
| **Extreme** | Max $800 \times 1000$ pt (~96 DPI) | 45% | Deflate All | Purge (`garbage=4`) | Maximum size reduction; acceptable visual loss for archiving. |
| **High** | Max $1100 \times 1400$ pt (~130 DPI) | 60% | Deflate All | Purge (`garbage=4`) | Strong reduction with readable scans and photographs. |
| **Balanced** | Max $1400 \times 1800$ pt (~180 DPI) | 75% | Deflate All | Clean (`garbage=3`) | **Default**. Excellent visual fidelity with meaningful compression. |
| **High Quality** | Max $2000 \times 2600$ pt (~250 DPI) | 85% | Deflate All | Clean (`garbage=3`) | Mild reduction; preserves fine lines and diagrams. |
| **Lossless** | No downsampling ($99999$) | $100$% (None) | Deflate All | Purge (`garbage=4`) | **Strictly loss-free**. Eliminates redundant xrefs and unused streams. |

### 2.2 Target File Size Mode
- Supports `target_size_bytes` (or KB/MB in UI).
- Begins with selected preset. If output exceeds target, engine progressively cascades to stronger presets (`high` -> `extreme`).
- Reports requested target vs achieved output size with honest reasons if constraints prevented exact matches.

### 2.3 Pre-Compression Structural Analysis
- Endpoint: `POST /api/studio/compress/analyze`
- Analyzes total pages, embedded images, high-res image count ($> 1200 \times 1600$), raster vs vector percentage, and delivers intelligent recommendations.

---

## 3. PDF Repair Engine Architecture

### 3.1 Repair Modes
1. **`validate_only`**:
   - Non-destructive structural inspection.
   - Inspects trailer integrity, xref consistency, stream length validity.
   - Returns diagnostic report with detected issue list and health status without altering the document.
2. **`automatic`**:
   - Reconstructs broken cross-reference (XREF) tables and rebuilds page tree.
   - Sanitizes corrupted object streams with `garbage=4, clean=True, deflate=True`.
3. **`advanced`**:
   - Deep salvage mode for truncated or severely damaged files.
   - Leverages secondary lenient parsers (`pypdf.PdfReader(strict=False)`).
   - Iterates through surviving page streams and reconstitutes them into a fresh document tree.
   - Honestly reports recovered vs unrecoverable page counts.

---

## 4. API Endpoints & Contract

| Endpoint | Method | Parameters | Response |
|---|---|---|---|
| `/api/studio/ocr/languages` | `GET` | None | JSON list of installed language models. |
| `/api/studio/ocr` | `POST` | `file`, `language`, `pages`, `mode`, `dpi` | PDF Stream with `X-Pages-OCRed`, `X-Extracted-Chars`, etc. |
| `/api/studio/compress/analyze` | `POST` | `file` | JSON analysis of image ratios and savings potential. |
| `/api/studio/compress` | `POST` | `file`, `preset`, `target_size_kb` | PDF Stream with `X-Saved-Bytes`, `X-Percent-Saved`, etc. |
| `/api/studio/repair` | `POST` | `file`, `mode` | JSON report (`validate_only`) or Repaired PDF Stream (`automatic`/`advanced`). |

---

## 5. Security & Resource Protection

- **Input Validation**: Strict magic byte validation (`%PDF-`).
- **Memory Bounded Processing**: Page-by-page streaming; avoids buffering entire high-resolution document pixmaps in RAM simultaneously.
- **Atomic File Finalization**: Temporary write with atomic rename prevents race conditions and corrupted file handles.
- **Temporary Cleanup**: All scratch files are managed within `tempfile.mkdtemp()` and cleaned up in `finally` blocks.
- **Zero Shell Injection**: Internal C++ bindings are utilized directly without external shell commands.

---

## 6. Dependency & Licensing Audit

- **PyMuPDF (`fitz`)**: Commercial-friendly bindings, AGPL/commercial dual-license. Bundled with internal libtesseract engine.
- **Tesseract Traineddata Models**: Apache License 2.0 (permissively licensed for commercial redistribution).
- **Pillow**: Historical PIL license (permissive).
- **pypdf**: BSD-3-Clause license (permissive).

---

## 7. Automated Test Suite Matrix

Validated by 20 dedicated Phase 4 automated tests in `tests/test_phase4_engine.py`:
- `test_01_installed_ocr_languages_discovery`: PASSED
- `test_02_api_studio_ocr_languages_endpoint`: PASSED
- `test_03_ocr_scanned_pdf_produces_searchable_text_layer`: PASSED
- `test_04_ocr_hybrid_detection_and_scanned_only_mode`: PASSED
- `test_05_ocr_selected_pages`: PASSED
- `test_06_ocr_missing_language_safety`: PASSED
- `test_07_api_studio_ocr_endpoint`: PASSED
- `test_08_analyze_pdf_compression`: PASSED
- `test_09_api_studio_compress_analyze_endpoint`: PASSED
- `test_10_compress_extreme_preset`: PASSED
- `test_11_compress_all_presets_and_lossless`: PASSED
- `test_12_compress_target_size_mode`: PASSED
- `test_13_api_studio_compress_endpoint`: PASSED
- `test_14_repair_validate_only_healthy_document`: PASSED
- `test_15_api_studio_repair_validate_only_endpoint`: PASSED
- `test_16_repair_corrupted_xref_pdf`: PASSED
- `test_17_repair_truncated_pdf_stream_salvage`: PASSED
- `test_18_repair_unrecoverable_garbage_safely_errors`: PASSED
- `test_19_api_studio_invalid_file_rejected`: PASSED
- `test_20_process_job_queue_integration`: PASSED

**Full Suite: 57 / 57 Tests Passing.**
