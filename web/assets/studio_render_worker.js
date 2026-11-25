/* PDF.js-backed Studio canvas renderer. The outer worker owns OffscreenCanvas,
   while a nested PDF.js worker parses and prepares page operator lists. */
importScripts('/assets/pdf.min.js');

// PDF.js 3.x still asks its DOMCanvasFactory for temporary canvases from
// inside a worker. Provide the canvas-only DOM surface it needs so those
// temporary surfaces are OffscreenCanvas instances too.
if (typeof self.document === 'undefined' && typeof OffscreenCanvas === 'function') {
  self.document = {
    createElement(name) {
      if (name !== 'canvas') throw new Error(`Unsupported worker DOM element: ${name}`);
      return new OffscreenCanvas(1, 1);
    },
  };
}

let loadingTask = null;
let pdfDocument = null;
let parserWorker = null;
let pdfWorker = null;
const renderQueue = [];
let renderQueueRunning = false;
let renderSequence = 0;
const activeRenders = new Map();
const cancelledRequests = new Set();

function reply(requestId, payload, transfer = []) {
  self.postMessage({ requestId, ...payload }, transfer);
}

async function closeDocument() {
  for (const renderTask of activeRenders.values()) {
    try { renderTask.cancel(); } catch { /* already completed */ }
  }
  activeRenders.clear();
  for (const queued of renderQueue.splice(0)) {
    cancelledRequests.add(queued.requestId);
    reply(queued.requestId, { action: 'rendered', cancelled: true });
  }
  try { await loadingTask?.destroy(); } catch { /* parser may already have stopped */ }
  loadingTask = null;
  pdfDocument = null;
  pdfWorker = null;
  parserWorker = null;
}

async function openDocument(requestId, { bytes, password }) {
  await closeDocument();
  if (typeof OffscreenCanvas === 'undefined') throw new Error('OffscreenCanvas is unavailable.');
  parserWorker = new Worker('/assets/pdf.worker.min.js');
  pdfWorker = new self.pdfjsLib.PDFWorker({ port: parserWorker });
  loadingTask = self.pdfjsLib.getDocument({
    data: new Uint8Array(bytes),
    isEvalSupported: false,
    // Worker rendering cannot reliably install document fonts with FontFace
    // in every browser. PDF.js's glyph-path renderer preserves embedded and
    // subset fonts without depending on a DOM font registry.
    disableFontFace: true,
    ...(typeof password === 'string' && password ? { password } : {}),
    worker: pdfWorker,
  });
  pdfDocument = await loadingTask.promise;
  reply(requestId, { action: 'opened', pageCount: pdfDocument.numPages });
}

async function renderPage(requestId, { pageNumber, scale, outputScale, rotation = 0 }) {
  if (cancelledRequests.delete(requestId)) {
    reply(requestId, { action: 'rendered', cancelled: true });
    return;
  }
  if (!pdfDocument) throw new Error('Studio render document is not open.');
  const page = await pdfDocument.getPage(pageNumber);
  if (cancelledRequests.delete(requestId)) {
    page.cleanup();
    reply(requestId, { action: 'rendered', cancelled: true });
    return;
  }
  const viewport = page.getViewport({ scale, rotation });
  const width = Math.max(1, Math.ceil(viewport.width * outputScale));
  const height = Math.max(1, Math.ceil(viewport.height * outputScale));
  const canvas = new OffscreenCanvas(width, height);
  const context = canvas.getContext('2d', { alpha: false });
  const renderTask = page.render({
    canvasContext: context,
    viewport,
    transform: outputScale === 1 ? null : [outputScale, 0, 0, outputScale, 0, 0],
  });
  activeRenders.set(requestId, renderTask);
  const started = performance.now();
  try {
    await renderTask.promise;
    if (cancelledRequests.delete(requestId)) {
      reply(requestId, { action: 'rendered', cancelled: true });
      return;
    }
    // A worker render can resolve successfully while returning a fully white
    // bitmap (for example when the browser's OffscreenCanvas PDF.js path fails
    // silently). Detect that before marking the Studio page as rendered so the
    // main-thread renderer can retry the same page instead of freezing a blank
    // canvas in the editor.
    const pixels = context.getImageData(0, 0, width, height).data;
    let hasVisibleInk = false;
    for (let index = 0; index < pixels.length; index += 4) {
      if (pixels[index] < 250 || pixels[index + 1] < 250 || pixels[index + 2] < 250) {
        hasVisibleInk = true;
        break;
      }
    }
    if (!hasVisibleInk) {
      throw new Error('Studio worker returned a blank page; retrying with the main-thread renderer.');
    }
    const bitmap = canvas.transferToImageBitmap();
    reply(requestId, {
      action: 'rendered', pageNumber, width, height,
      cssWidth: Math.ceil(viewport.width), cssHeight: Math.ceil(viewport.height),
      renderMilliseconds: Math.round(performance.now() - started), bitmap,
    }, [bitmap]);
  } finally {
    activeRenders.delete(requestId);
    page.cleanup();
  }
}

async function drainRenderQueue() {
  if (renderQueueRunning) return;
  renderQueueRunning = true;
  try {
    while (renderQueue.length) {
      renderQueue.sort((left, right) => right.priority - left.priority || left.sequence - right.sequence);
      const next = renderQueue.shift();
      try { await renderPage(next.requestId, next.payload); }
      catch (error) {
        reply(next.requestId, { action: 'error', error: error?.message || 'Studio page render failed.',
          errorName: error?.name || 'Error' });
      }
    }
  } finally {
    renderQueueRunning = false;
    if (renderQueue.length) void drainRenderQueue();
  }
}

self.onmessage = event => {
  const { action, requestId, ...payload } = event.data || {};
  if (!Number.isInteger(requestId)) return;
  if (action === 'open') {
    openDocument(requestId, payload).catch(error => reply(requestId, {
      action: 'error', error: error?.message || 'Studio render worker could not open this PDF.',
    }));
    return;
  }
  if (action === 'render') {
    renderQueue.push({ requestId, payload, priority: payload.priority ? 1 : 0, sequence: renderSequence++ });
    void drainRenderQueue();
    return;
  }
  if (action === 'cancel') {
    cancelledRequests.add(payload.targetRequestId);
    try { activeRenders.get(payload.targetRequestId)?.cancel(); } catch { /* task already finished */ }
    const queuedIndex = renderQueue.findIndex(item => item.requestId === payload.targetRequestId);
    if (queuedIndex >= 0) {
      renderQueue.splice(queuedIndex, 1);
      cancelledRequests.delete(payload.targetRequestId);
      reply(payload.targetRequestId, { action: 'rendered', cancelled: true });
    }
    return;
  }
  if (action === 'close') {
    closeDocument().finally(() => reply(requestId, { action: 'closed' }));
  }
};
