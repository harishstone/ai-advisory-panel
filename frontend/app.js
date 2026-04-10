/**
 * AI Advisory Panel — Frontend Logic
 * Vanilla JS. No frameworks, no build step.
 * Chat-style UI: messages accumulate in a timeline.
 */

const API_BASE = '';

// ─── State ─────────────────────────────────────────────────────────────────────

const state = {
  quoteLoaded: false,
  quoteNumber: null,
  activeQuestionId: null,
  isThinking: false,
};

// ─── DOM Helpers ───────────────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);
function showEl(id) { $(id).classList.remove('hidden'); }
function hideEl(id) { $(id).classList.add('hidden'); }
function setText(id, t) { $(id).textContent = t; }

let sidebarOpen = false;
function toggleSidebar() {
  const sidebar = $('sidebar');
  const overlay = $('mobile-overlay');
  sidebarOpen = !sidebarOpen;

  if (sidebarOpen) {
    sidebar.classList.remove('-translate-x-full');
    sidebar.classList.add('translate-x-0');
    overlay.classList.remove('hidden');
  } else {
    sidebar.classList.remove('translate-x-0');
    sidebar.classList.add('-translate-x-full');
    overlay.classList.add('hidden');
  }
}

// ─── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadQuestionList();

  // Enter to send in quote input
  $('quote-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') loadQuote();
  });

  const textarea = $('custom-input');

  // Shift+Enter = newline, Enter = send
  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      askCustom();
    }
  });

  // Auto-resize textarea
  textarea.addEventListener('input', () => {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 140) + 'px';
  });
});

// ─── Load Quote ────────────────────────────────────────────────────────────────

async function loadQuote() {
  const quoteNumber = $('quote-input').value.trim();
  if (!quoteNumber) {
    showQuoteError('Please enter a quote number.');
    return;
  }

  hideEl('quote-error');
  setLoadingBtn(true);

  try {
    const res = await fetch(`${API_BASE}/api/load-quote`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quote_number: quoteNumber })
    });

    const data = await res.json();

    if (!res.ok) {
      showQuoteError(data.detail || 'Failed to load quote.');
      return;
    }

    state.quoteLoaded = true;
    state.quoteNumber = quoteNumber;
    renderConfigStatus(data);
    addSystemMessage(`Quote #${quoteNumber} loaded — ${data.sections_loaded.length} configuration sections available`);
    if (data.warnings && data.warnings.length > 0) {
      addWarningsBlock(data.warnings);
    }

    // Auto-close sidebar on mobile after successfully loading a quote
    if (window.innerWidth < 768 && sidebarOpen) {
      toggleSidebar();
    }

  } catch (err) {
    showQuoteError('Network error — is the backend running?');
  } finally {
    setLoadingBtn(false);
  }
}

// ─── Config Status ─────────────────────────────────────────────────────────────

const SECTION_INFO = {
  profile: 'Profile',
  compute: 'Compute',
  storage_media: 'Storage',
  storage_config: 'RAID',
  network: 'Network',
  veeam: 'Veeam',
  environment: 'Env',
};

function renderConfigStatus(data) {
  $('config-quote-label').textContent = `Quote #${data.quote_number}`;

  const loaded = new Set(data.sections_loaded || []);
  $('config-chips').innerHTML = Object.entries(SECTION_INFO).map(([key, label]) => {
    const on = loaded.has(key);
    return `<span class="config-chip ${on ? 'config-chip-on' : 'config-chip-off'}">${label}</span>`;
  }).join('');

  showEl('config-status');
}

// ─── Question List ─────────────────────────────────────────────────────────────

async function loadQuestionList() {
  try {
    const res = await fetch(`${API_BASE}/api/questions`);
    const data = await res.json();
    renderQuestionList(data.questions);
  } catch {
    $('questions-list').innerHTML = '<div class="text-gray-600 text-xs px-2 py-2">Could not load questions.</div>';
  }
}

function renderQuestionList(questions) {
  $('questions-list').innerHTML = questions.map(q => `
    <button
      class="q-btn w-full text-left px-2 py-2 rounded-lg transition-colors"
      data-id="${q.id}"
      onclick="askPreselected(${q.id}, this)"
    >
      <div class="flex items-start gap-2">
        <span class="q-num flex-shrink-0 w-6 h-5 rounded text-xs font-bold flex items-center justify-center mt-0.5">${q.id}</span>
        <span class="q-text text-xs leading-snug line-clamp-2">${escapeHtml(q.text)}</span>
      </div>
    </button>
  `).join('');
}

// ─── Ask Pre-selected ──────────────────────────────────────────────────────────

async function askPreselected(questionId, buttonEl) {
  if (!state.quoteLoaded) {
    shakeQuoteInput();
    showQuoteError('Load a quote first.');
    return;
  }
  if (state.isThinking) return;

  document.querySelectorAll('.q-btn').forEach(btn => btn.classList.remove('q-btn-active'));
  buttonEl.classList.add('q-btn-active');
  state.activeQuestionId = questionId;

  const questionText = buttonEl.querySelector('.q-text').textContent.trim();
  addUserMessage(questionText);
  const thinkingId = addThinkingMessage();

  if (window.innerWidth < 768 && sidebarOpen) {
    toggleSidebar();
  }

  await streamAsk({ question_id: questionId }, thinkingId);
}

// ─── Ask Custom ───────────────────────────────────────────────────────────────

async function askCustom() {
  const question = $('custom-input').value.trim();
  if (!question) return;

  if (!state.quoteLoaded) {
    shakeQuoteInput();
    showQuoteError('Load a quote first.');
    return;
  }
  if (state.isThinking) return;

  document.querySelectorAll('.q-btn').forEach(btn => btn.classList.remove('q-btn-active'));
  $('custom-input').value = '';
  $('custom-input').style.height = 'auto';

  addUserMessage(question);
  const thinkingId = addThinkingMessage();
  setCustomBtnLoading(true);
  await streamAsk({ custom_question: question }, thinkingId);
  setCustomBtnLoading(false);
}

// ─── Stream Ask ───────────────────────────────────────────────────────────────

async function streamAsk(body, thinkingId) {
  try {
    const res = await fetch(`${API_BASE}/api/ask-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    if (!res.ok) {
      removeThinkingMessage(thinkingId);
      const data = await res.json().catch(() => ({}));
      addErrorMessage(data.detail || 'Failed to get a response.');
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let msgId = null;
    let fullText = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let event;
        try { event = JSON.parse(line.slice(6)); } catch { continue; }

        if (event.type === 'start') {
          // Wait for first token to create the text box

        } else if (event.type === 'token') {
          if (!msgId) {
            removeThinkingMessage(thinkingId);
            msgId = createStreamingBubble(event.warnings);
          }
          fullText += event.text;
          updateStreamingBubble(msgId, fullText);

        } else if (event.type === 'done') {
          if (!msgId) {
            removeThinkingMessage(thinkingId);
            msgId = createStreamingBubble();
          }
          finalizeStreamingBubble(msgId, fullText);

        } else if (event.type === 'error') {
          removeThinkingMessage(thinkingId);
          addErrorMessage(event.message);
        }
      }
    }

  } catch {
    removeThinkingMessage(thinkingId);
    addErrorMessage('Network error — is the backend running?');
  }
}

// ─── Message Builders ──────────────────────────────────────────────────────────

function addUserMessage(text) {
  showChat();
  appendToChat(`
    <div class="flex justify-end message-in">
      <div class="max-w-[75%]">
        <div class="bg-brand-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed shadow-sm message-content">
          ${escapeHtml(text)}
        </div>
        <div class="flex items-center justify-end mt-1 px-1 gap-1">
          <button onclick="editMessage(this)" class="p-1 text-gray-400 hover:text-gray-600 rounded transition-colors" title="Edit">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
          </button>
          <button onclick="copyMessage(this)" class="p-1 text-gray-400 hover:text-gray-600 rounded transition-colors" title="Copy">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
          </button>
        </div>
      </div>
    </div>
  `);
}

function addThinkingMessage() {
  showChat();
  state.isThinking = true;
  const id = `thinking-${Date.now()}`;
  appendToChat(`
    <div class="flex message-in" id="${id}">
      <div class="flex-1 min-w-0 mt-2">
        <div class="px-2">
          <span class="gpt-dot"></span>
        </div>
      </div>
    </div>
  `, id);
  return id;
}

function removeThinkingMessage(id) {
  state.isThinking = false;
  const el = document.getElementById(id);
  if (el) el.remove();
}

function addAssistantMessage(data) {
  showChat();

  const warningsHTML = (data.calibration_warnings || []).map(w => `
    <div class="flex gap-2 text-xs bg-blue-50 border border-blue-100 text-blue-700 rounded-xl px-3 py-2.5 mb-3 leading-relaxed">
      <svg class="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
      </svg>
      <span>${escapeHtml(w)}</span>
    </div>
  `).join('');

  appendToChat(`
    <div class="flex message-in">
      <div class="flex-1 min-w-0">
        ${warningsHTML}
        <div class="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm prose-response message-content">
          ${formatResponse(data.response)}
        </div>
        <div class="flex items-center justify-start mt-1 px-1">
          <button onclick="copyMessage(this)" class="p-1 text-gray-400 hover:text-gray-600 rounded transition-colors" title="Copy">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
          </button>
        </div>
      </div>
    </div>
  `);
}

function createStreamingBubble(warnings = []) {
  showChat();
  const id = `msg-${Date.now()}`;

  const warningsHTML = (warnings || []).map(w => `
    <div class="flex gap-2 text-xs bg-blue-50 border border-blue-100 text-blue-700 rounded-xl px-3 py-2.5 mb-3 leading-relaxed">
      <svg class="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
      </svg>
      <span>${escapeHtml(w)}</span>
    </div>
  `).join('');

  appendToChat(`
    <div class="flex message-in" id="${id}">
      <div class="flex-1 min-w-0">
        ${warningsHTML}
        <div class="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm prose-response message-content" id="${id}-body">
          <span id="${id}-text" class="streaming-text"></span>
        </div>
        <div class="flex items-center justify-start mt-1 px-1">
          <button onclick="copyMessage(this)" class="p-1 text-gray-400 hover:text-gray-600 rounded transition-colors" title="Copy">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
          </button>
        </div>
      </div>
    </div>
  `);

  return id;
}

function updateStreamingBubble(id, fullText) {
  const body = document.getElementById(`${id}-body`);
  if (body) body.innerHTML = formatResponse(fullText) + '<span class="gpt-dot-inline"></span>';
  scrollToBottom();
}

function finalizeStreamingBubble(id, fullText) {
  const body = document.getElementById(`${id}-body`);
  if (body) body.innerHTML = formatResponse(fullText);
  scrollToBottom();
}

function addSystemMessage(text) {
  showChat();
  appendToChat(`
    <div class="flex justify-center message-in mb-4">
      <div class="text-xs font-medium text-brand-700 bg-brand-50 border border-brand-200 rounded-full px-4 py-1.5 shadow-sm">
        ${escapeHtml(text)}
      </div>
    </div>
  `);
}

function addWarningsBlock(warnings) {
  // Remove any existing notice toast
  const existing = document.getElementById('config-notices-toast');
  if (existing) existing.remove();

  const id = `warnings-body-${Date.now()}`;
  const items = warnings.map(w => `
    <div class="flex gap-2 items-start">
      <svg class="w-3 h-3 flex-shrink-0 mt-0.5 text-amber-500" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
      </svg>
      <span>${escapeHtml(w)}</span>
    </div>
  `).join('');

  const toast = document.createElement('div');
  toast.id = 'config-notices-toast';
  toast.style.cssText = 'position:fixed;top:16px;right:16px;z-index:9999;max-width:340px;';
  toast.innerHTML = `
    <div class="text-xs bg-amber-50 border border-amber-200 rounded-xl shadow-lg px-4 py-3 text-amber-800 leading-relaxed">
      <div class="flex items-center justify-between gap-3">
        <div class="flex items-center gap-1.5 font-semibold">
          <svg class="w-3.5 h-3.5 text-amber-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
          </svg>
          ${warnings.length} config notice${warnings.length > 1 ? 's' : ''}
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          <button onclick="document.getElementById('${id}').classList.toggle('hidden')" class="underline text-amber-700 hover:text-amber-900">View</button>
          <button onclick="document.getElementById('config-notices-toast').remove()" class="text-amber-400 hover:text-amber-700 ml-1">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>
      </div>
      <div id="${id}" class="hidden mt-2 space-y-1.5 text-amber-700">${items}</div>
    </div>
  `;
  document.body.appendChild(toast);
}

function addErrorMessage(text) {
  showChat();
  appendToChat(`
    <div class="flex gap-3 message-in">
      <div class="ai-avatar ai-avatar-err flex-shrink-0">!</div>
      <div class="bg-red-50 border border-red-200 text-red-700 rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed shadow-sm">
        ${escapeHtml(text)}
      </div>
    </div>
  `);
}

// ─── Chat Helpers ──────────────────────────────────────────────────────────────

function appendToChat(html, id = null) {
  const container = $('messages-container');
  const wrapper = document.createElement('div');
  wrapper.innerHTML = html.trim();
  const el = wrapper.firstElementChild;
  if (id) el.id = id;
  container.appendChild(el);
  scrollToBottom();
}

function showChat() {
  hideEl('empty-state');
  showEl('messages-container');
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    const chat = $('chat-messages');
    chat.scrollTop = chat.scrollHeight;
  });
}

// ─── Clear Session ─────────────────────────────────────────────────────────────

async function clearSession() {
  try { await fetch(`${API_BASE}/api/clear`, { method: 'POST' }); } catch (_) { }

  state.quoteLoaded = false;
  state.quoteNumber = null;
  state.activeQuestionId = null;
  state.isThinking = false;

  $('quote-input').value = '';
  hideEl('config-status');
  hideEl('quote-error');

  document.querySelectorAll('.q-btn').forEach(btn => btn.classList.remove('q-btn-active'));

  $('messages-container').innerHTML = '';
  hideEl('messages-container');
  showEl('empty-state');
  const toast = document.getElementById('config-notices-toast');
  if (toast) toast.remove();
}

// ─── Response Formatter ────────────────────────────────────────────────────────

function formatResponse(text) {
  if (!text) return '';

  // Strip LaTeX notation before escaping — gpt-4o sometimes outputs it
  // \( ... \) inline math → extract inner content
  text = text.replace(/\\\((.+?)\\\)/gs, (_, inner) =>
    inner.replace(/\\,/g, ' ').replace(/\\text\{(.+?)\}/g, '$1')
      .replace(/\\times/g, '×').replace(/\\div/g, '÷')
      .replace(/\\frac\{(.+?)\}\{(.+?)\}/g, '($1) / ($2)')
      .replace(/\\_/g, '_').replace(/\s+/g, ' ').trim()
  );
  // \[ ... \] block math → same treatment
  text = text.replace(/\\\[(.+?)\\\]/gs, (_, inner) =>
    inner.replace(/\\,/g, ' ').replace(/\\text\{(.+?)\}/g, '$1')
      .replace(/\\times/g, '×').replace(/\\div/g, '÷')
      .replace(/\\frac\{(.+?)\}\{(.+?)\}/g, '($1) / ($2)')
      .replace(/\s+/g, ' ').trim()
  );

  // ── Mojibake recovery ──────────────────────────────────────────────────
  // If UTF-8 bytes were decoded as Windows-1252 (Python's cp1252 default on Windows), 
  // these exact byte patterns appear. We repair them BEFORE any other processing.
  text = text
    .replace(/\u00c3\u2014/g, '\u00d7')    // Ã— → × (cp1252 mapping for \xc3\x97)
    .replace(/\u00c3\u0097/g, '\u00d7')    // Ã— → × (latin1 mapping)
    .replace(/\u00c3\u00b7/g, '\u00f7')    // Ã· → ÷
    .replace(/\u00e2\u20ac\u201d/g, '\u2014') // â€” → — (em dash)
    .replace(/\u00e2\u20ac\u201c/g, '\u2013') // â€“ → – (en dash)
    .replace(/\u00e2\u20ac\u00a2/g, '\u2022') // â€¢ → •
    .replace(/\u00e2\u20ac\u2122/g, '\u2019') // â€™ → ' 
    .replace(/\u00e2\u20ac\u0153/g, '\u201c') // â€œ → " 
    .replace(/\u00e2\u20ac\u009d/g, '\u201d') // â€? → " 
    .replace(/\u00e2\u0089\u0088/g, '\u2248') // â‰ˆ → ≈
    .replace(/\u00e2\u0089\u00a5/g, '\u2265') // â‰¥ → ≥
    .replace(/\u00e2\u0089\u00a4/g, '\u2264') // â‰¤ → ≤
    .replace(/\u00c2\u00b1/g, '\u00b1')    // Â± → ±
    .replace(/\u00e2\u2020\u2019/g, '\u2192') // â†’ → →
    .replace(/\u00e2\u20ac\u00a6/g, '\u2026') // â€¦ → …
    .replace(/\u00c2\u00a0/g, ' ');         // Â  → non-breaking space

  // Additional fallback for literal text variations
  text = text
    .replace(/Ã\u0097/g, '×')
    .replace(/Ã\u00b7/g, '÷')
    .replace(/â€”/g, '—')
    .replace(/â€“/g, '–')
    .replace(/â€™/g, "'")
    .replace(/â€œ/g, '"')
    .replace(/Â±/g, '±')
    .replace(/â‰¥/g, '≥')
    .replace(/â‰¤/g, '≤')
    .replace(/â‰ˆ/g, '≈')
    .replace(/â†’/g, '→')
    .replace(/â€¦/g, '…')
    .replace(/â€"/g, '—') // catch the exact quote string seen by the user
    .replace(/Â /g, ' ');

  // Normalize display: keep Unicode symbols readable but consistent
  text = text
    .replace(/[\u2018\u2019]/g, "'")   // curly single quotes → straight
    .replace(/[\u201c\u201d]/g, '"');   // curly double quotes → straight

  let html = escapeHtml(text);

  // Tables — must run before newline processing
  html = html.replace(/((?:\|[^\n]+\|\n?){2,})/g, (match) => {
    const lines = match.trim().split('\n').filter(l => l.trim());
    if (lines.length < 2 || !/^\|[\s\-:|]+\|/.test(lines[1])) return match;
    const headers = lines[0].split('|').slice(1, -1)
      .map(c => `<th>${c.trim()}</th>`).join('');
    const rows = lines.slice(2).map(row =>
      `<tr>${row.split('|').slice(1, -1).map(c => `<td>${c.trim()}</td>`).join('')}</tr>`
    ).join('');
    return `<div class="table-wrap"><table class="response-table">
      <thead><tr>${headers}</tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
  });

  // Markdown headers
  html = html.replace(/^#{1,3}\s+(.+)$/gm, (_, h) =>
    `<h4 class="response-heading">${h}</h4>`
  );

  // ALL CAPS section headers (ESTIMATE, CALCULATION, etc.)
  html = html.replace(/^([A-Z][A-Z\s&\/]{3,}):?\s*$/gm, (_, h) =>
    `<h4 class="response-heading">${h}</h4>`
  );

  // Bold **text**
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // Bullet lists
  html = html.replace(/^[-•]\s+(.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*?<\/li>\n?)+/gs, m =>
    `<ul class="response-list">${m}</ul>`
  );

  // Numbered lists
  html = html.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');

  // Paragraph breaks
  html = html.replace(/\n\n+/g, '</p><p class="response-para">');
  html = `<p class="response-para">${html}</p>`;
  html = html.replace(/(?<!>)\n(?!<)/g, '<br>');

  return html;
}

// ─── Utilities ─────────────────────────────────────────────────────────────────

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatTime() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function showQuoteError(msg) {
  $('quote-error').textContent = msg;
  showEl('quote-error');
  setTimeout(() => hideEl('quote-error'), 5000);
}

function setLoadingBtn(loading) {
  $('load-btn').disabled = loading;
  setText('load-btn-text', loading ? 'Loading' : 'Load');
  loading ? showEl('load-spinner') : hideEl('load-spinner');
}

function setCustomBtnLoading(loading) {
  $('custom-btn').disabled = loading;
  if (loading) { showEl('custom-spinner'); hideEl('send-icon'); }
  else { hideEl('custom-spinner'); showEl('send-icon'); }
}

function shakeQuoteInput() {
  const el = $('quote-input');
  el.classList.add('shake');
  setTimeout(() => el.classList.remove('shake'), 500);
}

async function copyMessage(btn) {
  try {
    const bubble = btn.closest('.message-in').querySelector('.message-content');
    const text = bubble ? bubble.innerText : '';
    await navigator.clipboard.writeText(text);

    const originalHTML = btn.innerHTML;
    btn.innerHTML = `<svg class="w-3.5 h-3.5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>`;

    setTimeout(() => {
      btn.innerHTML = originalHTML;
    }, 2000);
  } catch (err) {
    console.error('Failed to copy', err);
  }
}

function editMessage(btn) {
  const container = btn.closest('.message-in');
  const innerWrap = container.children[0];
  const contentEl = innerWrap.querySelector('.message-content');
  if (!contentEl) return;
  const originalText = contentEl.innerText.trim();

  const originalHTML = innerWrap.innerHTML;
  const originalClasses = innerWrap.className;

  innerWrap.className = "w-full max-w-full mb-2";

  innerWrap.innerHTML = `
    <div class="bg-gray-50 border border-gray-300 rounded-2xl p-3 shadow-inner w-full">
      <textarea class="w-full bg-transparent border-none focus:outline-none resize-y text-sm text-gray-800" rows="3">${escapeHtml(originalText)}</textarea>
      <div class="flex justify-end gap-2 mt-2">
        <button class="cancel-btn px-4 py-1.5 text-xs text-gray-600 bg-gray-200 hover:bg-gray-300 rounded-full transition-colors font-medium">Cancel</button>
        <button class="save-btn px-4 py-1.5 text-xs text-white bg-brand-600 hover:bg-brand-500 rounded-full shadow-sm transition-colors font-medium">Save & Submit</button>
      </div>
    </div>
  `;

  const textarea = innerWrap.querySelector('textarea');
  textarea.focus();
  textarea.selectionStart = textarea.selectionEnd = textarea.value.length;

  innerWrap.querySelector('.cancel-btn').onclick = () => {
    innerWrap.className = originalClasses;
    innerWrap.innerHTML = originalHTML;
  };

  innerWrap.querySelector('.save-btn').onclick = async () => {
    const newText = textarea.value.trim();
    if (!newText) {
      // Just cancel if empty
      innerWrap.className = originalClasses;
      innerWrap.innerHTML = originalHTML;
      return;
    }

    // Wipe all messages originating after this one to simulate chat history rollback
    let nextNode = container.nextElementSibling;
    while (nextNode) {
      const toRemove = nextNode;
      nextNode = nextNode.nextElementSibling;
      toRemove.remove();
    }

    // Restore the bubble structural shell with the updated text
    innerWrap.className = originalClasses;
    innerWrap.innerHTML = originalHTML;
    innerWrap.querySelector('.message-content').innerHTML = escapeHtml(newText);

    // Resume standard querying loop
    if (state.isThinking) return;
    const thinkingId = addThinkingMessage();
    setCustomBtnLoading(true);
    await streamAsk({ custom_question: newText }, thinkingId);
    setCustomBtnLoading(false);
  };
}
