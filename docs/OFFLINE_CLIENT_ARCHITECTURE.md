# Paperplane Local Studio

## Purpose

This document defines the production architecture for a zero-server-cost
desktop and mobile companion to Paperplane PDF. The client is a separate
offline product, not a thin wrapper around the FastAPI service:

- PDF and media processing happens on the user's CPU/GPU.
- AI, RAG, cloud imports, telemetry, remote fonts, and external API calls are
  excluded from the offline build.
- The application must remain useful with Wi-Fi disabled after installation.
- The same Rust processing core is shared by Windows, Linux, macOS, Android,
  and iOS.

The recommended implementation is **Tauri v2 + a Rust core + a small
TypeScript UI**. It preserves the current Paperplane interaction model while
keeping native processing, filesystem access, and security-sensitive code out
of the browser layer.

## Architecture decision

### Recommended: Tauri v2 + Rust

| Layer | Responsibility | Choice |
|---|---|---|
| Shell | Windows/Linux/macOS/Android/iOS windows, menus, file pickers | Tauri v2 |
| UI | Responsive tool desk, page organizer, image editor | TypeScript + Vite + vanilla DOM or SolidJS |
| IPC | Typed commands and progress events | Tauri commands/events with generated DTOs |
| PDF rendering | Page rasterization, text selection, thumbnails | PDFium through `pdfium-render` |
| PDF structure | Merge, split, page tree edits, rewrite operations | Rust `lopdf`/`pdf-writer` plus a qpdf FFI boundary for hard cases |
| PDF encryption | Password protection and permission flags | qpdf native library, wrapped behind a narrow Rust API |
| Images | Decode/encode, resize, crop, sharpen, color operations | `image` + `fast_image_resize`; optional libvips desktop accelerator |
| OCR | Local searchable text layer | Tesseract/Leptonica native bundle, opt-in language packs |
| Office desktop bridge | High-fidelity DOCX/XLSX/PPTX rendering | Bundled portable LibreOffice headless process |
| Office mobile fallback | Simple document generation/structuring | Rust-native DOCX/XLSX writers; no promise of full Office layout fidelity |
| Parallelism | Batch jobs and independent page transforms | Rust `rayon` worker pool with bounded concurrency |
| GPU | UI composition, page canvas, image preview shaders | WebView compositor + optional `wgpu`; CPU fallback is mandatory |

### License and distribution gate

PDFium, qpdf, Tesseract, Leptonica, LibreOffice, and optional libvips must be
tracked in a third-party notice file and reviewed before shipping installers.
MuPDF is a technically strong alternative renderer, but it introduces an
AGPL/commercial licensing decision; it is not the default engine in this
blueprint. The implementation must not silently bundle a library whose license
is incompatible with the chosen distribution model.

## Runtime topology

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Tauri window                                                        │
│  ┌───────────────────────┐       typed invoke/events                │
│  │ TypeScript UI         │◄──────────────────────────────────────┐   │
│  │ - Home/tool routes    │                                       │   │
│  │ - page organizer      │                                       │   │
│  │ - image editor        │                                       │   │
│  └───────────────────────┘                                       │   │
│                                                                  ▼   │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Rust application layer                                         │  │
│  │ - job queue / cancellation / progress                          │  │
│  │ - secure temp files and atomic output                          │  │
│  │ - capability checks and input validation                        │  │
│  └───────────────┬──────────────────────┬─────────────────────────┘  │
│                  │                      │                            │
│          ┌───────▼────────┐     ┌───────▼─────────┐                  │
│          │ PDF core        │     │ Media / OCR      │                  │
│          │ PDFium + qpdf   │     │ image-rs/vips    │                  │
│          │ lopdf/pdf-writer│     │ Tesseract        │                  │
│          └──────────────────┘     └──────────────────┘                  │
│                  │                      │                            │
│          ┌───────▼──────────────────────▼─────────┐                  │
│          │ Local filesystem only                    │                  │
│          │ app data / temp / exports / language data│                  │
│          └─────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
```

There is no HTTP client in the offline core. Network permissions are disabled
in the Tauri capability configuration, and the UI does not load CDN assets.
The web product and local product may share icons and copy, but they do not
share a runtime dependency on the FastAPI server.

## Offline feature boundary

### Included in v1

1. **PDF core**: merge, split, reorder, delete, rotate, crop, watermark, and
   page numbering.
2. **Optimization**: object-stream rewrite, image downsampling, JPEG/WebP
   recompression where safe, metadata removal, and lossless deflation.
3. **Document/photo editor**: crop, resize, sharpen, brightness/contrast,
   rotate, annotations, freehand drawing, stamps, and signature placement.
4. **Conversions**: image-to-PDF, PDF-to-PNG/JPG/WebP, text-to-PDF, and local
   document structuring.
5. **Security**: password protect/unlock, AES-256 PDF encryption through the
   native security handler, visual redaction that rewrites the page content,
   and local signature placement.

### Explicitly excluded

- RAG chat, summarization, translation through external models, and AI API
  credentials.
- Cloud import/export, account login, billing, remote job queues, and hosted
  storage.
- Background telemetry or crash uploads in the privacy build.

### Capability matrix by platform

| Capability | Windows | Linux | macOS | Android | iOS |
|---|---:|---:|---:|---:|---:|
| PDF core and page organizer | Full | Full | Full | Full | Full |
| Image/photo editor | Full | Full | Full | Full | Full |
| Local OCR | Full with bundled packs | Full with bundled packs | Full with bundled packs | Optional language pack | Optional language pack |
| DOCX/XLSX/PPTX high-fidelity conversion | Bundled LibreOffice | Bundled LibreOffice | Bundled LibreOffice | Not in v1 | Not in v1 |
| Simple text/document structuring | Full | Full | Full | Full | Full |
| GPU preview acceleration | WebView/GPU | WebView/GPU | Metal/WebView | Vulkan/OpenGL via WebView | Metal/WebView |
| Network required | No | No | No | No | No |

Mobile Office conversion is intentionally not advertised as a full LibreOffice
replacement in v1. The mobile build can create and structure lightweight local
documents, while desktop builds can use the already verified portable
LibreOffice adapter for fidelity-critical conversions.

## Project layout

The local client should live beside the existing web codebase rather than
inside the FastAPI package. This keeps server dependencies out of mobile
builds and makes offline verification reproducible.

```text
offline-client/
├─ package.json
├─ pnpm-lock.yaml
├─ vite.config.ts
├─ src/
│  ├─ app.ts
│  ├─ router.ts
│  ├─ styles/
│  │  ├─ tokens.css
│  │  ├─ responsive.css
│  │  └─ components.css
│  ├─ ui/
│  │  ├─ AppShell.ts
│  │  ├─ ToolDesk.ts
│  │  ├─ PageOrganizer.ts
│  │  ├─ PhotoEditor.ts
│  │  ├─ SecurityPanel.ts
│  │  └─ components/
│  ├─ state/
│  │  ├─ documentStore.ts
│  │  ├─ jobStore.ts
│  │  └─ preferencesStore.ts
│  ├─ ipc/
│  │  ├─ commands.ts
│  │  ├─ events.ts
│  │  └─ dto.ts
│  └─ assets/
├─ src-tauri/
│  ├─ Cargo.toml
│  ├─ tauri.conf.json
│  ├─ capabilities/
│  │  └─ offline.json
│  ├─ icons/
│  └─ src/
│     ├─ main.rs
│     ├─ lib.rs
│     ├─ commands.rs
│     ├─ events.rs
│     ├─ error.rs
│     ├─ paths.rs
│     ├─ jobs/
│     │  ├─ queue.rs
│     │  ├─ cancellation.rs
│     │  └─ progress.rs
│     ├─ pdf_core/
│     │  ├─ mod.rs
│     │  ├─ render.rs
│     │  ├─ pages.rs
│     │  ├─ optimize.rs
│     │  ├─ redact.rs
│     │  └─ security.rs
│     ├─ media/
│     │  ├─ mod.rs
│     │  ├─ raster.rs
│     │  └─ filters.rs
│     ├─ ocr/
│     │  └─ tesseract.rs
│     ├─ office/
│     │  ├─ libreoffice.rs
│     │  └─ native_structuring.rs
│     └─ third_party/
│        ├─ pdfium.rs
│        ├─ qpdf.rs
│        └─ notices.rs
├─ vendor/
│  ├─ pdfium/<platform>/<arch>/
│  ├─ qpdf/<platform>/<arch>/
│  ├─ tesseract/<platform>/<arch>/
│  ├─ leptonica/<platform>/<arch>/
│  └─ libreoffice/<desktop-platform>/
├─ tests/
│  ├─ commands/
│  ├─ golden-pdfs/
│  ├─ golden-images/
│  └─ offline-network.spec.ts
└─ docs/
   ├─ THIRD_PARTY_NOTICES.md
   └─ RELEASE_MATRIX.md
```

### Entry points

- `src-tauri/src/main.rs`: platform process entry point; starts Tauri and
  registers commands.
- `src-tauri/src/lib.rs`: application wiring and dependency injection.
- `src/app.ts`: browser UI entry point; it must not import native libraries.
- `src-tauri/src/commands.rs`: the only public bridge from UI to Rust.

## Processing contract

Every operation follows the same typed lifecycle:

```text
select input → validate header/size → create private temp workspace
→ queue cancellable job → emit progress → write atomic output
→ verify output → move to export location → delete temp workspace
```

The UI receives a `JobId`, not a native pointer or an arbitrary filesystem
path. Rust owns all paths and returns an allow-listed output handle. A job
cannot write outside the app's temp directory or the user-selected export
directory. Output is written to `result.tmp`, flushed, verified, and renamed
atomically to avoid presenting partial PDFs after a crash.

### Typed command examples

```rust
#[tauri::command]
async fn merge_pdfs(
    app: tauri::AppHandle,
    inputs: Vec<InputHandle>,
    options: MergeOptions,
) -> Result<JobHandle, AppError>;

#[tauri::command]
async fn export_job(
    app: tauri::AppHandle,
    job_id: JobId,
    destination: ExportDestination,
) -> Result<ExportedFile, AppError>;

#[tauri::command]
async fn cancel_job(job_id: JobId) -> Result<(), AppError>;
```

The UI never constructs shell commands. In particular, LibreOffice is invoked
through `Command` with an explicit executable path and an argument vector, not
through a shell string.

## Native engine responsibilities

### PDFium: render and inspect

PDFium is the default renderer for page previews, thumbnails, zooming, text
selection, and image export. Render at a caller-selected DPI and use a bounded
cache keyed by `(document_hash, page, dpi, color_mode)`. The cache is local and
evictable; it is not a document archive.

### qpdf: structural repair and encryption

Use qpdf for cross-reference repair, linearization where useful, password
protection/unlock, and operations that need the PDF Standard Security Handler.
Expose only a small C ABI wrapper to Rust so the rest of the application does
not depend on qpdf internals. Passwords are passed in memory, cleared with
`zeroize`, and never persisted in job history.

### lopdf/pdf-writer: deterministic page operations

Use Rust-native PDF structures for page-tree operations, overlays, page
numbers, metadata removal, and simple text/image placement. This keeps common
operations fast and avoids starting a helper process for every page.

### image-rs and optional libvips

`image` plus `fast_image_resize` is the portable baseline for crop, resize,
rotate, contrast, sharpen, JPEG/PNG/WebP export, and image-to-PDF. On desktop,
libvips can be enabled as an optional accelerator for very large batches. The
feature must have a byte-for-byte tested CPU fallback for mobile and systems
where libvips is not bundled.

### OCR

Tesseract and Leptonica run as local native libraries. Language packs are
versioned assets selected by the user. OCR jobs create a new text layer and
must not claim success if the native engine or requested language data is
missing.

### LibreOffice desktop bridge

For DOCX/XLSX/PPTX conversion, reuse the verified headless adapter pattern from
the reference workspace:

1. Copy the input into a private per-job temp directory.
2. Launch the bundled `soffice` executable with a unique user profile and an
   explicit output directory.
3. Enforce a timeout and terminate the process tree on cancellation.
4. Verify the output exists, is non-empty, and can be opened by PDFium.
5. Delete the temporary profile and input copy.

Do not run one shared LibreOffice profile concurrently. A unique profile per
job prevents lock collisions and cross-job state leakage.

## CPU, GPU, and battery strategy

### CPU parallelism

- Use a bounded `rayon` pool sized to `available_parallelism()`, capped by a
  preference such as `min(physical_cores, 8)`.
- Parallelize independent page rasterization, image decode/encode, thumbnail
  generation, and batch conversion.
- Keep PDF object-graph mutation single-owner per document; merge results in a
  deterministic page order rather than allowing concurrent mutable access.
- Expose cancellation checks between pages and between expensive image stages.

### GPU usage

The GPU is used primarily for the UI compositor and preview rendering. PDF
rewrites, encryption, and most compression are CPU-bound and should not be
forced through a GPU path that could change output determinism.

- Tauri's WebView uses the platform compositor automatically.
- Optional `wgpu` shaders can accelerate image preview filters and gesture
  transforms in the editor.
- Metal is the preferred backend on macOS/iOS; Vulkan is preferred on Android
  and Linux where available; Direct3D/WebView composition is used on Windows.
- Every GPU feature has a CPU fallback and a capability probe. The UI should
  show "hardware acceleration unavailable" only as a diagnostic, never block a
  document operation.

### Battery and memory controls

- Pause background thumbnail generation when the app is backgrounded on mobile.
- Limit decoded page bitmaps by pixel count and evict least-recently-used
  previews.
- Offer `Balanced`, `Fast`, and `Low battery` worker profiles.
- Never load an entire large PDF into JavaScript memory; stream page data from
  Rust and request thumbnails by page.

## Security and privacy model

### No-network guarantee

The offline flavor is built with a separate Tauri capability file:

- no `http` or `websocket` permissions;
- no remote URL navigation;
- no CDN scripts, remote fonts, analytics, or update checks in the privacy
  build;
- `externalBin` contains only signed, bundled local helpers;
- an automated test runs the app behind a deny-all firewall and fails if a
  network connection is attempted.

Updates are user-initiated installer downloads from the normal distribution
channel; they are not part of document processing and can be disabled in
enterprise deployments.

### Input and output hardening

- Validate file signatures, not only filename extensions.
- Apply configurable maximum file size, page count, pixel count, and archive
  expansion limits before decoding.
- Keep each job in a randomly named directory with restrictive permissions.
- Resolve and compare canonical paths before every read/write.
- Use atomic writes and verify the generated PDF with PDFium before exposing it
  to the user.
- Treat PDF JavaScript, embedded files, launch actions, annotations, and
  external links as untrusted input; sanitize them when the user selects
  "secure cleanup".

### Correct redaction

Visual black rectangles are not redaction. The redaction command must remove
or replace matching text operators and rasterize/replace affected image
regions before writing a new PDF. The verification step should search the
output text and content streams for the redacted value and fail closed if it
is still present.

### Secrets and passwords

- Password fields use secure native memory and are cleared after the command.
- No password is placed in logs, crash reports, local history, or IPC event
  payloads.
- Signature images are stored only when the user explicitly exports them as a
  reusable local asset.
- A device keychain is optional for saved preferences, but document passwords
  are never silently saved.

## Offline UI wireframes

The shell uses the same visual language as the web platform, but it is
optimized for touch and keyboard use. Primary controls are at least 48 CSS px
on touch platforms.

### Desktop: Windows / Linux / macOS

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ P paperplane     Open  Save As  Undo  Redo        Search       Settings   │
├──────────────┬───────────────────────────────────────────────────────────┤
│ All tools    │ Merge PDF                         [Import files] [Export]  │
│ Organize     │ ┌───────────────────────────────────────────────────────┐ │
│ Optimize     │ │ Drop files here or choose from this device             │ │
│ Convert      │ └───────────────────────────────────────────────────────┘ │
│ Edit         │                                                           │
│ Security     │   [page 1] [page 2] [page 3]   Document preview           │
│              │                                                           │
│ Recent files │ Options: order · compression · metadata                  │
│              │ [Run locally]                         [Export PDF]        │
└──────────────┴───────────────────────────────────────────────────────────┘
```

### Mobile: Android / iOS

```text
┌──────────────────────────────┐
│ ☰  Merge PDF       ⋯         │
├──────────────────────────────┤
│  Local only · no upload      │
│ ┌──────────────────────────┐ │
│ │  Add files               │ │
│ │  Take photo / Files      │ │
│ └──────────────────────────┘ │
│                              │
│  Swipeable file cards        │
│  ┌─────────┐ ┌─────────┐    │
│  │ Page 1  │ │ Page 2  │ →  │
│  └─────────┘ └─────────┘    │
│                              │
│  Compression                 │
│  ○ Balanced  ○ Small  ○ Max │
│                              │
│ [Run locally]                │
├──────────────────────────────┤
│ Tools     Recent     Settings│
└──────────────────────────────┘
```

Mobile interactions:

- swipe the drawer from the left edge;
- swipe page cards to reorder, with a long-press fallback for precision;
- pinch to zoom the preview and two-finger pan the page;
- bottom sheets hold options so the document preview remains visible;
- destructive actions require a confirmation sheet with a plain-language
  warning.

## Build and development commands

These commands assume the new client is in `offline-client/` and uses pnpm.
Use the repository's pinned toolchain versions in CI; do not install a global
unversioned starter template.

```powershell
# JavaScript dependencies and Rust checks
pnpm install
pnpm lint
pnpm test
cargo test --manifest-path src-tauri/Cargo.toml
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets -- -D warnings

# Desktop development
pnpm tauri dev

# Windows installer
pnpm tauri build --bundles nsis,msi

# Linux packages
pnpm tauri build --bundles deb,appimage

# macOS disk image / app bundle (run on macOS)
pnpm tauri build --bundles dmg,app

# Android development and release APK/AAB (run with Android SDK configured)
pnpm tauri android init
pnpm tauri android dev
pnpm tauri android build --apk
pnpm tauri android build --aab

# iOS development and archive (run on macOS with Xcode)
pnpm tauri ios init
pnpm tauri ios dev
pnpm tauri ios build
```

The existing portable LibreOffice directory from the reference workspace is a
test fixture and validation source. Production installers should copy only the
platform-specific binaries and required resources into `vendor/libreoffice/`;
they should not depend on a user's Downloads directory.

## Delivery phases

### Phase A — Rust core proof

1. Create `offline-client/` and pin Rust, Node, pnpm, and Tauri versions.
2. Implement `InputHandle`, `JobId`, `JobProgress`, and `AppError` DTOs.
3. Integrate PDFium rendering and golden thumbnail tests.
4. Implement merge, split, reorder, rotate, delete, and export.
5. Add an offline network-deny integration test.

### Phase B — Editing and optimization

1. Add crop, watermark, page numbers, metadata, annotations, and signatures.
2. Add image-rs filters and PDF-to-image/image-to-PDF workflows.
3. Add lossless and quality-based compression with before/after metrics.
4. Add cancellation, bounded concurrency, and crash-safe atomic outputs.

### Phase C — Security and OCR

1. Integrate qpdf encryption/unlock behind a narrow Rust wrapper.
2. Implement content-rewriting redaction and redaction verification.
3. Bundle Tesseract/Leptonica language packs with explicit capability checks.
4. Add password hygiene and secure cleanup tests.

### Phase D — Desktop Office bridge

1. Bundle LibreOffice per desktop target with license notices.
2. Add unique-profile process isolation and timeout/cancellation handling.
3. Run the reference Unicode, malformed-input, overwrite, and concurrency
   matrices from the existing verification workspace.

### Phase E — Mobile hardening and release

1. Add Android/iOS file picker, share sheet, backgrounding, and storage tests.
2. Tune memory limits and low-battery profiles on real devices.
3. Produce signed Windows MSI/NSIS, Linux DEB/AppImage, macOS DMG, Android
   APK/AAB, and iOS archive builds.
4. Publish a feature matrix that clearly distinguishes desktop Office fidelity
   from mobile native document structuring.

## Acceptance checklist

- Airplane-mode smoke test completes merge, split, compress, image conversion,
  annotation, protect, unlock, and redaction.
- No network request is observable during a document job.
- A killed job leaves no readable input/password in the temp directory.
- Output verification rejects malformed or partial files.
- A 500-page thumbnail job remains responsive and can be cancelled.
- Redacted text is absent from extracted text and page content streams.
- The same golden fixtures pass on Windows, Linux, macOS, Android, and iOS
  within platform-specific rendering tolerances.
- Installers contain third-party notices and do not require a server account.
