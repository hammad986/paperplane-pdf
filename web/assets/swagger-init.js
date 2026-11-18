/* Kept as a same-origin script so deployment CSP does not need unsafe-inline. */
window.addEventListener('load', () => {
  if (typeof window.SwaggerUIBundle !== 'function') return;
  window.SwaggerUIBundle({
    url: '/spec/openapi.json',
    dom_id: '#swagger-ui',
    deepLinking: true,
    showExtensions: true,
    showCommonExtensions: true,
    presets: [
      window.SwaggerUIBundle.presets.apis,
      window.SwaggerUIBundle.SwaggerUIStandalonePreset,
    ],
    layout: 'BaseLayout',
  });
});
