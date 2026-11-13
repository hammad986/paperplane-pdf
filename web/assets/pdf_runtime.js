// Load the heavier PDF engines only when a PDF feature needs them.
(() => {
  const scriptPromises = new Map();

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

  async function transformLocalPdf(operation, files, options) {
    const buffers = await Promise.all(files.map(file => file.arrayBuffer()));
    return new Promise((resolve, reject) => {
      const worker = new Worker('/assets/local_pdf_worker.js?v=13');
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
    ensurePdfJs,
    ensurePdfLib,
    ensurePdfTools: () => Promise.all([ensurePdfJs(), ensurePdfLib()])
  });
})();
