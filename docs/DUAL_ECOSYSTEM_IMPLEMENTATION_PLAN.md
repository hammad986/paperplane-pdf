# Paperplane Dual-Ecosystem Implementation Plan

## Executive decision

Paperplane should remain two products with a shared design language, operation
catalog, and test fixtures, but **not** a shared runtime:

1. **Web platform:** FastAPI + server-rendered route shells + the existing
   vanilla JavaScript application. This is the SEO and high-intent acquisition
   surface.
2. **Offline client:** Tauri v2 + Rust processing core + local TypeScript UI.
   This is the zero-server-cost product for Windows, Linux, macOS, Android, and
   iOS.

The offline client must not call the FastAPI service, require an account, load a
CDN, or expose the web product's AI/RAG features. The web product may continue
to offer AI features when configured, but those capabilities are explicitly
absent from the local build.

## Current repository audit

The requested Phase 1 surface was already substantially present in this
codebase. The implementation status after this pass is:

| Area | Status | Evidence / decision |
|---|---|---|
| Windows Uvicorn workers | Complete | `app.py` forces one worker on `os.name == "nt"`; Linux keeps the configured worker count. |
| 37 public tool slugs | Complete | `server.py` keeps an explicit `OPERATION_SLUGS` and reverse map. |
| Per-route SEO metadata | Complete | `render_web_page()` injects title, description, canonical, Open Graph, Twitter, and JSON-LD. |
| How-To and FAQ content | Complete | `render_seo_content()` renders crawlable HTML below the interactive shell. |
| Sitemap and robots | Complete | `/sitemap.xml` includes the 37 operation pages plus category landing pages; `/robots.txt` disallows API internals. |
| Deferred heavy bundles | Complete | PDF.js, pdf-lib, and application engines use `defer`. |
| Clean URL routing | Complete | `app.js` maps slugs with `history.pushState()` and retains old `?tool=` links for compatibility. |
| Mobile navigation | Complete | The sidebar becomes a swipe-dismissable drawer at 900px, with an overlay and 48px touch targets for primary controls. |
| Cleanup isolation | Complete after this pass | `/api/system/cleanup` now queues the daemon; only `periodic_cleanup_worker()` performs disk cleanup. |
| Offline architecture | Blueprint complete | See `docs/OFFLINE_CLIENT_ARCHITECTURE.md`; this document defines delivery order and acceptance gates. |

### Important product boundary

The web platform still needs hosting for its FastAPI/API mode and SEO pages.
The **$0 server-cost mandate applies to the offline client**, whose document
processing is local. Browser zero-upload mode reduces web compute and privacy
risk for supported operations, but it does not eliminate the cost of serving
the web application itself.

## System A — production web platform

### Request and rendering flow

```text
GET /merge-pdf
  -> FastAPI slug registry
  -> resolve operation metadata
  -> render index.html shell
  -> inject canonical/meta/Open Graph/Twitter/JSON-LD
  -> inject static How-To, privacy, comparison, FAQ, and related links
  -> browser loads deferred application bundles
  -> app.js selects merge and updates the interactive tool desk
```

The slug registry is the source of truth for public URLs. Internal operation
IDs remain stable so API payloads, persistence, and browser state do not need a
breaking rename. Every public tool page must have:

- a stable slug and canonical URL;
- a unique title and meta description derived from operation metadata;
- `SoftwareApplication`, `HowTo`, and `FAQPage` JSON-LD;
- visible three-step instructions and related-tool links;
- a truthful privacy statement that distinguishes client mode from server mode;
- a working interactive tool desk after JavaScript hydration.

### SEO route inventory

The current inventory contains these 37 operation pages:

```text
merge-pdf                  split-pdf                  remove-pages-pdf
rotate-pdf                 organize-pdf               scan-to-pdf
compress-pdf               repair-pdf                 ocr-pdf
jpg-to-pdf                 word-to-pdf                excel-to-pdf
powerpoint-to-pdf          html-to-pdf                pdf-to-jpg
pdf-to-word                pdf-to-excel               pdf-to-powerpoint
pdf-to-pdfa                pdf-to-text                pdf-to-markdown
edit-pdf                   annotate-pdf                crop-pdf
redact-pdf                 watermark-pdf               add-page-numbers-to-pdf
protect-pdf                unlock-pdf                 sign-pdf
compare-pdf                fill-pdf-form               pdf-metadata
ai-pdf-chat                extract-pdf-data            summarize-pdf
translate-pdf
```

The category landing pages `/convert-pdf` and `/pdf-security` are intentionally
additional discovery pages and are not counted as operations.

### Web performance and privacy rules

1. Keep the initial shell free of PDF parsing work. PDF.js, pdf-lib, and editor
   engines remain deferred and should only be used after the shell paints.
2. Keep browser-local processing explicit. A client-mode operation must never
   fall back to an upload without telling the user.
3. Keep server uploads inside the existing job capability and lifecycle model:
   validate signatures, contain paths, isolate jobs, and purge expired files.
4. Keep the SEO content server-rendered. Do not move the route's primary
   instructions, FAQ answers, or canonical metadata into JavaScript.
5. Keep public URLs backward compatible. Existing `/?tool=<id>` URLs may
   redirect or hydrate into the clean slug, but new navigation must use the
   slug path.

### Responsive interaction model

- Desktop: persistent sidebar, top workspace tabs, two-column tool desk.
- Tablet: collapsible sidebar with a wider touch target and horizontally
  scrollable tool/category controls.
- Mobile: hamburger opens a fixed left drawer; the scrim closes it; a leftward
  swipe dismisses it; tool cards use horizontal snap scrolling; options stack
  into a single column.
- All primary navigation and action controls should remain at least 48 CSS px
  high on touch breakpoints.
- Do not use viewport-locked `100vh` sections for workflow content; preserve
  browser chrome and keyboard visibility on mobile.

## System B — offline standalone client

### Chosen stack

| Layer | Technology | Responsibility |
|---|---|---|
| App shell | Tauri v2 | Native windows, file pickers, menus, mobile packaging, capabilities. |
| UI | TypeScript + Vite; vanilla DOM or SolidJS | Responsive desktop/mobile workflow UI only. |
| IPC | Typed Tauri commands/events | Job handles, progress, cancellation, export handles. |
| Renderer | PDFium via `pdfium-render` | Page rasterization, thumbnails, selection, preview export. |
| PDF structure | Rust `lopdf` / `pdf-writer` | Deterministic page tree edits, overlays, metadata, page numbering. |
| Repair/encryption | qpdf through a narrow native wrapper | Cross-reference repair, AES-256 protection, unlock, permissions. |
| Images | `image` + `fast_image_resize`; optional libvips desktop path | Crop, resize, rotate, sharpen, brightness/contrast, encode/decode. |
| OCR | Tesseract + Leptonica | Local searchable text layers, with explicit language-pack checks. |
| Desktop Office bridge | Bundled portable LibreOffice | High-fidelity DOCX/XLSX/PPTX conversion on desktop only. |
| Parallelism | Rust `rayon` with bounded workers | Independent page rendering, thumbnails, and batch image work. |
| Preview acceleration | WebView compositor + optional `wgpu` | Gestures, image filters, and canvas transforms; CPU fallback required. |

MuPDF is not the default because its licensing requires an AGPL/commercial
decision. Any bundled PDFium, qpdf, Tesseract, Leptonica, LibreOffice, or
libvips binary must be recorded in `THIRD_PARTY_NOTICES.md` and checked for the
target distribution license before packaging.

### Local-only processing contract

Every job follows the same lifecycle:

```text
file picker -> signature/size validation -> private temp workspace
-> cancellable Rust job -> progress events -> atomic result
-> PDFium/output verification -> user export -> temp cleanup
```

The TypeScript layer receives an opaque `JobId` and allow-listed output handle;
it never constructs shell commands or passes arbitrary native paths. Passwords
are held only in secure native memory, cleared after use, and excluded from
logs, history, IPC events, and crash payloads.

### Offline feature boundary

Included in v1:

- merge, split, reorder, delete, rotate, crop, watermark, and page numbering;
- lossless and quality-based compression with before/after size metrics;
- crop, resize, sharpen, brightness/contrast, rotate, annotate, draw, stamps,
  and signature placement;
- image-to-PDF, PDF-to-PNG/JPG/WebP, text-to-PDF, and local document structuring;
- local AES-256 PDF protection/unlock and content-rewriting redaction.

Excluded from the offline binary:

- RAG chat, summarization, external translation, or any LLM/API credential;
- cloud import/export, account login, billing, hosted storage, or remote jobs;
- telemetry, remote fonts, CDN scripts, update checks in the privacy build;
- full LibreOffice-fidelity Office conversion on Android/iOS in v1.

### CPU, GPU, and battery strategy

- Cap the `rayon` pool at `min(physical_cores, 8)` and expose `Balanced`,
  `Fast`, and `Low battery` profiles.
- Parallelize independent page rasterization, image transforms, thumbnail
  generation, and batch conversions. Keep a single owner for PDF object graph
  mutation and merge results in deterministic page order.
- Use Direct3D/WebView composition on Windows, Vulkan where available on Linux
  and Android, and Metal on macOS/iOS. GPU acceleration is for preview/UI
  transforms, not encryption or deterministic PDF rewrites.
- Pause thumbnails while backgrounded on mobile, bound decoded pixel counts,
  evict LRU previews, and stream page requests instead of loading whole PDFs
  into JavaScript memory.

### Offline project layout

```text
offline-client/
├─ package.json                 # pinned Node/pnpm/Tauri toolchain
├─ vite.config.ts
├─ src/
│  ├─ app.ts                    # UI entry point; no native imports
│  ├─ router.ts
│  ├─ ipc/{commands,events,dto}.ts
│  ├─ state/{documentStore,jobStore,preferencesStore}.ts
│  ├─ ui/{AppShell,ToolDesk,PageOrganizer,PhotoEditor,SecurityPanel}.ts
│  └─ styles/{tokens,responsive,components}.css
├─ src-tauri/
│  ├─ Cargo.toml
│  ├─ tauri.conf.json
│  ├─ capabilities/offline.json
│  └─ src/
│     ├─ {main,lib,commands,events,error,paths}.rs
│     ├─ jobs/{queue,cancellation,progress}.rs
│     ├─ pdf_core/{render,pages,optimize,redact,security}.rs
│     ├─ media/{raster,filters}.rs
│     ├─ ocr/tesseract.rs
│     ├─ office/{libreoffice,native_structuring}.rs
│     └─ third_party/{pdfium,qpdf,notices}.rs
├─ vendor/<platform>/<arch>/    # signed native assets only
├─ tests/{commands,golden-pdfs,golden-images}/
└─ docs/{THIRD_PARTY_NOTICES,RELEASE_MATRIX}.md
```

### Platform delivery matrix

| Platform | PDF/media core | OCR | Office fidelity | UI acceleration | Package |
|---|---|---|---|---|---|
| Windows | Full | Bundled language packs | Bundled LibreOffice | WebView/Direct3D | MSI/NSIS |
| Linux | Full | Bundled language packs | Bundled LibreOffice | WebView/Vulkan | DEB/AppImage |
| macOS | Full | Bundled language packs | Bundled LibreOffice | WebView/Metal | DMG/App |
| Android | Full | Optional language packs | Native structuring only | WebView/Vulkan/OpenGL | APK/AAB |
| iOS | Full | Optional language packs | Native structuring only | WebView/Metal | Xcode archive |

## Delivery sequence and gates

### Phase 1 — Web hardening (current repository)

1. Keep the worker guard in `app.py` and add regression coverage around route
   inventory and clean URL metadata.
2. Keep cleanup exclusively in `periodic_cleanup_worker()`; administrative
   requests only set the daemon event.
3. Verify the 37 slugs, canonical/meta/JSON-LD output, sitemap, robots, mobile
   drawer, and deferred bundles.

### Phase 2 — Rust core proof

1. Pin the Rust, Node, pnpm, and Tauri versions.
2. Implement `InputHandle`, `JobId`, `JobProgress`, `ExportedFile`, and
   `AppError` DTOs.
3. Integrate PDFium and golden thumbnail tests.
4. Implement merge, split, reorder, rotate, delete, atomic export, and cancel.
5. Add a deny-all-network integration test.

### Phase 3 — Editing, conversion, and optimization

1. Add page overlays, crop, watermark, page numbers, metadata, annotations,
   signatures, and image filters.
2. Add PDF/image/text conversions and measured compression presets.
3. Add bounded concurrency, progress, cancellation, and crash-safe outputs.

### Phase 4 — Security, OCR, and desktop Office bridge

1. Add qpdf encryption/unlock and secure password handling.
2. Implement content-rewriting redaction and fail-closed verification.
3. Bundle Tesseract/Leptonica language packs with capability checks.
4. Bundle LibreOffice per desktop platform with a unique profile per job,
   timeout, cancellation, output verification, and license notices.

### Phase 5 — Mobile release hardening

1. Test file picker, share sheet, backgrounding, storage limits, memory, and
   low-battery profiles on real Android and iOS devices.
2. Produce signed MSI/NSIS, DEB/AppImage, DMG/App, APK/AAB, and iOS archive
   builds on their native build hosts.
3. Publish the platform capability matrix without implying desktop Office
   fidelity on mobile.

## Verification commands

Web checks from the repository root:

```powershell
python -m pytest tests/test_web_seo.py -q
python -m pytest -q
```

Offline client checks once `offline-client/` is created:

```powershell
pnpm install
pnpm lint
pnpm test
cargo test --manifest-path src-tauri/Cargo.toml
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets -- -D warnings
pnpm tauri build --bundles nsis,msi
```

The release gate is not just a successful build. It also requires an airplane
mode smoke test for core operations, an observable no-network test, clean temp
directories after cancellation, valid output verification, and proof that
redacted text is absent from both extracted text and page content streams.
