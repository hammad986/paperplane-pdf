// Load the heavier PDF engines only when a PDF feature needs them.
(() => {
  const scriptPromises = new Map();
  let activeStudioRenderSession = null;

  function loadScript(src, globalName) {
    if (window[globalName]) return Promise.resolve(window[globalName]);
    if (scriptPromises.has(src)) return scriptPromises.get(src);

    const promise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.async = true;
      script.dataset.pdfRuntime = globalName;
      script.onload = () => window[globalName]
        ? resolve(window[globalName])
        : reject(new Error(`PDF runtime loaded without ${globalName}.`));
      script.onerror = () => {
        script.remove();
        scriptPromises.delete(src);
        reject(new Error(`Could not load ${globalName}.`));
      };
      document.head.appendChild(script);
    });
    scriptPromises.set(src, promise);
    return promise;
  }

  async function ensurePdfJs() {
    const pdfjsLib = await loadScript('/assets/pdf.min.js', 'pdfjsLib');
    pdfjsLib.GlobalWorkerOptions.workerSrc = '/assets/pdf.worker.min.js';
    return pdfjsLib;
  }

  async function ensurePdfLib() {
    return loadScript('/assets/pdf-lib.min.js', 'PDFLib');
  }

  async function createStudioRenderSession(bytes, password = '') {
    if (typeof Worker !== 'function' || typeof OffscreenCanvas !== 'function'
        || !(bytes instanceof ArrayBuffer) || bytes.byteLength > 64 * 1024 * 1024) return null;
    const worker = new Worker('/assets/studio_render_worker.js?v=4');
    let nextRequestId = 1;
    const pending = new Map();
    let closed = false;
    const rejectPending = error => {
      for (const request of pending.values()) {
        clearTimeout(request.timeout);
        request.reject(error);
      }
      pending.clear();
    };
    const failWorker = message => {
      if (closed) return;
      const error = new Error(message || 'Studio render worker failed.');
      error.name = 'StudioRenderWorkerError';
      rejectPending(error);
    };
    worker.onmessage = event => {
      const response = event.data || {};
      const request = pending.get(response.requestId);
      if (!request) {
        response.bitmap?.close?.();
        return;
      }
      pending.delete(response.requestId);
      clearTimeout(request.timeout);
      if (response.action === 'error') {
        const error = new Error(response.error || 'Studio page rendering failed.');
        error.name = response.errorName || 'StudioRenderWorkerError';
        request.reject(error);
      } else if (response.cancelled) {
        const error = new Error('Studio page rendering was cancelled.');
        error.name = 'RenderingCancelledException';
        request.reject(error);
      } else request.resolve(response);
    };
    worker.onerror = event => failWorker(event.message);
    const request = (action, payload = {}, transfer = [], timeoutMs = 30000) => {
      if (closed) return Promise.reject(new Error('Studio render worker is closed.'));
      const requestId = nextRequestId++;
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          pending.delete(requestId);
          reject(new Error(`Studio ${action} request timed out.`));
        }, timeoutMs);
        pending.set(requestId, { resolve, reject, timeout });
        try { worker.postMessage({ action, requestId, ...payload }, transfer); }
        catch (error) {
          pending.delete(requestId);
          clearTimeout(timeout);
          reject(error);
        }
      });
    };
    try {
      const transferable = bytes.slice(0);
      const opened = await request('open', { bytes: transferable, password }, [transferable], 60000);
      let session;
      const onPageHide = () => session.close();
      session = {
        pageCount: opened.pageCount,
        renderPage(pageNumber, scale, outputScale, rotation = 0, timeoutMs = 90000, priority = false) {
          const requestId = nextRequestId++;
          const promise = requestWithId(requestId, 'render', { pageNumber, scale, outputScale, rotation, priority }, [], timeoutMs);
          return {
            promise,
            cancel() {
              if (closed) return;
              try { worker.postMessage({ action: 'cancel', requestId: nextRequestId++, targetRequestId: requestId }); }
              catch { /* the render worker may have already shut down */ }
            },
          };
        },
        close() {
          if (closed) return;
          closed = true;
          if (activeStudioRenderSession === session) activeStudioRenderSession = null;
          window.removeEventListener('pagehide', onPageHide);
          rejectPending(new Error('Studio render worker closed.'));
          worker.terminate();
        },
      };
      function requestWithId(requestId, action, payload, transfer, timeoutMs) {
        if (closed) return Promise.reject(new Error('Studio render worker is closed.'));
        return new Promise((resolve, reject) => {
          const timeout = setTimeout(() => {
            pending.delete(requestId);
            reject(new Error(`Studio ${action} request timed out.`));
          }, timeoutMs);
          pending.set(requestId, { resolve, reject, timeout });
          try { worker.postMessage({ action, requestId, ...payload }, transfer); }
          catch (error) {
            pending.delete(requestId);
            clearTimeout(timeout);
            reject(error);
          }
        });
      }
      activeStudioRenderSession = session;
      window.addEventListener('pagehide', onPageHide, { once: true });
      return session;
    } catch (error) {
      closed = true;
      worker.terminate();
      rejectPending(error);
      throw error;
    }
  }

  async function transformLocalPdf(operation, files, options) {
    const buffers = await Promise.all(files.map(file => file.arrayBuffer()));
    return new Promise((resolve, reject) => {
      const worker = new Worker('/assets/local_pdf_worker.js?v=26');
      const release = () => {
        worker.terminate();
        window.removeEventListener('pagehide', onPageHide);
      };
      const onPageHide = () => {
        release();
        reject(new Error('Browser processing ended when the page closed.'));
      };
      window.addEventListener('pagehide', onPageHide, { once: true });
      worker.onmessage = event => {
        release();
        if (event.data.error) reject(new Error(event.data.error));
        else resolve(event.data);
      };
      worker.onerror = () => {
        release();
        reject(new Error('The browser PDF worker could not complete this operation.'));
      };
      try {
        worker.postMessage({ operation, files: buffers, options }, buffers);
      } catch (error) {
        release();
        reject(error);
      }
    });
  }

  window.PaperplanePdfRuntime = Object.freeze({
    transformLocalPdf,
    createStudioRenderSession,
    getStudioRenderSession: () => activeStudioRenderSession,
    ensurePdfJs,
    ensurePdfLib,
    ensurePdfTools: () => Promise.all([ensurePdfJs(), ensurePdfLib()])
  });
})();
