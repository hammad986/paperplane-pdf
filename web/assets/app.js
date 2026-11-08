// ======================================================================
// Paperplane PDF Platform  -  Next-Gen Enterprise Studio Controller
// ======================================================================

const state = {
  operations: {},
  operation: 'merge',
  category: 'Organize',
  files: [],
  user: null,
  planLimits: {
    free_operations_per_day: 100,
    free_max_file_size_mb: 50,
    pro_max_file_size_mb: 500,
    max_batch_files: 100
  },
  clientSideMode: false,
  activeView: 'home', // 'home', 'tool-desk', 'desk', 'studio', 'ai'
  activeToolResult: null,
  
  // PDF Studio Engine State
  studio: {
    pdfDoc: null,
    currentPage: 1,
    scale: 1.0,
    totalCount: 0,
    srcFile: null,
    isLoading: false,
    pageObserver: null,
    pageRenderTasks: new Map(),
    activeTool: 'pan', // 'pan', 'draw', 'highlight', 'text', 'redact'
    isDrawing: false,
    annotations: [], // array of draw paths and stamps per page
    drawContext: null
  },
  aiConversation: []
};

const CLIENT_SIDE_SUPPORTED_OPERATIONS = new Set(['merge', 'split', 'remove', 'rotate']);
const CLIENT_SIDE_SUPPORTED_LABEL = 'Merge, Split / extract, Remove pages, and Rotate PDF';

let generatedControlId = 0;
function addMissingControlLabels(root) {
  const controls = [];
  if (root instanceof Element && root.matches('input, select, textarea')) controls.push(root);
  if (root.querySelectorAll) controls.push(...root.querySelectorAll('input, select, textarea'));
  controls.forEach(control => {
    if (control.type === 'hidden' || control.closest('label') || control.labels?.length) return;
    if (!control.id) control.id = `paperplane-control-${++generatedControlId}`;
    const label = document.createElement('label');
    label.className = 'sr-only';
    label.htmlFor = control.id;
    label.textContent = control.getAttribute('aria-label') || control.title || control.placeholder || control.name || control.id.replace(/[-_]/g, ' ');
    control.parentElement?.insertBefore(label, control);
  });
}

addMissingControlLabels(document);
new MutationObserver(records => {
  records.forEach(record => record.addedNodes.forEach(node => {
    if (node.nodeType === Node.ELEMENT_NODE) addMissingControlLabels(node);
  }));
}).observe(document.body, { childList: true, subtree: true });

// Tool-session values remain in memory while navigating. The two active
// workspaces may also save their source PDF and lightweight state in this
// browser's IndexedDB; the clear controls remove those local records.
const toolSessionCache = new Map();
let workspaceNavigationVersion = 0;
let localWorkDbPromise = null;
let pendingStudioRestore = null;
let studioPositionSaveTimer = null;
let studioPageJumpLockUntil = 0;
let studioRestorePending = false;
let studioRestorePromise = null;
let aiWorkspaceRestored = false;
let aiWorkspaceRestorePromise = null;

function openLocalWorkDb() {
  if (!('indexedDB' in window)) return Promise.reject(new Error('Local browser storage is unavailable.'));
  if (!localWorkDbPromise) {
    localWorkDbPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open('paperplane-local-work', 1);
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains('work')) request.result.createObjectStore('work');
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('Could not open local browser storage.'));
      request.onblocked = () => reject(new Error('Local browser storage is busy in another tab.'));
    });
  }
  return localWorkDbPromise;
}

async function readLocalWork(key) {
  const db = await openLocalWorkDb();
  return new Promise((resolve, reject) => {
    const request = db.transaction('work', 'readonly').objectStore('work').get(key);
    request.onsuccess = () => resolve(request.result ?? null);
    request.onerror = () => reject(request.error || new Error('Could not read saved work.'));
  });
}

async function writeLocalWork(key, value) {
  const db = await openLocalWorkDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('work', 'readwrite');
    tx.objectStore('work').put(value, key);
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => reject(tx.error || new Error('Could not save work in this browser.'));
    tx.onabort = () => reject(tx.error || new Error('Saving work was interrupted.'));
  });
}

async function removeLocalWork(...keys) {
  const db = await openLocalWorkDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('work', 'readwrite');
    const store = tx.objectStore('work');
    keys.forEach(key => store.delete(key));
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => reject(tx.error || new Error('Could not clear saved work.'));
    tx.onabort = () => reject(tx.error || new Error('Clearing saved work was interrupted.'));
  });
}

function localPdfRecord(file) {
  return {
    blob: file,
    name: file.name || 'document.pdf',
    type: file.type || 'application/pdf',
    lastModified: file.lastModified || Date.now()
  };
}

function fileFromLocalRecord(record) {
  if (!record?.blob) return null;
  return new File([record.blob], record.name || 'document.pdf', {
    type: record.type || 'application/pdf',
    lastModified: record.lastModified || Date.now()
  });
}

function saveStudioPagePosition() {
  if (!state.studio.pdfDoc) return;
  const position = { page: state.studio.currentPage };
  try { sessionStorage.setItem('paperplane-studio-position', JSON.stringify(position)); } catch { /* IndexedDB remains the durable store. */ }
  clearTimeout(studioPositionSaveTimer);
  studioPositionSaveTimer = setTimeout(() => {
    writeLocalWork('studio-position', position).catch(error => {
      console.warn('Paperplane could not save the Studio page position:', error);
    });
  }, 180);
}

function persistAiConversation() {
  writeLocalWork('ai-conversation', state.aiConversation).catch(error => {
    console.warn('Paperplane could not save AI chat locally:', error);
  });
}

function addAiConversationTurn(question, answer, citations = []) {
  state.aiConversation.push({ role: 'user', text: question });
  state.aiConversation.push({ role: 'assistant', text: answer, citations });
  persistAiConversation();
}

window.confirmAction = async function confirmAction(message, { confirmLabel = 'Continue', danger = false } = {}) {
  if (!('HTMLDialogElement' in window) || typeof HTMLDialogElement.prototype.showModal !== 'function') {
    return window.confirm(message);
  }
  const dialog = document.createElement('dialog');
  dialog.className = 'app-confirm-dialog';
  dialog.setAttribute('aria-labelledby', 'app-confirm-title');
  const title = document.createElement('h2');
  title.id = 'app-confirm-title';
  title.textContent = 'Please confirm';
  const copy = document.createElement('p');
  copy.textContent = message;
  const actions = document.createElement('div');
  actions.className = 'app-confirm-actions';
  const cancel = document.createElement('button');
  cancel.type = 'button';
  cancel.className = 'app-confirm-cancel';
  cancel.textContent = 'Cancel';
  const approve = document.createElement('button');
  approve.type = 'button';
  approve.className = danger ? 'app-confirm-accept danger' : 'app-confirm-accept';
  approve.textContent = confirmLabel;
  actions.append(cancel, approve);
  dialog.append(title, copy, actions);
  document.body.append(dialog);
  return new Promise(resolve => {
    const finish = value => {
      if (dialog.open) dialog.close();
      dialog.remove();
      resolve(value);
    };
    cancel.addEventListener('click', () => finish(false), { once: true });
    approve.addEventListener('click', () => finish(true), { once: true });
    dialog.addEventListener('cancel', event => { event.preventDefault(); finish(false); }, { once: true });
    dialog.showModal();
    cancel.focus();
  });
};

async function restoreAiWorkspace() {
  if (aiWorkspaceRestored) return false;
  if (aiWorkspaceRestorePromise) return aiWorkspaceRestorePromise;
  aiWorkspaceRestorePromise = (async () => {
  try {
    const [savedFile, savedMessages] = await Promise.all([
      readLocalWork('ai-pdf'),
      readLocalWork('ai-conversation')
    ]);
    const file = fileFromLocalRecord(savedFile);
    if (file) state.files = [file];
    state.aiConversation = Array.isArray(savedMessages) ? savedMessages : [];
    updateAiDocBar();
    renderAiConversation(state.aiConversation);
    if (file || state.aiConversation.length) rememberLocalWork(file?.name || 'AI chat');
    aiWorkspaceRestored = true;
    return Boolean(file || state.aiConversation.length);
  } catch (error) {
    console.warn('Paperplane could not restore AI work from this browser:', error);
    aiWorkspaceRestored = true;
    return false;
  }
  })();
  return aiWorkspaceRestorePromise;
}

async function restoreStudioWorkspace() {
  if (state.studio.pdfDoc || state.studio.isLoading) return false;
  if (studioRestorePromise) return studioRestorePromise;
  studioRestorePending = true;
  studioRestorePromise = (async () => {
    try {
      let saved = pendingStudioRestore;
      if (!saved) {
        try {
          const [file, position] = await Promise.all([readLocalWork('studio-pdf'), readLocalWork('studio-position')]);
          let sessionPosition = null;
          try { sessionPosition = JSON.parse(sessionStorage.getItem('paperplane-studio-position') || 'null'); } catch { /* ignore corrupt tab state */ }
          if (file) saved = { file, position: sessionPosition || position };
        } catch (error) { console.warn('Paperplane could not read saved Studio work:', error); }
      }
      if (!saved) return false;
      pendingStudioRestore = null;
      const file = fileFromLocalRecord(saved.file);
      if (!file) return false;
      const requestedPage = Math.max(1, Number(saved.position?.page) || 1);
      const loaded = await loadDocumentIntoStudio(file, { initialPage: requestedPage, persist: false });
      if (loaded) {
        showToast(`Restored ${file.name} on page ${state.studio.currentPage}`, 'success', 4000);
      }
      return Boolean(loaded);
    } finally {
      studioRestorePending = false;
      studioRestorePromise = null;
    }
  })();
  return studioRestorePromise;
}

async function clearStudioWorkspace() {
  clearTimeout(studioPositionSaveTimer);
  await removeLocalWork('studio-pdf', 'studio-position').catch(error => console.warn('Could not clear Studio work locally:', error));
  try { sessionStorage.removeItem('paperplane-studio-position'); } catch { /* storage may be disabled */ }
  if (state.studio.pageObserver) state.studio.pageObserver.disconnect();
  state.studio.pageRenderTasks.forEach(task => { try { task.cancel(); } catch { /* already complete */ } });
  state.studio.pageRenderTasks.clear();
  try { await state.studio.pdfDoc?.destroy?.(); } catch { /* already destroyed */ }
  state.studio.pdfDoc = null;
  state.studio.srcFile = null;
  state.studio.totalCount = 0;
  state.studio.currentPage = 1;
  $('#studio-page-stack')?.replaceChildren();
  $('#studio-page-count').textContent = '0';
  $('#page-jump-input').value = '1';
  $('#page-jump-input').disabled = true;
  $('#page-total-indicator').textContent = '0';
  if (window.PaperplaneEditor) window.PaperplaneEditor.loadDocument(null, 'document.pdf', 0);
  if (window.PaperplanePageOrganizer) {
    window.PaperplanePageOrganizer.pdfDoc = null;
    window.PaperplanePageOrganizer.sourceFile = null;
    window.PaperplanePageOrganizer.sourceName = 'document.pdf';
    window.PaperplanePageOrganizer.state.setPages(0);
    window.PaperplanePageOrganizer.renderThumbnails();
    window.PaperplanePageOrganizer._updateBatchToolbar();
  }
  showStudioEmptyState();
  await removeLocalWork('studio-pdf', 'studio-position').catch(error => console.warn('Could not finalize clearing Studio work:', error));
  try { sessionStorage.removeItem('paperplane-studio-position'); } catch { /* storage may be disabled */ }
}

let studioUndoTimer = null;
window.showStudioUndoMutation = (previousFile, page, description, expectedCurrentFile) => {
  const banner = $('#studio-undo-banner');
  if (!banner) return;
  clearTimeout(studioUndoTimer);
  banner.replaceChildren();
  const copy = document.createElement('span');
  copy.textContent = `${description}. `;
  const undo = document.createElement('button');
  undo.type = 'button';
  undo.className = 'work-clear-btn';
  undo.textContent = 'Undo';
  undo.addEventListener('click', async () => {
    if (state.studio.srcFile !== expectedCurrentFile) {
      banner.hidden = true;
      showToast('Undo expired because the document changed again.', 'warning');
      return;
    }
    undo.disabled = true;
    undo.textContent = 'Restoring…';
    const restored = await loadDocumentIntoStudio(previousFile, { initialPage: page });
    if (restored) {
      banner.hidden = true;
      showToast('Last page deletion undone.', 'success');
    } else {
      undo.disabled = false;
      undo.textContent = 'Retry undo';
      showToast('Undo could not restore the prior PDF. Try again before leaving Studio.', 'error', 7000);
    }
  }, { once: true });
  banner.append(copy, undo);
  banner.hidden = false;
  studioUndoTimer = setTimeout(() => { banner.hidden = true; }, 10000);
};

document.getElementById('studio-clear-work-btn')?.addEventListener('click', async () => {
  const confirmed = await window.confirmAction('Clear the saved PDF and page position from this browser? Export any annotations you want to keep first.', { confirmLabel: 'Clear saved work', danger: true });
  if (!confirmed) return;
  await clearStudioWorkspace();
  clearLocalWorkMarkerIfEmpty();
  showToast('Saved PDF and page position cleared from this browser', 'success');
});

function renderAiConversation(messages = []) {
  const container = $('#chat-messages');
  if (!container) return;
  container.querySelectorAll('.chat-bubble').forEach(node => node.remove());
  const emptyState = $('#ai-empty-state');
  if (emptyState) container.prepend(emptyState);
  messages.forEach(message => {
    const bubble = document.createElement('div');
    const isDocumentRequired = message.kind === 'document-required';
    bubble.className = `chat-bubble ${message.role === 'user' ? 'user' : 'ai'}${isDocumentRequired ? ' ai-document-required' : ''}`;
    if (message.role === 'user') {
      const label = document.createElement('strong');
      label.textContent = 'You: ';
      bubble.append(label, document.createTextNode(message.text || ''));
    } else if (isDocumentRequired) {
      const label = document.createElement('strong');
      label.textContent = 'Paperplane AI:';
      const guidance = document.createElement('p');
      guidance.textContent = message.text || 'Upload PDF to chat and ask questions about a document. General questions work without a PDF.';
      bubble.append(label, guidance);
    } else {
      const label = document.createElement('strong');
      label.textContent = 'Paperplane AI:';
      const answer = document.createElement('div');
      answer.className = 'chat-markdown';
      answer.innerHTML = renderMarkdown(message.text || '');
      bubble.append(label, answer);
      const citations = document.createElement('div');
      citations.className = 'chat-citation-tags';
      citations.innerHTML = (message.citations || []).map(page => `<span class="ai-citation-tag">Page ${escapeHtml(page)}</span>`).join('');
      bubble.appendChild(citations);
    }
    container.appendChild(bubble);
  });
  updateAiDocBar();
}

function rememberLocalWork(filename) {
  try { sessionStorage.setItem('paperplane-last-local-document', filename || 'PDF work'); } catch { /* storage may be disabled */ }
}

function hasInMemoryWork() {
  const cachedWork = [...toolSessionCache.values()].some(session => session.files?.length || session.result);
  return Boolean(state.activeToolResult || cachedWork || window.PaperplaneEditor?.editorState?.dirty);
}

function clearLocalWorkMarkerIfEmpty() {
  if (hasInMemoryWork()) return;
  try { sessionStorage.removeItem('paperplane-last-local-document'); } catch { /* storage may be disabled */ }
}

// Keep only the last signed-in email as a same-tab display hint. This is not
// an auth token or entitlement cache; API responses remain authoritative.
const AUTH_SHELL_SESSION_KEY = 'paperplane-last-auth-shell-email';

function cacheAuthShellEmail(email) {
  if (!email || typeof email !== 'string') return;
  try { sessionStorage.setItem(AUTH_SHELL_SESSION_KEY, email); } catch { /* session storage may be disabled */ }
}

function clearAuthShellEmail() {
  try { sessionStorage.removeItem(AUTH_SHELL_SESSION_KEY); } catch { /* session storage may be disabled */ }
}

function restoreCachedAuthShell() {
  let email = '';
  try { email = sessionStorage.getItem(AUTH_SHELL_SESSION_KEY) || ''; } catch { /* storage may be disabled */ }
  if (!email || !$('#topbar-auth-user') || !$('#topbar-username')) return false;

  const initial = (email[0] || 'U').toUpperCase();
  document.body.classList.add('auth-restoring');
  if ($('#topbar-auth-guest')) $('#topbar-auth-guest').hidden = true;
  $('#topbar-auth-user').hidden = false;
  $('#topbar-username').textContent = email;
  if ($('#topbar-avatar')) $('#topbar-avatar').textContent = initial;
  return true;
}

window.addEventListener('beforeunload', event => {
  if (!hasInMemoryWork()) return;
  event.preventDefault();
  event.returnValue = '';
});

function captureToolFormValues() {
  const form = $('#job-form');
  if (!form) return {};
  return Object.fromEntries([...form.elements]
    .filter(control => control.id && control.type !== 'file' && control.type !== 'submit' && control.type !== 'button')
    .map(control => [control.id, {
      value: control.value,
      checked: control.type === 'checkbox' || control.type === 'radio' ? control.checked : undefined
    }]));
}

function restoreToolFormValues(values = {}) {
  Object.entries(values).forEach(([id, saved]) => {
    const control = document.getElementById(id);
    if (!control) return;
    if (typeof saved.checked === 'boolean') control.checked = saved.checked;
    else if (saved.value !== undefined) control.value = saved.value;
  });
}

function saveToolSession(operation) {
  if (!operation) return;
  toolSessionCache.set(operation, {
    files: [...state.files],
    splitPageCount: state.splitPageCount ?? null,
    formValues: captureToolFormValues(),
    result: state.activeToolResult ? { ...state.activeToolResult } : null
  });
}

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

// Keep the quota area useful while account status is still loading. Without
// JavaScript the server-rendered 0 / daily-limit fallback remains visible.
const initialQuotaText = $('#quota-text');
if (document.body.classList.contains('auth-pending') && initialQuotaText) {
  initialQuotaText.textContent = '—';
  initialQuotaText.setAttribute('aria-label', 'Usage is loading');
}

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
  'Organize': ['merge', 'split', 'remove', 'rotate', 'organize', 'scan_pdf', 'grayscale'],
  'Convert': [
    'word_to_pdf', 'excel_to_pdf', 'powerpoint_to_pdf', 'jpg_to_pdf', 'html_to_pdf',
    'pdf_to_word', 'pdf_to_excel', 'pdf_to_powerpoint', 'pdf_to_jpg', 'pdf_to_pdfa',
    'pdf_to_text', 'pdf_to_markdown', 'photo_resizer'
  ],
  'Edit': ['edit', 'annotate', 'sign', 'watermark', 'page_numbers', 'redact', 'crop', 'flatten'],
  'AI': ['ai_chat', 'ai_extract', 'summarize', 'translate', 'protect', 'unlock', 'compress', 'repair', 'ocr', 'compare', 'forms', 'metadata', 'mask_aadhaar'],
  'All': [] // Dynamically holds every operation returned by the server catalog.
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
  translate: 'translate-pdf',
  photo_resizer: 'ssc-photo-resizer',
  mask_aadhaar: 'mask-aadhaar-card-online',
  grayscale: 'convert-pdf-to-grayscale',
  flatten: 'flatten-pdf'
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
  const examBtn = $('#exam-cashfree-checkout-btn');
  if (examBtn) {
    examBtn.disabled = false;
    examBtn.innerHTML = 'Pay ₹19 (24-Hour Pass) →';
  }
  const studentBtn = $('#student-cashfree-checkout-btn');
  if (studentBtn) {
    studentBtn.disabled = false;
    studentBtn.innerHTML = 'Pay ₹49/month with Cashfree →';
  }
  const proBtn = $('#pro-cashfree-checkout-btn');
  if (proBtn) {
    proBtn.disabled = false;
    proBtn.innerHTML = 'Pay ₹250/month with Cashfree →';
  }
  const cyberBtn = $('#cybercafe-cashfree-checkout-btn');
  if (cyberBtn) {
    cyberBtn.disabled = false;
    cyberBtn.innerHTML = 'Pay ₹299/month with Cashfree →';
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
  options.credentials = options.credentials || 'same-origin';
  options.headers = options.headers || {};

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
      const detail = typeof data.detail === 'string' ? data.detail : data.detail?.message;
      const msg = detail || 'This file is larger than the upload limit for your plan. Please select a smaller document or compress it first.';
      showUserErrorModal('File Size Limit Exceeded', msg, { icon: 'Archive' });
      throw new Error(msg);
    }

    const errorMsg = (typeof data.detail === 'string' ? data.detail : data.detail?.message) || (typeof data.error === 'string' ? data.error : data.error?.message) || `Request failed with status ${response.status}`;
    throw new Error(errorMsg);
  }

  return data;
}

// ----------------------------------------------------------------------
// App Shell Layout & Sidebar Controller
// ----------------------------------------------------------------------

// Toggle Sidebar Collapse
$('#collapse-sidebar-btn').onclick = () => {
  if (window.matchMedia('(max-width: 900px)').matches && $('#sidebar')?.classList.contains('mobile-open')) {
    closeMobileSidebar();
    return;
  }
  $('#app-shell').classList.toggle('sidebar-collapsed');
};

// Workspace View Switcher (directory, workbench, Studio, AI and public pages)
const studioMobileOrigins = new Map();
let seoContentRequestVersion = 0;

function placeStudioControl(selector, slotId, mobile) {
  const control = document.querySelector(selector);
  const slot = document.getElementById(slotId);
  if (!control || !slot) return;
  if (!studioMobileOrigins.has(control)) {
    studioMobileOrigins.set(control, { parent: control.parentElement, next: control.nextElementSibling });
  }
  const origin = studioMobileOrigins.get(control);
  if (mobile) {
    if (control.parentElement !== slot) slot.appendChild(control);
    return;
  }
  if (control.parentElement === origin.parent) return;
  if (origin.next?.parentElement === origin.parent) origin.parent.insertBefore(control, origin.next);
  else origin.parent.appendChild(control);
}

function syncStudioBatchPanelLocation() {
  const mobile = window.matchMedia('(max-width: 900px)').matches;
  const shell = $('#app-shell');
  const organizing = $('#btn-mode-organize')?.classList.contains('active');
  const drawerOpen = shell?.classList.contains('studio-pages-open');
  const batchPanel = $('#organizer-batch-bar');
  placeStudioControl('#organizer-batch-bar', 'studio-mobile-batch-slot', mobile && organizing && drawerOpen && batchPanel && !batchPanel.hidden);
}
window.syncStudioBatchPanelLocation = syncStudioBatchPanelLocation;

function updateStudioMobilePageSummary() {
  const summary = $('#studio-mobile-page-summary');
  if (!summary) return;
  const page = Math.max(1, Number($('#page-jump-input')?.value) || 1);
  const total = Math.max(0, Number($('#page-total-indicator')?.textContent) || 0);
  summary.textContent = `Page ${page} of ${total}`;
}

function syncStudioMobileLayout() {
  const mobile = window.matchMedia('(max-width: 900px)').matches;
  placeStudioControl('.studio-primary-ribbon > .studio-tool-group[title="History"]', 'studio-mobile-history-slot', mobile);
  placeStudioControl('.studio-primary-ribbon > .studio-export-group', 'studio-mobile-export-slot', mobile);
  placeStudioControl('#page-indicator', 'studio-mobile-page-slot', mobile);
  placeStudioControl('.studio-primary-ribbon > .studio-tool-group[title="Zoom Controls"]', 'studio-mobile-zoom-slot', mobile);
  placeStudioControl('.studio-sub-ribbon .editor-style-group', 'studio-mobile-properties-slot', mobile);

  if (!mobile) {
    $('#studio-mobile-properties-panel')?.setAttribute('hidden', '');
    $('#studio-mobile-pages-btn')?.setAttribute('aria-expanded', 'false');
    $('#studio-mobile-properties-btn')?.setAttribute('aria-expanded', 'false');
    $('#app-shell')?.classList.remove('studio-pages-open');
  }
  syncStudioBatchPanelLocation();
  updateStudioMobilePageSummary();
}

$('#studio-mobile-pages-btn')?.addEventListener('click', () => {
  const shell = $('#app-shell');
  if (!shell) return;
  const open = shell.classList.toggle('studio-pages-open');
  $('#studio-mobile-pages-btn')?.setAttribute('aria-expanded', String(open));
  $('#studio-mobile-properties-panel')?.setAttribute('hidden', '');
  $('#studio-mobile-properties-btn')?.setAttribute('aria-expanded', 'false');
  syncStudioBatchPanelLocation();
});

$('#studio-mobile-pages-close')?.addEventListener('click', () => {
  $('#app-shell')?.classList.remove('studio-pages-open');
  $('#studio-mobile-pages-btn')?.setAttribute('aria-expanded', 'false');
  syncStudioBatchPanelLocation();
});

$('#studio-mobile-properties-btn')?.addEventListener('click', () => {
  const panel = $('#studio-mobile-properties-panel');
  if (!panel) return;
  const open = panel.hidden;
  panel.hidden = !open;
  panel.setAttribute('aria-hidden', String(!open));
  $('#studio-mobile-properties-btn')?.setAttribute('aria-expanded', String(open));
  $('#app-shell')?.classList.remove('studio-pages-open');
  $('#studio-mobile-pages-btn')?.setAttribute('aria-expanded', 'false');
  syncStudioBatchPanelLocation();
  updateStudioMobilePageSummary();
});

$('#studio-mobile-properties-close')?.addEventListener('click', () => {
  $('#studio-mobile-properties-panel')?.setAttribute('hidden', '');
  $('#studio-mobile-properties-btn')?.setAttribute('aria-expanded', 'false');
});

window.addEventListener('resize', syncStudioMobileLayout, { passive: true });
syncStudioMobileLayout();
const studioPageSummaryObserver = new MutationObserver(updateStudioMobilePageSummary);
['#page-jump-input', '#page-total-indicator', '#studio-page-count'].forEach(selector => {
  const node = $(selector);
  if (node) studioPageSummaryObserver.observe(node, { childList: true, subtree: true, characterData: true, attributes: true });
});
$('#page-jump-input')?.addEventListener('input', updateStudioMobilePageSummary);

function switchWorkspaceView(view, extra = 'privacy', updateHistory = true, preserveOpenCloudModal = false) {
  // The root route remains a useful entry point, but the Tool Desk is the
  // single canonical directory for all PDF tools.
  if (view === 'home') view = 'tool-desk';
  workspaceNavigationVersion += 1;
  if (!preserveOpenCloudModal && view !== 'cloud' && $('#cloud-modal')) $('#cloud-modal').hidden = true;
  if ($('#sidebar')?.classList.contains('mobile-open')) closeMobileSidebar();
  try { sessionStorage.setItem('paperplane-active-view', view); } catch { /* storage may be disabled */ }
  state.activeView = view;
  const mobileViewLabels = { 'tool-desk': 'Tool Desk', desk: 'PDF Tool', studio: 'Studio', ai: 'AI', download: 'Waitlist' };
  if ($('#mobile-view-pill')) $('#mobile-view-pill').textContent = mobileViewLabels[view] || 'Paperplane';
  $('#tab-tool-desk-view')?.classList.toggle('active', view === 'tool-desk');
  $('#tab-desk-view')?.classList.toggle('active', view === 'desk');
  $('#tab-studio-view')?.classList.toggle('active', view === 'studio');
  $('#tab-ai-view')?.classList.toggle('active', view === 'ai');
  $('#tab-download-view')?.classList.toggle('active', view === 'download');

  if ($('#view-home')) $('#view-home').hidden = view !== 'home';
  if ($('#view-tool-desk-directory')) $('#view-tool-desk-directory').hidden = view !== 'tool-desk';
  if ($('#view-tool-desk')) $('#view-tool-desk').hidden = view !== 'desk';
  if ($('#view-pdf-studio')) $('#view-pdf-studio').hidden = view !== 'studio';
  if ($('#view-ai-studio')) $('#view-ai-studio').hidden = view !== 'ai';
  if ($('#view-legal')) $('#view-legal').hidden = view !== 'legal';
  if ($('#view-api-docs')) $('#view-api-docs').hidden = view !== 'api-docs';
  if ($('#view-download')) $('#view-download').hidden = view !== 'download';
  $('.main-area')?.classList.toggle('studio-active', view === 'studio');
  $('#app-shell')?.classList.toggle('studio-active', view === 'studio');
  $('#app-shell')?.classList.toggle('ai-active', view === 'ai');
  document.documentElement.classList.toggle('studio-active', view === 'studio');
  document.body.classList.toggle('studio-active', view === 'studio');
  if (view === 'studio' && !state.studio.pdfDoc) restoreStudioWorkspace();
  if (view === 'ai' && !aiWorkspaceRestored) restoreAiWorkspace();
  if (view === 'studio') syncStudioMobileLayout();
  else {
    $('#app-shell')?.classList.remove('studio-pages-open');
    $('#studio-mobile-properties-panel')?.setAttribute('hidden', '');
  }

  // Strict SEO Content containment: Only display crawlable SEO sections on Home and Tool Desk views
  const seoSection = $('.seo-content');
  if (seoSection) seoSection.style.display = (view === 'tool-desk' || view === 'desk') ? '' : 'none';

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
  } else if (view === 'tool-desk') {
    if (crumbCat) crumbCat.textContent = 'Workspace';
    if (crumbTool) crumbTool.textContent = 'Tool Desk';
    renderToolDeskDirectory();
    if (updateHistory && window.history.pushState && window.location.pathname !== '/tool-desk') {
      window.history.pushState({ view: 'tool-desk' }, '', '/tool-desk');
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
    if (crumbCat) crumbCat.textContent = 'Apps';
    if (crumbTool) crumbTool.textContent = 'Early Access Waitlist';
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
    if (updateHistory && window.history.pushState && window.location.pathname !== '/studio') {
      window.history.pushState({ view: 'studio' }, '', '/studio');
    }
  } else if (view === 'ai') {
    if (crumbCat) crumbCat.textContent = 'Workspace';
    if (crumbTool) crumbTool.textContent = 'AI Document Intelligence';
    if (typeof updateAiDocBar === 'function') updateAiDocBar();
  }

  if (view === 'studio' && !state.studio.pdfDoc && !state.studio.isLoading) showStudioEmptyState();

  // Update mobile bottom navigation bar active button
  const mobMap = {
    'tool-desk': '#mob-nav-desk',
    studio: '#mob-nav-studio',
    ai: '#mob-nav-ai',
    download: '#mob-nav-download'
  };
  $$('.mobile-nav-btn').forEach(b => b.classList.remove('active'));
  if (mobMap[view]) {
    $(mobMap[view])?.classList.add('active');
  }
}

function showStudioEmptyState() {
  const area = $('#studio-canvas-area');
  if (area && !state.studio.pdfDoc && !area.querySelector('.studio-empty-state')) {
    const empty = document.createElement('div');
    empty.className = 'studio-empty-state';
    empty.innerHTML = '<h2>No document open</h2><p>Open PDF, Import, or start a New Page.</p><div><button type="button" class="studio-empty-open">Open PDF</button><button type="button" class="studio-empty-new">New Page</button></div>';
    area.appendChild(empty);
    empty.querySelector('.studio-empty-open')?.addEventListener('click', () => $('#studio-upload-btn')?.click());
    empty.querySelector('.studio-empty-new')?.addEventListener('click', () => loadDocumentIntoStudio(new File([generateBlankA4PdfBytes()], 'blank-page.pdf', { type: 'application/pdf' })));
  }
}

// Navigation event bindings
$('#tab-tool-desk-view')?.addEventListener('click', () => switchWorkspaceView('tool-desk'));
$('#tab-studio-view')?.addEventListener('click', () => switchWorkspaceView('studio'));
$('#tab-ai-view')?.addEventListener('click', () => switchWorkspaceView('ai'));
$('#tab-download-view')?.addEventListener('click', () => switchWorkspaceView('download'));
$('#download-back-btn')?.addEventListener('click', () => switchWorkspaceView('home'));
$('#open-studio-btn')?.addEventListener('click', () => switchWorkspaceView('studio'));
$('#btn-back-to-home')?.addEventListener('click', () => switchWorkspaceView('home'));
$('#result-home-btn')?.addEventListener('click', () => switchWorkspaceView('home'));
$('#result-restart-btn')?.addEventListener('click', resetJobWorkflow);
$$('.brand').forEach(b => b.addEventListener('click', (e) => { e.preventDefault(); switchWorkspaceView('home'); }));

function clearResultPanel() {
  const resEl = $('#result');
  if (resEl) {
    resEl.hidden = true;
    resEl.className = 'result-card';
  }
  const resContent = $('#result-content');
  if (resContent) resContent.innerHTML = '';
  const resMeta = $('#result-meta');
  if (resMeta) resMeta.textContent = '';
  const dlLink = $('#result-download-link');
  if (dlLink) {
    if (dlLink.href && dlLink.href.startsWith('blob:')) {
      try { URL.revokeObjectURL(dlLink.href); } catch (e) { /* ignore */ }
    }
    dlLink.href = '#';
    dlLink.removeAttribute('download');
    dlLink.onclick = null;
  }
  const studioBtn = $('#result-view-studio-btn');
  if (studioBtn) {
    studioBtn.hidden = true;
    studioBtn.onclick = null;
  }
  if ($('#dropzone')) $('#dropzone').hidden = false;
  state.activeToolResult = null;
}

function clearResultAndStudio() {
  clearResultPanel();

  // Reset Studio Document State across operations
  if (state.studio) {
    if (state.studio.pageObserver) state.studio.pageObserver.disconnect();
    state.studio.pageRenderTasks.forEach(task => { try { task.cancel(); } catch { /* ignore completed tasks */ } });
    state.studio.pageRenderTasks.clear();
    if (state.studio.pdfDoc && typeof state.studio.pdfDoc.destroy === 'function') {
      try { state.studio.pdfDoc.destroy(); } catch (e) { /* ignore */ }
    }
    state.studio.pdfDoc = null;
    state.studio.totalCount = 0;
    state.studio.currentPage = 1;
    state.studio.srcFile = null;
  }
  if (window.PaperplaneEditor && typeof window.PaperplaneEditor.loadDocument === 'function') {
    try { window.PaperplaneEditor.loadDocument(null, 'document.pdf', 0); } catch (e) { /* ignore */ }
  }
  if (window.PaperplanePageOrganizer && typeof window.PaperplanePageOrganizer.loadDocument === 'function') {
    try { window.PaperplanePageOrganizer.loadDocument(null, null, '', 0); } catch (e) { /* ignore */ }
  }
  const studioThumbs = $('#studio-thumbnails-container');
  if (studioThumbs) studioThumbs.innerHTML = '';
  const studioPageStack = $('#studio-page-stack');
  const drawCanvas = $('#pdf-draw-canvas');
  if (studioPageStack) {
    studioPageStack.innerHTML = '<section class="page-render-wrapper studio-page-sheet" id="page-render-wrapper" data-page="1" aria-label="Page 1"><div class="studio-page-loading">No document open</div><canvas id="pdf-canvas" class="pdf-page-canvas"></canvas></section>';
    if (drawCanvas) studioPageStack.firstElementChild.appendChild(drawCanvas);
  }
  const studioCount = $('#studio-page-count');
  if (studioCount) studioCount.textContent = '0';
  const pageIndicator = $('#page-indicator');
  if (pageIndicator) {
    const jump = $('#page-jump-input');
    const total = $('#page-total-indicator');
    if (jump) { jump.value = '0'; jump.disabled = true; }
    if (total) total.textContent = '0';
  }
  clearLocalWorkMarkerIfEmpty();
}

function resetJobWorkflow() {
  state.files = [];
  state.splitPageCount = null;
  toolSessionCache.delete(state.operation);
  const form = $('#job-form');
  if (form) form.reset();
  renderFiles();
  renderOptions();
  updateButton();
  if ($('#progress-card')) $('#progress-card').hidden = true;
  clearResultAndStudio();
  clearLocalWorkMarkerIfEmpty();
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
      <button type="button" class="sidebar-tool-item ${isActive ? 'active' : ''}" data-select-operation="${key}">
        ${item.label}
      </button>
    `;
  }).join('');
}

// ----------------------------------------------------------------------
// Tool Desk catalog and category navigation.
// ----------------------------------------------------------------------

const HOME_CATEGORIES = [
  {
    id: 'organize',
    title: 'Organize PDF',
    badge: '7 Tools',
    iconColor: '#ff4b26',
    ops: ['merge', 'split', 'remove', 'rotate', 'organize', 'scan_pdf', 'grayscale']
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
    badge: '13 Tools',
    iconColor: '#3b82f6',
    ops: [
      'pdf_to_word', 'word_to_pdf', 'pdf_to_excel', 'excel_to_pdf',
      'pdf_to_powerpoint', 'powerpoint_to_pdf', 'pdf_to_jpg', 'jpg_to_pdf',
      'html_to_pdf', 'pdf_to_pdfa', 'pdf_to_text', 'pdf_to_markdown', 'photo_resizer'
    ]
  },
  {
    id: 'edit',
    title: 'Edit PDF',
    badge: '8 Tools',
    iconColor: '#f59e0b',
    ops: ['page_numbers', 'watermark', 'crop', 'compare', 'edit', 'annotate', 'flatten', 'metadata']
  },
  {
    id: 'security',
    title: 'Sign & Protect',
    badge: '6 Tools',
    iconColor: '#8b5cf6',
    ops: ['protect', 'unlock', 'sign', 'forms', 'redact', 'mask_aadhaar']
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
    translate: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 8 6 6"></path><path d="m4 14 6-6 2-3"></path><path d="M2 5h12"></path><path d="M7 2h1"></path><path d="m22 22-5-10-5 10"></path><path d="M14 18h6"></path></svg>`,
    photo_resizer: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>`,
    mask_aadhaar: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>`,
    grayscale: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a10 10 0 0 1 0 20z" fill="currentColor"></path></svg>`,
    flatten: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"></rect><line x1="9" y1="9" x2="15" y2="15"></line><line x1="15" y1="9" x2="9" y2="15"></line></svg>`,
    metadata: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><circle cx="12" cy="13" r="2"></circle><path d="M12 9v1"></path><path d="M12 16v1"></path></svg>`
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
              <div class="home-tool-card" role="button" tabindex="0" data-select-operation="${opId}">
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
        <button type="button" class="btn-primary-action" data-reset-home-search>Clear Search</button>
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

function renderToolDeskDirectory(category = null, searchQuery = null) {
  const catalog = $('#tool-desk-tools-catalog');
  if (!catalog) return;
  const activeFilter = category || $('#tool-desk-directory-filters .filter-pill.active')?.dataset.deskCategory || 'all';
  const query = (searchQuery ?? $('#tool-desk-search')?.value ?? '').trim().toLowerCase();
  let totalVisible = 0;
  const sections = HOME_CATEGORIES.map(cat => {
    if (activeFilter !== 'all' && cat.id !== activeFilter) return '';
    const ops = cat.ops.filter(id => {
      const op = state.operations[id];
      if (!op) return false;
      return !query || `${op.label} ${op.description || ''} ${id}`.toLowerCase().includes(query);
    });
    if (!ops.length) return '';
    totalVisible += ops.length;
    return `<section class="home-cat-section" data-cat="${cat.id}">
      <div class="home-cat-header"><div class="home-cat-title-group"><h2 class="home-cat-title" style="--cat-accent:${cat.iconColor}">${escapeHtml(cat.title)}</h2><span class="home-cat-count">${ops.length} tools</span></div></div>
      <div class="home-cat-grid">${ops.map(id => {
        const op = state.operations[id];
        const available = op.available !== false && !['DEPENDENCY_MISSING', 'SERVICE_UNAVAILABLE'].includes(op.status);
        const badge = available ? 'Ready' : (op.prerequisite || 'Temporarily unavailable');
        return `<button type="button" class="home-tool-card" data-select-operation="${escapeHtml(id)}">
          <span class="home-tool-icon" style="background:${cat.iconColor}1a;color:${cat.iconColor}">${getToolIconSvg(id)}</span>
          <span class="home-tool-body"><span class="home-tool-title">${escapeHtml(op.label)}</span><span class="home-tool-desc">${escapeHtml(op.description || 'Fast, private PDF processing.')}</span>
          <span class="home-tool-footer"><span class="home-status-badge ${available ? 'ready' : 'prereq'}">${escapeHtml(badge)}</span><span class="home-tool-arrow" aria-hidden="true">→</span></span></span></button>`;
      }).join('')}</div></section>`;
  }).join('');
  catalog.innerHTML = totalVisible ? sections : `<div class="home-no-results"><h2>No matching tools</h2><p>Try “merge”, “compress”, “sign”, or choose another category.</p><button type="button" class="btn-primary-action" id="tool-desk-reset-search">Clear search</button></div>`;
  const meta = $('#tool-desk-search-meta');
  if (meta) meta.textContent = `${totalVisible} ${totalVisible === 1 ? 'tool' : 'tools'}${query ? ` found for “${$('#tool-desk-search')?.value.trim()}”` : ' available'}`;
  $('#tool-desk-reset-search')?.addEventListener('click', () => {
    const input = $('#tool-desk-search');
    if (input) input.value = '';
    const all = $('#tool-desk-directory-filters [data-desk-category="all"]');
    $$('#tool-desk-directory-filters .filter-pill').forEach(item => item.classList.toggle('active', item === all));
    renderToolDeskDirectory('all', '');
  });
}

function initToolDeskDirectory() {
  $('#tool-desk-search')?.addEventListener('input', () => renderToolDeskDirectory());
  $$('#tool-desk-directory-filters [data-desk-category]').forEach(button => button.addEventListener('click', () => {
    $$('#tool-desk-directory-filters .filter-pill').forEach(item => item.classList.toggle('active', item === button));
    renderToolDeskDirectory(button.dataset.deskCategory);
  }));
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

  const requestVersion = ++seoContentRequestVersion;
  const operationLabel = state.operations[operation]?.label || operation;
  const isCurrentRequest = () => (
    requestVersion === seoContentRequestVersion && state.operation === operation
  );
  document.title = `${operationLabel} | Paperplane`;
  section.setAttribute('aria-busy', 'true');
  section.innerHTML = `<div class="seo-content-inner"><p class="seo-lede" role="status">Loading ${escapeHtml(operationLabel)} details…</p></div>`;

  try {
    const context = await safeFetch(`/api/seo/${encodeURIComponent(operation)}`);
    if (!isCurrentRequest()) return;
    const related = (context.related || []).map(relatedId => {
      const related = state.operations[relatedId] || { label: relatedId };
      const slug = TOOL_SLUGS[relatedId] || relatedId;
      return `<a class="seo-related-link" href="/${slug}">${escapeHtml(related.label)}</a>`;
    }).join(' ');
    const faqs = (context.faqs || []).map(([question, answer]) => (
      `<details class="seo-faq-item"><summary>${escapeHtml(question)}</summary><p>${escapeHtml(answer)}</p></details>`
    )).join('');
    const steps = (context.how_to || []).map((step, index) => (
      `<article class="seo-howto-step"><span>${String(index + 1).padStart(2, '0')}</span><h3>${escapeHtml(step)}</h3></article>`
    )).join('');

    section.innerHTML = `
      <div class="seo-content-inner">
        <div class="seo-eyebrow">${escapeHtml(context.category)} · privacy-first workflow</div>
        <h2 id="seo-page-heading">${escapeHtml(context.heading)}</h2>
        <p class="seo-lede">${escapeHtml(context.intro)}</p>
        <div class="seo-howto-grid">${steps}</div>
        <div class="seo-faq"><h3>Frequently asked questions</h3>${faqs}</div>
        <nav class="seo-related" aria-label="Related PDF tools"><strong>Related tools</strong>${related}</nav>
      </div>`;
    section.removeAttribute('aria-busy');
    if (context.title) document.title = context.title;
  } catch (error) {
    if (!isCurrentRequest()) return;
    section.removeAttribute('aria-busy');
    section.innerHTML = `<div class="seo-content-inner"><p class="seo-lede" role="status">${escapeHtml(operationLabel)} details could not load right now. The PDF tool is still available.</p></div>`;
    console.warn('Could not refresh SEO content for operation:', operation, error);
  }
}

// Select an operation and update view
function selectOperation(op, switchToDesk = true, preserveOpenCloudModal = false) {
  const previousOperation = state.operation;
  const opChanged = (previousOperation !== op);
  if (opChanged) saveToolSession(previousOperation);
  const cachedSession = opChanged ? toolSessionCache.get(op) || null : null;
  state.operation = op;
  const localProcessingWasEnabled = state.clientSideMode;
  syncClientSideControls();
  if (localProcessingWasEnabled && !CLIENT_SIDE_SUPPORTED_OPERATIONS.has(op)) {
    showToast(`${state.operations[op]?.label || op} uses server processing. Local Processing was turned off.`, 'info', 5000);
  }
  if (opChanged) {
    state.files = cachedSession?.files ? [...cachedSession.files] : [];
    state.splitPageCount = cachedSession?.splitPageCount ?? null;
    const form = $('#job-form');
    if (form) form.reset();
    if ($('#progress-card')) $('#progress-card').hidden = true;
    clearResultPanel();
  }
  const item = state.operations[op] || { label: op, accept: 'pdf', category: 'Organize PDF' };
  const operationUnavailable = item.available === false || item.status === 'DEPENDENCY_MISSING' || item.status === 'SERVICE_UNAVAILABLE';
  const availabilityNotice = $('#tool-availability-notice');
  if (availabilityNotice) {
    availabilityNotice.hidden = !operationUnavailable;
    availabilityNotice.textContent = operationUnavailable
      ? `${item.label} is currently unavailable. ${item.prerequisite || 'The required service is not enabled.'}`
      : '';
  }
  ['#file-input', '#browse', '#cloud-drop-btn'].forEach(selector => {
    const control = $(selector);
    if (control) control.disabled = operationUnavailable;
  });

  if ($('#crumb-tool')) $('#crumb-tool').textContent = item.label;
  if ($('#crumb-category')) $('#crumb-category').textContent = item.category;
  if ($('#tool-title')) $('#tool-title').textContent = item.label;
  if ($('#tool-hero-cat')) $('#tool-hero-cat').textContent = item.category;
  if ($('#tool-description')) $('#tool-description').textContent = item.description || 'Enterprise document workflow.';
  if ($('#desk-breadcrumb-label')) $('#desk-breadcrumb-label').textContent = `${item.category} / ${item.label}`;

  const tierBadge = $('#tool-tier-badge');
  if (tierBadge) {
    if (state.user) {
      const accountTier = String(state.user.tier || '').toLowerCase();
      const paidAccount = Boolean(state.user.is_pro || state.user.is_dev || ['developer', 'student_pro', 'cyber_cafe', 'exam_pass'].includes(accountTier));
      if (paidAccount) {
        const paidLabel = state.user.is_dev || accountTier === 'developer' ? 'Developer' : accountTier === 'student_pro' ? 'Student Pro' : accountTier === 'cyber_cafe' ? 'Cyber Café' : accountTier === 'exam_pass' ? 'Exam Pass' : 'Pro Power User';
        tierBadge.textContent = `👑 ${paidLabel} · Unlimited · ${state.planLimits.pro_max_file_size_mb} MB · ${state.planLimits.max_batch_files} files`;
        tierBadge.style.color = '#f59e0b';
        tierBadge.style.borderColor = 'rgba(245,158,11,0.3)';
        tierBadge.style.background = 'rgba(245,158,11,0.1)';
      } else {
        tierBadge.textContent = `✨ Free Account · ${state.planLimits.free_operations_per_day} ops/day · ${state.planLimits.free_max_file_size_mb} MB/file`;
        tierBadge.style.color = '#38bdf8';
        tierBadge.style.borderColor = 'rgba(56,189,248,0.3)';
        tierBadge.style.background = 'rgba(56,189,248,0.1)';
      }
    } else if (typeof HEAVY_TOOLS !== 'undefined' && HEAVY_TOOLS.has(op)) {
      tierBadge.textContent = '🔒 Free Account Required · Sign up in 10s';
      tierBadge.style.color = '#f59e0b';
      tierBadge.style.borderColor = 'rgba(245,158,11,0.3)';
      tierBadge.style.background = 'rgba(245,158,11,0.1)';
    } else {
      tierBadge.textContent = `⚡ Free Guest Tool · No Account Required (${state.planLimits.free_operations_per_day} ops/day · ${state.planLimits.free_max_file_size_mb} MB/file)`;
      tierBadge.style.color = '#10b981';
      tierBadge.style.borderColor = 'rgba(16,185,129,0.3)';
      tierBadge.style.background = 'rgba(16,185,129,0.1)';
    }
  }

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
    hint.textContent = `${item.accept === 'image' ? 'Images' : item.accept === 'office' ? 'Office documents' : 'PDF files'} up to ${state.planLimits.free_max_file_size_mb} MB on Free and ${state.planLimits.pro_max_file_size_mb} MB with Pro · batches up to ${state.planLimits.max_batch_files} files`;
  }

  renderOptions();
  if (opChanged) {
    restoreToolFormValues(cachedSession?.formValues || {});
    renderFiles();
    if (cachedSession?.result) {
      showDownloadResult(cachedSession.result.job, cachedSession.result.downloadUrl, { silent: true });
    }
  }
  renderSidebarTools();
  updateButton();
  if (op === 'ai_chat' && switchToDesk && state.activeView === 'home') {
    switchWorkspaceView('ai', null, true, preserveOpenCloudModal);
    return;
  }
  if (switchToDesk) {
    switchWorkspaceView('desk', null, true, preserveOpenCloudModal);
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
  if (data?.plan_limits) state.planLimits = { ...state.planLimits, ...data.plan_limits };
  const tier = (data && data.tier ? data.tier : 'free').toLowerCase();
  const isPaid = Boolean(data && (data.is_pro || data.is_dev || ['pro', 'developer', 'student_pro', 'cyber_cafe', 'exam_pass'].includes(tier)));
  const usage = data ? (data.usage_today || 0) : 0;
  const limit = data ? (data.daily_limit ?? 100) : 100;
  const freeFileMb = state.planLimits.free_max_file_size_mb;
  const proFileMb = state.planLimits.pro_max_file_size_mb;
  const maxBatchFiles = state.planLimits.max_batch_files;
  state.dailyLimit = limit;
  state.dailyUsage = usage;

  const quotaDescription = $('#settings-quota-description');
  if (quotaDescription) quotaDescription.textContent = `Free: ${state.planLimits.free_operations_per_day} PDF operations per day and files up to ${freeFileMb} MB each. Pro: no daily operation cap, files up to ${proFileMb} MB, and batches up to ${maxBatchFiles} files.`;
  const fileHint = $('#file-hint');
  if (fileHint) fileHint.textContent = `Files up to ${freeFileMb} MB on Free and ${proFileMb} MB with Pro · batches up to ${maxBatchFiles} files`;

  const quotaText = $('#quota-text');
  const quotaFill = $('#quota-fill');
  const sidebarUpgradeBtn = $('#sidebar-upgrade-btn');
  const topbarUpgradeBtn = $('#topbar-upgrade-btn');
  const roleBadge = $('#user-role-badge');
  
  const settingsQuotaText = $('#settings-quota-text');
  const settingsQuotaFill = $('#settings-quota-fill');
  const settingsTierName = $('#settings-tier-name');
  const settingsTierBadge = $('#settings-tier-badge');
  const settingsDailyLimit = $('#settings-daily-limit');
  quotaText?.removeAttribute('aria-label');
  if (settingsDailyLimit) settingsDailyLimit.textContent = isPaid ? '(No daily operation cap)' : `(${limit} operations / day)`;

  if (isPaid) {
    let tierName = 'Pro Power User Tier';
    let badgeText = 'ACTIVE PRO PASS';
    let badgeColor = '#10b981';
    let shortLabel = 'Pro';

    if (tier === 'developer') {
      tierName = 'Developer API Tier';
      badgeText = 'ACTIVE DEVELOPER PASS';
      badgeColor = '#3b82f6';
      shortLabel = 'Developer';
    } else if (tier === 'student_pro') {
      tierName = 'Student & Educator Pro Tier';
      badgeText = 'ACTIVE STUDENT PRO';
      badgeColor = '#10b981';
      shortLabel = 'Student';
    } else if (tier === 'cyber_cafe') {
      tierName = 'Cyber Café Pack Tier';
      badgeText = 'ACTIVE CSC PACK';
      badgeColor = '#8b5cf6';
      shortLabel = 'Cyber Café';
    } else if (tier === 'exam_pass') {
      tierName = '24-Hour Exam Pass';
      badgeText = 'ACTIVE EXAM PASS';
      badgeColor = '#3b82f6';
      shortLabel = 'Exam Pass';
    }

    if (quotaText) quotaText.textContent = `Unlimited · ${proFileMb} MB · ${maxBatchFiles} files`;
    if (quotaFill) {
      quotaFill.style.width = '100%';
      quotaFill.className = 'quota-progress-fill pro';
    }
    if (sidebarUpgradeBtn) sidebarUpgradeBtn.style.display = 'none';
    if (topbarUpgradeBtn) topbarUpgradeBtn.style.display = 'none';
    if (roleBadge) {
      roleBadge.textContent = shortLabel;
      roleBadge.style.color = badgeColor;
      roleBadge.style.fontWeight = '700';
    }
    if (settingsTierName) settingsTierName.textContent = tierName;
    if (settingsTierBadge) {
      settingsTierBadge.textContent = badgeText;
      settingsTierBadge.style.background = `${badgeColor}26`;
      settingsTierBadge.style.color = badgeColor;
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

function applyQuotaCount(count) {
  const numericCount = Number(count);
  if (!Number.isFinite(numericCount)) return;
  state.dailyUsage = numericCount;
  const tier = String(state.user?.tier || 'free').toLowerCase();
  if (['pro', 'developer', 'student_pro', 'cyber_cafe', 'exam_pass'].includes(tier)) return;
  const limit = Number(state.planLimits.free_operations_per_day) || 100;
  const pct = Math.min(100, Math.round((numericCount / limit) * 100));
  const quotaText = $('#quota-text');
  const quotaFill = $('#quota-fill');
  const settingsQuotaText = $('#settings-quota-text');
  const settingsQuotaFill = $('#settings-quota-fill');
  if (quotaText) quotaText.textContent = `${numericCount} / ${limit}`;
  if (settingsQuotaText) settingsQuotaText.textContent = `${numericCount} / ${limit}`;
  if (quotaFill) { quotaFill.style.width = `${pct}%`; quotaFill.className = `quota-progress-fill${numericCount >= limit ? ' full' : numericCount >= limit - 5 ? ' warn' : ''}`; }
  if (settingsQuotaFill) { settingsQuotaFill.style.width = `${pct}%`; settingsQuotaFill.className = `quota-progress-fill${numericCount >= limit ? ' full' : numericCount >= limit - 5 ? ' warn' : ''}`; }
}

const paperplaneNativeFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const response = await paperplaneNativeFetch(...args);
  const count = response.headers.get('X-Paperplane-Operations-Today');
  if (count !== null) applyQuotaCount(count);
  return response;
};

async function refreshQuotaUsage() {
  try {
    const response = await paperplaneNativeFetch('/api/auth/me', { credentials: 'same-origin' });
    if (!response.ok) return;
    const data = await response.json();
    state.user = data.authenticated ? data : null;
    updateBillingUI(data);
  } catch (error) {
    console.warn('Paperplane could not refresh the operation count:', error);
  }
}

async function checkAuthStatus() {
  try {
    const data = await safeFetch('/api/auth/me');
    state.user = data.authenticated ? data : null;
    updateBillingUI(data);
    if (data.authenticated) {
      cacheAuthShellEmail(data.email);
      document.body.classList.remove('auth-restoring');
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
        sBadge.textContent = data.is_dev ? 'Developer API Tier' : data.is_pro ? 'Pro Power User Tier' : `Free Sovereign Tier · ${state.planLimits.free_operations_per_day} operations/day`;
      }
      if ($('#settings-guest-actions')) $('#settings-guest-actions').hidden = true;
      if ($('#settings-user-actions')) $('#settings-user-actions').hidden = false;
    } else {
      clearAuthShellEmail();
      document.body.classList.remove('auth-restoring');
      state.user = null;
      $('#user-avatar').textContent = 'G';
      $('#user-name').textContent = 'Guest Explorer';
      if ($('#topbar-auth-guest')) $('#topbar-auth-guest').hidden = false;
      if ($('#topbar-auth-user')) $('#topbar-auth-user').hidden = true;
      if ($('#topbar-avatar')) $('#topbar-avatar').textContent = 'G';
      if ($('#topbar-username')) $('#topbar-username').textContent = 'Guest Explorer';
      if ($('#settings-user-avatar')) $('#settings-user-avatar').textContent = 'G';
      if ($('#settings-user-email')) $('#settings-user-email').textContent = 'Guest Explorer';
      if ($('#settings-user-badge')) $('#settings-user-badge').textContent = `Free Sovereign Tier · ${state.planLimits.free_operations_per_day} operations/day`;
      if ($('#settings-guest-actions')) $('#settings-guest-actions').hidden = false;
      if ($('#settings-user-actions')) $('#settings-user-actions').hidden = true;
    }
    if (state.activeView === 'desk' && $('#tool-title')) selectOperation(state.operation, false);
  } catch {
    state.user = null;
    if (!restoreCachedAuthShell()) {
      document.body.classList.remove('auth-restoring');
      $('#user-avatar').textContent = 'G';
      $('#user-name').textContent = 'Guest Explorer';
      if ($('#topbar-auth-guest')) $('#topbar-auth-guest').hidden = false;
      if ($('#topbar-auth-user')) $('#topbar-auth-user').hidden = true;
      if ($('#topbar-avatar')) $('#topbar-avatar').textContent = 'G';
      if ($('#topbar-username')) $('#topbar-username').textContent = 'Guest Explorer';
      updateBillingUI(null);
    }
    if (state.activeView === 'desk' && $('#tool-title')) selectOperation(state.operation, false);
  } finally {
    document.body.classList.remove('auth-pending');
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
        <button type="button" class="delete-file-btn" data-revoke-key="${escapeHtml(k.id)}" title="Revoke API Key"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
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
          <button type="button" class="btn-primary-action" style="padding: 4px 10px; font-size: 11px;" data-copy-value="${escapeHtml(data.api_key)}"> Copy Key</button>
        </div>
        <code style="display: block; background: #fff; color: #111; padding: 8px 12px; margin: 8px 0; border: 1px solid var(--border-light); border-radius: 6px; font-weight: bold; word-break: break-all; font-family: var(--font-mono); cursor: pointer;" data-copy-value="${escapeHtml(data.api_key)}" title="Click to copy">${escapeHtml(data.api_key)}</code>
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

function syncClientSideControls() {
  const supported = CLIENT_SIDE_SUPPORTED_OPERATIONS.has(state.operation);
  if (!supported) state.clientSideMode = false;
  const operationLabel = state.operations[state.operation]?.label || state.operation;
  const helpText = supported
    ? `Local processing is available for ${CLIENT_SIDE_SUPPORTED_LABEL}.`
    : `${operationLabel} uses temporary server processing. Local processing is available for ${CLIENT_SIDE_SUPPORTED_LABEL}.`;

  ['client-privacy-toggle', 'settings-client-privacy-toggle'].forEach(id => {
    const input = $(`#${id}`);
    if (!input) return;
    input.checked = state.clientSideMode;
    input.disabled = !supported;
    input.title = helpText;
    input.setAttribute('aria-label', supported
      ? `Use local processing for ${operationLabel}`
      : `Local processing is unavailable for ${operationLabel}; this tool uses temporary server processing`);
  });

  const label = $('#privacy-mode-label');
  if (label) label.textContent = state.clientSideMode ? 'Local Processing' : 'Server Mode';
  const sidebarHelp = $('#privacy-mode-support');
  if (sidebarHelp) sidebarHelp.textContent = supported
    ? 'Available for Merge, Split, Remove, Rotate'
    : 'This tool runs on the server';
  const settingsHelp = $('#settings-client-privacy-support');
  if (settingsHelp) settingsHelp.textContent = helpText;
  const pill = $('#engine-status-pill');
  if (pill) pill.className = state.clientSideMode ? 'engine-pill local' : 'engine-pill';
  const text = $('#engine-status-text');
  if (text) text.textContent = state.clientSideMode ? 'Local Processing' : 'Server Processing';
}

function setClientSideMode(enabled) {
  const supported = CLIENT_SIDE_SUPPORTED_OPERATIONS.has(state.operation);
  if (enabled && !supported) {
    state.clientSideMode = false;
    syncClientSideControls();
    showToast(`${state.operations[state.operation]?.label || state.operation} uses server processing. Local Processing is available for ${CLIENT_SIDE_SUPPORTED_LABEL}.`, 'warning', 6000);
    updateButton();
    return false;
  }

  state.clientSideMode = Boolean(enabled);
  syncClientSideControls();
  showToast(state.clientSideMode
    ? `${state.operations[state.operation]?.label || state.operation} will run in your browser.`
    : 'Server processing selected.', 'info');
  updateButton();
  return true;
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
    <div class="command-item" data-command-operation="${key}" tabindex="0" role="button">
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

function generateBlankA4PdfBytes() {
  const blankPdfStr = `%PDF-1.4\n1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] /Resources <<>>>> endobj\nxref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \ntrailer <</Size 4 /Root 1 0 R>>\nstartxref\n214\n%%EOF`;
  const buf = new Uint8Array(blankPdfStr.length);
  for (let i = 0; i < blankPdfStr.length; i++) buf[i] = blankPdfStr.charCodeAt(i);
  return buf.buffer;
}

function syncStudioZoomSelect(scale) {
  const sel = $('#zoom-select');
  if (!sel) return;
  if (scale === 'fit-width') {
    sel.value = 'fit-width';
    return;
  }
  const num = Number(scale) || 1.0;
  let found = false;
  for (const opt of sel.options) {
    if (opt.value === 'fit-width') continue;
    if (Math.abs(Number(opt.value) - num) < 0.05) {
      sel.value = opt.value;
      found = true;
      break;
    }
  }
  if (!found) {
    let customOpt = sel.querySelector('option[data-custom="true"]');
    if (!customOpt) {
      customOpt = document.createElement('option');
      customOpt.setAttribute('data-custom', 'true');
      sel.appendChild(customOpt);
    }
    customOpt.value = num.toString();
    customOpt.textContent = `${Math.round(num * 100)}%`;
    sel.value = customOpt.value;
  }
}

function showStudioLoading(text = 'Loading document…') {
  const overlay = $('#studio-loading-overlay');
  const textEl = $('#studio-loading-text');
  if (textEl) textEl.textContent = text;
  if (overlay) overlay.hidden = false;
  const container = $('#studio-thumbnails-container');
  if (container) container.innerHTML = `<div style="color: #94a3b8; font-size: 12px; text-align: center; padding: 24px;"><div class="studio-spinner" style="margin: 0 auto 10px; width: 24px; height: 24px; border-width: 2px;"></div>${escapeHtml(text)}</div>`;
}

function hideStudioLoading() {
  const overlay = $('#studio-loading-overlay');
  if (overlay) overlay.hidden = true;
}

async function loadDocumentIntoStudio(file, { initialPage = 1, persist = true } = {}) {
  if (file === null && state.studio.isLoading) {
    return false;
  }
  state.studio.isLoading = true;

  const container = $('#studio-thumbnails-container');
  if (container) container.innerHTML = '<div style="color: #94a3b8; font-size: 12px; text-align: center; padding: 20px;"><div class="studio-spinner" style="margin: 0 auto 10px; width: 20px; height: 20px; border-width: 2px;"></div>Rendering previews…</div>';

  try {
    try {
      if (file) rememberLocalWork(typeof file === 'string' ? 'processed PDF' : (file.name || 'PDF document'));
      else clearLocalWorkMarkerIfEmpty();
    } catch { /* storage may be disabled */ }
    $('#studio-canvas-area')?.querySelector('.studio-empty-state')?.remove();
    let arrayBuffer;
    if (typeof file === 'string' && file !== '/assets/demo.pdf') {
      const resp = await fetch(file);
      arrayBuffer = await resp.arrayBuffer();
    } else if (file && (file instanceof Blob || file instanceof File)) {
      arrayBuffer = await file.arrayBuffer();
    } else {
      // Create a clean, single blank white A4 PDF page dynamically when no document is uploaded
      arrayBuffer = generateBlankA4PdfBytes();
    }
    if (state.studio.pageObserver) state.studio.pageObserver.disconnect();
    state.studio.pageRenderTasks.forEach(task => { try { task.cancel(); } catch { /* task may already be complete */ } });
    state.studio.pageRenderTasks.clear();
    if (state.studio.pdfDoc && state.studio.pdfDoc !== file && typeof state.studio.pdfDoc.destroy === 'function') {
      try { await state.studio.pdfDoc.destroy(); } catch { /* a previous document may already be destroyed */ }
    }
    state.studio.pdfDoc = await pdfjsLib.getDocument({ data: arrayBuffer, isEvalSupported: false }).promise;
    state.studio.totalCount = state.studio.pdfDoc.numPages;
    state.studio.currentPage = Math.max(1, Math.min(state.studio.totalCount, Number(initialPage) || 1));
    state.studio.srcFile = file;
    $('#studio-page-count').textContent = state.studio.totalCount;
    const pageJump = $('#page-jump-input');
    const pageTotal = $('#page-total-indicator');
    if (pageJump) { pageJump.min = '1'; pageJump.max = String(state.studio.totalCount); pageJump.value = String(state.studio.currentPage); pageJump.disabled = false; }
    if (pageTotal) pageTotal.textContent = String(state.studio.totalCount);

    // Load into Phase 2 PaperplaneEditor
    let srcFile = file;
    if (!srcFile || typeof srcFile === 'string') {
      srcFile = new File([arrayBuffer], (file && file.name) || 'document.pdf', { type: 'application/pdf' });
    }
    state.studio.srcFile = srcFile;
    if (persist) {
      try {
        await Promise.all([
          writeLocalWork('studio-pdf', localPdfRecord(srcFile)),
          writeLocalWork('studio-position', { page: state.studio.currentPage })
        ]);
        try { sessionStorage.setItem('paperplane-studio-position', JSON.stringify({ page: state.studio.currentPage })); } catch { /* IndexedDB is the durable store. */ }
      } catch (error) {
        console.warn('Paperplane could not save the Studio PDF locally:', error);
        showToast('This browser could not save the PDF locally. Export your document before closing this tab.', 'warning', 7000);
      }
    }
    if (window.PaperplaneEditor) {
      window.PaperplaneEditor.loadDocument(srcFile, srcFile.name, state.studio.totalCount);
    }

    // Build stable page slots first so the viewer has a real continuous scroll
    // range before thumbnails or off-screen pages are painted.
    prepareStudioPageStack(state.studio.totalCount);
    syncStudioZoomSelect(state.studio.scale);
    setupStudioPageObserver();
    setActiveStudioPage(state.studio.currentPage, { scrollThumbnail: false });
    const firstPage = state.studio.currentPage;
    const renderDeadline = Date.now() + 10000;
    let firstPageRendered = false;
    let renderAttempt = 0;
    let firstCanvas = null;
    while (Date.now() < renderDeadline) {
      firstCanvas = studioPageSlot(firstPage)?.querySelector('.pdf-page-canvas');
      if (firstCanvas?.dataset.rendered === 'true' && firstCanvas.width > 1 && firstCanvas.height > 1) {
        firstPageRendered = true;
        break;
      }
      firstPageRendered = await renderStudioPage(firstPage, { priority: true, force: renderAttempt > 0 });
      renderAttempt += 1;
      firstCanvas = studioPageSlot(firstPage)?.querySelector('.pdf-page-canvas');
      if (firstPageRendered && firstCanvas?.dataset.rendered === 'true' && firstCanvas.width > 1 && firstCanvas.height > 1) break;
      await new Promise(resolve => setTimeout(resolve, 120));
    }
    if (!firstPageRendered || !firstCanvas || firstCanvas.dataset.rendered !== 'true' || firstCanvas.width < 1 || firstCanvas.height < 1) {
      throw new Error(`Page ${state.studio.currentPage} did not produce a visible canvas. Please retry or reopen the PDF.`);
    }

    // Load into Phase 3 Professional Page Organizer
    if (window.PaperplanePageOrganizer) {
      window.PaperplanePageOrganizer.loadDocument(state.studio.pdfDoc, srcFile, srcFile.name, state.studio.totalCount);
    } else {
      renderStudioThumbnails();
    }
    if (state.studio.currentPage > 1) {
      await jumpToStudioPage(state.studio.currentPage);
    }
    hideStudioLoading();
    return true;
  } catch (err) {
    state.studio.isLoading = false;
    const reason = err instanceof Error ? err.message : String(err);
    console.error('Failed to load PDF in Studio:', err);
    hideStudioLoading();
    showToast(`Failed to load PDF in Studio: ${reason}`, 'error', 6000);
    if (container) container.innerHTML = `<div style="color: #ff6b6b; font-size: 11px; padding: 12px;">Failed to load PDF in Studio: ${escapeHtml(reason)}</div>`;
    if (!state.studio.pdfDoc) {
      showStudioEmptyState();
      const empty = $('#studio-canvas-area')?.querySelector('.studio-empty-state');
      if (empty) {
        empty.querySelector('h2').textContent = 'Could not open document';
        empty.querySelector('p').textContent = reason;
      }
    }
    return false;
  } finally {
    state.studio.isLoading = false;
  }
}

function createStudioPageSlot(pageNum) {
  const stack = $('#studio-page-stack');
  const slot = document.createElement('section');
  slot.className = 'page-render-wrapper studio-page-sheet';
  slot.dataset.page = String(pageNum);
  slot.setAttribute('aria-label', `Page ${pageNum}`);
  slot.style.setProperty('--studio-page-ratio', '595 / 842');
  const availableWidth = Math.max(180, ($('#studio-canvas-area')?.clientWidth || window.innerWidth) - (window.innerWidth <= 900 ? 28 : 64));
  const initialWidth = Math.min(595, availableWidth);
  slot.style.width = `${initialWidth}px`;
  slot.style.height = `${Math.ceil(initialWidth * 842 / 595)}px`;
  slot.innerHTML = `<div class="studio-page-loading" role="status">Page ${pageNum} is loading…</div><canvas class="pdf-page-canvas" aria-label="PDF page ${pageNum}"></canvas>`;
  stack.appendChild(slot);
  return slot;
}

function prepareStudioPageStack(pageCount) {
  const stack = $('#studio-page-stack');
  if (!stack) return;
  const existingDrawCanvas = $('#pdf-draw-canvas');
  stack.innerHTML = '';
  for (let pageNum = 1; pageNum <= pageCount; pageNum++) {
    const slot = createStudioPageSlot(pageNum);
    const pdfCanvas = slot.querySelector('.pdf-page-canvas');
    if (pageNum === 1) pdfCanvas.id = 'pdf-canvas';
    if (pageNum === 1 && existingDrawCanvas) slot.appendChild(existingDrawCanvas);
  }
  const first = stack.querySelector('.studio-page-sheet[data-page="1"]');
  if (first) first.id = 'page-render-wrapper';
}

function studioPageSlot(pageNum) {
  return document.querySelector(`#studio-page-stack .studio-page-sheet[data-page="${Number(pageNum)}"]`);
}

function setupStudioPageObserver() {
  const area = $('#studio-canvas-area');
  if (!area || !('IntersectionObserver' in window)) return;
  if (state.studio.pageObserver) state.studio.pageObserver.disconnect();
  state.studio.pageObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const pageNum = Number(entry.target.dataset.page);
      renderStudioPage(pageNum).catch(err => console.error(`Studio page ${pageNum} render failed:`, err));
    });
  }, { root: window.matchMedia('(max-width: 900px)').matches ? null : area, rootMargin: '120% 0px', threshold: 0.01 });
  document.querySelectorAll('#studio-page-stack .studio-page-sheet').forEach(slot => state.studio.pageObserver.observe(slot));
}

function getStudioPageScale(baseViewport) {
  const area = $('#studio-canvas-area');
  const horizontalPadding = window.innerWidth <= 900 ? 28 : 64;
  const availableWidth = Math.max(180, (area?.clientWidth || window.innerWidth) - horizontalPadding);
  const requested = state.studio.scale === 'fit-width' ? Number.POSITIVE_INFINITY : (Number(state.studio.scale) || 1);
  return Math.max(0.3, Math.min(requested, availableWidth / baseViewport.width));
}

function updateStudioPageSlotSize(slot, viewport) {
  slot.style.setProperty('--studio-page-ratio', `${viewport.width} / ${viewport.height}`);
  slot.style.width = `${Math.ceil(viewport.width)}px`;
  slot.style.height = `${Math.ceil(viewport.height)}px`;
  slot.dataset.pageWidth = String(viewport.width);
  slot.dataset.pageHeight = String(viewport.height);
}

function scrollStudioThumbnailIntoView(pageNum) {
  const panel = $('#studio-thumbnails-container');
  const card = panel?.querySelector(`.organizer-thumb-card[data-page="${Number(pageNum)}"]`);
  if (!panel || !card) return;

  const grid = panel.querySelector('.organizer-grid');
  const horizontalPhoneStrip = window.matchMedia('(max-width: 900px)').matches
    && grid?.classList.contains('strip-mode')
    && getComputedStyle(grid).display === 'flex';
  const scrollport = horizontalPhoneStrip ? grid : panel;

  // Native scrollIntoView can scroll the entire document when a deep thumbnail
  // becomes active, hiding the Studio toolbar and canvas. Move only the
  // thumbnail panel on its active axis instead.
  const panelRect = scrollport.getBoundingClientRect();
  const cardRect = card.getBoundingClientRect();
  if (horizontalPhoneStrip) {
    if (cardRect.left < panelRect.left) scrollport.scrollLeft += cardRect.left - panelRect.left;
    else if (cardRect.right > panelRect.right) scrollport.scrollLeft += cardRect.right - panelRect.right;
  } else {
    if (cardRect.top < panelRect.top) scrollport.scrollTop += cardRect.top - panelRect.top;
    else if (cardRect.bottom > panelRect.bottom) scrollport.scrollTop += cardRect.bottom - panelRect.bottom;
  }
}

function setActiveStudioPage(pageNum, { scrollThumbnail = true } = {}) {
  if (!state.studio.pdfDoc) return;
  const target = Math.max(1, Math.min(state.studio.totalCount, Number(pageNum) || 1));
  state.studio.currentPage = target;
  const pageJump = $('#page-jump-input');
  const pageTotal = $('#page-total-indicator');
  if (pageJump) pageJump.value = String(target);
  if (pageTotal) pageTotal.textContent = String(state.studio.totalCount);

  const activeSlot = studioPageSlot(target);
  if (activeSlot) {
    document.querySelectorAll('#studio-page-stack .studio-page-sheet.is-current').forEach(slot => slot.classList.remove('is-current'));
    document.querySelectorAll('#studio-page-stack .studio-page-sheet').forEach(slot => { if (slot !== activeSlot) slot.removeAttribute('id'); });
    activeSlot.classList.add('is-current');
    activeSlot.id = 'page-render-wrapper';
    document.querySelectorAll('#studio-page-stack .pdf-page-canvas').forEach(canvas => canvas.removeAttribute('id'));
    activeSlot.querySelector('.pdf-page-canvas')?.setAttribute('id', 'pdf-canvas');
    const drawCanvas = $('#pdf-draw-canvas');
    if (drawCanvas && drawCanvas.parentElement !== activeSlot) activeSlot.appendChild(drawCanvas);
  }

  const pageOrganizer = window.PaperplanePageOrganizer;
  if (pageOrganizer?.state) {
    pageOrganizer.state.activePage = target;
    pageOrganizer._updateCardStates();
    if (scrollThumbnail) scrollStudioThumbnailIntoView(target);
  }
  const activeCanvas = activeSlot?.querySelector('.pdf-page-canvas');
  if (activeCanvas?.dataset.rendered === 'true' && window.PaperplaneEditor) {
    const baseWidth = Number(activeSlot.dataset.baseWidth || 595);
    const baseHeight = Number(activeSlot.dataset.baseHeight || 842);
    const scale = Number(activeSlot.dataset.effectiveScale || 1);
    window.PaperplaneEditor.onPageRendered(activeCanvas, $('#pdf-draw-canvas'), activeSlot, scale, target, baseWidth, baseHeight);
  }
  saveStudioPagePosition();
}

async function renderStudioPage(pageNum, { priority = false, force = false } = {}) {
  if (!state.studio.pdfDoc) return false;
  const studioDoc = state.studio.pdfDoc;
  const target = Math.max(1, Math.min(state.studio.totalCount, Number(pageNum) || 1));
  const slot = studioPageSlot(target) || createStudioPageSlot(target);
  const canvas = slot.querySelector('.pdf-page-canvas');
  const loading = slot.querySelector('.studio-page-loading');
  const basePage = await studioDoc.getPage(target);
  if (state.studio.pdfDoc !== studioDoc) return false;
  const baseViewport = basePage.getViewport({ scale: 1 });
  const scale = getStudioPageScale(baseViewport);
  const viewport = basePage.getViewport({ scale });
  updateStudioPageSlotSize(slot, viewport);
  slot.dataset.baseWidth = String(baseViewport.width);
  slot.dataset.baseHeight = String(baseViewport.height);
  slot.dataset.effectiveScale = String(scale);
  if (!force && canvas.dataset.rendered === 'true' && Number(canvas.dataset.renderedScale) === scale) {
    if (target === state.studio.currentPage) setActiveStudioPage(target, { scrollThumbnail: false });
    return true;
  }

  const oldTask = state.studio.pageRenderTasks.get(target);
  if (oldTask && target === state.studio.currentPage) {
    try { await oldTask.promise; } catch { /* the active page may be re-queued below */ }
    if (state.studio.pdfDoc !== studioDoc) return false;
    if (canvas.dataset.rendered === 'true' && Number(canvas.dataset.renderedScale) === scale) return true;
    if (state.studio.pageRenderTasks.get(target) === oldTask) state.studio.pageRenderTasks.delete(target);
  } else if (oldTask) {
    try { oldTask.cancel(); } catch { /* already completed */ }
  }
  const renderId = String((Number(slot.dataset.renderId) || 0) + 1);
  slot.dataset.renderId = renderId;
  if (loading) { loading.hidden = false; loading.textContent = `Loading page ${target}…`; }
  if (priority) {
    const overlay = $('#studio-loading-overlay');
    if (overlay) overlay.hidden = false;
    const text = $('#studio-loading-text');
    if (text) text.textContent = `Rendering page ${target}…`;
  }

  const outputScale = window.devicePixelRatio || 1;
  canvas.width = Math.ceil(viewport.width * outputScale);
  canvas.height = Math.ceil(viewport.height * outputScale);
  canvas.style.width = `${Math.ceil(viewport.width)}px`;
  canvas.style.height = `${Math.ceil(viewport.height)}px`;
  const context = canvas.getContext('2d', { alpha: false });
  const transform = outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : null;
  const renderTask = basePage.render({ canvasContext: context, transform, viewport });
  state.studio.pageRenderTasks.set(target, renderTask);
  try {
    await renderTask.promise;
  } catch (err) {
    if (slot.dataset.renderId !== renderId || state.studio.pdfDoc !== studioDoc) return false;
    if (err?.name === 'RenderingCancelledException') {
      if (target === state.studio.currentPage) requestAnimationFrame(() => renderStudioPage(target, { priority: true, force: true }));
      return false;
    }
    if (loading) {
      loading.hidden = false;
      loading.innerHTML = `Page ${target} could not render. <button type="button" class="studio-page-retry" data-page="${target}">Retry</button>`;
    }
    console.error(`Studio render failed for page ${target}:`, err);
    return false;
  } finally {
    if (state.studio.pageRenderTasks.get(target) === renderTask) state.studio.pageRenderTasks.delete(target);
  }
  if (slot.dataset.renderId !== renderId) return false;
  canvas.dataset.rendered = 'true';
  canvas.dataset.renderedScale = String(scale);
  if (loading) loading.hidden = true;
  const overlay = $('#studio-loading-overlay');
  if (overlay) overlay.hidden = true;
  if (target === state.studio.currentPage) setActiveStudioPage(target, { scrollThumbnail: false });
  if (window.PaperplaneEditor && target === state.studio.currentPage) {
    window.PaperplaneEditor.onPageRendered(canvas, $('#pdf-draw-canvas'), slot, scale, target, baseViewport.width, baseViewport.height);
  } else if (!window.PaperplaneEditor && target === state.studio.currentPage) initStudioDrawingLayer();
  pruneStudioPageCanvases(target);
  return true;
}

function pruneStudioPageCanvases(centerPage) {
  document.querySelectorAll('#studio-page-stack .studio-page-sheet').forEach(slot => {
    const pageNum = Number(slot.dataset.page);
    // A render started for an older scroll position can finish after the user
    // has navigated elsewhere. Keep the active page (and its immediate neighbors)
    // pinned so that an outdated render cannot blank the page the user is viewing.
    if (pageNum === state.studio.currentPage || Math.abs(pageNum - centerPage) <= 2 || Math.abs(pageNum - state.studio.currentPage) <= 2 || state.studio.pageRenderTasks.has(pageNum)) return;
    const canvas = slot.querySelector('.pdf-page-canvas');
    if (canvas?.dataset.rendered === 'true') {
      canvas.width = 0;
      canvas.height = 0;
      canvas.dataset.rendered = 'false';
      const loading = slot.querySelector('.studio-page-loading');
      if (loading) { loading.hidden = false; loading.textContent = `Page ${pageNum} preview is paused to keep Studio responsive. Select it to load the page.`; }
    }
  });
}

function alignStudioPageInViewport(slot, behavior = 'auto') {
  const area = $('#studio-canvas-area');
  if (area) {
    const areaTop = area.getBoundingClientRect().top;
    const pageTop = slot.getBoundingClientRect().top - areaTop + area.scrollTop;
    area.scrollTo({ top: Math.max(0, pageTop - 10), behavior });
  }
}

async function jumpToStudioPage(pageNum, behavior = 'auto') {
  if (!state.studio.pdfDoc) return false;
  const target = Math.max(1, Math.min(state.studio.totalCount, Number(pageNum) || 1));
  const slot = studioPageSlot(target) || createStudioPageSlot(target);
  const canvas = slot.querySelector('.pdf-page-canvas');
  const loading = slot.querySelector('.studio-page-loading');
  setActiveStudioPage(target);
  if (canvas?.dataset.rendered !== 'true' && loading) {
    loading.hidden = false;
    loading.textContent = `Loading page ${target}…`;
  }
  // Move the requested page into view before awaiting PDF.js. This keeps the
  // prior page or its lazy-render placeholder from appearing as the jump result.
  studioPageJumpLockUntil = performance.now() + 1200;
  alignStudioPageInViewport(slot, behavior);

  let rendered = await renderStudioPage(target, { priority: true });
  if (!rendered) rendered = await renderStudioPage(target, { priority: true, force: true });
  setActiveStudioPage(target, { scrollThumbnail: false });
  // Page sizes can differ, so align again after the target's true dimensions are known.
  alignStudioPageInViewport(slot, 'auto');
  studioPageJumpLockUntil = performance.now() + 900;
  return rendered;
}

const studioPageStack = $('#studio-page-stack');
const studioCanvasArea = $('#studio-canvas-area');
if (studioPageStack) {
  studioPageStack.addEventListener('click', event => {
    const retry = event.target.closest('.studio-page-retry');
    if (retry) renderStudioPage(Number(retry.dataset.page), { priority: true, force: true });
  });
}
if (studioCanvasArea) {
  let activeSyncScheduled = false;
  const syncActivePageToViewport = () => {
    if (activeSyncScheduled) return;
    activeSyncScheduled = true;
    requestAnimationFrame(() => {
      activeSyncScheduled = false;
      if (!state.studio.pdfDoc) return;
      if (state.studio.isLoading) return;
      if (performance.now() < studioPageJumpLockUntil) return;
      const mobilePageFlow = window.matchMedia('(max-width: 900px)').matches;
      const areaRect = mobilePageFlow
        ? { top: $('.topbar')?.getBoundingClientRect().bottom || 0, bottom: window.innerHeight }
        : studioCanvasArea.getBoundingClientRect();
      const centerY = mobilePageFlow
        ? areaRect.top + Math.min((areaRect.bottom - areaRect.top) * 0.34, 260)
        : areaRect.top + Math.min(areaRect.height * 0.38, 280);
      let closest = state.studio.currentPage;
      let distance = Number.POSITIVE_INFINITY;
      document.querySelectorAll('#studio-page-stack .studio-page-sheet').forEach(slot => {
        const rect = slot.getBoundingClientRect();
        if (rect.bottom < areaRect.top || rect.top > areaRect.bottom) return;
        const d = Math.abs((rect.top + Math.min(rect.height * 0.25, 180)) - centerY);
        if (d < distance) { distance = d; closest = Number(slot.dataset.page); }
      });
      if (closest !== state.studio.currentPage) setActiveStudioPage(closest);
    });
  };
  studioCanvasArea.addEventListener('scroll', syncActivePageToViewport, { passive: true });
  window.addEventListener('scroll', syncActivePageToViewport, { passive: true });
}

window.jumpToStudioPage = jumpToStudioPage;

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
      jumpToStudioPage(i);
    };

    container.appendChild(card);
  }
}

// Studio Document Open Button
const studioUploadBtn = $('#studio-upload-btn');
const studioFileInput = $('#studio-file-input');
if (studioUploadBtn && studioFileInput) {
  studioUploadBtn.onclick = () => {
    studioFileInput.click();
  };
  studioFileInput.onchange = (e) => {
    const file = e.target.files[0];
    if (file) {
      loadDocumentIntoStudio(file).then((loaded) => {
        if (loaded) showToast(`Loaded ${file.name} into Studio!`);
        else showToast('Could not load this PDF in Studio. Check that the file is a valid, readable PDF.', 'error', 5500);
      });
    }
  };
}

const studioCloseDocBtn = $('#studio-close-doc-btn');
if (studioCloseDocBtn) {
  studioCloseDocBtn.onclick = () => {
    loadDocumentIntoStudio(null).then((loaded) => {
      if (loaded) showToast('Started new blank document in Studio.', 'info');
      else showToast('Could not create a blank Studio document.', 'error', 5500);
    });
  };
}

// Studio Navigation & Zoom Controls
$('#prev-page-btn').onclick = () => jumpToStudioPage(state.studio.currentPage - 1);

$('#next-page-btn').onclick = () => jumpToStudioPage(state.studio.currentPage + 1);

const pageJumpInput = $('#page-jump-input');
if (pageJumpInput) {
  let lastJumpTarget = null;
  let lastJumpAt = 0;
  const jumpToEnteredPage = () => {
    const target = Math.max(1, Math.min(state.studio.totalCount, Number(pageJumpInput.value) || 1));
    pageJumpInput.value = String(target);
    const now = performance.now();
    if (target === lastJumpTarget && now - lastJumpAt < 500) return;
    lastJumpTarget = target;
    lastJumpAt = now;
    jumpToStudioPage(target);
  };
  pageJumpInput.addEventListener('change', jumpToEnteredPage);
  pageJumpInput.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); jumpToEnteredPage(); pageJumpInput.blur(); } });
}

async function refreshVisibleStudioPages() {
  if (!state.studio.pdfDoc) return;
  const area = $('#studio-canvas-area');
  const areaRect = area?.getBoundingClientRect();
  const visible = [...document.querySelectorAll('#studio-page-stack .studio-page-sheet')].filter(slot => {
    if (!areaRect) return Number(slot.dataset.page) === state.studio.currentPage;
    const rect = slot.getBoundingClientRect();
    return rect.bottom >= areaRect.top - areaRect.height && rect.top <= areaRect.bottom + areaRect.height;
  });
  document.querySelectorAll('#studio-page-stack .studio-page-sheet').forEach(slot => {
    const canvas = slot.querySelector('.pdf-page-canvas');
    const page = Number(slot.dataset.page);
    const baseWidth = Number(slot.dataset.baseWidth || 595);
    const baseHeight = Number(slot.dataset.baseHeight || 842);
    const effectiveScale = getStudioPageScale({ width: baseWidth });
    const width = baseWidth * effectiveScale;
    const height = baseHeight * effectiveScale;
    updateStudioPageSlotSize(slot, { width, height });
    slot.dataset.effectiveScale = String(effectiveScale);
    if (canvas) {
      canvas.dataset.rendered = 'false';
      canvas.width = 0;
      canvas.height = 0;
      const status = slot.querySelector('.studio-page-loading');
      if (status) { status.hidden = false; status.textContent = `Loading page ${page}…`; }
    }
  });
  state.studio.pageRenderTasks.forEach(task => { try { task.cancel(); } catch { /* already complete */ } });
  state.studio.pageRenderTasks.clear();
  const pages = new Set([state.studio.currentPage, ...visible.map(slot => Number(slot.dataset.page))]);
  await Promise.all([...pages].map(page => renderStudioPage(page, { priority: page === state.studio.currentPage, force: true })));
}

function setStudioZoom(value) {
  state.studio.scale = value;
  syncStudioZoomSelect(value);
  refreshVisibleStudioPages();
}

$('#zoom-in-btn').onclick = () => {
  const current = Number(state.studio.scale) || 1.0;
  setStudioZoom(Math.min(3, +(current + 0.25).toFixed(2)));
};

$('#zoom-out-btn').onclick = () => {
  const current = Number(state.studio.scale) || 1.0;
  setStudioZoom(Math.max(0.3, +(current - 0.25).toFixed(2)));
};

$('#zoom-select').onchange = e => setStudioZoom(e.target.value);

// Studio scroll is continuous. Ordinary wheel/touch gestures scroll all pages;
// Ctrl/Cmd+wheel adjusts zoom without interrupting page navigation.
if (studioCanvasArea) studioCanvasArea.addEventListener('wheel', e => {
  if (!e.ctrlKey || !state.studio.pdfDoc) return;
  e.preventDefault();
  const current = Number(state.studio.scale) || 1.0;
  const delta = e.deltaY < 0 ? 0.1 : -0.1;
  setStudioZoom(Math.max(0.3, Math.min(3, +(current + delta).toFixed(2))));
}, { passive: false });

let studioResizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(studioResizeTimer);
  studioResizeTimer = setTimeout(() => {
    if (state.studio.pdfDoc) setupStudioPageObserver();
    refreshVisibleStudioPages();
  }, 180);
});

const drawCanvasEl = $('#pdf-draw-canvas');
if (drawCanvasEl) {
  drawCanvasEl.addEventListener('wheel', e => {
    if (e.ctrlKey) {
      e.preventDefault();
      const current = Number(state.studio.scale) || 1.0;
      const delta = e.deltaY < 0 ? 0.15 : -0.15;
      const newScale = Math.max(0.5, Math.min(3.0, +(current + delta).toFixed(2)));
      setStudioZoom(newScale);
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

// Page insertion, duplication, and deletion are owned by the Phase 3 page
// organizer controller. Avoid a second legacy handler here: it ran a parallel
// mutation and called the removed initStudioViewer() entry point.
$('#editor-extract-page-btn')?.addEventListener('click', () => {
  if (!window.PaperplanePageOrganizer || !state.studio.pdfDoc) return;
  window.PaperplanePageOrganizer.extractPages([state.studio.currentPage]);
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
  const preservePageThroughModeChange = () => {
    if (!state.studio.pdfDoc) return;
    const pageToKeep = Math.max(1, Number($('#page-jump-input')?.value) || state.studio.currentPage || 1);
    requestAnimationFrame(() => requestAnimationFrame(() => jumpToStudioPage(pageToKeep, 'auto')));
  };

  btnModeAnnotate.onclick = () => {
    btnModeAnnotate.classList.add('active');
    btnModeOrganize.classList.remove('active');
    if (window.matchMedia('(max-width: 900px)').matches) {
      $('#app-shell')?.classList.remove('studio-pages-open');
      $('#studio-mobile-pages-btn')?.setAttribute('aria-expanded', 'false');
      syncStudioBatchPanelLocation();
    }
    if (annotateRibbon) annotateRibbon.hidden = false;
    if (batchBar) batchBar.hidden = true;
    if (window.PaperplanePageOrganizer) {
      window.PaperplanePageOrganizer._updateBatchToolbar();
      syncStudioBatchPanelLocation();
    }
    preservePageThroughModeChange();
  };

  btnModeOrganize.onclick = () => {
    btnModeOrganize.classList.add('active');
    btnModeAnnotate.classList.remove('active');
    if (window.matchMedia('(max-width: 900px)').matches) {
      // Page selection only exists in the mobile pages drawer. Open it as part
      // of entering Organize mode so the selected mode always exposes its work.
      $('#app-shell')?.classList.add('studio-pages-open');
      $('#studio-mobile-pages-btn')?.setAttribute('aria-expanded', 'true');
      $('#studio-mobile-properties-panel')?.setAttribute('hidden', '');
      $('#studio-mobile-properties-btn')?.setAttribute('aria-expanded', 'false');
      syncStudioBatchPanelLocation();
    }
    if (annotateRibbon) annotateRibbon.hidden = true;
    if (window.PaperplanePageOrganizer) {
      window.PaperplanePageOrganizer._updateBatchToolbar();
    } else if (batchBar) {
      batchBar.hidden = true;
    }
    syncStudioBatchPanelLocation();
    preservePageThroughModeChange();
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
    if (isHidden) moreToolsMenu.querySelector('.studio-dropdown-item')?.focus();
  };

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !moreToolsMenu.hidden) {
      moreToolsMenu.hidden = true;
      moreToolsTrigger.setAttribute('aria-expanded', 'false');
      moreToolsTrigger.focus();
    }
  });

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
  $('#studio-ocr-btn')?.addEventListener('click', () => { selectOperation('ocr'); });
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
    fields += selectField('preset', 'Target Compression Preset', [
      { value: '100kb', label: '🎯 Under 100 KB (Govt / SSC Exam Form)' },
      { value: '200kb', label: '🎯 Under 200 KB (UPSC / NTA / NEET)' },
      { value: '500kb', label: '🎯 Under 500 KB (State PSC & College)' },
      { value: 'balanced', label: 'Balanced (Standard 75% Quality)' },
      { value: 'high', label: 'High Compression (60% Quality)' },
      { value: 'extreme', label: 'Extreme Compression (Smallest Size)' },
      { value: 'custom', label: 'Custom Quality & DPI' }
    ]);
    fields += field('target_size_kb', 'Or Specify Custom Target Size (KB)', 'number', '', '10', '50000', '5');
    fields += selectField('quality', 'Image Quality (for Custom mode)', [
      { value: '65', label: '65 (High Compression)' },
      { value: '75', label: '75 (Balanced)' },
      { value: '85', label: '85 (Low Loss)' }
    ]);
    fields += selectField('dpi', 'Max Image Resolution (for Custom mode)', [
      { value: '150', label: '150 DPI (Screen)' },
      { value: '72', label: '72 DPI (Web)' },
      { value: '300', label: '300 DPI (Print)' }
    ]);
  } else if (state.operation === 'photo_resizer') {
    fields += selectField('preset', 'Exam Preset', [
      { value: 'ssc_photo', label: '📸 SSC Exam Photo (3.5 × 4.5 cm, 20 KB - 50 KB)' },
      { value: 'ssc_sign', label: '✍️ SSC Signature (4.0 × 2.0 cm, 10 KB - 20 KB)' },
      { value: 'upsc_photo', label: '📸 UPSC Photo (350 × 350 px, 20 KB - 300 KB)' },
      { value: 'upsc_sign', label: '✍️ UPSC Signature (350 × 350 px, 20 KB - 300 KB)' },
      { value: 'ibps_photo', label: '📸 IBPS / Bank Photo (200 × 230 px, 20 KB - 50 KB)' },
      { value: 'ibps_sign', label: '✍️ IBPS / Bank Signature (140 × 60 px, 10 KB - 20 KB)' }
    ]);
    fields += selectField('format', 'Output Format', [
      { value: 'jpg', label: 'JPG Image (Standard for portals)' },
      { value: 'pdf', label: 'PDF Document (Single-page)' }
    ]);
  } else if (state.operation === 'mask_aadhaar') {
    fields += '<div class="option-field option-field-wide" style="background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.3); border-radius: 8px; padding: 12px;"><strong style="color: #10b981;">🛡️ UIDAI Compliant 1-Click Masking</strong><p style="margin: 4px 0 0; font-size: 12px; color: var(--text-muted);">Paperplane automatically searches for 12-digit Aadhaar numbers and permanently black-boxes or redacts the first 8 digits (XXXX-XXXX-1234) in memory.</p></div>';
  } else if (state.operation === 'grayscale') {
    fields += '<div class="option-field option-field-wide" style="background: rgba(59,130,246,0.08); border: 1px solid rgba(59,130,246,0.3); border-radius: 8px; padding: 12px;"><strong style="color: #3b82f6;">🖤 Grayscale for monochrome printing</strong><p style="margin: 4px 0 0; font-size: 12px; color: var(--text-muted);">Already-grayscale PDFs are preserved. Colored pages are rendered as images, so the output can be larger and their text may need OCR before it can be searched or copied. Use Compress PDF when reducing file size is your goal.</p></div>';
  } else if (state.operation === 'flatten') {
    fields += '<div class="option-field option-field-wide" style="background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.3); border-radius: 8px; padding: 12px;"><strong style="color: #f59e0b;">📑 Permanent Form Flattening</strong><p style="margin: 4px 0 0; font-size: 12px; color: var(--text-muted);">Permanently bakes interactive AcroForm field values directly into the page content, preventing further modification in final submissions.</p></div>';
  } else if (state.operation === 'watermark') {
    fields += field('text', 'Watermark text (leave empty if image selected)', 'text', 'CONFIDENTIAL');
    fields += field('opacity', 'Opacity (0.05 to 0.8)', 'number', '0.2', '0.05', '0.8', '0.01');
    fields += '<div class="option-field"><label for="watermark_image_file">Or Select Watermark Image</label><input id="watermark_image_file" type="file" accept="image/*"></div>';
  } else if (state.operation === 'page_numbers') {
    fields += selectField('position', 'Position', ['Footer center', 'Footer left', 'Footer right', 'Header center', 'Header left', 'Header right']);
    fields += selectField('format', 'Numbering Format', ['Page {n} of {total}', 'Page {n}', '{n}']);
    fields += field('start_number', 'Starting Number', 'number', '1', '1', '9999', '1');
    fields += field('start_page', 'First Page to Number', 'number', '1', '1', '9999', '1');
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
    fields += `<div class="option-field option-field-wide"><label for="fields">Form JSON Map</label><textarea id="fields" rows="3" wrap="soft" placeholder='{"Name":"Alex", "Email":"alex@example.com", "City":"Pune"}'></textarea></div>`;
  } else if (state.operation === 'ai_extract') {
    fields += selectField('doc_type', 'Document Type', ['auto', 'general', 'invoice', 'resume']);
  }

  o.innerHTML = fields;
  o.hidden = !fields;
  o.style.display = fields ? '' : 'none';

  if (state.operation === 'forms') {
    const formMap = $('#fields');
    if (formMap) {
      const resizeFormMap = () => {
        formMap.style.height = 'auto';
        const maxHeight = Math.max(240, Math.min(720, Math.round(window.innerHeight * 0.85)));
        formMap.style.height = `${Math.min(formMap.scrollHeight, maxHeight)}px`;
        formMap.style.overflowY = formMap.scrollHeight > maxHeight ? 'auto' : 'hidden';
      };
      formMap.addEventListener('input', resizeFormMap);
      resizeFormMap();
    }
  }

  if (state.operation === 'html_to_pdf') {
    const urlEl = $('#url');
    if (urlEl) {
      urlEl.addEventListener('input', () => updateButton());
    }
  }

  if (['protect', 'unlock'].includes(state.operation) || (state.operation || '').includes('protect') || (state.operation || '').includes('unlock')) {
    const pwdEl = $('#password');
    if (pwdEl) {
      pwdEl.addEventListener('input', () => updateButton());
    }
  }
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
        <button class="delete-file-btn" data-remove-file="${idx}" title="Remove file"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
    </div>
  `).join('');
}

window.removeFile = idx => {
  state.files.splice(idx, 1);
  renderFiles();
  updateButton();
  clearLocalWorkMarkerIfEmpty();
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
  if (state.files.length) rememberLocalWork(state.files[0].name || 'PDF document');
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
          const doc = await pdfjsLib.getDocument({ data: e.target.result, isEvalSupported: false }).promise;
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
}

function updateButton() {
  const btn = $('#run-button');
  if (!btn) return;
  syncClientSideControls();
  const currentOperation = state.operations[state.operation];
  const toolLabel = currentOperation?.label || 'Run Tool';
  if (currentOperation && (currentOperation.available === false || currentOperation.status === 'DEPENDENCY_MISSING' || currentOperation.status === 'SERVICE_UNAVAILABLE')) {
    btn.disabled = true;
    btn.innerHTML = `${toolLabel} unavailable <span>✕</span>`;
    return;
  }
  const isHtml = state.operation === 'html_to_pdf';

  if (isHtml) {
    const urlInput = $('#url');
    const urlVal = urlInput ? urlInput.value.trim() : '';
    const isValidUrl = /^https?:\/\/.+/i.test(urlVal);
    btn.disabled = !isValidUrl;
    btn.innerHTML = isValidUrl
      ? 'Convert URL to PDF <span>→</span>'
      : 'Enter valid URL to continue <span>→</span>';
    return;
  }

  const hasFiles = state.files.length > 0;
  const activeToolLabel = currentOperation?.label || 'Run Tool';

  const isSecurity = ['protect', 'unlock'].includes(state.operation) || (state.operation || '').includes('protect') || (state.operation || '').includes('unlock');
  if (isSecurity) {
    if (!hasFiles) {
      btn.disabled = true;
      btn.innerHTML = 'Select files to continue <span>→</span>';
      return;
    }
    const pwdInput = $('#password');
    const pwdVal = pwdInput ? pwdInput.value.trim() : '';
    if (!pwdVal) {
      btn.disabled = true;
      btn.innerHTML = ((state.operation || '').includes('protect')
        ? 'Enter encryption password to continue'
        : 'Enter unlock password to continue') + ' <span>→</span>';
      return;
    }
    btn.disabled = false;
    btn.innerHTML = `${activeToolLabel} Now <span>→</span>`;
    return;
  }

  if (state.operation === 'split' && state.splitPageCount === 1) {
    btn.disabled = true;
    btn.innerHTML = 'Only 1 page found (Cannot be split) <span>✕</span>';
    return;
  }

  btn.disabled = !hasFiles;
  btn.innerHTML = hasFiles
    ? `${activeToolLabel} Now <span>→</span>`
    : 'Select files to continue <span>→</span>';
}

const HEAVY_TOOLS = new Set([
  'ai_chat'
]);

function checkAccessRequirement(operation, files = []) {
  const operationInfo = state.operations[operation];
  if (operationInfo && (operationInfo.available === false || operationInfo.status === 'DEPENDENCY_MISSING' || operationInfo.status === 'SERVICE_UNAVAILABLE')) {
    showToast(operationInfo.prerequisite || `${operationInfo.label || 'This tool'} is currently unavailable.`, 'warning', 5000);
    return false;
  }
  const accountTier = String(state.user?.tier || '').toLowerCase();
  const paidAccount = Boolean(state.user && (state.user.is_pro || state.user.is_dev || ['developer', 'student_pro', 'cyber_cafe', 'exam_pass'].includes(accountTier)));
  if (!state.user && HEAVY_TOOLS.has(operation)) {
    showToast('This advanced AI / conversion tool requires a free account. Please sign in or register.', 'info');
    openAuthModal('', 'login');
    return false;
  }
  const maxMb = paidAccount ? state.planLimits.pro_max_file_size_mb : state.planLimits.free_max_file_size_mb;
  const largeFile = files.find(f => f.size > maxMb * 1024 * 1024);
  if (largeFile) {
    showToast(`"${largeFile.name}" is over the ${maxMb} MB ${paidAccount ? 'account' : 'Free'} file limit. Choose a smaller file${paidAccount ? '' : ' or upgrade for larger uploads'}.`, 'warning');
    if (!state.user) openAuthModal('', 'login');
    return false;
  }
  return true;
}

$('#browse').onclick = () => {
  if (HEAVY_TOOLS.has(state.operation) && !state.user) {
    showToast('This advanced AI / conversion tool requires a free account. Please sign in or register.', 'info');
    openAuthModal('', 'login');
    return;
  }
  $('#file-input').click();
};

const dropzoneEl = $('#dropzone');
if (dropzoneEl) {
  dropzoneEl.onclick = (e) => {
    if (e.target.closest('#browse') || e.target.closest('#cloud-drop-btn') || e.target.closest('.cloud-import-btn')) return;
    if (HEAVY_TOOLS.has(state.operation) && !state.user) {
      showToast('This advanced AI / conversion tool requires a free account. Please sign in or register.', 'info');
      openAuthModal('', 'login');
      return;
    }
    $('#file-input').click();
  };
}

$('#file-input').onchange = e => {
  const selected = [...e.target.files];
  if (!checkAccessRequirement(state.operation, selected)) return;
  addFiles(selected);
};

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
  const dropped = [...e.dataTransfer.files];
  if (!checkAccessRequirement(state.operation, dropped)) return;
  addFiles(dropped);
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

$('#topbar-cloud-btn').onclick = (e) => {
  if (e) e.stopPropagation();
  $('#cloud-modal').hidden = false;
  $('#cloud-url').value = '';
};

$('#cloud-drop-btn').onclick = (e) => {
  if (e) e.stopPropagation();
  $('#cloud-modal').hidden = false;
  $('#cloud-url').value = '';
};

$('#close-cloud-modal').onclick = () => $('#cloud-modal').hidden = true;
$('#cloud-modal')?.addEventListener('click', event => {
  if (event.target === $('#cloud-modal')) $('#cloud-modal').hidden = true;
});
document.addEventListener('keydown', event => {
  const cloudModal = $('#cloud-modal');
  if (event.key === 'Escape' && cloudModal && !cloudModal.hidden) {
    cloudModal.hidden = true;
  }
});

$('#cloud-form').onsubmit = async e => {
  e.preventDefault();
  const fileUrl = $('#cloud-url').value.trim();
  const btn = $('#cloud-submit-btn');
  const errorBox = $('#cloud-error');
  if (errorBox) { errorBox.hidden = true; errorBox.textContent = ''; }
  btn.disabled = true;
  btn.textContent = 'Importing Document…';

  try {
    const formData = new FormData();
    formData.append('file_url', fileUrl);
    const res = await safeFetch('/api/cloud/sync', { method: 'POST', body: formData });
    if (res.data_url) {
      const file = dataUrlToFile(res.data_url, res.filename);
      const signature = await file.slice(0, 5).text();
      if (file.type !== 'application/pdf' || signature !== '%PDF-') {
        throw new Error('This tool currently imports PDF files only. Choose a direct PDF link; images and Office files must use their matching converter.');
      }
      let pageCount = 0;
      try {
        const parsed = await pdfjsLib.getDocument({ data: await file.arrayBuffer(), isEvalSupported: false }).promise;
        pageCount = parsed.numPages;
        await parsed.destroy();
      } catch {
        throw new Error('The link returned a PDF file, but this browser could not open it. Check that the PDF is not damaged or password-protected.');
      }
      if (state.activeView === 'ai') {
        state.files = [file];
        await writeLocalWork('ai-pdf', localPdfRecord(file));
        rememberLocalWork(file.name);
        updateAiDocBar();
      } else if (state.activeView === 'studio') {
        const loaded = await loadDocumentIntoStudio(file);
        if (!loaded) throw new Error('The PDF could not be opened in Studio. Your current document is still available.');
      } else {
        addFiles([file]);
      }
      $('#cloud-modal').hidden = true;
      showToast(`Imported ${file.name} · ${(file.size / (1024 * 1024)).toFixed(2)} MB · ${pageCount} pages`, 'success', 6000);
    } else throw new Error('The link did not return a downloadable PDF. Check sharing access and try again.');
  } catch (err) {
    if (errorBox) { errorBox.textContent = err.message; errorBox.hidden = false; }
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

  if (isHtml) {
    const urlVal = ($('#url')?.value || '').trim();
    if (!urlVal || !/^https?:\/\/.+/i.test(urlVal)) {
      showResult('Please enter a valid public URL starting with http:// or https://', true);
      showToast('Please enter a valid public URL starting with http:// or https://', 'warning', 4000);
      $('#url')?.focus();
      return;
    }
  }

  const isSecurity = ['protect', 'unlock'].includes(state.operation) || (state.operation || '').includes('protect') || (state.operation || '').includes('unlock');
  if (isSecurity) {
    const pwd = ($('#password')?.value || '').trim();
    if (!pwd) {
      const msg = (state.operation || '').includes('protect')
        ? 'Please enter a password to encrypt this PDF.'
        : 'Please enter the password to unlock this PDF.';
      showResult(msg, true);
      showToast(msg, 'warning', 4000);
      $('#password')?.focus();
      return;
    }
  }

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
      console.warn('Browser-local processing failed:', clientErr);
      showResult('This PDF could not be processed in your browser. Turn off Local Processing and retry with server processing.', true);
      return;
    } finally {
      btn.disabled = false;
      updateButton();
    }
  }

  // Server Workflow Execution
  const options = {};
  $$('#options input, #options select, #options textarea').forEach(input => {
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
    const isSecurityOp = ['protect', 'unlock'].includes(state.operation) || (state.operation || '').includes('protect') || (state.operation || '').includes('unlock');
    const isRequiredErr = error.message.toLowerCase().includes('required') || error.message.toLowerCase().includes('please enter') || error.message.toLowerCase().includes('please provide');
    if (error.message.includes('TIER_LIMIT') || error.message.includes('limit reached')) {
      // Upgrade modal already opened by safeFetch
    } else if (!isSecurityOp && !isRequiredErr && error.message.toLowerCase().includes('password')) {
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

function showDownloadResult(job, downloadUrl, { silent = false } = {}) {
  state.activeToolResult = { job: { ...job }, downloadUrl };
  toolSessionCache.set(state.operation, {
    files: [...state.files],
    splitPageCount: state.splitPageCount ?? null,
    formValues: captureToolFormValues(),
    result: state.activeToolResult
  });
  rememberLocalWork(job?.output_name || 'processed PDF');
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

  // Direct fetch fallback onclick with reassuring immediate UI feedback
  dlLink.onclick = async (e) => {
    e.preventDefault();
    const originalContent = dlLink.innerHTML;
    try {
      dlLink.style.pointerEvents = 'none';
      dlLink.innerHTML = `<span class="studio-spinner" style="width: 14px; height: 14px; border-width: 2px; display: inline-block; vertical-align: middle; margin-right: 6px;"></span> Preparing download…`;
      showToast('Preparing your file download…', 'info', 2000);
      const res = await fetch(downloadUrl, { credentials: 'same-origin' });
      if (!res.ok) throw new Error(`Server returned HTTP ${res.status}`);
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
      console.warn('Blob download fallback:', err);
      showToast(`Download failed: ${err.message}`, 'error', 4000);
    } finally {
      dlLink.innerHTML = originalContent;
      dlLink.style.pointerEvents = '';
    }
  };

  const isPdf = outName.toLowerCase().endsWith('.pdf');
  const studioBtn = $('#result-view-studio-btn');
  if (studioBtn) {
    studioBtn.hidden = !isPdf;
    if (isPdf) {
      studioBtn.onclick = async (e) => {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        state.studio.isLoading = true;
        switchWorkspaceView('studio');
        showStudioLoading('Loading document…');
        showToast('Opening processed document in Studio…', 'info');
        try {
          const res = await fetch(downloadUrl, { credentials: 'same-origin' });
          if (!res.ok) throw new Error(`Could not fetch the processed PDF (HTTP ${res.status}).`);
          const blob = await res.blob();
          const studioFile = new File([blob], outName, { type: blob.type || 'application/pdf' });
          const loaded = await loadDocumentIntoStudio(studioFile);
          if (!loaded) throw new Error('The processed file could not be rendered as a PDF.');
        } catch (err) {
          console.warn('Could not load output into Studio directly:', err);
          showToast(`Could not open the processed PDF in Studio: ${err instanceof Error ? err.message : String(err)}`, 'error', 6500);
          if (!state.studio.pdfDoc) {
            switchWorkspaceView('desk');
          }
        } finally {
          state.studio.isLoading = false;
          hideStudioLoading();
        }
      };
    }
  }

  result.hidden = false;
  if (!silent) {
    checkAuthStatus();
    showToast('Processing complete! Document ready for download.');
  }
}

function showResult(message, isError = false) {
  if (isError) {
    state.activeToolResult = null;
    const session = toolSessionCache.get(state.operation);
    if (session) { session.result = null; toolSessionCache.set(state.operation, session); }
  }
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
    showToast('A PDF download is unavailable in this browser. The summary was downloaded as a text file instead.', 'warning');
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
  showRichAiResult(
    'Grounded AI answer',
    data.citations?.length ? 'Document-grounded answer' : 'Direct answer',
    `<div class="ai-result-answer">${renderMarkdown(data.answer)}</div><div class="ai-result-citations"><strong>Verified sources</strong>${citations}</div><button type="button" class="btn-primary-action ai-open-studio-result-btn">Open in Full AI Interactive Studio →</button>`,
    { showStudio: true },
  );
  $('.ai-open-studio-result-btn')?.addEventListener('click', () => switchWorkspaceView('ai'));
}

function summaryCitationHtml(citations = []) {
  const pages = [...new Set((Array.isArray(citations) ? citations : []).map(Number).filter(Number.isInteger))].sort((a, b) => a - b);
  if (!pages.length) return '<div class="ai-result-citations"><strong>Sources</strong><span class="ai-citation-tag muted">No verified page citations returned</span></div>';
  return `<div class="ai-result-citations"><strong>Verified pages</strong>${pages.map(page => `<span class="ai-citation-tag">Page ${page}</span>`).join('')}</div>`;
}

function showSummaryDeskResult(summary, citations = []) {
  currentSummaryText = summary || '';
  const fileName = (state.files[0]?.name || 'document').replace(/\.[^/.]+$/, '');
  showRichAiResult(
    'Executive briefing ready',
    `${fileName} · formatted Markdown · local/provider grounded`,
    `<article class="ai-result-markdown">${renderMarkdown(currentSummaryText)}</article>${summaryCitationHtml(citations)}<div class="ai-result-actions"><button type="button" class="btn-demo-upgrade" id="desk-copy-summary-btn">Copy Summary</button><button type="button" class="btn-demo-upgrade" id="desk-download-summary-txt-btn">Download TXT</button><button type="button" class="btn-demo-upgrade" id="desk-download-summary-pdf-btn">Download PDF</button></div>`,
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
  const response = await fetch(url, { ...options, credentials: 'same-origin', headers });
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
    showSummaryDeskResult(data.summary, data.citations);
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
    const warningCount = response.headers.get('X-Paperplane-Translation-Warnings') || '0';
    const mode = response.headers.get('X-Paperplane-Translation-Mode') || 'translated';
    const name = `${(state.files[0]?.name || 'document').replace(/\.[^/.]+$/, '')}_translated.pdf`;
    const targetLanguage = options.target_language || 'es';
    if (mode === 'failed' || mode === 'source_preserved') {
      showRichAiResult('Translation failed', `${targetLanguage} · no translated text produced · ${warningCount} warning(s)`, '<p>No translated PDF is available. The source document was not changed. Check the provider connection and retry.</p>', { showStudio: false });
      showToast('Translation failed. No translated download was created.', 'error');
      return;
    }

    const url = URL.createObjectURL(blob);
    const isPartial = mode === 'partial';
    const resultTitle = isPartial ? 'Partial translation ready' : 'Translation complete';
    const resultSummary = `${targetLanguage} · ${isPartial ? 'some source text was preserved' : 'translated text'} · ${warningCount} warning(s)`;
    const resultMessage = isPartial
      ? 'Some text could not be translated and remains in the original language. Review the PDF before sharing it.'
      : 'Translated text was rendered into the original page layout.';
    const downloadLabel = isPartial ? 'Download partial translation' : 'Download translated PDF';
    showRichAiResult(resultTitle, resultSummary, `<p>${resultMessage}</p><a class="btn-download" href="${url}" download="${escapeHtml(name)}">${downloadLabel}</a>`, { showStudio: false });
    showToast(isPartial ? 'Partial translation ready; some source text remains.' : 'Translation completed.', isPartial ? 'warning' : 'success');
  }
}

// ----------------------------------------------------------------------
// Client-Side WASM / JS Processing via PDF-Lib
// ----------------------------------------------------------------------

async function processClientSide() {
  if (typeof PDFLib === 'undefined') {
    throw new Error('The local PDF processor is unavailable in this browser.');
  }

  if (!CLIENT_SIDE_SUPPORTED_OPERATIONS.has(state.operation)) {
    throw new Error('This tool uses temporary server processing. Turn off Local Processing and retry.');
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

  throw new Error('This tool uses temporary server processing. Turn off Local Processing and retry.');
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
let executiveBriefAvailable = null;

function setExecutiveBriefAvailability(available) {
  executiveBriefAvailable = typeof available === 'boolean' ? available : null;
  const button = $('#trigger-summary-btn');
  const summaryBox = $('#summary-display');
  if (button) button.disabled = executiveBriefAvailable === false;
  if (!summaryBox) return;

  if (executiveBriefAvailable === false) {
    summaryBox.textContent = 'Executive Brief is unavailable because AI analysis is not configured for this workspace. Ask the site administrator to configure AI, then reload this page.';
  } else if (summaryBox.textContent.includes('AI analysis is not configured for this workspace')) {
    summaryBox.textContent = 'Summary will appear here after generation...';
  }
}

async function checkExecutiveBriefAvailability() {
  try {
    const capability = await safeFetch('/api/ai/capabilities');
    setExecutiveBriefAvailability(capability.executive_brief_available === true);
  } catch {
    // Keep the action available if the capability check itself is temporarily unavailable;
    // the operation endpoint will return the specific actionable service error.
    setExecutiveBriefAvailability(null);
  }
}

function getAiChatPlaceholder() {
  const file = state.files.find(item => item?.name?.toLowerCase().endsWith('.pdf'));
  if (window.matchMedia('(max-width: 480px)').matches) {
    return file ? 'Ask about this PDF…' : 'Ask anything…';
  }
  return file ? `Ask a question about ${file.name}...` : 'Ask a general question or about your PDF...';
}

window.addEventListener('resize', () => {
  const input = $('#chat-input');
  if (input) input.placeholder = getAiChatPlaceholder();
}, { passive: true });

function updateAiDocBar() {
  const uploadZone = $('#ai-upload-zone');
  const activeBar = $('#ai-active-doc-bar');
  const emptyState = $('#ai-empty-state');
  const inlineUploadButton = $('#ai-upload-inline-btn');
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
    if (emptyState) emptyState.hidden = true;
    if (inlineUploadButton) inlineUploadButton.hidden = true;
    if (docName) docName.textContent = file.name;
    if (docMeta) docMeta.textContent = `${formatBytes(file.size)} • PDF Document`;
    if (docMeta && window.pdfjsLib) {
      file.arrayBuffer().then(buffer => window.pdfjsLib.getDocument({ data: buffer, isEvalSupported: false }).promise)
        .then(pdf => { if (state.files[0] === file) docMeta.textContent = `${formatBytes(file.size)} • ${pdf.numPages} pages`; })
        .catch(() => { /* The chat upload still reports a readable user-facing status. */ });
    }
    if (chatInput) {
      chatInput.disabled = false;
      chatInput.placeholder = getAiChatPlaceholder();
    }
    if (chatBtn) chatBtn.disabled = false;
    if (extractBtn) extractBtn.disabled = false;
    if (summaryBtn) summaryBtn.disabled = executiveBriefAvailable === false;
  } else {
    if (uploadZone) uploadZone.hidden = false;
    if (activeBar) activeBar.hidden = true;
    if (emptyState) emptyState.hidden = state.aiConversation.length > 0;
    if (inlineUploadButton) inlineUploadButton.hidden = false;
    if (chatInput) {
      chatInput.disabled = false;
      chatInput.placeholder = getAiChatPlaceholder();
    }
    if (chatBtn) chatBtn.disabled = false;
    if (extractBtn) extractBtn.disabled = false;
    if (summaryBtn) summaryBtn.disabled = executiveBriefAvailable === false;
  }
}

// AI Studio File Input & Dropzone Wiring
const aiFileInput = $('#ai-file-input');
const aiUploadBtn = $('#ai-upload-btn');
const aiInlineUploadBtn = $('#ai-upload-inline-btn');
const aiBrowseTrigger = $('#ai-browse-trigger');
const aiUploadZone = $('#ai-upload-zone');
const aiChangeDocBtn = $('#ai-change-doc-btn');
const aiClearDocBtn = $('#ai-clear-doc-btn');

if (aiUploadBtn) aiUploadBtn.onclick = (e) => { e.stopPropagation(); aiFileInput?.click(); };
if (aiInlineUploadBtn) aiInlineUploadBtn.onclick = () => aiFileInput?.click();
if (aiBrowseTrigger) aiBrowseTrigger.onclick = () => aiFileInput?.click();
if (aiChangeDocBtn) aiChangeDocBtn.onclick = () => aiFileInput?.click();

if (aiClearDocBtn) {
  aiClearDocBtn.onclick = async () => {
    state.files = [];
    state.aiConversation = [];
    await removeLocalWork('ai-pdf', 'ai-conversation').catch(error => console.warn('Could not clear AI work locally:', error));
    clearLocalWorkMarkerIfEmpty();
    updateAiDocBar();
    renderAiConversation([]);
    $('#summary-display').textContent = 'Summary will appear here after generation...';
    const sumActions = $('#summary-actions-bar');
    if (sumActions) sumActions.hidden = true;
    showToast('Document cleared from AI workspace', 'info');
  };
}

if (aiFileInput) {
  aiFileInput.onchange = async (e) => {
    if (e.target.files?.length) {
      const file = e.target.files[0];
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        showToast('Please select a valid PDF file.', 'warning');
        return;
      }
      state.files = [file];
      writeLocalWork('ai-pdf', localPdfRecord(file)).catch(error => {
        console.warn('Paperplane could not save the AI PDF locally:', error);
        showToast('This browser could not save the PDF locally. Download any results you want to keep.', 'warning', 7000);
      });
      rememberLocalWork(file.name);
      updateAiDocBar();
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
      writeLocalWork('ai-pdf', localPdfRecord(file)).catch(error => {
        console.warn('Paperplane could not save the AI PDF locally:', error);
        showToast('This browser could not save the PDF locally. Download any results you want to keep.', 'warning', 7000);
      });
      rememberLocalWork(file.name);
      updateAiDocBar();
    }
  };
}

// AI Test Connection
const testConnBtn = $('#ai-test-connection-btn');
if (testConnBtn) {
  testConnBtn.onclick = async () => {
    const statusEl = $('#ai-connection-status');
    testConnBtn.disabled = true;
    testConnBtn.textContent = 'Testing...';
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.className = 'ai-connection-status pending';
      statusEl.textContent = 'Checking AI service…';
    }
    try {
      const res = await safeFetch('/api/ai/test-connection');
      if (res.status === 'connected' || res.status === 'inference_succeeded') {
        if (statusEl) { statusEl.className = 'ai-connection-status'; statusEl.textContent = 'AI Connected'; }
        showToast('AI Connected', 'success');
      } else if (res.status === 'configuration_missing') {
        if (statusEl) { statusEl.className = 'ai-connection-status error'; statusEl.textContent = 'AI provider is not configured'; }
        showToast('AI provider is not configured', 'warning', 6000);
      } else {
        const message = res.message || 'AI request failed, please try again';
        if (statusEl) { statusEl.className = 'ai-connection-status error'; statusEl.textContent = message; }
        showToast(message, 'error', 6000);
      }
    } catch (err) {
      const message = err.message || 'AI request failed, please try again';
      if (statusEl) { statusEl.className = 'ai-connection-status error'; statusEl.textContent = message; }
      showToast(message, 'error', 6000);
    } finally {
      testConnBtn.disabled = false;
      testConnBtn.textContent = 'Test AI Connection';
    }
  };
}

// AI Chat Clear
const chatClearBtn = $('#ai-chat-clear-btn');
if (chatClearBtn) {
  chatClearBtn.onclick = async () => {
    activeAIChatController?.abort();
    state.aiConversation = [];
    renderAiConversation([]);
    await removeLocalWork('ai-conversation').catch(error => console.warn('Could not clear AI chat locally:', error));
    clearLocalWorkMarkerIfEmpty();
    showToast('Conversation cleared', 'info');
  };
}

$('#ai-clear-work-btn')?.addEventListener('click', async () => {
  activeAIChatController?.abort();
  state.files = [];
  state.aiConversation = [];
  await removeLocalWork('ai-pdf', 'ai-conversation').catch(error => console.warn('Could not clear AI work locally:', error));
  renderAiConversation([]);
  updateAiDocBar();
  $('#summary-display').textContent = 'Summary will appear here after generation...';
  const summaryActions = $('#summary-actions-bar');
  if (summaryActions) summaryActions.hidden = true;
  clearLocalWorkMarkerIfEmpty();
  showToast('Saved PDF and chat history cleared from this browser', 'success');
});

// AI chat streams real provider deltas and server-reported work stages.
let activeAIChatController = null;
const chatStopBtn = $('#chat-stop-btn');
chatStopBtn?.addEventListener('click', () => activeAIChatController?.abort());

function safeAiErrorMessage(error) {
  const raw = String(error?.message || 'AI request failed. Please try again.').trim();
  if (/api[_ -]?key|authorization|bearer\s|https?:\/\/|bluesminds|gemini|openai|anthropic|nvidia|gpt[-_]/i.test(raw)) {
    return 'Paperplane AI could not complete this request. Please try again or contact support.';
  }
  return raw.slice(0, 240);
}

function questionRequiresPdf(question) {
  const asksAboutSource = /\b(?:this|that|my|your|uploaded|attached|older|current)\s+(?:pdf|document|file|paper|notes?|invoice|resume|report|contract)\b|\b(?:from|in|inside|on)\s+(?:the\s+)?(?:pdf|document|file|upload|attachment)\b|\baccording\s+to\s+(?:the|this|my)\b|\bpage\s+\d+\b/i.test(question);
  const asksForSourceAnalysis = /\b(?:summari[sz]e|summary|extract|find|identify|quote|cite|search|look\s+for|keywords?)\b.*\b(?:pdf|document|file|paper|notes?|uploaded|attached)\b|\b(?:pdf|document|file|paper|notes?)\b.*\b(?:keyword|summari[sz]e|summary|extract|page|citation|quote)\b|\b(?:keyword|summari[sz]e|summary|extract|find|identify|quote|cite)\b.*\b(?:from|in|inside|of|within)\b.*\b(?:pdf|document|file|paper|notes?)\b/i.test(question);
  return asksAboutSource || asksForSourceAnalysis;
}

$('#chat-form').onsubmit = async e => {
  e.preventDefault();
  const input = $('#chat-input');
  const question = input.value.trim();
  if (!question) return;

  const msgs = $('#chat-messages');
  const emptyState = $('#ai-empty-state');
  if (emptyState) emptyState.hidden = true;
  const userBubble = document.createElement('div');
  userBubble.className = 'chat-bubble user';
  userBubble.innerHTML = `<strong>You:</strong> ${escapeHtml(question)}`;
  msgs.appendChild(userBubble);
  input.value = '';
  if (!state.files.length && questionRequiresPdf(question)) {
    const guidance = document.createElement('div');
    guidance.className = 'chat-bubble ai ai-document-required';
    guidance.innerHTML = '<strong>Paperplane AI:</strong><p>Upload PDF to chat and ask questions about a document. General questions work without a PDF.</p>';
    msgs.appendChild(guidance);
    state.aiConversation.push({ role: 'user', text: question });
    state.aiConversation.push({ role: 'assistant', kind: 'document-required', text: 'Upload PDF to chat and ask questions about a document. General questions work without a PDF.' });
    persistAiConversation();
    updateAiDocBar();
    msgs.scrollTop = msgs.scrollHeight;
    return;
  }
  const answerBubble = document.createElement('div');
  answerBubble.className = 'chat-bubble ai ai-stream-bubble';
  answerBubble.innerHTML = '<strong>Paperplane AI:</strong><div class="ai-stage-line" aria-live="polite"><span class="ai-stage-dots">•••</span><span>Thinking…</span></div><ol class="ai-stage-timeline" aria-label="AI work stages"><li data-ai-stage="thinking">Thinking</li><li data-ai-stage="extracting">Extracting</li><li data-ai-stage="analysing">Analysing</li><li data-ai-stage="searching">Searching</li><li data-ai-stage="generating">Generating</li></ol><div class="chat-markdown ai-stream-text"></div><div class="ai-response-mode" hidden></div><div class="chat-citation-tags"></div>';
  msgs.appendChild(answerBubble);
  const stageNode = answerBubble.querySelector('.ai-stage-line span:last-child');
  const stageDots = answerBubble.querySelector('.ai-stage-dots');
  const stageItems = [...answerBubble.querySelectorAll('[data-ai-stage]')];
  const stageKeys = { 'Thinking…': 'thinking', 'Extracting…': 'extracting', 'Analysing…': 'analysing', 'Searching…': 'searching', 'Generating…': 'generating' };
  const completedStages = new Set();
  const updateStage = value => {
    stageNode.textContent = value;
    const active = stageKeys[value];
    if (active) completedStages.add(active);
    stageItems.forEach(item => {
      const key = item.dataset.aiStage;
      const isActive = key === active;
      item.classList.toggle('is-active', isActive);
      item.classList.toggle('is-complete', completedStages.has(key) && !isActive);
      if (isActive) item.setAttribute('aria-current', 'step');
      else item.removeAttribute('aria-current');
    });
  };
  const textNode = answerBubble.querySelector('.ai-stream-text');
  const responseModeNode = answerBubble.querySelector('.ai-response-mode');
  const citationsNode = answerBubble.querySelector('.chat-citation-tags');
  let answerText = '';
  let responseCitations = [];
  let streamFailed = false;
  msgs.scrollTop = msgs.scrollHeight;

  const form = new FormData();
  if (state.files.length) form.append('file', state.files[0]);
  form.append('question', question);
  rememberLocalWork(state.files[0]?.name || 'AI chat');

  const btn = $('#chat-send-btn');
  activeAIChatController = new AbortController();
  btn.disabled = true;
  btn.textContent = 'Ask';
  input.disabled = true;
  if (chatStopBtn) chatStopBtn.hidden = false;

  try {
    const response = await fetch('/api/ai/chat/stream', { method: 'POST', body: form, signal: activeAIChatController.signal, credentials: 'same-origin' });
    if (!response.ok || !response.body) {
      let message = 'AI request failed, please try again';
      try { const body = await response.json(); if (/not configured/i.test(body.detail || '')) message = 'AI provider is not configured'; } catch { /* retain plain fallback */ }
      throw new Error(message);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = '';
    let completed = false;
    while (!completed) {
      const { value, done } = await reader.read();
      pending += decoder.decode(value || new Uint8Array(), { stream: !done });
      const frames = pending.split(/\r?\n\r?\n/);
      pending = frames.pop() || '';
      for (const frame of frames) {
        const eventName = frame.match(/^event:\s*(.+)$/m)?.[1]?.trim();
        const dataLine = frame.match(/^data:\s*(.+)$/m)?.[1];
        if (!dataLine) continue;
        let payload;
        try { payload = JSON.parse(dataLine); } catch { continue; }
        if (eventName === 'stage') updateStage(payload.stage);
        if (eventName === 'token') {
          answerText += payload.text || '';
          textNode.textContent = answerText;
        }
        if (eventName === 'replace') {
          answerText = payload.text || '';
          textNode.textContent = answerText;
        }
        if (eventName === 'done') {
          responseCitations = Array.isArray(payload.citations) ? payload.citations : [];
          citationsNode.innerHTML = responseCitations.map(page => `<span class="ai-citation-tag">Page ${escapeHtml(page)}</span>`).join('');
          if (payload.mode === 'local_extraction' && responseModeNode) {
            responseModeNode.hidden = false;
            responseModeNode.textContent = 'Local document extract · AI provider is disabled';
          }
          updateStage('Complete');
          stageItems.forEach(item => {
            if (completedStages.has(item.dataset.aiStage)) item.classList.add('is-complete');
            item.classList.remove('is-active');
            item.removeAttribute('aria-current');
          });
          textNode.innerHTML = renderMarkdown(answerText);
          completed = true;
        }
        if (eventName === 'error') throw new Error(/not configured/i.test(payload.message || '') ? 'AI provider is not configured' : (payload.message || 'AI request failed, please try again'));
      }
      if (done) completed = true;
      msgs.scrollTop = msgs.scrollHeight;
    }
  } catch (err) {
    const errMsg = safeAiErrorMessage(err);
    if (err.name === 'AbortError') {
      stageNode.textContent = 'Stopped';
      stageDots?.remove();
    } else {
      activeAIChatController?.abort();
      streamFailed = true;
      stageNode.textContent = 'Connection interrupted';
      stageDots?.remove();
      const failure = document.createElement('div');
      failure.className = 'ai-chat-error';
      failure.innerHTML = `${escapeHtml(errMsg)} <button type="button" class="ai-chat-retry">Retry</button>`;
      failure.querySelector('.ai-chat-retry').onclick = () => {
        failure.remove();
        answerBubble.remove();
        input.value = question;
        $('#chat-form').requestSubmit();
      };
      answerBubble.appendChild(failure);
    }
  } finally {
    activeAIChatController = null;
    btn.disabled = false;
    btn.textContent = 'Ask';
    input.disabled = false;
    if (chatStopBtn) chatStopBtn.hidden = true;
    if (!streamFailed && stageNode.textContent === 'Complete') stageDots?.remove();
    if (!streamFailed && stageNode.textContent === 'Complete') {
      addAiConversationTurn(question, answerText, responseCitations);
      await refreshQuotaUsage();
    }
    msgs.scrollTop = msgs.scrollHeight;
  }
};

// Executive Summarizer
async function generateExecutiveBrief() {
  if (executiveBriefAvailable === false) {
    setExecutiveBriefAvailability(false);
    return;
  }
  if (!state.files.length) {
    showToast('Please upload or select a PDF document first.', 'warning');
    aiFileInput?.click();
    return;
  }
  const btn = $('#trigger-summary-btn');
  const summaryBox = $('#summary-display');
  const actionsBar = $('#summary-actions-bar');
  currentSummaryText = '';
  btn.disabled = true;
  btn.textContent = 'Generating Executive Brief...';
  summaryBox.textContent = 'Generating an executive brief from this PDF…';
  if (actionsBar) actionsBar.hidden = true;
  const form = new FormData();
  form.append('file', state.files[0]);

  try {
    const res = await safeFetch('/api/ai/summarize', { method: 'POST', body: form });
    currentSummaryText = res.summary || '';
    if (!currentSummaryText.trim()) throw new Error('Paperplane AI returned an empty executive brief. Please retry.');
    summaryBox.innerHTML = `${renderMarkdown(currentSummaryText)}${summaryCitationHtml(res.citations)}`;
    if (actionsBar) actionsBar.hidden = false;
    showToast('Executive brief generated successfully!', 'success');
  } catch (err) {
    const errMsg = safeAiErrorMessage(err);
    summaryBox.innerHTML = `<div class="ai-summary-error" role="alert">${escapeHtml(errMsg)} <button type="button" id="summary-retry-btn" class="btn-secondary-action">Retry</button></div>`;
    $('#summary-retry-btn')?.addEventListener('click', generateExecutiveBrief, { once: true });
    if (actionsBar) actionsBar.hidden = true;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate Executive Brief';
  }
}

$('#trigger-summary-btn').onclick = generateExecutiveBrief;

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
    subEl.textContent = `File: ${fileName} • ${data.total_pages} Page${data.total_pages === 1 ? '' : 's'} • Structured extraction`;
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
      const currencyCode = typeof inv.currency === 'string' ? inv.currency.trim() : '';
      const cur = currencyCode ? ` (${currencyCode})` : ' (currency not identified)';
      const formatExtractedAmount = value => {
        if (value == null || value === '') return null;
        return currencyCode ? `${currencyCode} ${value}` : String(value);
      };
      const fields = [
        { label: `Total Amount${cur}`, val: formatExtractedAmount(inv.total_amount), highlight: true },
        { label: 'Invoice #', val: inv.invoice_number },
        { label: 'Invoice Date', val: inv.invoice_date },
        { label: 'Due Date', val: inv.due_date },
        { label: `Subtotal${currencyCode ? ` (${currencyCode})` : ''}`, val: formatExtractedAmount(inv.subtotal) },
        { label: `Tax Amount${currencyCode ? ` (${currencyCode})` : ''}`, val: formatExtractedAmount(inv.tax_amount) },
        { label: 'Vendor / Issuer', val: inv.vendor },
        { label: 'Customer / Bill To', val: inv.customer },
        { label: 'Payment Terms', val: inv.payment_terms }
      ];

      fields.forEach(f => {
        const card = document.createElement('div');
        card.className = 'extraction-field-card';
        const isNull = !f.val;
        const displayVal = isNull ? '—' : escapeHtml(String(f.val));
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
            <td style="text-align: right;">${item.unit_price != null ? escapeHtml(formatExtractedAmount(item.unit_price) || '-') : '-'}</td>
            <td style="text-align: right; font-weight: 700;">${item.amount != null ? escapeHtml(formatExtractedAmount(item.amount) || '-') : '-'}</td>
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
        const displayVal = isNull ? '—' : escapeHtml(String(f.val));
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
        ...(gen.document_date ? [{ label: 'Document Date', val: gen.document_date }] : []),
        { label: 'Detected Topics Count', val: gen.detected_topics?.length ? `${gen.detected_topics.length} topic${gen.detected_topics.length === 1 ? '' : 's'}` : null }
      ];

      fields.forEach(f => {
        const card = document.createElement('div');
        card.className = 'extraction-field-card';
        const isNull = !f.val;
        const displayVal = isNull ? '—' : escapeHtml(String(f.val));
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
        <button class="delete-file-btn" data-revoke-key="${escapeHtml(k.id)}" title="Revoke API Key"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
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
        <button type="button" class="btn-primary-action" style="padding: 4px 10px; font-size: 11px;" data-copy-value="${escapeHtml(data.api_key)}"> Copy Key</button>
      </div>
      <code style="display: block; background: #fff; padding: 8px 12px; margin: 8px 0; border: 1px solid var(--border-light); border-radius: 6px; font-weight: bold; word-break: break-all; font-family: var(--font-mono); cursor: pointer;" data-copy-value="${escapeHtml(data.api_key)}" title="Click to copy">${escapeHtml(data.api_key)}</code>
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
function openAuthModal(msgOrMode = '', requestedMode = null) {
  let msg = '';
  if (msgOrMode === 'login' || msgOrMode === 'register') {
    authMode = msgOrMode;
  } else {
    msg = msgOrMode || '';
    if (requestedMode === 'login' || requestedMode === 'register') {
      authMode = requestedMode;
    }
  }

  const modal = $('#auth-modal');
  if (modal) modal.hidden = false;

  const otpPane = $('#auth-otp-pane');
  if (otpPane) otpPane.hidden = true;
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

  if (authMode === 'register') {
    $('#tab-register')?.classList.add('active');
    $('#tab-login')?.classList.remove('active');
    $('#auth-modal-title').textContent = 'Create an Account';
    $('#auth-submit-btn').innerHTML = 'Create Account <span>→</span>';
    if ($('#auth-confirm-password-row')) $('#auth-confirm-password-row').hidden = false;
    if ($('#auth-forgot-row')) $('#auth-forgot-row').hidden = true;
  } else {
    $('#tab-login')?.classList.add('active');
    $('#tab-register')?.classList.remove('active');
    $('#auth-modal-title').textContent = 'Sign In to Paperplane';
    $('#auth-submit-btn').innerHTML = 'Sign In <span>→</span>';
    if ($('#auth-confirm-password-row')) $('#auth-confirm-password-row').hidden = true;
    if ($('#auth-forgot-row')) $('#auth-forgot-row').hidden = false;
  }

  const errEl = $('#auth-error');
  if (errEl) {
    if (msg) {
      errEl.textContent = msg;
      errEl.hidden = false;
    } else {
      errEl.textContent = '';
      errEl.hidden = true;
    }
  }
  initGoogleAuth();
}

function setAuthMode(mode) {
  if (mode === 'register') $('#tab-register')?.click();
  else $('#tab-login')?.click();
}

$('#close-auth-modal').onclick = () => {
  $('#auth-modal').hidden = true;
  const otpPane = $('#auth-otp-pane');
  if (otpPane) otpPane.hidden = true;
  const authForm = $('#auth-form');
  if (authForm) authForm.hidden = false;
  const errEl = $('#auth-error');
  if (errEl) {
    errEl.hidden = true;
    errEl.textContent = '';
  }
};

$('#tab-login').onclick = () => {
  authMode = 'login';
  $('#tab-login').classList.add('active');
  $('#tab-register').classList.remove('active');
  $('#auth-modal-title').textContent = 'Sign In to Paperplane';
  $('#auth-submit-btn').innerHTML = 'Sign In <span>→</span>';
  if ($('#auth-confirm-password-row')) $('#auth-confirm-password-row').hidden = true;
  if ($('#auth-forgot-row')) $('#auth-forgot-row').hidden = false;
  const otpPane = $('#auth-otp-pane');
  if (otpPane) otpPane.hidden = true;
  const authForm = $('#auth-form');
  if (authForm) authForm.hidden = false;
  const errEl = $('#auth-error');
  if (errEl) {
    errEl.hidden = true;
    errEl.textContent = '';
  }
};

$('#tab-register').onclick = () => {
  authMode = 'register';
  $('#tab-register').classList.add('active');
  $('#tab-login').classList.remove('active');
  $('#auth-modal-title').textContent = 'Create an Account';
  $('#auth-submit-btn').innerHTML = 'Create Account <span>→</span>';
  if ($('#auth-confirm-password-row')) $('#auth-confirm-password-row').hidden = false;
  if ($('#auth-forgot-row')) $('#auth-forgot-row').hidden = true;
  const otpPane = $('#auth-otp-pane');
  if (otpPane) otpPane.hidden = true;
  const authForm = $('#auth-form');
  if (authForm) authForm.hidden = false;
  const errEl = $('#auth-error');
  if (errEl) {
    errEl.hidden = true;
    errEl.textContent = '';
  }
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
    if (data.status === 'success' || data.user_id) {
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
    } else if (data.status === 'success' || data.user_id) {
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

      if (res.status === 'success' || res.user_id) {
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

let restoreCollapsedSidebarAfterMobileClose = false;

function openMobileSidebar() {
  const sidebar = $('#sidebar');
  const backdrop = $('#mobile-backdrop');
  const shell = $('#app-shell');
  restoreCollapsedSidebarAfterMobileClose = Boolean(shell?.classList.contains('sidebar-collapsed'));
  shell?.classList.remove('sidebar-collapsed');
  if (sidebar) sidebar.classList.add('mobile-open');
  if (backdrop) backdrop.hidden = false;
  $('#mobile-menu-btn')?.setAttribute('aria-expanded', 'true');
}

function closeMobileSidebar() {
  const sidebar = $('#sidebar');
  const backdrop = $('#mobile-backdrop');
  const shell = $('#app-shell');
  if (sidebar) sidebar.classList.remove('mobile-open');
  if (backdrop) backdrop.hidden = true;
  if (restoreCollapsedSidebarAfterMobileClose) shell?.classList.add('sidebar-collapsed');
  restoreCollapsedSidebarAfterMobileClose = false;
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

  const examBtn = $('#exam-cashfree-checkout-btn');
  if (examBtn) examBtn.onclick = () => initiateCheckout('exam_pass', examBtn);

  const studentBtn = $('#student-cashfree-checkout-btn');
  if (studentBtn) studentBtn.onclick = () => initiateCheckout('student_pro', studentBtn);

  const proBtn = $('#pro-cashfree-checkout-btn');
  if (proBtn) proBtn.onclick = () => initiateCheckout('pro', proBtn);

  const cyberBtn = $('#cybercafe-cashfree-checkout-btn');
  if (cyberBtn) cyberBtn.onclick = () => initiateCheckout('cyber_cafe', cyberBtn);

  const devBtn = $('#dev-cashfree-checkout-btn');
  if (devBtn) devBtn.onclick = () => initiateCheckout('developer', devBtn);
}

async function initiateCheckout(tier, btnEl) {
  if (!state.user) {
    closeUpgradeModal();
    openAuthModal('Please sign in or create an account to subscribe.', 'register');
    showToast('Please sign in or create an account to subscribe.', 'info', 4000);
    return;
  }

  const originalText = btnEl.innerHTML;
  btnEl.disabled = true;
  btnEl.innerHTML = 'Connecting to Cashfree…';

  try {
    const res = await safeFetch('/api/billing/checkout-session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tier: tier, currency: 'INR', mode: 'subscription' })
    });

    if (res.mode === 'demo_activated') {
      const tierDisplayNames = {
        exam_pass: '24-Hour Exam Pass (₹19)',
        student_pro: 'Student & Educator Pro (₹49/mo)',
        pro: 'Pro Power User (₹250/mo)',
        cyber_cafe: 'Cyber Café Pack (₹299/mo)',
        developer: 'Developer API (₹750/mo)'
      };
      showToast(`${tierDisplayNames[tier] || 'Pro'} Plan Activated!`, 'success', 5000);
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
  const startupNavigationVersion = workspaceNavigationVersion;
  restoreCachedAuthShell();
  // Snapshot reload-only session markers before asynchronous setup. Reading
  // them after the network awaits can consume fresh work created by a fast user.
  let previousView = null;
  let previousDoc = null;
  try {
    previousView = sessionStorage.getItem('paperplane-active-view');
    previousDoc = sessionStorage.getItem('paperplane-last-local-document');
    if (previousDoc) sessionStorage.removeItem('paperplane-last-local-document');
  } catch { /* session storage may be disabled */ }

  initBillingHandlers();
  initMobileNav();
  initHomeSearchAndFilter();
  initToolDeskDirectory();
  await checkAuthStatus();
  await checkExecutiveBriefAvailability();
  await handleCashfreeReturn();
  await initGoogleAuth();

  try {
    const data = await safeFetch('/api/operations');
    state.operations = data;
    renderSidebarTools();
    renderHomeToolsGrid();
    renderToolDeskDirectory();
    const userNavigatedDuringStartup = workspaceNavigationVersion !== startupNavigationVersion;
    if (!userNavigatedDuringStartup) {
      handleInitialRouting();
    } else if (state.activeView === 'desk' && state.operations[state.operation]) {
      // A slow auth/catalog startup must not discard a view the user already chose.
      // Reapply the selected tool now that its server metadata is available.
      selectOperation(state.operation, true);
    }
    try {
      // Restore the last workspace only on a plain root reload; explicit tool
      // and document routes continue to take precedence.
      const isRootWorkspaceReload = window.location.pathname.replace(/\/+$/, '') === '' && !window.location.search;
      if (!userNavigatedDuringStartup && isRootWorkspaceReload && (previousView === 'studio' || previousView === 'ai')) {
        switchWorkspaceView(previousView);
      }
      let restoredWork = false;
      if (state.activeView === 'ai') restoredWork = await restoreAiWorkspace();
      if (state.activeView === 'studio') {
        await restoreStudioWorkspace();
        restoredWork = Boolean(state.studio.pdfDoc);
      }
      if (previousDoc && !restoredWork) showToast('Some temporary tool uploads may need to be selected again after reload.', 'info', 7000);
    } catch { /* session storage may be disabled */ }
  } catch (err) {
    console.error('Failed to load operations catalog:', err);
    showToast('Tool catalog is temporarily unavailable. The server-rendered page remains available.', 'warning', 6000);
  }
}

async function handleCashfreeReturn() {
  const params = new URLSearchParams(window.location.search);
  const orderId = params.get('order_id');
  const billingReturn = params.get('billing');
  if (!['return', 'success'].includes(billingReturn) || !orderId) return;
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
      showToast('Checkout cancelled or payment not completed. No plan change was made.', 'info', 6000);
    }
  } catch (err) {
    showToast(`Payment was not verified. No plan change was made: ${err.message}`, 'warning', 6000);
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

// Keep interaction handlers in this script instead of executable HTML attributes.
document.addEventListener('click', event => {
  const target = event.target.closest('[data-workspace-view], [data-platform], [data-select-operation], [data-command-operation], [data-reset-home-search], [data-remove-file], [data-revoke-key], [data-copy-value]');
  if (!target) return;
  if (target.dataset.workspaceView) switchWorkspaceView(target.dataset.workspaceView);
  else if (target.dataset.platform) {
    const platformInput = $('#waitlist-platform');
    if (platformInput) platformInput.value = target.dataset.platform;
    $('#waitlist-email')?.focus();
  } else if (target.dataset.selectOperation) selectOperation(target.dataset.selectOperation);
  else if (target.dataset.commandOperation) selectOperationFromCommand(target.dataset.commandOperation);
  else if (target.hasAttribute('data-reset-home-search')) resetHomeSearch();
  else if (target.hasAttribute('data-remove-file')) removeFile(Number(target.dataset.removeFile));
  else if (target.dataset.revokeKey) revokeKey(target.dataset.revokeKey);
  else if (target.hasAttribute('data-copy-value')) copyToClipboard(target.dataset.copyValue);
});

document.addEventListener('keydown', event => {
  const target = event.target.closest('[data-select-operation], [data-command-operation]');
  if (!target || !['Enter', ' '].includes(event.key)) return;
  if (target.classList.contains('home-tool-card')) event.preventDefault();
  if (target.dataset.selectOperation) selectOperation(target.dataset.selectOperation);
  else if (target.dataset.commandOperation) selectOperationFromCommand(target.dataset.commandOperation);
});

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
          posBadge.textContent = data.waitlist_number
            ? `You're on the apps waitlist! (Position #${data.waitlist_number})`
            : "You're on the apps waitlist!";
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
  // Initial route resolution may finish after the user has opened Cloud Import.
  // Preserve that explicit action instead of silently dismissing the modal.
  const setInitialView = (view, extra = null) => switchWorkspaceView(view, extra, false, true);

  if (typeof checkPasswordResetUrl === 'function') {
    checkPasswordResetUrl();
  }

  if (path.includes('terms') || urlParams.get('legal') === 'terms' || urlParams.get('tab') === 'terms') {
    setInitialView('legal', 'terms');
  } else if (path.includes('privacy') || urlParams.get('legal') === 'privacy' || urlParams.get('view') === 'legal') {
    setInitialView('legal', 'privacy');
  } else if (path.includes('reset-password')) {
    checkPasswordResetUrl();
    setInitialView('home');
  } else if (path.includes('developers') || path.includes('api-docs') || path.includes('/docs/api') || urlParams.get('view') === 'api-docs') {
    setInitialView('api-docs');
  } else if (path.includes('download') || path.includes('apps') || urlParams.get('view') === 'download') {
    setInitialView('download');
  } else if (pathSlug === 'tool-desk') {
    setInitialView('tool-desk');
  } else if (pathSlug === 'studio' || urlParams.get('view') === 'studio') {
    setInitialView('studio');
  } else if (OPERATION_BY_SLUG[pathSlug]) {
    selectOperation(OPERATION_BY_SLUG[pathSlug], true, true);
  } else if (pathSlug === 'convert-pdf') {
    renderToolDeskDirectory('convert');
    setInitialView('tool-desk');
  } else if (pathSlug === 'pdf-security') {
    renderToolDeskDirectory('security');
    setInitialView('tool-desk');
  } else if (urlParams.get('tool') && state.operations && state.operations[urlParams.get('tool')]) {
    // Backward compatibility for links created before clean URL routing.
    selectOperation(urlParams.get('tool'), true, true);
  } else {
    selectOperation('merge', false);
    setInitialView('home');
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
  } else if (pathSlug === 'tool-desk') {
    switchWorkspaceView('tool-desk', null, false);
  } else if (pathSlug === 'studio') {
    switchWorkspaceView('studio', null, false);
  } else if (OPERATION_BY_SLUG[pathSlug]) {
    selectOperation(OPERATION_BY_SLUG[pathSlug], true);
  } else if (urlParams.get('tool')) {
    selectOperation(urlParams.get('tool'), true);
  } else {
    switchWorkspaceView('home', null, false);
  }
});


