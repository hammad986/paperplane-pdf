// ======================================================================
// Paperplane PDF Platform  -  Next-Gen Enterprise Studio Controller
// ======================================================================

const state = {
  operations: {},
  operation: 'merge',
  category: 'Organize',
  files: [],
  user: null,
  clientSideMode: false,
  activeView: 'home', // 'home', 'desk', 'studio', 'ai'
  
  // PDF Studio Engine State
  studio: {
    pdfDoc: null,
    currentPage: 1,
    scale: 1.0,
    totalCount: 0,
    activeTool: 'pan', // 'pan', 'draw', 'highlight', 'text', 'redact'
    isDrawing: false,
    annotations: [], // array of draw paths and stamps per page
    drawContext: null
  }
};

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Category Grouping for Crisp Navigation
const CATEGORY_MAP = {
  'Organize': ['merge', 'split', 'remove', 'rotate', 'organize', 'scan_pdf'],
  'Convert': [
    'word_to_pdf', 'excel_to_pdf', 'powerpoint_to_pdf', 'jpg_to_pdf', 'html_to_pdf',
    'pdf_to_word', 'pdf_to_excel', 'pdf_to_powerpoint', 'pdf_to_jpg', 'pdf_to_pdfa',
    'pdf_to_text', 'pdf_to_markdown'
  ],
  'Edit': ['edit', 'annotate', 'sign', 'watermark', 'page_numbers', 'redact', 'crop'],
  'AI': ['ai_chat', 'ai_extract', 'summarize', 'translate', 'protect', 'unlock', 'compress', 'repair', 'ocr', 'compare', 'forms', 'metadata'],
  'All': [] // Dynamically holds all 37
};

// Stable public URLs shared with the FastAPI SEO router.  Internal operation
// ids remain unchanged so existing API payloads and local state keep working.
const TOOL_SLUGS = {
  merge: 'merge-pdf',
  split: 'split-pdf',
  remove: 'remove-pages-pdf',
  rotate: 'rotate-pdf',
  organize: 'organize-pdf',
  scan_pdf: 'scan-to-pdf',
  compress: 'compress-pdf',
  repair: 'repair-pdf',
  ocr: 'ocr-pdf',
  jpg_to_pdf: 'jpg-to-pdf',
  word_to_pdf: 'word-to-pdf',
  excel_to_pdf: 'excel-to-pdf',
  powerpoint_to_pdf: 'powerpoint-to-pdf',
  html_to_pdf: 'html-to-pdf',
  pdf_to_jpg: 'pdf-to-jpg',
  pdf_to_word: 'pdf-to-word',
  pdf_to_excel: 'pdf-to-excel',
  pdf_to_powerpoint: 'pdf-to-powerpoint',
  pdf_to_pdfa: 'pdf-to-pdfa',
  pdf_to_text: 'pdf-to-text',
  pdf_to_markdown: 'pdf-to-markdown',
  edit: 'edit-pdf',
  annotate: 'annotate-pdf',
  crop: 'crop-pdf',
  redact: 'redact-pdf',
  watermark: 'watermark-pdf',
  page_numbers: 'add-page-numbers-to-pdf',
  protect: 'protect-pdf',
  unlock: 'unlock-pdf',
  sign: 'sign-pdf',
  compare: 'compare-pdf',
  forms: 'fill-pdf-form',
  metadata: 'pdf-metadata',
  ai_chat: 'ai-pdf-chat',
  ai_extract: 'extract-pdf-data',
  summarize: 'summarize-pdf',
  translate: 'translate-pdf'
};
const OPERATION_BY_SLUG = Object.fromEntries(
  Object.entries(TOOL_SLUGS).map(([operation, slug]) => [slug, operation])
);

function operationPath(operation) {
  return `/${TOOL_SLUGS[operation] || operation}`;
}

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function showToast(message, type = 'success', duration = 3500) {
  const existing = $('.toast-notice');
  if (existing) existing.remove();
  const toast = document.createElement('div');
  const icon = type === 'success' ? 'OK' : type === 'error' ? '!' : type === 'warning' ? '•' : 'i';
  toast.className = `toast-notice toast-${type}`;
  toast.innerHTML = `<span style="font-weight: 700; font-size: 11px; padding: 1px 5px; border-radius: 3px; background: rgba(255,255,255,0.15);">${icon}</span> <span>${message}</span>`;
  document.body.appendChild(toast);
  setTimeout(() => {
    if (toast.parentNode) toast.remove();
  }, duration);
}

function triggerConfetti() {
  const styleId = 'paperplane-confetti-style';
  if (!document.getElementById(styleId)) {
    const style = document.createElement('style');
    style.id = styleId;
    style.textContent = `
      @keyframes paperplane-confetti-fall {
        0% { transform: translate3d(0, -12vh, 0) rotate(0deg); opacity: 1; }
        100% { transform: translate3d(var(--confetti-drift), 110vh, 0) rotate(720deg); opacity: 0; }
      }
      .paperplane-confetti-piece {
        position: fixed; top: 0; left: 50%; z-index: 10000;
        width: 8px; height: 13px; pointer-events: none;
        animation: paperplane-confetti-fall var(--confetti-duration) ease-in forwards;
      }
    `;
    document.head.appendChild(style);
  }

  const colors = ['#ff4b26', '#10b981', '#3b82f6', '#f59e0b', '#ec4899', '#ffffff'];
  const container = document.createDocumentFragment();
  for (let index = 0; index < 56; index += 1) {
    const piece = document.createElement('span');
    piece.className = 'paperplane-confetti-piece';
    piece.style.left = `${Math.random() * 100}%`;
    piece.style.background = colors[index % colors.length];
    piece.style.setProperty('--confetti-drift', `${Math.round((Math.random() - 0.5) * 260)}px`);
    piece.style.setProperty('--confetti-duration', `${2.1 + Math.random() * 1.6}s`);
    piece.style.transform = `rotate(${Math.round(Math.random() * 180)}deg)`;
    container.appendChild(piece);
    setTimeout(() => piece.remove(), 4200);
  }
  document.body.appendChild(container);
}

function showUserErrorModal(title, message, options = {}) {
  const modal = $('#error-modal');
  if (!modal) return;
  const iconEl = $('#error-dialog-icon');
  const titleEl = $('#error-dialog-title');
  const msgEl = $('#error-dialog-message');
  const actionsEl = $('#error-dialog-actions');

  if (iconEl) iconEl.textContent = options.icon || "Warning";
  if (titleEl) titleEl.textContent = title || 'Notice';
  if (msgEl) msgEl.textContent = message || 'An unexpected condition occurred.';

  if (actionsEl) {
    actionsEl.innerHTML = '';
    if (options.actionText && options.onAction) {
      const actBtn = document.createElement('button');
      actBtn.type = 'button';
      actBtn.className = 'btn-primary-action';
      actBtn.style.flex = '1';
      actBtn.style.justifyContent = 'center';
      actBtn.textContent = options.actionText;
      actBtn.onclick = () => {
        modal.hidden = true;
        options.onAction();
      };
      actionsEl.appendChild(actBtn);

      const cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.className = 'btn-demo-upgrade';
      cancelBtn.style.flex = '1';
      cancelBtn.textContent = 'Dismiss';
      cancelBtn.onclick = () => { modal.hidden = true; };
      actionsEl.appendChild(cancelBtn);
    } else {
      const okBtn = document.createElement('button');
      okBtn.type = 'button';
      okBtn.className = 'btn-primary-action';
      okBtn.style.width = '100%';
      okBtn.style.justifyContent = 'center';
      okBtn.textContent = 'Got It';
      okBtn.onclick = () => { modal.hidden = true; };
      actionsEl.appendChild(okBtn);
    }
  }

  modal.hidden = false;
}

function openUpgradeModal(contextMessage = '') {
  const modal = $('#upgrade-modal');
  if (!modal) return;
  const alertEl = $('#upgrade-context-alert');
  if (alertEl) {
    if (contextMessage) {
      alertEl.textContent = contextMessage;
      alertEl.hidden = false;
    } else {
      alertEl.hidden = true;
    }
  }
  const proBtn = $('#pro-cashfree-checkout-btn');
  if (proBtn) {
    proBtn.disabled = false;
    proBtn.innerHTML = 'Pay ₹250/month with Cashfree →';
  }
  const devBtn = $('#dev-cashfree-checkout-btn');
  if (devBtn) {
    devBtn.disabled = false;
    devBtn.innerHTML = 'Pay ₹750/month with Cashfree →';
  }
  modal.hidden = false;
}

function closeUpgradeModal() {
  const modal = $('#upgrade-modal');
  if (modal) modal.hidden = true;
}

// ----------------------------------------------------------------------
// Bulletproof Safe Fetch Wrapper
// ----------------------------------------------------------------------

async function safeFetch(url, options = {}) {
  options.headers = options.headers || {};
  const token = localStorage.getItem('paperplane_token');
  if (token && !options.headers['Authorization']) {
    options.headers['Authorization'] = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(url, options);
  } catch (netErr) {
    throw new Error(`Connection error: Could not reach server. (${netErr.message})`);
  }

  const contentType = response.headers.get('content-type') || '';
  let data;

  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch {
      data = { detail: 'Server returned an invalid JSON response.' };
    }
  } else {
    const rawText = await response.text();
    const cleanText = rawText.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
    data = { detail: cleanText.slice(0, 300) || `Server returned HTTP ${response.status} (${response.statusText})` };
  }

  if (!response.ok) {
    if (response.status === 401) {
      openAuthModal('Authentication required. Sign in or create an account to proceed.');
      throw new Error(data.detail || 'Authentication required.');
    }

    if (response.status === 402) {
      const errDetail = typeof data.detail === 'object' ? data.detail : data;
      const msg = errDetail.message || errDetail.detail || 'Daily operation limit reached on Free Tier.';
      openUpgradeModal(msg);
      throw new Error(msg);
    }

    if (response.status === 413) {
      const msg = 'File exceeds the 500 MB limit. Please select a smaller document or compress it first.';
      showUserErrorModal('File Size Limit Exceeded', msg, { icon: 'Archive' });
      throw new Error(msg);
    }

    const errorMsg = (typeof data.detail === 'string' ? data.detail : data.detail?.message) || data.error?.message || `Request failed with status ${response.status}`;
    throw new Error(errorMsg);
  }

  return data;
}

// ----------------------------------------------------------------------
// App Shell Layout & Sidebar Controller
// ----------------------------------------------------------------------

// Toggle Sidebar Collapse
$('#collapse-sidebar-btn').onclick = () => {
  $('#app-shell').classList.toggle('sidebar-collapsed');
};

// Workspace View Switcher (Home / Desk / Studio / AI / Legal / ApiDocs)
function switchWorkspaceView(view, extra = 'privacy', updateHistory = true) {
  state.activeView = view;
  $('#tab-home-view')?.classList.toggle('active', view === 'home');
  $('#tab-desk-view')?.classList.toggle('active', view === 'desk');
  $('#tab-studio-view')?.classList.toggle('active', view === 'studio');
  $('#tab-ai-view')?.classList.toggle('active', view === 'ai');
  $('#tab-download-view')?.classList.toggle('active', view === 'download');

  if ($('#view-home')) $('#view-home').hidden = view !== 'home';
  if ($('#view-tool-desk')) $('#view-tool-desk').hidden = view !== 'desk';
  if ($('#view-pdf-studio')) $('#view-pdf-studio').hidden = view !== 'studio';
  if ($('#view-ai-studio')) $('#view-ai-studio').hidden = view !== 'ai';
  if ($('#view-legal')) $('#view-legal').hidden = view !== 'legal';
  if ($('#view-api-docs')) $('#view-api-docs').hidden = view !== 'api-docs';
  if ($('#view-download')) $('#view-download').hidden = view !== 'download';
  $('.main-area')?.classList.toggle('studio-active', view === 'studio');

  // Strict SEO Content containment: Only display crawlable SEO sections on Home and Tool Desk views
  const seoSection = $('.seo-content');
  if (seoSection) {
    seoSection.style.display = (view === 'home' || view === 'desk') ? '' : 'none';
  }

  // Dynamic Topbar Breadcrumb updates
  const crumbCat = $('#crumb-category');
  const crumbTool = $('#crumb-tool');
  if (view === 'home') {
    $('#app-shell')?.classList.add('sidebar-collapsed');
    if (crumbCat) crumbCat.textContent = 'All Tools';
    if (crumbTool) crumbTool.textContent = 'Directory';
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (updateHistory && window.history.pushState && window.location.pathname !== '/') {
      window.history.pushState({ view: 'home' }, '', '/');
    }
  } else if (view === 'legal') {
    if (crumbCat) crumbCat.textContent = 'Compliance';
    const isTerms = extra === 'terms';
    if (crumbTool) crumbTool.textContent = isTerms ? 'Terms of Service' : 'Privacy Policy';
    switchFullLegalTab(extra);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (updateHistory && window.history.pushState) {
      const targetPath = isTerms ? '/terms' : '/privacy';
      if (window.location.pathname !== targetPath) {
        window.history.pushState({ view: 'legal', extra }, '', targetPath);
      }
    }
  } else if (view === 'api-docs') {
    if (crumbCat) crumbCat.textContent = 'Developers';
    if (crumbTool) crumbTool.textContent = 'REST API v2.0 Specifications';
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (updateHistory && window.history.pushState) {
      if (window.location.pathname !== '/api-docs') {
        window.history.pushState({ view: 'api-docs' }, '', '/api-docs');
      }
    }
  } else if (view === 'download') {
    if (crumbCat) crumbCat.textContent = 'Ecosystem';
    if (crumbTool) crumbTool.textContent = 'Native Desktop & Mobile Apps';
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (updateHistory && window.history.pushState) {
      if (window.location.pathname !== '/download') {
        window.history.pushState({ view: 'download' }, '', '/download');
      }
    }
  } else if (view === 'desk') {
    if (crumbCat) crumbCat.textContent = state.operations[state.operation]?.category || 'Organize PDF';
    if (crumbTool) crumbTool.textContent = state.operations[state.operation]?.label || 'Merge PDF';
    if (updateHistory && window.history.pushState) {
      const targetPath = operationPath(state.operation);
      if (window.location.pathname !== targetPath) {
        window.history.pushState({ view: 'desk', op: state.operation }, '', targetPath);
      }
    }
  } else if (view === 'studio') {
    if (crumbCat) crumbCat.textContent = 'Workspace';
    if (crumbTool) crumbTool.textContent = 'Advanced PDF Studio';
  } else if (view === 'ai') {
    if (crumbCat) crumbCat.textContent = 'Workspace';
    if (crumbTool) crumbTool.textContent = 'AI Document Intelligence';
    if (typeof updateAiDocBar === 'function') updateAiDocBar();
  }

  if (view === 'studio' && !state.studio.pdfDoc) {
    if (state.files.length && state.files[0].name.toLowerCase().endsWith('.pdf')) {
      loadDocumentIntoStudio(state.files[0]);
    } else {
      loadDocumentIntoStudio(null);
    }
  }

  // Update mobile bottom navigation bar active button
  const mobMap = {
    home: '#mob-nav-home',
    desk: '#mob-nav-desk',
    studio: '#mob-nav-studio',
    ai: '#mob-nav-ai'
  };
  $$('.mobile-nav-btn').forEach(b => b.classList.remove('active'));
  if (mobMap[view]) {
    $(mobMap[view])?.classList.add('active');
  }
}

// Navigation event bindings
$('#tab-home-view')?.addEventListener('click', () => switchWorkspaceView('home'));
$('#tab-desk-view')?.addEventListener('click', () => switchWorkspaceView('desk'));
$('#tab-studio-view')?.addEventListener('click', () => switchWorkspaceView('studio'));
$('#tab-ai-view')?.addEventListener('click', () => switchWorkspaceView('ai'));
$('#tab-download-view')?.addEventListener('click', () => switchWorkspaceView('download'));
$('#download-back-btn')?.addEventListener('click', () => switchWorkspaceView('home'));
$('#open-studio-btn')?.addEventListener('click', () => switchWorkspaceView('studio'));
$('#result-view-studio-btn')?.addEventListener('click', () => switchWorkspaceView('studio'));
$('#btn-back-to-home')?.addEventListener('click', () => switchWorkspaceView('home'));
$('#result-home-btn')?.addEventListener('click', () => switchWorkspaceView('home'));
$('#result-restart-btn')?.addEventListener('click', resetJobWorkflow);
$$('.brand').forEach(b => b.addEventListener('click', (e) => { e.preventDefault(); switchWorkspaceView('home'); }));

function resetJobWorkflow() {
  state.files = [];
  const form = $('#job-form');
  if (form) form.reset();
  renderFiles();
  renderOptions();
  updateButton();
  if ($('#progress-card')) $('#progress-card').hidden = true;
  if ($('#result')) $('#result').hidden = true;
  if ($('#dropzone')) $('#dropzone').hidden = false;
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Category Navigation Switcher in Sidebar
$$('.nav-category-tab').forEach(button => {
  button.onclick = () => {
    $$('.nav-category-tab').forEach(b => b.classList.remove('active'));
    button.classList.add('active');
    state.category = button.dataset.category;
    renderSidebarTools();
  };
});

function renderSidebarTools() {
  const container = $('#sidebar-tools-container');
  if (!container) return;
  const cat = state.category;
  let toolKeys = [];

  if (cat === 'All') {
    toolKeys = Object.keys(state.operations);
  } else {
    toolKeys = CATEGORY_MAP[cat] || [];
  }

  container.innerHTML = toolKeys.map(key => {
    const item = state.operations[key] || { label: key };
    const isActive = key === state.operation;
    return `
      <button type="button" class="sidebar-tool-item ${isActive ? 'active' : ''}" onclick="selectOperation('${key}')">
        ${item.label}
      </button>
    `;
  }).join('');
}

// ----------------------------------------------------------------------
// Home Page Tools Catalog & Categorical Discovery (iLovePDF Workflow)
// ----------------------------------------------------------------------

const HOME_CATEGORIES = [
  {
    id: 'organize',
    title: 'Organize PDF',
    badge: '6 Tools',
    iconColor: '#ff4b26',
    ops: ['merge', 'split', 'remove', 'rotate', 'organize', 'scan_pdf']
  },
  {
    id: 'optimize',
    title: 'Optimize PDF',
    badge: '3 Tools',
    iconColor: '#10b981',
    ops: ['compress', 'repair', 'ocr']
  },
  {
    id: 'convert',
    title: 'Convert PDF',
    badge: '12 Tools',
    iconColor: '#3b82f6',
    ops: [
      'pdf_to_word', 'word_to_pdf', 'pdf_to_excel', 'excel_to_pdf',
      'pdf_to_powerpoint', 'powerpoint_to_pdf', 'pdf_to_jpg', 'jpg_to_pdf',
      'html_to_pdf', 'pdf_to_pdfa', 'pdf_to_text', 'pdf_to_markdown'
    ]
  },
  {
    id: 'edit',
    title: 'Edit PDF',
    badge: '7 Tools',
    iconColor: '#f59e0b',
    ops: ['rotate', 'page_numbers', 'watermark', 'crop', 'compare', 'edit', 'annotate']
  },
  {
    id: 'security',
    title: 'Sign & Protect',
    badge: '5 Tools',
    iconColor: '#8b5cf6',
    ops: ['protect', 'unlock', 'sign', 'forms', 'redact']
  },
  {
    id: 'ai',
    title: 'PDF Intelligence',
    badge: '4 Tools',
    iconColor: '#ec4899',
    ops: ['ai_chat', 'summarize', 'ai_extract', 'translate']
  }
];

function getToolIconSvg(opId) {
  const icons = {
    merge: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="2" width="12" height="15" rx="2"></rect><rect x="8" y="7" width="12" height="15" rx="2"></rect><path d="M12 11h4"></path><path d="M14 9v4"></path></svg>`,
    split: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3v18"></path><path d="M18 3v18"></path><path d="m14 9-4 6"></path><circle cx="6" cy="6" r="3"></circle><circle cx="18" cy="18" r="3"></circle></svg>`,
    remove: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"></path><path d="M10 11v6"></path><path d="M14 11v6"></path><path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12"></path><path d="M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3"></path></svg>`,
    rotate: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.85.83 6.72 2.24L21 8"></path><path d="M21 3v5h-5"></path></svg>`,
    organize: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>`,
    scan_pdf: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7V5a2 2 0 0 1 2-2h2"></path><path d="M17 3h2a2 2 0 0 1 2 2v2"></path><path d="M21 17v2a2 2 0 0 1-2 2h-2"></path><path d="M7 21H5a2 2 0 0 1-2-2v-2"></path><line x1="7" y1="12" x2="17" y2="12"></line></svg>`,
    compress: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"></polyline><polyline points="20 10 14 10 14 4"></polyline><line x1="14" y1="10" x2="21" y2="3"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>`,
    repair: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m14.7 6.3 3 3-9.4 9.4H5.3v-3l9.4-9.4Z"></path><path d="M18 3a3 3 0 0 1 3 3c0 .8-.3 1.5-.8 2L18 6l-2-2 2-2c.5-.5 1.2-.8 2-.8Z"></path></svg>`,
    ocr: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"></path><circle cx="12" cy="12" r="3"></circle></svg>`,
    pdf_to_word: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="9" y1="15" x2="15" y2="15"></line></svg>`,
    word_to_pdf: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><path d="M9 13h6"></path></svg>`,
    protect: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>`,
    unlock: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 9.9-1"></path></svg>`,
    sign: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"></path><line x1="12" y1="11" x2="12" y2="17"></line></svg>`,
    watermark: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="m4.93 4.93 14.14 14.14"></path></svg>`,
    ai_chat: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>`,
    summarize: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>`,
    translate: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 8 6 6"></path><path d="m4 14 6-6 2-3"></path><path d="M2 5h12"></path><path d="M7 2h1"></path><path d="m22 22-5-10-5 10"></path><path d="M14 18h6"></path></svg>`
  };
  return icons[opId] || `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>`;
}

function renderHomeToolsGrid(filterCategory = 'all', searchQuery = '') {
  const catalogEl = $('#home-tools-catalog');
  if (!catalogEl) return;

  const normalizedQuery = searchQuery.trim().toLowerCase();
  let totalVisible = 0;
  let html = '';

  HOME_CATEGORIES.forEach(cat => {
    if (filterCategory !== 'all' && cat.id !== filterCategory) return;

    const visibleOps = cat.ops.filter(opId => {
      const op = state.operations[opId];
      if (!op) return false;
      if (!normalizedQuery) return true;
      return op.label.toLowerCase().includes(normalizedQuery) ||
             (op.description && op.description.toLowerCase().includes(normalizedQuery)) ||
             opId.toLowerCase().includes(normalizedQuery);
    });

    if (!visibleOps.length) return;
    totalVisible += visibleOps.length;

    html += `
      <section class="home-cat-section" data-cat="${cat.id}">
        <div class="home-cat-header">
          <div class="home-cat-title-group">
            <h2 class="home-cat-title" style="--cat-accent: ${cat.iconColor}">${cat.title}</h2>
            <span class="home-cat-count">${visibleOps.length} tools</span>
          </div>
        </div>
        <div class="home-cat-grid">
          ${visibleOps.map(opId => {
            const op = state.operations[opId];
            const isAvailable = op.available !== false && op.status !== 'DEPENDENCY_MISSING';
            const badgeText = isAvailable ? 'Ready' : (op.prerequisite || 'Engine Required');
            const badgeClass = isAvailable ? 'ready' : 'prereq';
            return `
              <div class="home-tool-card" role="button" tabindex="0" onclick="selectOperation('${opId}')" onkeydown="if(event.key==='Enter'||event.key===' ')selectOperation('${opId}')">
                <div class="home-tool-icon" style="background: ${cat.iconColor}1a; color: ${cat.iconColor};">
                  ${getToolIconSvg(opId)}
                </div>
                <div class="home-tool-body">
                  <h3 class="home-tool-title">${op.label}</h3>
                  <p class="home-tool-desc">${op.description || 'Fast, sovereign document processing.'}</p>
                  <div class="home-tool-footer">
                    <span class="home-status-badge ${badgeClass}">${badgeText}</span>
                    <span class="home-tool-arrow">→</span>
                  </div>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </section>
    `;
  });

  if (totalVisible === 0) {
    html = `
      <div class="home-no-results">
        <div class="no-results-icon">Search</div>
        <h3>No tools matched "${searchQuery}"</h3>
        <p>Try searching for "merge", "split", "word", "compress", or "sign".</p>
        <button type="button" class="btn-primary-action" onclick="resetHomeSearch()">Clear Search</button>
      </div>
    `;
  }

  catalogEl.innerHTML = html;

  const searchMeta = $('#home-search-meta');
  if (searchMeta) {
    if (normalizedQuery) {
      searchMeta.hidden = false;
      $('#home-search-count').textContent = totalVisible;
      $('#home-search-query').textContent = searchQuery;
    } else {
      searchMeta.hidden = true;
    }
  }
}

function initHomeSearchAndFilter() {
  const searchInput = $('#home-search-input');
  const clearBtn = $('#home-search-clear');
  const resetBtn = $('#home-reset-search-btn');

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      const q = searchInput.value;
      if (clearBtn) clearBtn.hidden = !q;
      const activePill = $('.home-filter-pills .filter-pill.active');
      const cat = activePill ? activePill.dataset.category : 'all';
      renderHomeToolsGrid(cat, q);
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener('click', resetHomeSearch);
  }
  if (resetBtn) {
    resetBtn.addEventListener('click', resetHomeSearch);
  }

  $$('.home-filter-pills .filter-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      $$('.home-filter-pills .filter-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      const cat = pill.dataset.category;
      const q = searchInput ? searchInput.value : '';
      renderHomeToolsGrid(cat, q);
    });
  });
}

function resetHomeSearch() {
  const searchInput = $('#home-search-input');
  if (searchInput) searchInput.value = '';
  const clearBtn = $('#home-search-clear');
  if (clearBtn) clearBtn.hidden = true;
  const activePill = $('.home-filter-pills .filter-pill.active');
  const cat = activePill ? activePill.dataset.category : 'all';
  renderHomeToolsGrid(cat, '');
}

function activateHomeCategoryFilter(category) {
  const normalized = String(category || 'all').toLowerCase();
  $$('.home-filter-pills .filter-pill').forEach(pill => {
    const active = pill.dataset.category === normalized;
    pill.classList.toggle('active', active);
    pill.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  renderHomeToolsGrid(normalized);
}

async function syncSeoContent(operation) {
  const section = $('.seo-content');
  if (!section || !operation) return;

  try {
    const context = await safeFetch(`/api/seo/${encodeURIComponent(operation)}`);
    const related = (context.related || []).map(relatedId => {
      const related = state.operations[relatedId] || { label: relatedId };
      const slug = TOOL_SLUGS[relatedId] || relatedId;
      return `<a class="seo-related-link" href="/${slug}">${escapeHtml(related.label)}</a>`;
    }).join(' ');
    const faqs = (context.faqs || []).map(([question, answer]) => (
      `<details class="seo-faq-item"><summary>${escapeHtml(question)}</summary><p>${escapeHtml(answer)}</p></details>`
    )).join('');
    const steps = (context.how_to || []).map((step, index) => (
      `<article class="seo-howto-step"><span>${String(index + 1).padStart(2, '0')}</span><h3>${escapeHtml(step)}</h3><p>${escapeHtml(step)}</p></article>`
    )).join('');

    section.innerHTML = `
      <div class="seo-content-inner">
        <div class="seo-eyebrow">${escapeHtml(context.category)} · privacy-first workflow</div>
        <h2 id="seo-page-heading">${escapeHtml(context.heading)}</h2>
        <p class="seo-lede">${escapeHtml(context.intro)}</p>
        <div class="seo-howto-grid">${steps}</div>
        <div class="seo-proof-grid">
          <article class="seo-proof-card"><h3>Zero-Upload Client Privacy Mode</h3><p>For ${escapeHtml(context.heading.toLowerCase())}, supported browser workflows can run locally with pdf-lib and WebAssembly so the source file never touches a server.</p></article>
          <article class="seo-proof-card"><h3>Built for practical PDF work</h3><p>The ${escapeHtml(context.heading.toLowerCase())} workflow keeps the relevant controls close to the upload queue so you can finish one document job without a heavyweight suite.</p></article>
          <article class="seo-proof-card"><h3>Transparent safety controls</h3><p>Before you download ${escapeHtml(context.heading.toLowerCase())} results, Paperplane validates the output and applies isolated storage, path containment, and lifecycle cleanup.</p></article>
        </div>
        <div class="seo-comparison" role="region" aria-label="PDF tool comparison">
          <h3>Why use Paperplane for ${escapeHtml(context.heading.toLowerCase())}?</h3>
          <div class="seo-comparison-table" role="table">
            <div class="seo-comparison-row seo-comparison-head" role="row"><span>Capability</span><span>Paperplane</span><span>Traditional desktop suites</span></div>
            <div class="seo-comparison-row" role="row"><span>Browser zero-upload processing</span><strong>Supported</strong><span>Usually unavailable</span></div>
            <div class="seo-comparison-row" role="row"><span>Dedicated ${escapeHtml(context.category)} URL</span><strong>One focused page</strong><span>One application shell</span></div>
            <div class="seo-comparison-row" role="row"><span>Installation required</span><strong>No for web workflows</strong><span>Often required</span></div>
          </div>
        </div>
        <div class="seo-faq"><h3>Frequently asked questions</h3>${faqs}</div>
        <nav class="seo-related" aria-label="Related PDF tools"><strong>Related tools</strong>${related}</nav>
      </div>`;
  } catch (error) {
    // Keep the server-rendered copy visible if a client-side refresh fails;
    // navigation must never blank the crawlable content surface.
    console.warn('Could not refresh SEO content for operation:', operation, error);
  }
}

// Select an operation and update view
function selectOperation(op, switchToDesk = true) {
  state.operation = op;
  const item = state.operations[op] || { label: op, accept: 'pdf', category: 'Organize PDF' };

  if ($('#crumb-tool')) $('#crumb-tool').textContent = item.label;
  if ($('#crumb-category')) $('#crumb-category').textContent = item.category;
  if ($('#tool-title')) $('#tool-title').textContent = item.label;
  if ($('#tool-hero-cat')) $('#tool-hero-cat').textContent = item.category;
  if ($('#tool-description')) $('#tool-description').textContent = item.description || 'Enterprise document workflow.';
  if ($('#desk-breadcrumb-label')) $('#desk-breadcrumb-label').textContent = `${item.category} / ${item.label}`;

  // Update input constraints
  const fileInput = $('#file-input');
  if (fileInput) {
    if (item.accept === 'image') {
      fileInput.accept = '.jpg,.jpeg,.png,.tiff,.webp';
    } else if (item.accept === 'office') {
      fileInput.accept = '.doc,.docx,.xls,.xlsx,.ppt,.pptx';
    } else if (item.accept === 'url') {
      fileInput.accept = '';
    } else {
      fileInput.accept = '.pdf';
    }
    fileInput.multiple = ['merge', 'jpg_to_pdf', 'compare', 'scan_pdf'].includes(op);
  }

  const hint = $('#file-hint');
  if (hint) {
    hint.textContent = `${item.accept === 'image' ? 'Images' : item.accept === 'office' ? 'Office documents' : 'PDF files'} up to 500 MB (batch up to 100 files)`;
  }

  renderOptions();
  renderSidebarTools();
  updateButton();
  if (op === 'ai_chat' && switchToDesk && state.activeView === 'home') {
    switchWorkspaceView('ai');
    showToast('Upload a PDF to start grounded AI Chat.', 'info');
    const aiInput = $('#ai-file-input');
    if (!state.files.length && aiInput) aiInput.click();
    return;
  }
  if (switchToDesk) {
    switchWorkspaceView('desk');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  if (switchToDesk || state.activeView === 'desk') {
    syncSeoContent(op);
  }

  // Close mobile sidebar drawer if open
  if (window.innerWidth <= 900) {
    closeMobileSidebar();
  }
}

// ----------------------------------------------------------------------
// Sticky Bottom-Left Profile & Auth Management
// ----------------------------------------------------------------------

function updateBillingUI(data) {
  const isPro = Boolean(data && data.is_pro);
  const isDev = Boolean(data && (data.is_dev || data.tier === 'developer'));
  const usage = data ? (data.usage_today || 0) : 0;
  const limit = data ? (data.limit || 100) : 100;
  state.dailyLimit = limit;

  const quotaText = $('#quota-text');
  const quotaFill = $('#quota-fill');
  const sidebarUpgradeBtn = $('#sidebar-upgrade-btn');
  const topbarUpgradeBtn = $('#topbar-upgrade-btn');
  const roleBadge = $('#user-role-badge');
  
  const settingsQuotaText = $('#settings-quota-text');
  const settingsQuotaFill = $('#settings-quota-fill');
  const settingsTierName = $('#settings-tier-name');
  const settingsTierBadge = $('#settings-tier-badge');

  if (isDev) {
    const label = 'Developer API';
    if (quotaText) quotaText.textContent = 'Unlimited (Developer)';
    if (quotaFill) {
      quotaFill.style.width = '100%';
      quotaFill.className = 'quota-progress-fill pro';
    }
    if (sidebarUpgradeBtn) sidebarUpgradeBtn.style.display = 'none';
    if (topbarUpgradeBtn) topbarUpgradeBtn.style.display = 'none';
    if (roleBadge) {
      roleBadge.textContent = label;
      roleBadge.style.color = '#3b82f6';
      roleBadge.style.fontWeight = '700';
    }
    if (settingsTierName) settingsTierName.textContent = 'Developer API Tier';
    if (settingsTierBadge) {
      settingsTierBadge.textContent = 'ACTIVE DEVELOPER PASS';
      settingsTierBadge.style.background = 'rgba(59, 130, 246, 0.15)';
      settingsTierBadge.style.color = '#3b82f6';
    }
    if (settingsQuotaText) settingsQuotaText.textContent = 'Unlimited Operations';
    if (settingsQuotaFill) {
      settingsQuotaFill.style.width = '100%';
      settingsQuotaFill.className = 'quota-progress-fill pro';
    }
  } else if (isPro) {
    const label = 'Pro Power User';
    if (quotaText) quotaText.textContent = 'Unlimited (Pro)';
    if (quotaFill) {
      quotaFill.style.width = '100%';
      quotaFill.className = 'quota-progress-fill pro';
    }
    if (sidebarUpgradeBtn) sidebarUpgradeBtn.style.display = 'none';
    if (topbarUpgradeBtn) topbarUpgradeBtn.style.display = 'none';
    if (roleBadge) {
      roleBadge.textContent = label;
      roleBadge.style.color = '#10b981';
      roleBadge.style.fontWeight = '700';
    }
    if (settingsTierName) settingsTierName.textContent = 'Pro Power User Tier';
    if (settingsTierBadge) {
      settingsTierBadge.textContent = 'ACTIVE PRO PASS';
      settingsTierBadge.style.background = 'rgba(16, 185, 129, 0.15)';
      settingsTierBadge.style.color = '#10b981';
    }
    if (settingsQuotaText) settingsQuotaText.textContent = 'Unlimited Operations';
    if (settingsQuotaFill) {
      settingsQuotaFill.style.width = '100%';
      settingsQuotaFill.className = 'quota-progress-fill pro';
    }
  } else {
    if (quotaText) quotaText.textContent = `${usage} / ${limit}`;
    const pct = Math.min(100, Math.round((usage / limit) * 100));
    if (quotaFill) {
      quotaFill.style.width = `${pct}%`;
      quotaFill.className = 'quota-progress-fill' + (usage >= limit ? ' full' : usage >= limit - 5 ? ' warn' : '');
    }
    if (sidebarUpgradeBtn) sidebarUpgradeBtn.style.display = 'flex';
    if (topbarUpgradeBtn) topbarUpgradeBtn.style.display = 'inline-flex';
    if (roleBadge) {
      roleBadge.textContent = 'Free Sovereign Tier';
      roleBadge.style.color = '';
      roleBadge.style.fontWeight = '';
    }
    if (settingsTierName) settingsTierName.textContent = 'Free Sovereign Tier';
    if (settingsTierBadge) {
      settingsTierBadge.textContent = 'FREE SOVEREIGN';
      settingsTierBadge.style.background = '';
      settingsTierBadge.style.color = '';
    }
    if (settingsQuotaText) settingsQuotaText.textContent = `${usage} / ${limit}`;
    if (settingsQuotaFill) {
      settingsQuotaFill.style.width = `${pct}%`;
      settingsQuotaFill.className = 'quota-progress-fill' + (usage >= limit ? ' full' : usage >= limit - 5 ? ' warn' : '');
    }
  }
}

async function checkAuthStatus() {
  try {
    const data = await safeFetch('/api/auth/me');
    updateBillingUI(data);
    if (data.authenticated) {
      state.user = data;
      const initial = (data.email[0] || 'U').toUpperCase();
      $('#user-avatar').textContent = initial;
      $('#user-name').textContent = data.email;
      if ($('#topbar-auth-guest')) $('#topbar-auth-guest').hidden = true;
      if ($('#topbar-auth-user')) $('#topbar-auth-user').hidden = false;
      if ($('#topbar-avatar')) $('#topbar-avatar').textContent = initial;
      if ($('#topbar-username')) $('#topbar-username').textContent = data.email;
      
      const sAvatar = $('#settings-user-avatar');
      const sEmail = $('#settings-user-email');
      const sBadge = $('#settings-user-badge');
      if (sAvatar) sAvatar.textContent = initial;
      if (sEmail) sEmail.textContent = data.email;
      if (sBadge) {
        sBadge.textContent = data.is_dev ? 'Developer API Tier' : data.is_pro ? 'Pro Power User Tier' : 'Free Sovereign Tier (100 files/day)';
      }
      if ($('#settings-guest-actions')) $('#settings-guest-actions').hidden = true;
      if ($('#settings-user-actions')) $('#settings-user-actions').hidden = false;
    } else {
      state.user = null;
      $('#user-avatar').textContent = 'G';
      $('#user-name').textContent = 'Guest Explorer';
      if ($('#topbar-auth-guest')) $('#topbar-auth-guest').hidden = false;
      if ($('#topbar-auth-user')) $('#topbar-auth-user').hidden = true;
      if ($('#topbar-avatar')) $('#topbar-avatar').textContent = 'G';
      if ($('#topbar-username')) $('#topbar-username').textContent = 'Guest Explorer';
      if ($('#settings-user-avatar')) $('#settings-user-avatar').textContent = 'G';
      if ($('#settings-user-email')) $('#settings-user-email').textContent = 'Guest Explorer';
      if ($('#settings-user-badge')) $('#settings-user-badge').textContent = 'Free Sovereign Tier · 100 free files/day';
      if ($('#settings-guest-actions')) $('#settings-guest-actions').hidden = false;
      if ($('#settings-user-actions')) $('#settings-user-actions').hidden = true;
    }
  } catch {
    state.user = null;
    $('#user-avatar').textContent = 'G';
    $('#user-name').textContent = 'Guest Explorer';
    if ($('#topbar-auth-guest')) $('#topbar-auth-guest').hidden = false;
    if ($('#topbar-auth-user')) $('#topbar-auth-user').hidden = true;
    if ($('#topbar-avatar')) $('#topbar-avatar').textContent = 'G';
    if ($('#topbar-username')) $('#topbar-username').textContent = 'Guest Explorer';
    updateBillingUI(null);
  }
}

// ----------------------------------------------------------------------
// Settings Modal Controller (Tabbed Architecture)
// ----------------------------------------------------------------------

function openSettingsModal(defaultTab = 'account') {
  const modal = $('#settings-modal');
  if (!modal) return;
  modal.hidden = false;
  switchSettingsTab(defaultTab);
}

function switchSettingsTab(tabName) {
  $$('.settings-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });
  $$('.settings-pane').forEach(pane => {
    pane.hidden = pane.id !== `pane-${tabName}`;
  });

  if (tabName === 'api') {
    loadSettingsApiKeys();
  }
}

// Wire Settings Tabs
$$('.settings-tab-btn').forEach(btn => {
  btn.onclick = () => switchSettingsTab(btn.dataset.tab);
});

// Wire Sidebar Profile Card and Settings Gear Icon
if ($('#sidebar-settings-gear-btn')) {
  $('#sidebar-settings-gear-btn').onclick = () => openSettingsModal('account');
}
if ($('#sidebar-profile-card')) {
  $('#sidebar-profile-card').onclick = () => openSettingsModal('account');
}
if ($('#close-settings-modal')) {
  $('#close-settings-modal').onclick = () => $('#settings-modal').hidden = true;
}

// Account actions in Settings
if ($('#settings-signin-btn')) {
  $('#settings-signin-btn').onclick = () => {
    $('#settings-modal').hidden = true;
    openAuthModal();
    if ($('#tab-login')) $('#tab-login').click();
  };
}
if ($('#settings-register-btn')) {
  $('#settings-register-btn').onclick = () => {
    $('#settings-modal').hidden = true;
    openAuthModal();
    if ($('#tab-register')) $('#tab-register').click();
  };
}
if ($('#settings-signout-btn')) {
  $('#settings-signout-btn').onclick = () => {
    localStorage.removeItem('paperplane_token');
    document.cookie = 'paperplane_token=; path=/; max-age=0; SameSite=Lax';
    checkAuthStatus();
    $('#settings-modal').hidden = true;
    showToast('Signed out of Paperplane.');
  };
}

// Appearance Theme Controls in Settings
function applyTheme(themeName) {
  document.body.classList.remove('dark-mode', 'light-mode');
  if (themeName === 'light') {
    document.body.classList.add('light-mode');
    $('#theme-light-btn')?.classList.add('active');
    $('#theme-dark-btn')?.classList.remove('active');
  } else {
    document.body.classList.add('dark-mode');
    $('#theme-dark-btn')?.classList.add('active');
    $('#theme-light-btn')?.classList.remove('active');
  }
  localStorage.setItem('paperplane_theme', themeName);
}

if ($('#theme-dark-btn')) $('#theme-dark-btn').onclick = () => applyTheme('dark');
if ($('#theme-light-btn')) $('#theme-light-btn').onclick = () => applyTheme('light');
if ($('#contrast-toggle-input')) {
  $('#contrast-toggle-input').onchange = e => {
    document.body.classList.toggle('sharp-contrast', e.target.checked);
  };
}

// Initialize Theme from localStorage
const savedTheme = localStorage.getItem('paperplane_theme') || 'light';
applyTheme(savedTheme);

// Billing actions in Settings
if ($('#settings-upgrade-plan-btn')) {
  $('#settings-upgrade-plan-btn').onclick = () => {
    $('#settings-modal').hidden = true;
    openUpgradeModal();
  };
}

// Settings API Keys Loader & Creator
async function loadSettingsApiKeys() {
  const list = $('#settings-api-keys-list');
  if (!list) return;
  list.innerHTML = '<div style="color: var(--text-muted); font-size: 12.5px; padding: 10px;">Loading active API keys…</div>';

  try {
    const data = await safeFetch('/api/developer/keys');
    if (!data.keys || !data.keys.length) {
      list.innerHTML = '<div style="color: var(--text-muted); font-size: 12.5px; padding: 10px;">No active API keys found. Generate a dedicated key below.</div>';
      return;
    }
    list.innerHTML = data.keys.map(k => `
      <div class="file-row-card">
        <div>
          <strong>${k.name}</strong> · <code style="font-family: var(--font-mono); font-size: 11px;">${k.key_prefix}</code>
          <small style="display: block; color: var(--text-muted);">Created: ${new Date(k.created_at * 1000).toLocaleDateString()}</small>
        </div>
        <button type="button" class="delete-file-btn" onclick="revokeKey('${k.id}')" title="Revoke API Key"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
    `).join('');
  } catch (err) {
    list.innerHTML = `<div class="result-card error">${err.message}</div>`;
  }
}

if ($('#settings-create-key-form')) {
  $('#settings-create-key-form').onsubmit = async e => {
    e.preventDefault();
    const name = $('#settings-key-name').value.trim();
    const form = new FormData();
    form.append('name', name);
    try {
      const data = await safeFetch('/api/developer/keys', { method: 'POST', body: form });
      const alertEl = $('#settings-new-key-alert');
      alertEl.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
          <strong>API Key Generated:</strong>
          <button type="button" class="btn-primary-action" style="padding: 4px 10px; font-size: 11px;" onclick="copyToClipboard('${data.api_key}')"> Copy Key</button>
        </div>
        <code style="display: block; background: #fff; color: #111; padding: 8px 12px; margin: 8px 0; border: 1px solid var(--border-light); border-radius: 6px; font-weight: bold; word-break: break-all; font-family: var(--font-mono); cursor: pointer;" onclick="copyToClipboard('${data.api_key}')" title="Click to copy">${data.api_key}</code>
        <small style="color: var(--text-muted);">Store this secret key securely. It cannot be shown again.</small>
      `;
      alertEl.hidden = false;
      $('#settings-key-name').value = '';
      loadSettingsApiKeys();
      showToast('Dedicated REST API key generated!', 'success');
    } catch (err) {
      showToast(err.message, 'error');
    }
  };
}

// Zero-Upload Client-Side WASM Toggle
function setClientSideMode(enabled) {
  state.clientSideMode = enabled;
  ['client-privacy-toggle', 'settings-client-privacy-toggle'].forEach(id => {
    const input = $(`#${id}`);
    if (input) input.checked = enabled;
  });
  const pill = $('#engine-status-pill');
  const label = $('#privacy-mode-label');
  const text = $('#engine-status-text');

  if (state.clientSideMode) {
    if (pill) pill.className = 'engine-pill wasm';
    if (text) text.textContent = 'Zero-Upload WASM';
    if (label) label.textContent = 'Zero-Upload WASM';
    showToast('100% Client-Side Privacy Mode Activated (Zero Uploads).');
  } else {
    if (pill) pill.className = 'engine-pill';
    if (text) text.textContent = 'Server Fast Queue';
    if (label) label.textContent = 'Server Mode';
    showToast('Server High-Speed Engine Active.');
  }
  updateButton();
}
$('#client-privacy-toggle').onchange = e => setClientSideMode(e.target.checked);
$('#settings-client-privacy-toggle').onchange = e => setClientSideMode(e.target.checked);

if ($('#theme-toggle')) {
  $('#theme-toggle').onclick = () => {
    document.body.classList.toggle('high-contrast');
  };
}

// ----------------------------------------------------------------------
// Command Palette & Global Search (Ctrl+K)
// ----------------------------------------------------------------------

function openCommandPalette() {
  $('#command-modal').hidden = false;
  $('#command-input').value = '';
  $('#command-input').focus();
  renderCommandResults('');
}

function closeAllModals() {
  if ($('#command-modal')) $('#command-modal').hidden = true;
  if ($('#settings-modal')) $('#settings-modal').hidden = true;
  if ($('#auth-modal')) $('#auth-modal').hidden = true;
  if ($('#cloud-modal')) $('#cloud-modal').hidden = true;
  if ($('#upgrade-modal')) $('#upgrade-modal').hidden = true;
  if ($('#error-modal')) $('#error-modal').hidden = true;
}

if ($('#sidebar-search-trigger')) $('#sidebar-search-trigger').onclick = openCommandPalette;
if ($('#topbar-search-btn')) $('#topbar-search-btn').onclick = openCommandPalette;
if ($('#close-command-btn')) $('#close-command-btn').onclick = () => {
  if ($('#command-modal')) $('#command-modal').hidden = true;
};

window.onkeydown = e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    openCommandPalette();
  } else if (e.key === 'Escape') {
    closeAllModals();
  }
};

$('#command-input').oninput = e => renderCommandResults(e.target.value.trim());

function renderCommandResults(query) {
  const container = $('#command-results');
  const q = query.toLowerCase();
  const matches = Object.entries(state.operations).filter(([key, item]) => {
    return key.toLowerCase().includes(q) || item.label.toLowerCase().includes(q) || (item.description || '').toLowerCase().includes(q);
  });

  if (!matches.length) {
    container.innerHTML = '<div style="padding: 24px; text-align: center; color: var(--text-muted); font-size: 13px;">No matching tools found.</div>';
    return;
  }

  container.innerHTML = matches.map(([key, item]) => `
    <div class="command-item" onclick="selectOperationFromCommand('${key}')">
      <div class="command-item-left">
        <span style="font-weight: 700; color: var(--brand-accent);">API</span>
        <div>
          <strong>${item.label}</strong>
          <small style="display: block;">${item.description || 'Production workflow'}</small>
        </div>
      </div>
      <span class="command-item-badge">${item.category}</span>
    </div>
  `).join('');
}

window.selectOperationFromCommand = key => {
  selectOperation(key);
  $('#command-modal').hidden = true;
};

// ----------------------------------------------------------------------
// In-App PDF Studio (Viewer & Editor via PDF.js)
// ----------------------------------------------------------------------

if (typeof pdfjsLib !== 'undefined') {
  pdfjsLib.GlobalWorkerOptions.workerSrc = '/assets/pdf.worker.min.js';
}

async function loadDocumentIntoStudio(file) {
  const container = $('#studio-thumbnails-container');
  container.innerHTML = '<div style="color: #fff; font-size: 12px; text-align: center; padding: 20px;">Rendering studio previews…</div>';

  try {
    let arrayBuffer;
    if (typeof file === 'string' && file !== '/assets/demo.pdf') {
      const resp = await fetch(file);
      arrayBuffer = await resp.arrayBuffer();
    } else if (file && (file instanceof Blob || file instanceof File)) {
      arrayBuffer = await file.arrayBuffer();
    } else {
      // Create a clean, single blank A4 PDF page dynamically when no document is uploaded
      if (typeof PDFLib !== 'undefined') {
        const blankDoc = await PDFLib.PDFDocument.create();
        blankDoc.addPage([595.28, 841.89]);
        const pdfBytes = await blankDoc.save();
        arrayBuffer = pdfBytes.buffer;
      } else {
        const resp = await fetch('/assets/demo.pdf');
        arrayBuffer = await resp.arrayBuffer();
      }
    }
    state.studio.pdfDoc = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    state.studio.totalCount = state.studio.pdfDoc.numPages;
    state.studio.currentPage = 1;
    $('#studio-page-count').textContent = state.studio.totalCount;

    // Load into Phase 2 PaperplaneEditor
    let srcFile = file;
    if (!srcFile || typeof srcFile === 'string') {
      srcFile = new File([arrayBuffer], (file && file.name) || 'document.pdf', { type: 'application/pdf' });
    }
    if (window.PaperplaneEditor) {
      window.PaperplaneEditor.loadDocument(srcFile, srcFile.name, state.studio.totalCount);
    }

    // Render Page 1 on canvas
    await renderStudioPage(1);

    // Load into Phase 3 Professional Page Organizer
    if (window.PaperplanePageOrganizer) {
      window.PaperplanePageOrganizer.loadDocument(state.studio.pdfDoc, srcFile, srcFile.name, state.studio.totalCount);
    } else {
      renderStudioThumbnails();
    }
  } catch (err) {
    container.innerHTML = `<div style="color: #ff6b6b; font-size: 11px; padding: 12px;">Failed to load PDF in Studio: ${err.message}</div>`;
  }
}

async function renderStudioPage(pageNum) {
  if (!state.studio.pdfDoc) return;
  state.studio.currentPage = pageNum;
  $('#page-indicator').textContent = `${pageNum} / ${state.studio.totalCount}`;

  if (window.PaperplanePageOrganizer && window.PaperplanePageOrganizer.state) {
    window.PaperplanePageOrganizer.state.activePage = pageNum;
    window.PaperplanePageOrganizer._updateCardStates();
  }

  const page = await state.studio.pdfDoc.getPage(pageNum);
  const canvas = $('#pdf-canvas');
  const drawCanvas = $('#pdf-draw-canvas');
  const ctx = canvas.getContext('2d');

  let scale = state.studio.scale;
  if (scale === 'fit-width') {
    const containerWidth = $('#studio-canvas-area').clientWidth - 64;
    const baseViewport = page.getViewport({ scale: 1.0 });
    scale = containerWidth / baseViewport.width;
  } else {
    scale = Number(scale);
  }

  const viewport = page.getViewport({ scale: scale });
  const outputScale = window.devicePixelRatio || 1;

  canvas.width = Math.floor(viewport.width * outputScale);
  canvas.height = Math.floor(viewport.height * outputScale);
  canvas.style.width = Math.floor(viewport.width) + "px";
  canvas.style.height = Math.floor(viewport.height) + "px";

  drawCanvas.width = canvas.width;
  drawCanvas.height = canvas.height;
  drawCanvas.style.width = canvas.style.width;
  drawCanvas.style.height = canvas.style.height;

  const transform = outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : null;
  const renderContext = { canvasContext: ctx, transform: transform, viewport: viewport };
  await page.render(renderContext).promise;

  // Initialize and synchronize Phase 2 Editor overlay
  if (window.PaperplaneEditor) {
    const baseVp = page.getViewport({ scale: 1.0 });
    window.PaperplaneEditor.onPageRendered(
      canvas,
      drawCanvas,
      $('#page-render-wrapper'),
      scale,
      pageNum,
      baseVp.width,
      baseVp.height
    );
  } else {
    initStudioDrawingLayer();
  }
}

async function renderStudioThumbnails() {
  const container = $('#studio-thumbnails-container');
  container.innerHTML = '';

  for (let i = 1; i <= state.studio.totalCount; i++) {
    const page = await state.studio.pdfDoc.getPage(i);
    const viewport = page.getViewport({ scale: 0.25 });
    
    const card = document.createElement('div');
    card.className = `thumb-card ${i === state.studio.currentPage ? 'active' : ''}`;
    card.dataset.page = i;

    const thumbCanvas = document.createElement('canvas');
    thumbCanvas.width = viewport.width;
    thumbCanvas.height = viewport.height;
    const thumbCtx = thumbCanvas.getContext('2d');

    await page.render({ canvasContext: thumbCtx, viewport: viewport }).promise;

    card.innerHTML = `
      <div class="thumb-card-footer">
        <span>Page ${i}</span>
        <div class="thumb-actions">
          <button type="button" class="thumb-action-btn" title="Rotate 90°">⟳</button>
        </div>
      </div>
    `;
    card.insertBefore(thumbCanvas, card.firstChild);

    card.onclick = (e) => {
      if (e.target.tagName.toLowerCase() === 'button') return;
      $$('.thumb-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      renderStudioPage(i);
    };

    container.appendChild(card);
  }
}

// Studio Document Open Button
const studioUploadBtn = $('#studio-upload-btn');
const studioFileInput = $('#studio-file-input');
if (studioUploadBtn && studioFileInput) {
  studioUploadBtn.onclick = () => {
    if (!state.user && !state.token) {
      showToast('Please sign in or create an account to edit PDF documents.', 'warning');
      openAuthModal('login');
      return;
    }
    studioFileInput.click();
  };
  studioFileInput.onchange = (e) => {
    const file = e.target.files[0];
    if (file) {
      loadDocumentIntoStudio(file);
      showToast(`Loaded ${file.name} into Studio!`);
    }
  };
}

// Studio Navigation & Zoom Controls
$('#prev-page-btn').onclick = () => {
  if (state.studio.currentPage > 1) {
    renderStudioPage(state.studio.currentPage - 1);
  }
};

$('#next-page-btn').onclick = () => {
  if (state.studio.currentPage < state.studio.totalCount) {
    renderStudioPage(state.studio.currentPage + 1);
  }
};

$('#zoom-in-btn').onclick = () => {
  const current = Number(state.studio.scale) || 1.0;
  state.studio.scale = Math.min(2.5, current + 0.25);
  $('#zoom-select').value = state.studio.scale.toString();
  renderStudioPage(state.studio.currentPage);
};

$('#zoom-out-btn').onclick = () => {
  const current = Number(state.studio.scale) || 1.0;
  state.studio.scale = Math.max(0.5, current - 0.25);
  $('#zoom-select').value = state.studio.scale.toString();
  renderStudioPage(state.studio.currentPage);
};

$('#zoom-select').onchange = e => {
  state.studio.scale = e.target.value;
  renderStudioPage(state.studio.currentPage);
};

// Natural Smooth Wheel Scrolling & Ctrl+Wheel Zoom in Studio Viewport
const studioCanvasArea = $('#studio-canvas-area');
if (studioCanvasArea) {
  studioCanvasArea.addEventListener('wheel', e => {
    if (e.ctrlKey) {
      e.preventDefault();
      const current = Number(state.studio.scale) || 1.0;
      const delta = e.deltaY < 0 ? 0.15 : -0.15;
      const newScale = Math.max(0.5, Math.min(3.0, +(current + delta).toFixed(2)));
      state.studio.scale = newScale;
      const zoomSelect = $('#zoom-select');
      if (zoomSelect) zoomSelect.value = newScale.toString();
      renderStudioPage(state.studio.currentPage);
    }
  }, { passive: false });
}

const drawCanvasEl = $('#pdf-draw-canvas');
if (drawCanvasEl) {
  drawCanvasEl.addEventListener('wheel', e => {
    if (e.ctrlKey) {
      e.preventDefault();
      const current = Number(state.studio.scale) || 1.0;
      const delta = e.deltaY < 0 ? 0.15 : -0.15;
      const newScale = Math.max(0.5, Math.min(3.0, +(current + delta).toFixed(2)));
      state.studio.scale = newScale;
      const zoomSelect = $('#zoom-select');
      if (zoomSelect) zoomSelect.value = newScale.toString();
      renderStudioPage(state.studio.currentPage);
    } else if (studioCanvasArea) {
      if (e.deltaX) studioCanvasArea.scrollLeft += e.deltaX;
      if (e.deltaY) studioCanvasArea.scrollTop += e.deltaY;
    }
  }, { passive: false });
}

// Phase 2: Professional PDF Editor Suite Integration
const studioTools = [
  'select', 'pan', 'text', 'image', 'rect', 'ellipse',
  'arrow', 'draw', 'sig', 'stamp', 'highlight', 'redact'
];

const toolMapping = {
  'select': 'select',
  'pan': 'pan',
  'text': 'text',
  'image': 'image',
  'rect': 'rectangle',
  'ellipse': 'ellipse',
  'arrow': 'arrow',
  'draw': 'drawing',
  'sig': 'signature',
  'stamp': 'stamp',
  'highlight': 'highlight',
  'redact': 'redact'
};

studioTools.forEach(t => {
  const btn = $(`#tool-${t}-btn`);
  if (btn) {
    btn.onclick = () => {
      studioTools.forEach(x => $(`#tool-${x}-btn`)?.classList.remove('active'));
      btn.classList.add('active');
      const mapped = toolMapping[t] || t;
      state.studio.activeTool = mapped;
      if (window.PaperplaneEditor) {
        window.PaperplaneEditor.setTool(mapped);
      }
      const drawCanvas = $('#pdf-draw-canvas');
      if (drawCanvas) {
        drawCanvas.style.pointerEvents = t === 'pan' ? 'none' : 'auto';
        drawCanvas.style.cursor = t === 'pan' ? 'default' : t === 'select' ? 'default' : 'crosshair';
      }
    };
  }
});

// Color and stroke controls
$('#editor-color-picker')?.addEventListener('input', e => {
  if (window.PaperplaneEditor) window.PaperplaneEditor.setColor(e.target.value);
});

$('#editor-stroke-width')?.addEventListener('change', e => {
  if (window.PaperplaneEditor) window.PaperplaneEditor.setStrokeWidth(Number(e.target.value));
});

// Object actions
$('#editor-delete-obj-btn')?.addEventListener('click', () => {
  if (window.PaperplaneEditor?.canvas) window.PaperplaneEditor.canvas.deleteSelected();
});

// Undo & Redo buttons
$('#editor-undo-btn')?.addEventListener('click', () => {
  if (window.PaperplaneEditor) window.PaperplaneEditor.undo();
});

$('#editor-redo-btn')?.addEventListener('click', () => {
  if (window.PaperplaneEditor) window.PaperplaneEditor.redo();
});

// Clear canvas button
$('#clear-canvas-btn')?.addEventListener('click', () => {
  if (window.PaperplaneEditor) {
    if (confirm('Clear all annotations on this page?')) {
      window.PaperplaneEditor.clearPage(state.studio.currentPage);
    }
  }
});

// Page operations
$('#editor-insert-page-btn')?.addEventListener('click', async () => {
  if (!window.PaperplaneEditor) return;
  const newFile = await window.PaperplaneEditor.insertBlankPage(state.studio.currentPage);
  if (newFile) {
    state.files = [newFile];
    await initStudioViewer(newFile);
  }
});

$('#editor-dup-page-btn')?.addEventListener('click', async () => {
  if (!window.PaperplaneEditor) return;
  const newFile = await window.PaperplaneEditor.duplicatePage(state.studio.currentPage);
  if (newFile) {
    state.files = [newFile];
    await initStudioViewer(newFile);
  }
});

$('#editor-delete-page-btn')?.addEventListener('click', async () => {
  if (!window.PaperplaneEditor) return;
  if (confirm(`Delete page ${state.studio.currentPage}?`)) {
    const newFile = await window.PaperplaneEditor.deletePage(state.studio.currentPage);
    if (newFile) {
      state.files = [newFile];
      await initStudioViewer(newFile);
    }
  }
});

// Export / Save PDF Button
$('#save-studio-btn')?.addEventListener('click', async () => {
  if (window.PaperplaneEditor && window.PaperplaneEditor.editorState.sourceFile) {
    await window.PaperplaneEditor.exportPDF();
  } else {
    showToast('No PDF loaded in editor.', 'error');
  }
});

// Wire Phase 2 Text Floating Panel
const textPanel = $('#editor-text-panel');
if (textPanel) {
  $('#editor-cancel-text-btn')?.addEventListener('click', () => {
    textPanel.hidden = true;
  });

  let textBold = false;
  let textItalic = false;

  $('#editor-text-bold')?.addEventListener('click', e => {
    textBold = !textBold;
    e.currentTarget.classList.toggle('active', textBold);
  });

  $('#editor-text-italic')?.addEventListener('click', e => {
    textItalic = !textItalic;
    e.currentTarget.classList.toggle('active', textItalic);
  });

  $('#editor-place-text-btn')?.addEventListener('click', () => {
    const input = $('#editor-text-input');
    const text = input ? input.value.trim() : '';
    if (!text) {
      showToast('Please type text to place.', 'error');
      return;
    }
    const fontSize = Number($('#editor-font-size')?.value) || 16;
    const color = $('#editor-text-color')?.value || '#142023';

    if (window.PaperplaneEditor?.canvas) {
      window.PaperplaneEditor.canvas.placeTextObject(text, {
        fontSize,
        color,
        bold: textBold,
        italic: textItalic
      });
    }
    textPanel.hidden = true;
    if (input) input.value = '';
  });
}

// Wire Phase 2 Signature Modal
const sigModal = $('#editor-signature-modal');
if (sigModal) {
  let sigPad = null;
  let sigMode = 'draw';

  function ensureSigPad() {
    if (!sigPad) {
      const sigCanvas = $('#editor-sig-canvas');
      if (sigCanvas && window.EditorClasses?.SignaturePad) {
        sigPad = new window.EditorClasses.SignaturePad(sigCanvas);
      }
    }
    return sigPad;
  }

  $('#sig-tab-draw')?.addEventListener('click', () => {
    sigMode = 'draw';
    $('#sig-tab-draw').classList.add('active');
    $('#sig-tab-type').classList.remove('active');
    $('#sig-draw-pane').hidden = false;
    $('#sig-type-pane').hidden = true;
    const pad = ensureSigPad();
    if (pad) pad.setMode('draw');
  });

  $('#sig-tab-type')?.addEventListener('click', () => {
    sigMode = 'type';
    $('#sig-tab-type').classList.add('active');
    $('#sig-tab-draw').classList.remove('active');
    $('#sig-type-pane').hidden = false;
    $('#sig-draw-pane').hidden = true;
    const pad = ensureSigPad();
    if (pad) pad.setMode('type');
  });

  $('#editor-sig-type-input')?.addEventListener('input', e => {
    const val = e.target.value;
    const preview = $('#sig-type-preview');
    if (preview) preview.textContent = val || 'Your Signature';
    const pad = ensureSigPad();
    if (pad) pad.setTypedText(val);
  });

  $('#editor-sig-clear-btn')?.addEventListener('click', () => {
    const pad = ensureSigPad();
    if (pad) pad.clear();
    const typeInp = $('#editor-sig-type-input');
    if (typeInp) typeInp.value = '';
    const preview = $('#sig-type-preview');
    if (preview) preview.textContent = 'Your Signature';
  });

  $('#editor-sig-close-btn')?.addEventListener('click', () => { sigModal.hidden = true; });
  $('#editor-sig-cancel-btn')?.addEventListener('click', () => { sigModal.hidden = true; });

  $('#editor-sig-place-btn')?.addEventListener('click', () => {
    const pad = ensureSigPad();
    let dataURL = null;
    let typedText = null;

    if (sigMode === 'draw') {
      if (pad && !pad.isEmpty()) {
        dataURL = pad.toDataURL();
      } else {
        showToast('Please draw your signature before placing.', 'error');
        return;
      }
    } else {
      const typeInp = $('#editor-sig-type-input');
      typedText = typeInp ? typeInp.value.trim() : '';
      if (!typedText) {
        showToast('Please type your name for signature.', 'error');
        return;
      }
    }

    const docRaw = sigModal.dataset.pendingDoc;
    const doc = docRaw ? JSON.parse(docRaw) : { x: 72, y: 500 };

    if (window.PaperplaneEditor?.canvas) {
      window.PaperplaneEditor.canvas.placeSignature(dataURL, typedText, doc);
    }
    sigModal.hidden = true;
    if (pad) pad.clear();
  });
}

// Wire Phase 2 Document Stamp Picker
const stampModal = $('#editor-stamp-picker');
if (stampModal) {
  $('#editor-stamp-close-btn')?.addEventListener('click', () => { stampModal.hidden = true; });

  $$('.stamp-preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const label = btn.dataset.label || 'APPROVED';
      const color = btn.dataset.color || '#10b981';
      if (window.PaperplaneEditor?.canvas) {
        window.PaperplaneEditor.canvas.placeStamp(label, color);
      }
      stampModal.hidden = true;
    });
  });

  $('#editor-custom-stamp-btn')?.addEventListener('click', () => {
    const input = $('#editor-custom-stamp-text');
    const label = input ? input.value.trim().toUpperCase() : '';
    if (!label) {
      showToast('Enter a custom stamp label.', 'error');
      return;
    }
    if (window.PaperplaneEditor?.canvas) {
      window.PaperplaneEditor.canvas.placeStamp(label, '#ef4444');
    }
    stampModal.hidden = true;
    if (input) input.value = '';
  });
}

// Wire 2-Tier Studio Ribbon: Annotate vs Organize Mode Switcher
const btnModeAnnotate = $('#btn-mode-annotate');
const btnModeOrganize = $('#btn-mode-organize');
const annotateRibbon = $('#studio-annotate-ribbon');
const batchBar = $('#organizer-batch-bar');

if (btnModeAnnotate && btnModeOrganize) {
  btnModeAnnotate.onclick = () => {
    btnModeAnnotate.classList.add('active');
    btnModeOrganize.classList.remove('active');
    if (annotateRibbon) annotateRibbon.hidden = false;
    if (batchBar) batchBar.hidden = true;
  };

  btnModeOrganize.onclick = () => {
    btnModeOrganize.classList.add('active');
    btnModeAnnotate.classList.remove('active');
    if (annotateRibbon) annotateRibbon.hidden = true;
    if (batchBar) batchBar.hidden = false;
  };
}

// Wire Studio "More Tools" Dropdown Menu
const moreToolsTrigger = $('#btn-more-tools-trigger');
const moreToolsMenu = $('#studio-more-dropdown');

if (moreToolsTrigger && moreToolsMenu) {
  moreToolsTrigger.onclick = (e) => {
    e.stopPropagation();
    const isHidden = moreToolsMenu.hidden;
    moreToolsMenu.hidden = !isHidden;
    moreToolsTrigger.setAttribute('aria-expanded', String(isHidden));
  };

  document.addEventListener('click', (e) => {
    if (!moreToolsMenu.hidden && !moreToolsMenu.contains(e.target) && !moreToolsTrigger.contains(e.target)) {
      moreToolsMenu.hidden = true;
      moreToolsTrigger.setAttribute('aria-expanded', 'false');
    }
  });

  $$('.studio-dropdown-item', moreToolsMenu).forEach(item => {
    item.addEventListener('click', () => {
      moreToolsMenu.hidden = true;
      moreToolsTrigger.setAttribute('aria-expanded', 'false');
    });
  });

  // Action listeners for Studio "More Tools" items
  $('#studio-compress-btn')?.addEventListener('click', () => { selectOperation('compress'); });
  $('#studio-ocr-btn')?.addEventListener('click', () => { selectOperation('ocr_pdf'); });
  $('#studio-repair-btn')?.addEventListener('click', () => { selectOperation('repair'); });
  $('#studio-convert-btn')?.addEventListener('click', () => { selectOperation('pdf_to_word'); });
  $('#studio-forms-btn')?.addEventListener('click', () => { selectOperation('flatten'); });
  $('#studio-sign-btn')?.addEventListener('click', () => { selectOperation('sign'); });
  $('#studio-security-btn')?.addEventListener('click', () => { selectOperation('protect'); });
}

function initStudioDrawingLayer() {
  // Retained as fallback when PaperplaneEditor is not loaded
  const canvas = $('#pdf-draw-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  state.studio.drawContext = ctx;
}

// ----------------------------------------------------------------------
// Dynamic Options Panel Generator
// ----------------------------------------------------------------------

function renderOptions() {
  const o = $('#options');
  if (!o) return;
  let fields = '';

  if (state.operation === 'merge') {
    fields += field('password', 'File Password (optional, if any file is encrypted)', 'password', 'Password for protected files');
  } else if (['split', 'remove'].includes(state.operation)) {
    if (state.operation === 'split') {
      const pageCount = state.splitPageCount;
      if (pageCount === 1) {
        fields += '<div class="option-field option-field-wide" style="background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; padding: 12px;"><strong style="color: #ef4444;">⚠️ Only 1 page found and can\'t be split</strong><p style="margin: 4px 0 0; font-size: 12px; color: var(--text-muted);">This document only contains 1 page. Splitting requires a multi-page document.</p></div>';
      } else if (pageCount && pageCount > 1) {
        fields += `<div class="option-field option-field-wide" style="background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.3); border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;"><strong style="color: #10b981;">📄 Document Analyzed: Total ${pageCount} pages found</strong></div>`;
        fields += selectField('split_mode', 'Split Mode', [
          { value: 'all_pages', label: `Extract all ${pageCount} pages into individual PDF files (ZIP)` },
          { value: 'range', label: 'Extract custom page ranges' }
        ]);
        fields += `<div class="option-field option-field-wide" id="split-range-container"><label for="pages">Pages or ranges to extract</label><input id="pages" type="text" placeholder="e.g. 1-3, 5, 8-${pageCount}" value="1-${pageCount}"></div>`;
      } else {
        fields += field('pages', 'Pages or ranges to extract (e.g. 1-3, 5, 8-12)', 'text', '1-3, 5, 8-12');
      }
    } else {
      fields += field('pages', 'Pages to remove (e.g. 2, 4-6)', 'text', '2, 4-6');
    }
  } else if (state.operation === 'rotate') {
    fields += selectField('degrees', 'Rotation Angle', [90, 180, 270]);
  } else if (state.operation === 'compress') {
    fields += selectField('quality', 'Compression Quality', [
      { value: '65', label: '65 (High Compression)' },
      { value: '75', label: '75 (Balanced)' },
      { value: '85', label: '85 (Low Loss)' }
    ]);
    fields += selectField('dpi', 'Max Image Resolution', [
      { value: '150', label: '150 DPI (Screen)' },
      { value: '72', label: '72 DPI (Web)' },
      { value: '300', label: '300 DPI (Print)' }
    ]);
  } else if (state.operation === 'watermark') {
    fields += field('text', 'Watermark text (leave empty if image selected)', 'text', 'CONFIDENTIAL');
    fields += field('opacity', 'Opacity (0.05 to 0.8)', 'number', '0.2', '0.05', '0.8', '0.01');
    fields += '<div class="option-field"><label for="watermark_image_file">Or Select Watermark Image</label><input id="watermark_image_file" type="file" accept="image/*"></div>';
  } else if (state.operation === 'page_numbers') {
    fields += selectField('position', 'Position', ['Footer center', 'Footer left', 'Footer right', 'Header left', 'Header right']);
  } else if (['protect', 'unlock'].includes(state.operation)) {
    fields += field('password', 'PDF Password', 'password', 'Enter password');
  } else if (state.operation === 'redact') {
    fields += field('terms', 'Keywords to permanently sanitize', 'text', 'SSN, account number, secret');
  } else if (state.operation === 'crop') {
    fields += ['left', 'top', 'right', 'bottom'].map(side => field(side, `${side} margin (pt)`, 'number', '0', '0', '1000', '1')).join('');
  } else if (state.operation === 'edit') {
    fields += field('text', 'Text to stamp', 'text', 'APPROVED');
    fields += field('page', 'Page number', 'number', '1', '1', '999', '1');
    fields += field('x', 'X coordinate (pt)', 'number', '72', '0', '9999', '1');
    fields += field('y', 'Y coordinate (pt)', 'number', '72', '0', '9999', '1');
  } else if (state.operation === 'translate') {
    fields += selectField('target_language', 'Target Language', ['es (Spanish)', 'fr (French)', 'de (German)', 'hi (Hindi)', 'ja (Japanese)', 'zh (Chinese)', 'ar (Arabic)', 'pt (Portuguese)', 'it (Italian)', 'ru (Russian)']);
  } else if (state.operation === 'ai_chat') {
    fields += '<div class="option-field option-field-wide"><label for="question">Ask this document</label><input id="question" type="text" placeholder="Ask any question about this document (e.g. key terms, dates, summary)..." autocomplete="off"></div>';
  } else if (state.operation === 'ocr') {
    fields += selectField('language', 'OCR Language', ['eng (English)', 'spa (Spanish)', 'deu (German)', 'fra (French)', 'hin (Hindi)']);
  } else if (state.operation === 'repair') {
    fields += selectField('mode', 'Repair Mode', ['automatic (Automatic Recovery)', 'validate_xref (Validate XRef Only)']);
  } else if (['word_to_pdf', 'excel_to_pdf', 'powerpoint_to_pdf'].includes(state.operation)) {
    fields += '<div class="option-field option-field-wide option-engine-badge"><span class="engine-badge-dot"></span><div><strong>Paperplane High-Fidelity Engine</strong><small>Enterprise headless conversion with ISO-standard fidelity.</small></div></div>';
  } else if (state.operation === 'pdf_to_jpg') {
    fields += selectField('dpi', 'Export Resolution', ['150 (Balanced)', '300 (Print)', '72 (Web)']);
  } else if (state.operation === 'pdf_to_pdfa') {
    fields += selectField('conformance', 'PDF/A Conformance', ['PDF/A-1b (Archival standard)', 'PDF/A-2b (Modern vector)']);
  } else if (state.operation === 'annotate') {
    fields += selectField('annot_type', 'Annotation Type', ['highlight', 'underline', 'strikeout', 'note', 'rect']);
    fields += field('page', 'Target Page Number', 'number', '1', '1', '999', '1');
    fields += field('text', 'Text to find & annotate', 'text', 'Important');
    fields += field('content', 'Comment / Sticky Note Text', 'text', 'Review this section');
  } else if (state.operation === 'summarize') {
    fields += '<div class="option-field" style="grid-column: span 2;"><label>Executive Document Summary</label><p style="color: var(--text-muted); font-size: 13px;">Generates executive briefing and key bullet points using deep NLP summarization.</p></div>';
  } else if (state.operation === 'sign') {
    fields += field('signature', 'Signer Name (optional typed fallback)', 'text', 'John Doe');
  } else if (state.operation === 'html_to_pdf') {
    fields += field('url', 'Public URL to convert', 'url', 'https://example.com');
  } else if (state.operation === 'metadata') {
    fields += field('title', 'Document Title', 'text', '') + field('author', 'Author', 'text', '') + field('subject', 'Subject', 'text', '');
  } else if (state.operation === 'forms') {
    fields += `<div class="option-field" style="grid-column: span 2;"><label for="fields">Form JSON Map</label><input id="fields" type="text" placeholder='{"FullName":"Alex", "Agreed": true}'></div>`;
  } else if (state.operation === 'ai_extract') {
    fields += selectField('doc_type', 'Document Type', ['auto', 'invoice', 'resume']);
  }

  o.innerHTML = fields;
  o.hidden = !fields;
  o.style.display = fields ? '' : 'none';
}

function field(id, label, type, placeholder, min = '', max = '', step = '') {
  return `<div class="option-field"><label for="${id}">${label}</label><input id="${id}" type="${type}" placeholder="${placeholder}" ${min ? `min="${min}" max="${max}" step="${step}"` : ''}></div>`;
}

function selectField(id, label, values) {
  return `<div class="option-field"><label for="${id}">${label}</label><select id="${id}">${values.map(v => {
    if (typeof v === 'object' && v !== null) {
      return `<option value="${v.value}">${v.label}</option>`;
    }
    return `<option value="${v}">${v}</option>`;
  }).join('')}</select></div>`;
}

// ----------------------------------------------------------------------
// File Upload & Dropzone Management
// ----------------------------------------------------------------------

function renderFiles() {
  if (typeof updateAiDocBar === 'function') updateAiDocBar();
  const list = $('#file-list');
  list.innerHTML = state.files.map((file, idx) => `
    <div class="file-row-card">
      <div class="file-row-left">
        <span class="file-row-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></span>
        <div>
          <span class="file-row-name">${file.name}</span>
          <span class="file-row-size">· ${formatBytes(file.size)}</span>
        </div>
      </div>
      <div class="file-row-actions">
        <button class="delete-file-btn" onclick="removeFile(${idx})" title="Remove file"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
    </div>
  `).join('');
}

window.removeFile = idx => {
  state.files.splice(idx, 1);
  renderFiles();
  updateButton();
};

function addFiles(newFiles) {
  // Validate file types for specific tools
  if (state.operation === 'png_to_pdf') {
    const nonPng = newFiles.filter(f => !f.name.toLowerCase().endsWith('.png'));
    if (nonPng.length > 0) {
      showToast('Only PNG images (.png) are accepted for PNG to PDF. JPEG/JPG is not allowed.', 'warning', 4500);
      newFiles = newFiles.filter(f => f.name.toLowerCase().endsWith('.png'));
      if (!newFiles.length) return;
    }
  }

  state.files = [...state.files, ...newFiles];
  renderFiles();
  updateButton();

  // If on Split tool, analyze page count dynamically
  if (state.operation === 'split' && state.files.length && state.files[0].name.toLowerCase().endsWith('.pdf')) {
    const targetFile = state.files[0];
    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        if (typeof PDFLib !== 'undefined') {
          const doc = await PDFLib.PDFDocument.load(e.target.result);
          state.splitPageCount = doc.getPageCount();
          renderOptions();
          updateButton();
        } else if (typeof pdfjsLib !== 'undefined') {
          const doc = await pdfjsLib.getDocument({ data: e.target.result }).promise;
          state.splitPageCount = doc.numPages;
          renderOptions();
          updateButton();
        }
      } catch (err) {
        console.warn('Split page analysis error:', err);
      }
    };
    reader.readAsArrayBuffer(targetFile);
  }

  // If a PDF is uploaded, automatically prime the in-app studio
  if (state.files.length && state.files[0].name.toLowerCase().endsWith('.pdf')) {
    loadDocumentIntoStudio(state.files[0]);
  }
}

function updateButton() {
  const btn = $('#run-button');
  const isHtml = state.operation === 'html_to_pdf';
  const hasFiles = state.files.length > 0 || isHtml;
  const toolLabel = state.operations[state.operation]?.label || 'Run Tool';

  if (state.operation === 'split' && state.splitPageCount === 1) {
    btn.disabled = true;
    btn.innerHTML = 'Only 1 page found (Cannot be split) <span>✕</span>';
    return;
  }

  btn.disabled = !hasFiles;
  btn.innerHTML = hasFiles
    ? `${toolLabel} Now <span>→</span>`
    : 'Select files to continue <span>→</span>';
}

$('#browse').onclick = () => {
  if (!state.user && !state.token) {
    showToast('Please sign in or create an account to process documents.', 'warning');
    openAuthModal('login');
    return;
  }
  $('#file-input').click();
};

const dropzoneEl = $('#dropzone');
if (dropzoneEl) {
  dropzoneEl.onclick = (e) => {
    if (e.target.closest('#browse')) return;
    if (!state.user && !state.token) {
      showToast('Please sign in or create an account to process documents.', 'warning');
      openAuthModal('login');
      return;
    }
    $('#file-input').click();
  };
}

$('#file-input').onchange = e => addFiles([...e.target.files]);

['dragenter', 'dragover'].forEach(event => {
  $('#dropzone').addEventListener(event, e => {
    e.preventDefault();
    $('#dropzone').classList.add('over');
  });
});

['dragleave', 'drop'].forEach(event => {
  $('#dropzone').addEventListener(event, e => {
    e.preventDefault();
    $('#dropzone').classList.remove('over');
  });
});

$('#dropzone').ondrop = e => {
  if (!state.user && !state.token) {
    showToast('Please sign in or create an account to process documents.', 'warning');
    openAuthModal('login');
    return;
  }
  addFiles([...e.dataTransfer.files]);
};

// ----------------------------------------------------------------------
// Cloud Import Modal & Handler
// ----------------------------------------------------------------------

function dataUrlToFile(dataUrl, filename) {
  const arr = dataUrl.split(',');
  const mime = arr[0].match(/:(.*?);/)[1];
  const bstr = atob(arr[1]);
  let n = bstr.length;
  const u8arr = new Uint8Array(n);
  while (n--) {
    u8arr[n] = bstr.charCodeAt(n);
  }
  return new File([u8arr], filename, { type: mime });
}

$('#topbar-cloud-btn').onclick = () => {
  $('#cloud-modal').hidden = false;
  $('#cloud-url').value = '';
};

$('#cloud-drop-btn').onclick = () => {
  $('#cloud-modal').hidden = false;
  $('#cloud-url').value = '';
};

$('#close-cloud-modal').onclick = () => $('#cloud-modal').hidden = true;

$('#cloud-form').onsubmit = async e => {
  e.preventDefault();
  const fileUrl = $('#cloud-url').value.trim();
  const btn = $('#cloud-submit-btn');
  btn.disabled = true;
  btn.textContent = 'Importing Document…';

  try {
    const formData = new FormData();
    formData.append('file_url', fileUrl);
    const res = await safeFetch('/api/cloud/sync', { method: 'POST', body: formData });
    if (res.data_url) {
      const file = dataUrlToFile(res.data_url, res.filename);
      addFiles([file]);
      $('#cloud-modal').hidden = true;
      showToast(`Imported ${res.filename} via ${res.provider}!`);
    }
  } catch (err) {
    $('#cloud-error').textContent = err.message;
    $('#cloud-error').hidden = false;
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Fetch & Import Document <span>→</span>';
  }
};

// ----------------------------------------------------------------------
// Progress Animation & Job Execution
// ----------------------------------------------------------------------

function updateProgress(step, percent, title) {
  $('#progress-card').hidden = false;
  $('#progress-bar-fill').style.width = `${percent}%`;
  $('#progress-percent').textContent = `${percent}%`;
  if (title) $('#progress-status-title').textContent = title;

  [1, 2, 3, 4].forEach(s => {
    const el = $(`#step-${s}`);
    if (el) {
      el.className = s < step ? 'progress-step done' : s === step ? 'progress-step active' : 'progress-step';
    }
  });
}

$('#job-form').onsubmit = async e => {
  e.preventDefault();
  const isHtml = state.operation === 'html_to_pdf';
  if (!state.files.length && !isHtml) return;

  const btn = $('#run-button');
  btn.disabled = true;
  $('#result').hidden = true;

  updateProgress(1, 15, 'Preparing document streams…');

  // Client-Side WASM Mode
  if (state.clientSideMode) {
    try {
      updateProgress(2, 60, 'Processing locally in browser RAM…');
      await processClientSide();
      updateProgress(4, 100, 'Complete!');
      setTimeout(() => $('#progress-card').hidden = true, 1200);
      return;
    } catch (clientErr) {
      showResult(`Client-side mode error: ${clientErr.message}`, true);
      return;
    } finally {
      btn.disabled = false;
      updateButton();
    }
  }

  // Server Workflow Execution
  const options = {};
  $$('#options input, #options select').forEach(input => {
    if (input.value) {
      options[input.id] = input.type === 'number' ? Number(input.value) : input.value;
    }
  });

  if (options.target_language && typeof options.target_language === 'string' && options.target_language.includes(' ')) {
    options.target_language = options.target_language.split(' ')[0];
  }
  if (options.language && typeof options.language === 'string' && options.language.includes(' ')) {
    options.language = options.language.split(' ')[0];
  }
  if (options.mode && typeof options.mode === 'string' && options.mode.includes(' ')) {
    options.mode = options.mode.split(' ')[0];
  }
  if (options.dpi && typeof options.dpi === 'string' && options.dpi.includes(' ')) {
    options.dpi = options.dpi.split(' ')[0];
  }

  if (['ai_chat', 'summarize', 'translate', 'ai_extract'].includes(state.operation)) {
    try {
      updateProgress(2, 40, 'Starting grounded AI workflow…');
      await runDeskAiWorkflow(options);
      updateProgress(4, 100, 'AI workflow complete');
      setTimeout(() => $('#progress-card').hidden = true, 800);
    } catch (error) {
      $('#progress-card').hidden = true;
      showResult(error.message, true);
      showToast(error.message, 'error', 4500);
    } finally {
      btn.disabled = false;
      updateButton();
    }
    return;
  }

  const form = new FormData();
  form.append('operation', state.operation);
  form.append('options', JSON.stringify(options));
  state.files.forEach(f => form.append('files', f));

  try {
    updateProgress(2, 40, 'Dispatching to worker pool…');
    const data = await safeFetch('/api/jobs', { method: 'POST', body: form });
    
    updateProgress(3, 75, 'Transforming & compressing streams…');
    const job = await waitForJob(data.status_url);
    
    updateProgress(4, 100, 'Finished!');
    setTimeout(() => $('#progress-card').hidden = true, 800);
    showDownloadResult(job, data.download_url);
    await checkAuthStatus();
  } catch (error) {
    $('#progress-card').hidden = true;
    if (error.message.includes('TIER_LIMIT') || error.message.includes('limit reached')) {
      // Upgrade modal already opened by safeFetch
    } else if (error.message.toLowerCase().includes('password')) {
      showUserErrorModal(
        'Protected PDF Detected',
        'This document is password protected or the provided password is invalid. Please unlock it using Paperplane Unlock.',
        {
          icon: '',
          actionText: 'Open Unlock Tool',
          onAction: () => selectOperation('unlock')
        }
      );
    } else {
      showResult(error.message, true);
      showToast(error.message, 'error', 4500);
    }
  } finally {
    btn.disabled = false;
    updateButton();
  }
};

async function waitForJob(url) {
  for (let attempt = 0; attempt < 180; attempt++) {
    const job = await safeFetch(url);
    if (job.status === 'completed') return job;
    if (job.status === 'failed') throw new Error(job.error || 'The job failed during processing.');
    await new Promise(r => setTimeout(r, 600));
  }
  throw new Error('Processing timed out.');
}

function showDownloadResult(job, downloadUrl) {
  const result = $('#result');
  result.className = 'result-card';
  const content = $('#result-content');
  if (content) {
    content.hidden = true;
    content.innerHTML = '';
  }
  $('#result-title').textContent = 'Your document is ready!';
  const outName = job.output_name || 'document.pdf';
  $('#result-meta').textContent = `${outName} · ${formatBytes(job.output_size)}`;
  const dlLink = $('#result-download-link');
  dlLink.href = downloadUrl;
  dlLink.setAttribute('download', outName);
  dlLink.hidden = false;

  // Direct fetch fallback onclick to guarantee zero download error across all browsers
  dlLink.onclick = async (e) => {
    e.preventDefault();
    try {
      showToast('Starting file download…', 'info', 2000);
      const token = localStorage.getItem('paperplane_token');
      const headers = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const res = await fetch(downloadUrl, { credentials: 'same-origin', headers });
      if (!res.ok) throw new Error(`Download failed with status ${res.status}`);
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const tempA = document.createElement('a');
      tempA.href = blobUrl;
      tempA.download = outName;
      document.body.appendChild(tempA);
      tempA.click();
      setTimeout(() => {
        tempA.remove();
        URL.revokeObjectURL(blobUrl);
      }, 1000);
      showToast('Download complete!', 'success', 2500);
    } catch (err) {
      console.warn('Blob download fallback triggered direct link navigation:', err);
      window.location.href = downloadUrl;
    }
  };

  $('#result-view-studio-btn').hidden = false;
  result.hidden = false;
  showToast('Processing complete! Document ready for download.');
}

function showResult(message, isError = false) {
  const result = $('#result');
  result.className = isError ? 'result-card error' : 'result-card';
  $('#result-title').textContent = isError ? 'Operation Failed' : 'Notice';
  $('#result-meta').textContent = message;
  if ($('#result-content')) {
    $('#result-content').hidden = true;
    $('#result-content').innerHTML = '';
  }
  if ($('#result-download-link')) $('#result-download-link').hidden = true;
  if ($('#result-view-studio-btn')) $('#result-view-studio-btn').hidden = true;
  result.hidden = false;
}

function renderMarkdown(markdown) {
  const lines = String(markdown || '').replace(/\r/g, '').split('\n');
  let html = '';
  let inList = false;
  const closeList = () => {
    if (inList) { html += '</ul>'; inList = false; }
  };
  lines.forEach(line => {
    const trimmed = line.trim();
    if (!trimmed) { closeList(); return; }
    if (/^###\s+/.test(trimmed)) { closeList(); html += `<h4>${escapeHtml(trimmed.replace(/^###\s+/, ''))}</h4>`; return; }
    if (/^##\s+/.test(trimmed)) { closeList(); html += `<h3>${escapeHtml(trimmed.replace(/^##\s+/, ''))}</h3>`; return; }
    if (/^#\s+/.test(trimmed)) { closeList(); html += `<h2>${escapeHtml(trimmed.replace(/^#\s+/, ''))}</h2>`; return; }
    if (/^[-*]\s+/.test(trimmed)) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += `<li>${escapeHtml(trimmed.replace(/^[-*]\s+/, ''))}</li>`;
      return;
    }
    closeList();
    const safe = escapeHtml(trimmed).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`(.+?)`/g, '<code>$1</code>');
    html += `<p>${safe}</p>`;
  });
  closeList();
  return html || '<p>No response was generated.</p>';
}

function plainMarkdown(markdown) {
  return String(markdown || '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/`(.+?)`/g, '$1');
}

let currentSummaryText = '';

function showRichAiResult(title, meta, contentHtml, actions = {}) {
  const result = $('#result');
  const content = $('#result-content');
  if (!result || !content) return;
  result.className = 'result-card ai-result-card';
  $('#result-title').textContent = title;
  $('#result-meta').textContent = meta;
  content.innerHTML = contentHtml;
  content.hidden = false;
  $('#result-download-link').hidden = true;
  $('#result-view-studio-btn').hidden = actions.showStudio !== false;
  result.hidden = false;
}

function downloadTextFile(text, filename) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function downloadSummaryPdf(text, filename) {
  if (typeof PDFLib === 'undefined') {
    downloadTextFile(text, filename.replace(/\.pdf$/i, '.txt'));
    showToast('PDF-Lib is unavailable; downloaded the summary as TXT.', 'warning');
    return;
  }
  const { PDFDocument, StandardFonts, rgb } = PDFLib;
  const pdf = await PDFDocument.create();
  const font = await pdf.embedFont(StandardFonts.Helvetica);
  const fontSize = 10;
  const lineHeight = 15;
  const maxChars = 105;
  const lines = [];
  plainMarkdown(text).split('\n').forEach(line => {
    if (!line.trim()) { lines.push(''); return; }
    for (let i = 0; i < line.length; i += maxChars) lines.push(line.slice(i, i + maxChars));
  });
  let page = pdf.addPage([612, 792]);
  let y = 750;
  lines.forEach(line => {
    if (y < 48) { page = pdf.addPage([612, 792]); y = 750; }
    page.drawText(line, { x: 48, y, size: fontSize, font, color: rgb(0.08, 0.12, 0.14) });
    y -= lineHeight;
  });
  const bytes = await pdf.save();
  downloadBlob(bytes, filename, 'application/pdf');
}

function showAiChatDeskResult(data) {
  const citations = data.citations?.length
    ? data.citations.map(page => `<span class="ai-citation-tag">Page ${escapeHtml(page)}</span>`).join('')
    : '<span class="ai-citation-tag muted">No page citation returned</span>';
  const provider = escapeHtml(data.provider || data.retrieval_method || 'Paperplane grounded engine');
  showRichAiResult(
    'Grounded AI answer',
    `${provider} · ${data.fallback_used ? 'local fallback active' : 'document-grounded'}`,
    `<div class="ai-result-answer">${renderMarkdown(data.answer)}</div><div class="ai-result-citations"><strong>Verified sources</strong>${citations}</div><button type="button" class="btn-primary-action ai-open-studio-result-btn">Open in Full AI Interactive Studio →</button>`,
    { showStudio: true },
  );
  $('.ai-open-studio-result-btn')?.addEventListener('click', () => switchWorkspaceView('ai'));
}

function showSummaryDeskResult(summary) {
  currentSummaryText = summary || '';
  const fileName = (state.files[0]?.name || 'document').replace(/\.[^/.]+$/, '');
  showRichAiResult(
    'Executive briefing ready',
    `${fileName} · formatted Markdown · local/provider grounded`,
    `<article class="ai-result-markdown">${renderMarkdown(currentSummaryText)}</article><div class="ai-result-actions"><button type="button" class="btn-demo-upgrade" id="desk-copy-summary-btn">Copy Summary</button><button type="button" class="btn-demo-upgrade" id="desk-download-summary-txt-btn">Download TXT</button><button type="button" class="btn-demo-upgrade" id="desk-download-summary-pdf-btn">Download PDF</button></div>`,
    { showStudio: false },
  );
  $('#desk-copy-summary-btn')?.addEventListener('click', async () => {
    await navigator.clipboard.writeText(currentSummaryText);
    showToast('Summary copied to clipboard.', 'success');
  });
  $('#desk-download-summary-txt-btn')?.addEventListener('click', () => downloadTextFile(currentSummaryText, `${fileName}_executive_brief.txt`));
  $('#desk-download-summary-pdf-btn')?.addEventListener('click', () => downloadSummaryPdf(currentSummaryText, `${fileName}_executive_brief.pdf`));
}

async function fetchBinary(url, options = {}) {
  const headers = options.headers || {};
  const token = localStorage.getItem('paperplane_token');
  if (token && !headers.Authorization) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try { const data = await response.json(); message = data.detail || message; } catch { /* non-JSON error */ }
    throw new Error(message);
  }
  return { blob: await response.blob(), response };
}

async function runDeskAiWorkflow(options) {
  const operation = state.operation;
  if (operation === 'ai_chat') {
    const form = new FormData();
    form.append('file', state.files[0]);
    form.append('question', options.question || 'Summarize the key contents of this document.');
    showAiChatDeskResult(await safeFetch('/api/ai/chat', { method: 'POST', body: form }));
    showToast('AI answer rendered with verified page citations.', 'success');
    return;
  }
  if (operation === 'summarize') {
    const form = new FormData();
    form.append('file', state.files[0]);
    const data = await safeFetch('/api/ai/summarize', { method: 'POST', body: form });
    showSummaryDeskResult(data.summary);
    showToast('Executive briefing rendered on-screen.', 'success');
    return;
  }
  if (operation === 'ai_extract') {
    const form = new FormData();
    form.append('file', state.files[0]);
    form.append('doc_type', options.doc_type || 'auto');
    const data = await safeFetch('/api/ai/extract', { method: 'POST', body: form });
    renderExtractionResultsModal(data.data);
    showRichAiResult('Structured extraction ready', `${data.data.document_type || 'general'} · interactive viewer opened`, '<p>Review the structured fields, source pages, warnings, and export controls in the extraction viewer.</p>', { showStudio: false });
    $('#extraction-results-modal').hidden = false;
    showToast('Structured entities rendered in the interactive viewer.', 'success');
    return;
  }
  if (operation === 'translate') {
    const form = new FormData();
    form.append('file', state.files[0]);
    form.append('target_language', options.target_language || 'es');
    const { blob, response } = await fetchBinary('/api/ai/translate', { method: 'POST', body: form });
    const url = URL.createObjectURL(blob);
    const warningCount = response.headers.get('X-Paperplane-Translation-Warnings') || '0';
    const mode = response.headers.get('X-Paperplane-Translation-Mode') || 'translated';
    const name = `${(state.files[0]?.name || 'document').replace(/\.[^/.]+$/, '')}_translated.pdf`;
    showRichAiResult('Translation workflow complete', `${options.target_language || 'es'} · ${mode === 'translated' ? 'translated blocks' : 'source preserved fallback'} · ${warningCount} warning(s)`, `<p>${mode === 'translated' ? 'Translated text was rendered into the original page layout.' : 'The provider was unavailable within the bounded budget, so source text was preserved instead of claiming a false translation.'}</p><a class="btn-download" href="${url}" download="${escapeHtml(name)}">Download translated PDF</a>`, { showStudio: false });
    showToast('Translation result rendered with bounded fallback behavior.', mode === 'translated' ? 'success' : 'warning');
  }
}

// ----------------------------------------------------------------------
// Client-Side WASM / JS Processing via PDF-Lib
// ----------------------------------------------------------------------

async function processClientSide() {
  if (typeof PDFLib === 'undefined') {
    throw new Error('Client-side PDF-Lib is not loaded.');
  }

  const { PDFDocument, degrees, rgb } = PDFLib;

  if (state.operation === 'merge') {
    const mergedPdf = await PDFDocument.create();
    for (const file of state.files) {
      const bytes = await file.arrayBuffer();
      const pdf = await PDFDocument.load(bytes);
      const copiedPages = await mergedPdf.copyPages(pdf, pdf.getPageIndices());
      copiedPages.forEach(page => mergedPdf.addPage(page));
    }
    const pdfBytes = await mergedPdf.save();
    downloadBlob(pdfBytes, 'merged_private.pdf', 'application/pdf');
    return;
  }

  if (state.operation === 'split' || state.operation === 'remove') {
    const bytes = await state.files[0].arrayBuffer();
    const pdf = await PDFDocument.load(bytes);
    const newPdf = await PDFDocument.create();
    const total = pdf.getPageCount();
    const pagesStr = $('#pages')?.value || '1';
    
    const indices = [];
    pagesStr.split(',').forEach(part => {
      part = part.trim();
      if (part.includes('-')) {
        const [start, end] = part.split('-').map(Number);
        for (let i = start; i <= end; i++) if (i >= 1 && i <= total) indices.push(i - 1);
      } else {
        const p = Number(part);
        if (p >= 1 && p <= total) indices.push(p - 1);
      }
    });

    const targetIndices = state.operation === 'remove'
      ? pdf.getPageIndices().filter(idx => !indices.includes(idx))
      : indices;

    const copied = await newPdf.copyPages(pdf, targetIndices);
    copied.forEach(page => newPdf.addPage(page));
    const pdfBytes = await newPdf.save();
    downloadBlob(pdfBytes, 'extracted_private.pdf', 'application/pdf');
    return;
  }

  if (state.operation === 'rotate') {
    const bytes = await state.files[0].arrayBuffer();
    const pdf = await PDFDocument.load(bytes);
    const rot = Number($('#degrees')?.value || 90);
    pdf.getPages().forEach(page => {
      page.setRotation(degrees(page.getRotation().angle + rot));
    });
    const pdfBytes = await pdf.save();
    downloadBlob(pdfBytes, 'rotated_private.pdf', 'application/pdf');
    return;
  }

  throw new Error(`The operation '${state.operation}' requires the server high-speed engine.`);
}

function downloadBlob(bytes, filename, mimeType) {
  const blob = new Blob([bytes], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast(`Downloaded ${filename} processed locally!`);
}

// ----------------------------------------------------------------------
// AI Document Intelligence Studio & Structured Extraction Controller
// ----------------------------------------------------------------------

let currentExtractionData = null;

function updateAiDocBar() {
  const uploadZone = $('#ai-upload-zone');
  const activeBar = $('#ai-active-doc-bar');
  const docName = $('#ai-doc-name');
  const docMeta = $('#ai-doc-meta');
  const chatInput = $('#chat-input');
  const chatBtn = $('#chat-send-btn');
  const extractBtn = $('#trigger-extract-btn');
  const summaryBtn = $('#trigger-summary-btn');

  if (state.files.length && state.files[0].name.toLowerCase().endsWith('.pdf')) {
    const file = state.files[0];
    if (uploadZone) uploadZone.hidden = true;
    if (activeBar) activeBar.hidden = false;
    if (docName) docName.textContent = file.name;
    if (docMeta) docMeta.textContent = `${formatBytes(file.size)} • PDF Document`;
    if (chatInput) {
      chatInput.disabled = false;
      chatInput.placeholder = `Ask a question about ${file.name}...`;
    }
    if (chatBtn) chatBtn.disabled = false;
    if (extractBtn) extractBtn.disabled = false;
    if (summaryBtn) summaryBtn.disabled = false;
  } else {
    if (uploadZone) uploadZone.hidden = false;
    if (activeBar) activeBar.hidden = true;
    if (chatInput) {
      chatInput.disabled = false;
      chatInput.placeholder = 'Click here or upload a PDF to ask questions...';
    }
    if (chatBtn) chatBtn.disabled = false;
    if (extractBtn) extractBtn.disabled = false;
    if (summaryBtn) summaryBtn.disabled = false;
  }
}

// AI Studio File Input & Dropzone Wiring
const aiFileInput = $('#ai-file-input');
const aiUploadBtn = $('#ai-upload-btn');
const aiBrowseTrigger = $('#ai-browse-trigger');
const aiUploadZone = $('#ai-upload-zone');
const aiChangeDocBtn = $('#ai-change-doc-btn');
const aiClearDocBtn = $('#ai-clear-doc-btn');

const chatInputEl = $('#chat-input');
if (chatInputEl) {
  chatInputEl.addEventListener('click', () => {
    if (!state.files.length) {
      showToast('Please select a PDF document to begin grounded AI Q&A.', 'info');
      aiFileInput?.click();
    }
  });
}

if (aiUploadBtn) aiUploadBtn.onclick = (e) => { e.stopPropagation(); aiFileInput?.click(); };
if (aiBrowseTrigger) aiBrowseTrigger.onclick = () => aiFileInput?.click();
if (aiChangeDocBtn) aiChangeDocBtn.onclick = () => aiFileInput?.click();

if (aiClearDocBtn) {
  aiClearDocBtn.onclick = () => {
    state.files = [];
    updateAiDocBar();
    $('#chat-messages').innerHTML = `
      <div class="chat-bubble ai">
        <strong>Paperplane AI:</strong> Document cleared. Upload a new PDF above to begin grounded document analysis.
      </div>
    `;
    $('#summary-display').textContent = 'Summary will appear here after generation...';
    const sumActions = $('#summary-actions-bar');
    if (sumActions) sumActions.hidden = true;
    showToast('Document cleared from AI workspace', 'info');
  };
}

if (aiFileInput) {
  aiFileInput.onchange = (e) => {
    if (e.target.files?.length) {
      const file = e.target.files[0];
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        showToast('Please select a valid PDF file.', 'warning');
        return;
      }
      state.files = [file];
      updateAiDocBar();
      showToast(`Loaded ${file.name} for AI analysis`, 'success');
      aiFileInput.value = '';
    }
  };
}

if (aiUploadZone) {
  aiUploadZone.ondragover = (e) => {
    e.preventDefault();
    aiUploadZone.style.borderColor = 'var(--accent)';
  };
  aiUploadZone.ondragleave = () => {
    aiUploadZone.style.borderColor = '';
  };
  aiUploadZone.ondrop = (e) => {
    e.preventDefault();
    aiUploadZone.style.borderColor = '';
    if (e.dataTransfer?.files?.length) {
      const file = e.dataTransfer.files[0];
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        showToast('Please drop a valid PDF file.', 'warning');
        return;
      }
      state.files = [file];
      updateAiDocBar();
      showToast(`Loaded ${file.name} for AI analysis`, 'success');
    }
  };
}

// AI Test Connection
const testConnBtn = $('#ai-test-connection-btn');
if (testConnBtn) {
  testConnBtn.onclick = async () => {
    testConnBtn.disabled = true;
    testConnBtn.textContent = 'Testing...';
    try {
      const res = await safeFetch('/api/ai/test-connection');
      if (res.status === 'connected' || res.status === 'inference_succeeded') {
        showToast(`AI Connected: ${res.provider} (${res.model}) HTTP ${res.http_status}`, 'success');
      } else if (res.status === 'upstream_client_restricted' || res.status === 'credentials_rejected') {
        showToast(`AgentRouter (${res.model || 'gpt-6.1-sol'}): Client unauthorized (HTTP 401). Local BM25 Engine fallback active.`, 'info', 7000);
      } else {
        showToast(`AI Status (${res.status}): ${res.advice || res.message || 'Offline mode active'}`, 'warning', 6000);
      }
    } catch (err) {
      showToast(`AI Connection Test: Local deterministic BM25 fallback is active.`, 'info');
    } finally {
      testConnBtn.disabled = false;
      testConnBtn.textContent = 'Test AI Connection';
    }
  };
}

// AI Chat Clear
const chatClearBtn = $('#ai-chat-clear-btn');
if (chatClearBtn) {
  chatClearBtn.onclick = () => {
    $('#chat-messages').innerHTML = `
      <div class="chat-bubble ai">
        <strong>Paperplane AI:</strong> Conversation history cleared. Ask any new question about the document!
      </div>
    `;
    showToast('Conversation cleared', 'info');
  };
}

// AI Document Grounded Chat Submit
$('#chat-form').onsubmit = async e => {
  e.preventDefault();
  if (!state.files.length) {
    showToast('Please select or upload a PDF document first before asking questions.', 'warning');
    aiFileInput?.click();
    return;
  }

  const input = $('#chat-input');
  const question = input.value.trim();
  if (!question) return;

  const msgs = $('#chat-messages');
  msgs.innerHTML += `<div class="chat-bubble user"><strong>You:</strong> ${escapeHtml(question)}</div>`;
  input.value = '';
  msgs.scrollTop = msgs.scrollHeight;

  const form = new FormData();
  form.append('file', state.files[0]);
  form.append('question', question);

  const btn = $('#chat-send-btn');
  btn.disabled = true;
  btn.textContent = 'Searching…';

  try {
    const res = await safeFetch('/api/ai/chat', { method: 'POST', body: form });
    const citations = res.citations?.length
      ? `<br><span class="chat-citation-tag">Cited: Pages ${res.citations.join(', ')}</span>`
      : '';
    const retrievalInfo = res.retrieval_method
      ? `<br><small style="color: var(--text-muted); font-size: 11px;">Grounded via ${res.retrieval_method}</small>`
      : '';
    const citationTags = res.citations?.length
      ? res.citations.map(page => `<span class="ai-citation-tag">Page ${escapeHtml(page)}</span>`).join('')
      : '';
    msgs.innerHTML += `<div class="chat-bubble ai"><strong>Paperplane AI:</strong><div class="chat-markdown">${renderMarkdown(res.answer)}</div><div class="chat-citation-tags">${citationTags}</div>${retrievalInfo}</div>`;
  } catch (err) {
    msgs.innerHTML += `<div class="chat-bubble ai" style="border-color: var(--error); color: var(--error);">Error: ${escapeHtml(err.message)}</div>`;
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Ask';
    msgs.scrollTop = msgs.scrollHeight;
  }
};

// Executive Summarizer
$('#trigger-summary-btn').onclick = async () => {
  if (!state.files.length) {
    showToast('Please upload or select a PDF document first.', 'warning');
    aiFileInput?.click();
    return;
  }
  const btn = $('#trigger-summary-btn');
  btn.disabled = true;
  btn.textContent = 'Generating Executive Brief...';
  const form = new FormData();
  form.append('file', state.files[0]);

  try {
    const res = await safeFetch('/api/ai/summarize', { method: 'POST', body: form });
    const summaryBox = $('#summary-display');
    currentSummaryText = res.summary || '';
    summaryBox.innerHTML = renderMarkdown(currentSummaryText);
    const actionsBar = $('#summary-actions-bar');
    if (actionsBar) actionsBar.hidden = false;
    showToast('Executive brief generated successfully!', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate Executive Brief';
  }
};

const copySummaryBtn = $('#copy-summary-btn');
if (copySummaryBtn) {
  copySummaryBtn.onclick = async () => {
    const text = currentSummaryText || $('#summary-display').textContent;
    if (text) {
      await navigator.clipboard.writeText(text);
      showToast('Executive brief copied to clipboard!', 'success');
    }
  };
}

const downloadSummaryTxtBtn = $('#download-summary-txt-btn');
if (downloadSummaryTxtBtn) {
  downloadSummaryTxtBtn.onclick = () => {
    const text = currentSummaryText || $('#summary-display').textContent;
    if (!text) return;
    const docName = (state.files[0]?.name || 'document').replace(/\.[^/.]+$/, '');
    downloadTextFile(text, `${docName}_executive_brief.txt`);
    showToast('Downloaded executive brief as TXT', 'success');
  };
}

const downloadSummaryPdfBtn = $('#download-summary-pdf-btn');
if (downloadSummaryPdfBtn) {
  downloadSummaryPdfBtn.onclick = async () => {
    const text = currentSummaryText || $('#summary-display').textContent;
    if (!text) return;
    const docName = (state.files[0]?.name || 'document').replace(/\.[^/.]+$/, '');
    await downloadSummaryPdf(text, `${docName}_executive_brief.pdf`);
  };
}

// ----------------------------------------------------------------------
// Smart Metadata Extraction Results Experience
// ----------------------------------------------------------------------

function renderExtractionResultsModal(data) {
  currentExtractionData = data;
  const modal = $('#extraction-results-modal');
  if (!modal) return;

  const docType = (data.document_type || 'general').toLowerCase();
  const fileName = state.files[0]?.name || 'document.pdf';

  // Header badges & titles
  const badgeEl = $('#extraction-doc-type-badge');
  if (badgeEl) badgeEl.textContent = docType.toUpperCase();
  const titleEl = $('#extraction-modal-title');
  if (titleEl) {
    titleEl.textContent = docType === 'invoice'
      ? 'Invoice Extraction Results'
      : (docType === 'resume' ? 'Resume Extraction Results' : 'Document Metadata Results');
  }
  const subEl = $('#extraction-modal-subtitle');
  if (subEl) {
    subEl.textContent = `File: ${fileName} • ${data.total_pages} Page${data.total_pages === 1 ? '' : 's'} • Engine: ${data.provider || 'Deterministic Parser'}`;
  }

  // Reset tab selection to Structured View
  $('#ext-tab-structured')?.classList.add('active');
  $('#ext-tab-json')?.classList.remove('active');
  const structView = $('#ext-view-structured');
  const jsonView = $('#ext-view-json');
  if (structView) structView.hidden = false;
  if (jsonView) jsonView.hidden = true;

  // Warnings alert box
  const warnBox = $('#extraction-warnings-box');
  const warnList = $('#extraction-warnings-list');
  if (data.warnings && data.warnings.length > 0) {
    if (warnBox) warnBox.hidden = false;
    if (warnList) warnList.innerHTML = data.warnings.map(w => `<div>• ${escapeHtml(w)}</div>`).join('');
  } else {
    if (warnBox) warnBox.hidden = true;
    if (warnList) warnList.innerHTML = '';
  }

  // Key Fields Grid
  const grid = $('#extraction-fields-grid');
  if (grid) {
    grid.innerHTML = '';

    if (docType === 'invoice') {
      const inv = data.invoice_data || {};
      const cur = inv.currency ? ` (${escapeHtml(inv.currency)})` : '';
      const fields = [
        { label: `Total Amount${cur}`, val: inv.total_amount ? `${inv.currency || '$'}${inv.total_amount}` : null, highlight: true },
        { label: 'Invoice #', val: inv.invoice_number },
        { label: 'Invoice Date', val: inv.invoice_date },
        { label: 'Due Date', val: inv.due_date },
        { label: 'Subtotal', val: inv.subtotal ? `${inv.currency || '$'}${inv.subtotal}` : null },
        { label: 'Tax Amount', val: inv.tax_amount ? `${inv.currency || '$'}${inv.tax_amount}` : null },
        { label: 'Vendor / Issuer', val: inv.vendor },
        { label: 'Customer / Bill To', val: inv.customer },
        { label: 'Payment Terms', val: inv.payment_terms }
      ];

      fields.forEach(f => {
        const card = document.createElement('div');
        card.className = 'extraction-field-card';
        const isNull = !f.val;
        const displayVal = isNull ? 'Not detected' : escapeHtml(String(f.val));
        const valClass = `extraction-field-value ${isNull ? 'null-val' : ''} ${f.highlight && !isNull ? 'highlight-val' : ''}`;
        card.innerHTML = `
          <span class="extraction-field-label">${escapeHtml(f.label)}</span>
          <span class="${valClass}">${displayVal}</span>
        `;
        grid.appendChild(card);
      });

      // Line Items Section
      const lineItemsSection = $('#extraction-line-items-section');
      if (lineItemsSection) lineItemsSection.hidden = false;
      const items = inv.line_items || [];
      const countBadge = $('#extraction-items-count');
      const tbody = $('#extraction-items-tbody');
      const tableWrap = $('#extraction-items-table');
      const emptyState = $('#extraction-items-empty');

      if (countBadge) countBadge.textContent = `${items.length} item${items.length === 1 ? '' : 's'}`;
      if (tbody) tbody.innerHTML = '';

      if (items.length > 0) {
        if (tableWrap) tableWrap.hidden = false;
        if (emptyState) emptyState.hidden = true;
        items.forEach((item, idx) => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td style="color: var(--text-muted); font-size: 11px;">${idx + 1}</td>
            <td><strong>${escapeHtml(item.description || 'Item')}</strong></td>
            <td style="text-align: right;">${item.quantity != null ? item.quantity : '1'}</td>
            <td style="text-align: right;">${item.unit_price != null ? (inv.currency || '$') + item.unit_price : '-'}</td>
            <td style="text-align: right; font-weight: 700;">${item.amount != null ? (inv.currency || '$') + item.amount : '-'}</td>
          `;
          tbody?.appendChild(tr);
        });
      } else {
        if (tableWrap) tableWrap.hidden = true;
        if (emptyState) emptyState.hidden = false;
      }

    } else if (docType === 'resume') {
      const res_data = data.resume_data || {};
      const fields = [
        { label: 'Candidate Name', val: res_data.candidate_name, highlight: true },
        { label: 'Headline / Role', val: res_data.headline_or_title },
        { label: 'Matched Skills Count', val: res_data.skills?.length ? `${res_data.skills.length} skills matched` : null },
        { label: 'Summary', val: res_data.summary }
      ];

      fields.forEach(f => {
        const card = document.createElement('div');
        card.className = 'extraction-field-card';
        const isNull = !f.val;
        const displayVal = isNull ? 'Not detected' : escapeHtml(String(f.val));
        const valClass = `extraction-field-value ${isNull ? 'null-val' : ''} ${f.highlight && !isNull ? 'highlight-val' : ''}`;
        card.innerHTML = `
          <span class="extraction-field-label">${escapeHtml(f.label)}</span>
          <span class="${valClass}">${displayVal}</span>
        `;
        grid.appendChild(card);
      });

      const lineItemsSection = $('#extraction-line-items-section');
      if (lineItemsSection) lineItemsSection.hidden = true;

    } else {
      // General Document
      const gen = data.general_data || {};
      const fields = [
        { label: 'Document Title', val: gen.title, highlight: true },
        { label: 'Document Date', val: gen.document_date },
        { label: 'Detected Topics Count', val: gen.detected_topics?.length ? `${gen.detected_topics.length} topics` : null }
      ];

      fields.forEach(f => {
        const card = document.createElement('div');
        card.className = 'extraction-field-card';
        const isNull = !f.val;
        const displayVal = isNull ? 'Not detected' : escapeHtml(String(f.val));
        const valClass = `extraction-field-value ${isNull ? 'null-val' : ''} ${f.highlight && !isNull ? 'highlight-val' : ''}`;
        card.innerHTML = `
          <span class="extraction-field-label">${escapeHtml(f.label)}</span>
          <span class="${valClass}">${displayVal}</span>
        `;
        grid.appendChild(card);
      });

      const lineItemsSection = $('#extraction-line-items-section');
      if (lineItemsSection) lineItemsSection.hidden = true;
    }
  }

  // Contacts
  const contactsContainer = $('#extraction-contacts-container');
  if (contactsContainer) {
    contactsContainer.innerHTML = '';
    const emails = data.contact?.emails || [];
    const phones = data.contact?.phones || [];
    if (emails.length === 0 && phones.length === 0) {
      contactsContainer.innerHTML = '<span style="color: var(--text-muted); font-style: italic;">No contact details found</span>';
    } else {
      emails.forEach(em => {
        contactsContainer.innerHTML += `<span class="extraction-pill">${escapeHtml(em)}</span>`;
      });
      phones.forEach(ph => {
        contactsContainer.innerHTML += `<span class="extraction-pill">${escapeHtml(ph)}</span>`;
      });
    }
  }

  // Source pages
  const sourcePagesContainer = $('#extraction-source-pages');
  if (sourcePagesContainer) {
    const sp = data.source_pages || [1];
    sourcePagesContainer.innerHTML = sp.map(p => `<span class="extraction-pill">Page ${p}</span>`).join('');
  }

  // Developer JSON view
  const jsonCodeEl = $('#extraction-json-code');
  if (jsonCodeEl) {
    jsonCodeEl.textContent = JSON.stringify(data, null, 2);
  }

  modal.hidden = false;
}

$('#trigger-extract-btn').onclick = async () => {
  if (!state.files.length) {
    showToast('Please upload or select a PDF document first.', 'warning');
    aiFileInput?.click();
    return;
  }
  const btn = $('#trigger-extract-btn');
  btn.disabled = true;
  btn.textContent = 'Extracting Entities...';

  const form = new FormData();
  form.append('file', state.files[0]);
  const docTypeVal = $('#ai-extract-type-select')?.value || 'auto';
  form.append('doc_type', docTypeVal);

  try {
    const res = await safeFetch('/api/ai/extract', { method: 'POST', body: form });
    renderExtractionResultsModal(res.data);
    showToast('Structured extraction completed successfully!', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Extract Structured Entities';
  }
};

// Extraction Modal Controls & Tab Switching
const extModal = $('#extraction-results-modal');
const extCloseBtn = $('#extraction-modal-close-btn');
const extDoneBtn = $('#extraction-modal-done-btn');
if (extCloseBtn) extCloseBtn.onclick = () => { if (extModal) extModal.hidden = true; };
if (extDoneBtn) extDoneBtn.onclick = () => { if (extModal) extModal.hidden = true; };

const extTabStructured = $('#ext-tab-structured');
const extTabJson = $('#ext-tab-json');
const extViewStructured = $('#ext-view-structured');
const extViewJson = $('#ext-view-json');

if (extTabStructured) {
  extTabStructured.onclick = () => {
    extTabStructured.classList.add('active');
    extTabJson?.classList.remove('active');
    if (extViewStructured) extViewStructured.hidden = false;
    if (extViewJson) extViewJson.hidden = true;
  };
}

if (extTabJson) {
  extTabJson.onclick = () => {
    extTabJson.classList.add('active');
    extTabStructured?.classList.remove('active');
    if (extViewJson) extViewJson.hidden = false;
    if (extViewStructured) extViewStructured.hidden = true;
  };
}

function copyExtractionJson() {
  if (!currentExtractionData) return;
  const jsonStr = JSON.stringify(currentExtractionData, null, 2);
  navigator.clipboard.writeText(jsonStr);
  showToast('Canonical JSON copied to clipboard!', 'success');
}

const copyJsonBtn = $('#extraction-copy-json-btn');
const copyJsonTabBtn = $('#extraction-copy-json-tab-btn');
if (copyJsonBtn) copyJsonBtn.onclick = copyExtractionJson;
if (copyJsonTabBtn) copyJsonTabBtn.onclick = copyExtractionJson;

const exportJsonBtn = $('#extraction-export-json-btn');
if (exportJsonBtn) {
  exportJsonBtn.onclick = () => {
    if (!currentExtractionData) return;
    const jsonStr = JSON.stringify(currentExtractionData, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json;charset=utf-8' });
    const docName = (state.files[0]?.name || 'document').replace(/\.[^/.]+$/, '');
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${docName}_extracted.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast('Exported structured JSON file', 'success');
  };
}

const exportCsvBtn = $('#extraction-export-csv-btn');
if (exportCsvBtn) {
  exportCsvBtn.onclick = () => {
    if (!currentExtractionData) return;
    const csvStr = currentExtractionData.csv_export || '';
    if (!csvStr) {
      showToast('No tabular data available for CSV export', 'warning');
      return;
    }
    const blob = new Blob([csvStr], { type: 'text/csv;charset=utf-8' });
    const docName = (state.files[0]?.name || 'document').replace(/\.[^/.]+$/, '');
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${docName}_extracted.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast('Exported CSV file', 'success');
  };
}

// ----------------------------------------------------------------------
// Developer API Keys Modal Controller
// ----------------------------------------------------------------------

async function loadApiKeys() {
  const list = $('#api-keys-list');
  if (!list) return;
  list.innerHTML = 'Loading keys…';
  try {
    const data = await safeFetch('/api/developer/keys');
    if (!data.keys || !data.keys.length) {
      list.innerHTML = '<div style="color: var(--text-muted); font-size: 13px; padding: 10px;">No active API keys found. Generate one below.</div>';
      return;
    }
    list.innerHTML = data.keys.map(k => `
      <div class="file-row-card">
        <div>
          <strong>${k.name}</strong> · <code style="font-family: var(--font-mono); font-size: 11px;">${k.key_prefix}</code>
          <small style="display: block; color: var(--text-muted);">Created: ${new Date(k.created_at * 1000).toLocaleDateString()}</small>
        </div>
        <button class="delete-file-btn" onclick="revokeKey('${k.id}')" title="Revoke API Key"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
    `).join('');
  } catch (err) {
    list.innerHTML = `<div class="result-card error">${err.message}</div>`;
  }
}

window.revokeKey = async keyId => {
  if (!confirm('Are you sure you want to revoke this API key?')) return;
  try {
    await safeFetch(`/api/developer/keys/${keyId}`, { method: 'DELETE' });
    loadSettingsApiKeys();
    if ($('#api-keys-list')) loadApiKeys();
    showToast('API key revoked.', 'info');
  } catch (err) {
    showToast(err.message, 'error');
  }
};

if ($('#create-key-form')) {
  $('#create-key-form').onsubmit = async e => {
  e.preventDefault();
  const name = $('#new-key-name').value.trim();
  const form = new FormData();
  form.append('name', name);
  try {
    const data = await safeFetch('/api/developer/keys', { method: 'POST', body: form });
    $('#new-key-alert').innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
        <strong>API Key Generated:</strong>
        <button type="button" class="btn-primary-action" style="padding: 4px 10px; font-size: 11px;" onclick="copyToClipboard('${data.api_key}')"> Copy Key</button>
      </div>
      <code style="display: block; background: #fff; padding: 8px 12px; margin: 8px 0; border: 1px solid var(--border-light); border-radius: 6px; font-weight: bold; word-break: break-all; font-family: var(--font-mono); cursor: pointer;" onclick="copyToClipboard('${data.api_key}')" title="Click to copy">${data.api_key}</code>
      <small style="color: var(--text-muted);">Click key to copy. It cannot be shown again.</small>
    `;
    $('#new-key-alert').hidden = false;
    $('#new-key-name').value = '';
    loadApiKeys();
    showToast('New API key generated!', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
  };
}

window.copyToClipboard = text => {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text);
  } else {
    const input = document.createElement('textarea');
    input.value = text;
    document.body.appendChild(input);
    input.select();
    document.execCommand('copy');
    input.remove();
  }
  showToast('API key copied to clipboard! ');
};

// ----------------------------------------------------------------------
// Cloud Import Modal Controller
// ----------------------------------------------------------------------

function openCloudModal() {
  $('#cloud-modal').hidden = false;
  $('#cloud-url').value = '';
  $('#cloud-url').focus();
  $('#cloud-error').hidden = true;
}

if ($('#topbar-cloud-btn')) $('#topbar-cloud-btn').onclick = openCloudModal;
if ($('#cloud-drop-btn')) $('#cloud-drop-btn').onclick = openCloudModal;
if ($('#close-cloud-modal')) $('#close-cloud-modal').onclick = () => $('#cloud-modal').hidden = true;

// Close modals when clicking backdrop
$$('.modal-backdrop').forEach(modal => {
  modal.onclick = e => {
    if (e.target === modal) modal.hidden = true;
  };
});
if ($('#command-modal')) {
  $('#command-modal').onclick = e => {
    if (e.target === $('#command-modal')) $('#command-modal').hidden = true;
  };
}

// ----------------------------------------------------------------------
// Auth Modal Controller & Social Auth
// ----------------------------------------------------------------------

let authMode = 'login';
function openAuthModal(msg = '', requestedMode = null) {
  if (requestedMode === 'login' || requestedMode === 'register') authMode = requestedMode;
  $('#auth-modal').hidden = false;
  const forgotPane = $('#auth-forgot-pane');
  if (forgotPane) forgotPane.hidden = true;
  const authForm = $('#auth-form');
  if (authForm) authForm.hidden = false;
  const authTabs = $('#auth-tabs');
  if (authTabs) authTabs.hidden = false;
  const authDivider = $('#auth-divider');
  if (authDivider) authDivider.hidden = false;
  const googleBtn = $('#google-auth-btn');
  if (googleBtn) {
    googleBtn.hidden = false;
    googleBtn.style.display = 'flex';
  }
  const gisContainer = $('#google-gis-container');
  if (gisContainer) gisContainer.hidden = false;
  $('#auth-modal-title').textContent = authMode === 'login' ? 'Sign In to Paperplane' : 'Create an Account';

  if (msg) {
    $('#auth-error').textContent = msg;
    $('#auth-error').hidden = false;
  } else {
    $('#auth-error').hidden = true;
  }
  initGoogleAuth();
}

function setAuthMode(mode) {
  if (mode === 'register') $('#tab-register')?.click();
  else $('#tab-login')?.click();
}

$('#close-auth-modal').onclick = () => $('#auth-modal').hidden = true;

$('#tab-login').onclick = () => {
  authMode = 'login';
  $('#tab-login').classList.add('active');
  $('#tab-register').classList.remove('active');
  $('#auth-modal-title').textContent = 'Sign In to Paperplane';
  $('#auth-submit-btn').innerHTML = 'Sign In <span>→</span>';
  if ($('#auth-confirm-password-row')) $('#auth-confirm-password-row').hidden = true;
  if ($('#auth-forgot-row')) $('#auth-forgot-row').hidden = false;
  $('#auth-error').hidden = true;
};

$('#tab-register').onclick = () => {
  authMode = 'register';
  $('#tab-register').classList.add('active');
  $('#tab-login').classList.remove('active');
  $('#auth-modal-title').textContent = 'Create an Account';
  $('#auth-submit-btn').innerHTML = 'Create Account <span>→</span>';
  if ($('#auth-confirm-password-row')) $('#auth-confirm-password-row').hidden = false;
  if ($('#auth-forgot-row')) $('#auth-forgot-row').hidden = true;
  $('#auth-error').hidden = true;
};

if ($('#topbar-signin-btn')) {
  $('#topbar-signin-btn').onclick = () => {
    openAuthModal('', 'login');
    setAuthMode('login');
  };
}
if ($('#topbar-register-btn')) {
  $('#topbar-register-btn').onclick = () => {
    openAuthModal('', 'register');
    setAuthMode('register');
  };
}
if ($('#topbar-user-profile-btn')) {
  $('#topbar-user-profile-btn').onclick = () => openSettingsModal('account');
}

// Password Show / Hide Eye Toggle
const pwToggleBtn = $('#password-toggle-btn');
const pwInput = $('#auth-password');
if (pwToggleBtn && pwInput) {
  pwToggleBtn.onclick = () => {
    const isPassword = pwInput.type === 'password';
    pwInput.type = isPassword ? 'text' : 'password';
    pwToggleBtn.title = isPassword ? 'Hide password' : 'Show password';
  };
}

const confirmToggleBtn = $('#confirm-password-toggle-btn');
const confirmInput = $('#auth-confirm-password');
if (confirmToggleBtn && confirmInput) {
  confirmToggleBtn.onclick = () => {
    const isPassword = confirmInput.type === 'password';
    confirmInput.type = isPassword ? 'text' : 'password';
    confirmToggleBtn.title = isPassword ? 'Hide password' : 'Show password';
  };
}

// ----------------------------------------------------------------------
// Two-Factor & Confirmation OTP State
// ----------------------------------------------------------------------
let pendingAuth = null;
let otpTimerInterval = null;

function startOtpCountdown(seconds = 60) {
  if (otpTimerInterval) clearInterval(otpTimerInterval);
  let remaining = seconds;
  const countdownEl = $('#otp-countdown');
  const timerTextEl = $('#otp-timer-text');
  const resendBtn = $('#btn-resend-otp');

  if (countdownEl) countdownEl.textContent = remaining;
  if (timerTextEl) timerTextEl.style.display = '';
  if (resendBtn) resendBtn.style.display = 'none';

  otpTimerInterval = setInterval(() => {
    remaining -= 1;
    if (countdownEl) countdownEl.textContent = remaining;
    if (remaining <= 0) {
      clearInterval(otpTimerInterval);
      if (timerTextEl) timerTextEl.style.display = 'none';
      if (resendBtn) resendBtn.style.display = '';
    }
  }, 1000);
}

function showOtpView(email, purpose) {
  pendingAuth = { email, purpose };
  $('#auth-form').hidden = true;
  $('#auth-tabs').hidden = true;
  $('#auth-divider').hidden = true;
  const googleBtn = $('#google-auth-btn');
  if (googleBtn) googleBtn.hidden = true;
  $('#google-gis-container').hidden = true;

  $('#auth-otp-pane').hidden = false;
  $('#auth-modal-title').textContent = purpose === 'signup' ? 'Confirm Your Account' : 'Two-Factor Verification';
  $('#auth-otp-email-display').textContent = email;
  $('#auth-otp-code').value = '';
  $('#auth-otp-error').hidden = true;
  $('#auth-otp-submit-btn').innerHTML = purpose === 'signup' ? 'Verify & Activate Account <span>→</span>' : 'Verify & Sign In <span>→</span>';
  startOtpCountdown(60);
  setTimeout(() => $('#auth-otp-code')?.focus(), 50);
}

// Official Google Identity Services (GIS) & Social Authentication
let googleAuthConfig = null;
let googleAuthInitialized = false;

async function initGoogleAuth() {
  const manualBtn = $('#google-auth-btn');
  if (manualBtn && !manualBtn.hasAttribute('data-bound')) {
    manualBtn.setAttribute('data-bound', 'true');
    manualBtn.onclick = async () => {
      if (googleAuthConfig && googleAuthConfig.google_enabled && googleAuthConfig.google_client_id && window.google?.accounts?.id) {
        try {
          window.google.accounts.id.prompt();
          return;
        } catch (e) {
          console.warn('GIS prompt error:', e);
        }
      }
      showToast('Google Sign-In is production-ready. Set GOOGLE_CLIENT_ID in .env to connect your Google Cloud credentials. Please sign in with email/password.', 'info', 6000);
    };
  }

  if (googleAuthInitialized) return;
  try {
    if (!googleAuthConfig) {
      googleAuthConfig = await safeFetch('/api/auth/config');
    }
    const cfg = googleAuthConfig;

    if (cfg && cfg.google_enabled && cfg.google_client_id) {
      const setupGIS = () => {
        if (!window.google?.accounts?.id) return false;
        try {
          window.google.accounts.id.initialize({
            client_id: cfg.google_client_id,
            callback: handleGoogleAuthCallback,
            auto_select: false,
            cancel_on_tap_outside: true
          });
          googleAuthInitialized = true;
          return true;
        } catch (e) {
          console.warn('Google Identity Services initialization warning:', e);
          return false;
        }
      };

      if (!setupGIS()) {
        let attempts = 0;
        const interval = setInterval(() => {
          attempts++;
          if (setupGIS() || attempts > 30) {
            clearInterval(interval);
          }
        }, 150);
      }
    } else {
      googleAuthInitialized = true;
    }
  } catch (err) {
    console.warn('Could not load Google auth config:', err);
  }
}

async function handleGoogleAuthCallback(response) {
  if (!response || !response.credential) {
    $('#auth-error').textContent = 'Google authentication did not return a valid credential token.';
    $('#auth-error').hidden = false;
    return;
  }
  const btn = $('#google-auth-btn');
  if (btn) btn.disabled = true;
  try {
    const data = await safeFetch('/api/auth/google', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credential: response.credential })
    });
    if (data.token) {
      localStorage.setItem('paperplane_token', data.token);
      document.cookie = `paperplane_token=${data.token}; path=/; max-age=1209600; SameSite=Lax`;
      $('#auth-modal').hidden = true;
      await checkAuthStatus();
      showToast('Signed in with Google successfully!');
    }
  } catch (err) {
    $('#auth-error').textContent = err.message || 'Google token verification failed.';
    $('#auth-error').hidden = false;
  } finally {
    if (btn) btn.disabled = false;
  }
}

const googleAuthBtn = $('#google-auth-btn');
if (googleAuthBtn) {
  googleAuthBtn.onclick = () => {
    if (window.google?.accounts?.id && googleAuthConfig?.google_client_id) {
      window.google.accounts.id.prompt();
    } else {
      showToast('Google Sign-In is initializing or client ID is not configured.', 'warning');
    }
  };
}

// Secure Logout Handler
const signoutBtn = $('#settings-signout-btn');
if (signoutBtn) {
  signoutBtn.onclick = async () => {
    try {
      await safeFetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {
      console.warn('Logout request warning:', e);
    }
    localStorage.removeItem('paperplane_token');
    document.cookie = 'paperplane_token=; path=/; max-age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax';
    $('#settings-modal').hidden = true;
    await checkAuthStatus();
    showToast('Signed out of Paperplane.');
  };
}

$('#auth-form').onsubmit = async e => {
  e.preventDefault();
  const email = $('#auth-email').value.trim();
  const password = $('#auth-password').value;
  const confirmPassword = $('#auth-confirm-password')?.value;
  $('#auth-error').hidden = true;

  if (authMode === 'register') {
    if (password !== confirmPassword) {
      $('#auth-error').textContent = 'Passwords do not match. Please re-enter.';
      $('#auth-error').hidden = false;
      return;
    }
    if (password.length < 8) {
      $('#auth-error').textContent = 'Password must be at least 8 characters.';
      $('#auth-error').hidden = false;
      return;
    }
  }

  const btn = $('#auth-submit-btn');
  btn.disabled = true;

  try {
    const formData = new FormData();
    formData.append('email', email);
    formData.append('password', password);
    formData.append('require_otp', '1');
    if (authMode === 'register' && confirmPassword) {
      formData.append('confirm_password', confirmPassword);
    }

    const endpoint = authMode === 'login' ? '/api/auth/login' : '/api/auth/register';
    const data = await safeFetch(endpoint, { method: 'POST', body: formData });

    if (data.status === 'otp_required') {
      showOtpView(data.email, data.purpose);
      showToast(data.message || 'Verification code sent to your email.');
    } else if (data.token) {
      localStorage.setItem('paperplane_token', data.token);
      document.cookie = `paperplane_token=${data.token}; path=/; max-age=1209600; SameSite=Lax`;
      $('#auth-modal').hidden = true;
      await checkAuthStatus();
      showToast('Signed in successfully!');
    }
  } catch (err) {
    $('#auth-error').textContent = err.message;
    $('#auth-error').hidden = false;
  } finally {
    btn.disabled = false;
  }
};

const authOtpForm = $('#auth-otp-form');
if (authOtpForm) {
  authOtpForm.onsubmit = async e => {
    e.preventDefault();
    if (!pendingAuth) return;

    const code = $('#auth-otp-code').value.trim();
    if (!code || code.length !== 6) {
      $('#auth-otp-error').textContent = 'Please enter the 6-digit code sent to your email.';
      $('#auth-otp-error').hidden = false;
      return;
    }

    const btn = $('#auth-otp-submit-btn');
    btn.disabled = true;
    $('#auth-otp-error').hidden = true;

    try {
      const endpoint = pendingAuth.purpose === 'signup' ? '/api/auth/verify-signup-otp' : '/api/auth/verify-login-otp';
      const res = await safeFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: pendingAuth.email, otp: code })
      });

      if (res.token) {
        localStorage.setItem('paperplane_token', res.token);
        document.cookie = `paperplane_token=${res.token}; path=/; max-age=1209600; SameSite=Lax`;
        if (otpTimerInterval) clearInterval(otpTimerInterval);
        $('#auth-modal').hidden = true;
        await checkAuthStatus();
        showToast(pendingAuth.purpose === 'signup' ? 'Account verified and activated!' : 'Signed in successfully!', 'success');
      }
    } catch (err) {
      $('#auth-otp-error').textContent = err.message || 'Invalid or expired verification code.';
      $('#auth-otp-error').hidden = false;
    } finally {
      btn.disabled = false;
    }
  };
}

const resendOtpBtn = $('#btn-resend-otp');
if (resendOtpBtn) {
  resendOtpBtn.onclick = async () => {
    if (!pendingAuth) return;
    resendOtpBtn.disabled = true;
    resendOtpBtn.textContent = 'Sending…';
    try {
      const res = await safeFetch('/api/auth/resend-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: pendingAuth.email, purpose: pendingAuth.purpose })
      });
      showToast(res.message || 'A new code has been sent to your email.', 'success');
      if ($('#auth-otp-code')) {
        $('#auth-otp-code').value = '';
        $('#auth-otp-code').focus();
      }
      startOtpCountdown(60);
    } catch (err) {
      $('#auth-otp-error').textContent = err.message || 'Could not resend code. Please try again later.';
      $('#auth-otp-error').hidden = false;
    } finally {
      resendOtpBtn.disabled = false;
      resendOtpBtn.textContent = 'Resend Code';
    }
  };
}

const backOtpBtn = $('#auth-otp-back-btn');
if (backOtpBtn) {
  backOtpBtn.onclick = () => {
    if (otpTimerInterval) clearInterval(otpTimerInterval);
    $('#auth-otp-pane').hidden = true;
    $('#auth-form').hidden = false;
    $('#auth-tabs').hidden = false;
    $('#auth-divider').hidden = false;
    const googleBtn = $('#google-auth-btn');
    if (googleBtn) {
      googleBtn.hidden = false;
      googleBtn.style.display = 'flex';
    }
    $('#google-gis-container').hidden = false;
    $('#auth-modal-title').textContent = authMode === 'login' ? 'Sign In to Paperplane' : 'Create an Account';
  };
}

// ----------------------------------------------------------------------
// Password Reset & Recovery Controller
// ----------------------------------------------------------------------

const linkForgotPw = $('#link-forgot-password');
if (linkForgotPw) {
  linkForgotPw.onclick = () => {
    $('#auth-form').hidden = true;
    $('#auth-tabs').hidden = true;
    $('#auth-divider').hidden = true;
    const googleBtn = $('#google-auth-btn');
    if (googleBtn) googleBtn.hidden = true;
    $('#google-gis-container').hidden = true;
    $('#auth-forgot-pane').hidden = false;
    $('#auth-modal-title').textContent = 'Reset Account Password';
    const msg = $('#forgot-message');
    if (msg) msg.hidden = true;
  };
}

const backForgotBtn = $('#forgot-back-btn');
if (backForgotBtn) {
  backForgotBtn.onclick = () => {
    $('#auth-forgot-pane').hidden = true;
    $('#auth-form').hidden = false;
    $('#auth-tabs').hidden = false;
    $('#auth-divider').hidden = false;
    const googleBtn = $('#google-auth-btn');
    if (googleBtn) {
      googleBtn.hidden = false;
      googleBtn.style.display = 'flex';
    }
    $('#google-gis-container').hidden = false;
    $('#auth-modal-title').textContent = authMode === 'login' ? 'Sign In to Paperplane' : 'Create an Account';
  };
}

const forgotPwForm = $('#forgot-password-form');
if (forgotPwForm) {
  forgotPwForm.onsubmit = async e => {
    e.preventDefault();
    const email = $('#forgot-email').value.trim();
    const btn = $('#forgot-submit-btn');
    const msg = $('#forgot-message');
    btn.disabled = true;
    msg.hidden = true;

    try {
      const res = await safeFetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      msg.className = 'result-card success';
      let html = `<p style="margin: 0; color: #34d399;">${res.message || 'If an account exists, a password reset link has been dispatched.'}</p>`;
      if (res.dev_reset_url) {
        html += `<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.1);"><a href="${res.dev_reset_url}" style="color: var(--accent); text-decoration: underline; font-weight: 600;">[Dev Mode] Click here to open reset password link</a></div>`;
      }
      msg.innerHTML = html;
      msg.hidden = false;
    } catch (err) {
      msg.className = 'result-card error';
      msg.textContent = err.message;
      msg.hidden = false;
    } finally {
      btn.disabled = false;
    }
  };
}

// Password Reset Modal Handlers
const closeResetModalBtn = $('#close-reset-modal');
if (closeResetModalBtn) {
  closeResetModalBtn.onclick = () => {
    $('#reset-password-modal').hidden = true;
  };
}

const resetPwToggle1 = $('#reset-toggle-btn-1');
const resetPwInput1 = $('#reset-new-password');
if (resetPwToggle1 && resetPwInput1) {
  resetPwToggle1.onclick = () => {
    const isPw = resetPwInput1.type === 'password';
    resetPwInput1.type = isPw ? 'text' : 'password';
  };
}

const resetPwToggle2 = $('#reset-toggle-btn-2');
const resetPwInput2 = $('#reset-confirm-password');
if (resetPwToggle2 && resetPwInput2) {
  resetPwToggle2.onclick = () => {
    const isPw = resetPwInput2.type === 'password';
    resetPwInput2.type = isPw ? 'text' : 'password';
  };
}

const resetPwForm = $('#reset-password-form');
if (resetPwForm) {
  resetPwForm.onsubmit = async e => {
    e.preventDefault();
    const token = $('#reset-token').value.trim();
    const newPassword = $('#reset-new-password').value;
    const confirmPassword = $('#reset-confirm-password').value;
    const errBox = $('#reset-error');
    errBox.hidden = true;

    if (newPassword !== confirmPassword) {
      errBox.textContent = 'Passwords do not match.';
      errBox.hidden = false;
      return;
    }
    if (newPassword.length < 8) {
      errBox.textContent = 'Password must be at least 8 characters.';
      errBox.hidden = false;
      return;
    }

    const btn = $('#reset-submit-btn');
    btn.disabled = true;

    try {
      const res = await safeFetch('/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: newPassword })
      });
      $('#reset-password-modal').hidden = true;
      showToast(res.message || 'Password updated successfully! Please sign in.', 'success');
      openAuthModal();
    } catch (err) {
      errBox.textContent = err.message;
      errBox.hidden = false;
    } finally {
      btn.disabled = false;
    }
  };
}

function checkPasswordResetUrl() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token') || params.get('reset_token');
  if (token || window.location.pathname.includes('/reset-password') || params.has('reset')) {
    const resetModal = $('#reset-password-modal');
    const tokenInput = $('#reset-token');
    if (resetModal) {
      if (token && tokenInput) tokenInput.value = token;
      resetModal.hidden = false;
    }
  }
}

// Settings Modal: Change Password Handler
const changePwForm = $('#settings-change-password-form');
if (changePwForm) {
  changePwForm.onsubmit = async e => {
    e.preventDefault();
    const oldPassword = $('#settings-old-password').value;
    const newPassword = $('#settings-new-password').value;
    const confirmPassword = $('#settings-confirm-password').value;
    const msgBox = $('#settings-password-msg');
    msgBox.hidden = true;

    if (newPassword !== confirmPassword) {
      msgBox.className = 'result-card error';
      msgBox.textContent = 'New passwords do not match.';
      msgBox.hidden = false;
      return;
    }
    if (newPassword.length < 8) {
      msgBox.className = 'result-card error';
      msgBox.textContent = 'Password must be at least 8 characters.';
      msgBox.hidden = false;
      return;
    }

    const submitBtn = $('#settings-password-submit-btn');
    submitBtn.disabled = true;

    try {
      const res = await safeFetch('/api/user/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
      });
      msgBox.className = 'result-card success';
      msgBox.textContent = res.message || 'Password successfully updated.';
      msgBox.hidden = false;
      changePwForm.reset();
      showToast('Password updated successfully!');
    } catch (err) {
      msgBox.className = 'result-card error';
      msgBox.textContent = err.message;
      msgBox.hidden = false;
    } finally {
      submitBtn.disabled = false;
    }
  };
}

// ----------------------------------------------------------------------
// Mobile Navigation Drawer
// ----------------------------------------------------------------------

function openMobileSidebar() {
  const sidebar = $('#sidebar');
  const backdrop = $('#mobile-backdrop');
  if (sidebar) sidebar.classList.add('mobile-open');
  if (backdrop) backdrop.hidden = false;
  $('#mobile-menu-btn')?.setAttribute('aria-expanded', 'true');
}

function closeMobileSidebar() {
  const sidebar = $('#sidebar');
  const backdrop = $('#mobile-backdrop');
  if (sidebar) sidebar.classList.remove('mobile-open');
  if (backdrop) backdrop.hidden = true;
  $('#mobile-menu-btn')?.setAttribute('aria-expanded', 'false');
}

function initMobileNav() {
  const menuBtn = $('#mobile-menu-btn');
  const backdrop = $('#mobile-backdrop');
  const sidebar = $('#sidebar');
  if (menuBtn) menuBtn.onclick = openMobileSidebar;
  if (backdrop) backdrop.onclick = closeMobileSidebar;

  // Swipe the drawer left to dismiss it on touch devices.  The gesture is
  // intentionally bounded to horizontal movement so scrolling the tool list
  // remains natural.
  let touchStartX = 0;
  let touchStartY = 0;
  sidebar?.addEventListener('touchstart', event => {
    const touch = event.changedTouches[0];
    touchStartX = touch.clientX;
    touchStartY = touch.clientY;
  }, { passive: true });
  sidebar?.addEventListener('touchend', event => {
    const touch = event.changedTouches[0];
    const deltaX = touch.clientX - touchStartX;
    const deltaY = touch.clientY - touchStartY;
    if (Math.abs(deltaX) > 56 && Math.abs(deltaX) > Math.abs(deltaY) * 1.25 && deltaX < 0) {
      closeMobileSidebar();
    }
  }, { passive: true });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeMobileSidebar();
  });
}

// ----------------------------------------------------------------------
// Multi-Tier Subscription & Cashfree Checkout Handlers
// ----------------------------------------------------------------------

function initBillingHandlers() {
  if ($('#topbar-upgrade-btn')) $('#topbar-upgrade-btn').onclick = () => openUpgradeModal();
  if ($('#sidebar-upgrade-btn')) $('#sidebar-upgrade-btn').onclick = () => openUpgradeModal();
  if ($('#close-upgrade-modal')) $('#close-upgrade-modal').onclick = closeUpgradeModal;

  // Pro Power User Checkout (₹250/mo)
  const proBtn = $('#pro-cashfree-checkout-btn');
  if (proBtn) {
    proBtn.onclick = () => initiateCheckout('pro', proBtn);
  }


  // Developer API Checkout (₹750/mo)
  const devBtn = $('#dev-cashfree-checkout-btn');
  if (devBtn) {
    devBtn.onclick = () => initiateCheckout('developer', devBtn);
  }


}

async function initiateCheckout(tier, btnEl) {
  const originalText = btnEl.innerHTML;
  btnEl.disabled = true;
  btnEl.innerHTML = 'Connecting to Cashfree…';

  try {
    const res = await safeFetch('/api/billing/checkout-session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tier: tier, mode: 'subscription' })
    });

    if (res.mode === 'demo_activated') {
      showToast(`${tier === 'developer' ? 'Developer API' : 'Pro Power User'} Tier Activated!`, 'success', 5000);
      closeUpgradeModal();
      await checkAuthStatus();
    } else if (res.payment_session_id) {
      if (typeof window.Cashfree !== 'function') {
        throw new Error('Cashfree Checkout SDK did not load. Please refresh and try again.');
      }
      const cashfree = window.Cashfree({
        mode: res.environment === 'PROD' ? 'production' : 'sandbox'
      });
      await cashfree.checkout({
        paymentSessionId: res.payment_session_id,
        redirectTarget: '_self'
      });
    } else {
      showToast('Checkout session created.', 'info');
    }
  } catch (err) {
    showUserErrorModal('Checkout Error', `Could not initiate Cashfree checkout: ${err.message}`);
  } finally {
    btnEl.disabled = false;
    btnEl.innerHTML = originalText;
  }
}

// ----------------------------------------------------------------------
// Initialization
// ----------------------------------------------------------------------

async function init() {
  initBillingHandlers();
  initMobileNav();
  initHomeSearchAndFilter();
  await checkAuthStatus();
  await handleCashfreeReturn();
  await initGoogleAuth();

  try {
    const data = await safeFetch('/api/operations');
    state.operations = data;
    renderSidebarTools();
    renderHomeToolsGrid();
    
    handleInitialRouting();
  } catch (err) {
    console.error('Failed to load operations catalog:', err);
    showToast('Tool catalog is temporarily unavailable. The server-rendered page remains available.', 'warning', 6000);
  }
}

async function handleCashfreeReturn() {
  const params = new URLSearchParams(window.location.search);
  const orderId = params.get('order_id');
  if (params.get('billing') !== 'success' || !orderId) return;
  try {
    const result = await safeFetch(`/api/billing/verify-order/${encodeURIComponent(orderId)}`);
    if (result.status === 'paid') {
      triggerConfetti();
      showToast('Cashfree payment verified. Your new tier is active!', 'success', 5500);
      showUserErrorModal(
        'Payment Succeeded!',
        `Welcome to the ${result.tier === 'developer' ? 'Developer API' : 'Pro'} tier. Your Cashfree payment is verified and your account is active.`,
        { icon: 'Success' }
      );
      await checkAuthStatus();
    } else {
      showToast('Cashfree payment is still being confirmed. We will refresh your tier when the webhook arrives.', 'info', 6000);
    }
  } catch (err) {
    showToast(`Payment verification is pending: ${err.message}`, 'warning', 6000);
  } finally {
    window.history.replaceState({}, document.title, window.location.pathname);
  }
}

// --------------------------------------------------------------------------
// Full-Screen Legal Center Controller (Privacy Policy & Terms of Service)
// --------------------------------------------------------------------------
function switchFullLegalTab(tab = 'privacy') {
  const isPrivacy = tab === 'privacy';
  $('#full-legal-tab-privacy')?.classList.toggle('active', isPrivacy);
  $('#full-legal-tab-terms')?.classList.toggle('active', !isPrivacy);
  if ($('#full-privacy-pane')) $('#full-privacy-pane').hidden = !isPrivacy;
  if ($('#full-terms-pane')) $('#full-terms-pane').hidden = isPrivacy;
  const crumbTool = $('#crumb-tool');
  if (crumbTool && state.activeView === 'legal') {
    crumbTool.textContent = isPrivacy ? 'Privacy Policy' : 'Terms of Service';
  }
}

// Back to workspace buttons
if ($('#legal-back-btn')) $('#legal-back-btn').onclick = () => switchWorkspaceView('home');
if ($('#api-docs-back-btn')) $('#api-docs-back-btn').onclick = () => switchWorkspaceView('home');

// Legal view tabs
if ($('#full-legal-tab-privacy')) $('#full-legal-tab-privacy').onclick = () => switchFullLegalTab('privacy');
if ($('#full-legal-tab-terms')) $('#full-legal-tab-terms').onclick = () => switchFullLegalTab('terms');

// Global footer links
if ($('#footer-link-developers')) $('#footer-link-developers').onclick = () => switchWorkspaceView('api-docs');
if ($('#footer-link-privacy')) $('#footer-link-privacy').onclick = () => switchWorkspaceView('legal', 'privacy');
if ($('#footer-link-terms')) $('#footer-link-terms').onclick = () => switchWorkspaceView('legal', 'terms');
if ($('#footer-link-api-docs')) $('#footer-link-api-docs').onclick = () => switchWorkspaceView('api-docs');

// Auth modal legal notices
if ($('#link-auth-privacy')) $('#link-auth-privacy').onclick = e => {
  e.preventDefault();
  $('#auth-modal').hidden = true;
  switchWorkspaceView('legal', 'privacy');
};
if ($('#link-auth-terms')) $('#link-auth-terms').onclick = e => {
  e.preventDefault();
  $('#auth-modal').hidden = true;
  switchWorkspaceView('legal', 'terms');
};

// Settings modal -> Dedicated REST API Docs View
if ($('#open-api-docs-btn')) $('#open-api-docs-btn').onclick = () => {
  $('#settings-modal').hidden = true;
  switchWorkspaceView('api-docs');
};

// Full API View -> Manage API Keys button in hero box
if ($('#full-api-generate-key-btn')) $('#full-api-generate-key-btn').onclick = () => {
  switchSettingsTab('api');
  openSettingsModal();
};

// Interactive Code Tabs in Full API View
$$('.full-api-tab').forEach(tab => {
  tab.onclick = () => {
    $$('.full-api-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const lang = tab.dataset.lang;
    ['curl', 'python', 'node', 'js'].forEach(l => {
      const block = $(`#full-api-code-${l}`);
      if (block) block.hidden = l !== lang;
    });
  };
});

// Copy button in Full API View
if ($('#btn-copy-full-api-code')) {
  $('#btn-copy-full-api-code').onclick = async () => {
    const activeBlock = Array.from($$('.api-code-block')).find(b => !b.hidden && b.id.startsWith('full-api-code'));
    if (activeBlock) {
      try {
        await navigator.clipboard.writeText(activeBlock.textContent.trim());
        const originalText = $('#btn-copy-full-api-code').innerHTML;
        $('#btn-copy-full-api-code').innerHTML = 'Copied!';
        setTimeout(() => { $('#btn-copy-full-api-code').innerHTML = originalText; }, 2000);
        showToast('Code snippet copied to clipboard!');
      } catch (err) {
        showToast('Press Ctrl+C to copy snippet');
      }
    }
  };
}

// Global Window Exports
window.state = state;
window.selectOperation = selectOperation;
window.switchWorkspaceView = switchWorkspaceView;
window.switchFullLegalTab = switchFullLegalTab;
window.loadDocumentIntoStudio = loadDocumentIntoStudio;
window.openCommandPalette = openCommandPalette;
window.openCloudModal = openCloudModal;
window.openAuthModal = openAuthModal;
window.openSettingsModal = openSettingsModal;
window.switchSettingsTab = switchSettingsTab;
window.applyTheme = applyTheme;
window.openUpgradeModal = openUpgradeModal;
window.closeUpgradeModal = closeUpgradeModal;
window.showUserErrorModal = showUserErrorModal;
window.openMobileSidebar = openMobileSidebar;
window.closeMobileSidebar = closeMobileSidebar;
window.resetHomeSearch = resetHomeSearch;
window.resetJobWorkflow = resetJobWorkflow;

// Native Desktop & Mobile Apps Waitlist Form Handler
const waitlistForm = $('#waitlist-form');
if (waitlistForm) {
  waitlistForm.onsubmit = async (e) => {
    e.preventDefault();
    const email = $('#waitlist-email')?.value?.trim();
    const platform = $('#waitlist-platform')?.value || 'all';
    const btn = $('#waitlist-submit-btn');
    const errBox = $('#waitlist-error');
    const successBox = $('#waitlist-success');

    if (!email) return;
    if (errBox) errBox.hidden = true;
    if (btn) btn.disabled = true;

    try {
      const res = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, platform })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to join waitlist');

      waitlistForm.hidden = true;
      if (successBox) {
        successBox.hidden = false;
        const posBadge = $('#waitlist-position-badge');
        if (posBadge) {
          posBadge.textContent = `You're on the early access list! (Queue Position #${data.waitlist_number || 42})`;
        }
      }
      showToast('Successfully joined the native apps waitlist!', 'success');
    } catch (err) {
      if (errBox) {
        errBox.textContent = err.message;
        errBox.hidden = false;
      }
    } finally {
      if (btn) btn.disabled = false;
    }
  };
}

// URL Path & Query Parameter Routing Engine
function handleInitialRouting() {
  const path = window.location.pathname.toLowerCase();
  const pathSlug = path.replace(/^\/+|\/+$/g, '');
  const urlParams = new URLSearchParams(window.location.search);

  if (typeof checkPasswordResetUrl === 'function') {
    checkPasswordResetUrl();
  }

  if (path.includes('terms') || urlParams.get('legal') === 'terms' || urlParams.get('tab') === 'terms') {
    switchWorkspaceView('legal', 'terms', false);
  } else if (path.includes('privacy') || urlParams.get('legal') === 'privacy' || urlParams.get('view') === 'legal') {
    switchWorkspaceView('legal', 'privacy', false);
  } else if (path.includes('developers') || path.includes('api-docs') || path.includes('/docs/api') || urlParams.get('view') === 'api-docs') {
    switchWorkspaceView('api-docs', null, false);
  } else if (path.includes('download') || path.includes('apps') || urlParams.get('view') === 'download') {
    switchWorkspaceView('download', null, false);
  } else if (OPERATION_BY_SLUG[pathSlug]) {
    selectOperation(OPERATION_BY_SLUG[pathSlug], true);
  } else if (pathSlug === 'convert-pdf') {
    activateHomeCategoryFilter('convert');
    switchWorkspaceView('home', null, false);
  } else if (pathSlug === 'pdf-security') {
    activateHomeCategoryFilter('security');
    switchWorkspaceView('home', null, false);
  } else if (urlParams.get('tool') && state.operations && state.operations[urlParams.get('tool')]) {
    // Backward compatibility for links created before clean URL routing.
    selectOperation(urlParams.get('tool'), true);
  } else {
    selectOperation('merge', false);
    switchWorkspaceView('home', null, false);
  }
}

init();


// Natural Browser History Back/Forward Navigation
window.addEventListener('popstate', e => {
  const path = window.location.pathname.toLowerCase();
  const pathSlug = path.replace(/^\/+|\/+$/g, '');
  const urlParams = new URLSearchParams(window.location.search);
  if (path.includes('terms')) {
    switchWorkspaceView('legal', 'terms', false);
  } else if (path.includes('privacy')) {
    switchWorkspaceView('legal', 'privacy', false);
  } else if (path.includes('developers') || path.includes('api-docs') || path.includes('/docs/api')) {
    switchWorkspaceView('api-docs', null, false);
  } else if (path.includes('download') || path.includes('apps')) {
    switchWorkspaceView('download', null, false);
  } else if (OPERATION_BY_SLUG[pathSlug]) {
    selectOperation(OPERATION_BY_SLUG[pathSlug], true);
  } else if (urlParams.get('tool')) {
    selectOperation(urlParams.get('tool'), true);
  } else {
    switchWorkspaceView('home', null, false);
  }
});


