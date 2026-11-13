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

  window.PaperplanePdfRuntime = Object.freeze({
    ensurePdfJs,
    ensurePdfLib,
    ensurePdfTools: () => Promise.all([ensurePdfJs(), ensurePdfLib()])
  });
})();
