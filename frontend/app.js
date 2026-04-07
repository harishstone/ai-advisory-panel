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

  } catch (err) {
    showQuoteError('Network error — is the backend running?');
  } finally {
    setLoadingBtn(false);
  }
}

// ─── Config Status ─────────────────────────────────────────────────────────────

const SECTION_INFO = {
  profile:        'Profile',
  compute:        'Compute',
  storage_media:  'Storage',
  storage_config: 'RAID',
  network:        'Network',
  veeam:          'Veeam',
  environment:    'Env',
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

  // Activate sidebar button
  document.querySelectorAll('.q-btn').forEach(btn => btn.classList.remove('q-btn-active'));
  buttonEl.classList.add('q-btn-active');
  state.activeQuestionId = questionId;

  const questionText = buttonEl.querySelector('.q-text').textContent.trim();
  addUserMessage(questionText);
  const thinkingId = addThinkingMessage();

  try {
    const res = await fetch(`${API_BASE}/api/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question_id: questionId })
    });

    const data = await res.json();
    removeThinkingMessage(thinkingId);

    if (!res.ok) {
      addErrorMessage(data.detail || 'Failed to get a response.');
      return;
    }

    addAssistantMessage(data);

  } catch {
    removeThinkingMessage(thinkingId);
    addErrorMessage('Network error — is the backend running?');
  }
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

  try {
    const res = await fetch(`${API_BASE}/api/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ custom_question: question })
    });

    const data = await res.json();
    removeThinkingMessage(thinkingId);

    if (!res.ok) {
      addErrorMessage(data.detail || 'Failed to get a response.');
      return;
    }

    addAssistantMessage(data);

  } catch {
    removeThinkingMessage(thinkingId);
    addErrorMessage('Network error — is the backend running?');
  } finally {
    setCustomBtnLoading(false);
  }
}

// ─── Message Builders ──────────────────────────────────────────────────────────

function addUserMessage(text) {
  showChat();
  appendToChat(`
    <div class="flex justify-end message-in">
      <div class="max-w-[75%]">
        <div class="bg-brand-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed shadow-sm">
          ${escapeHtml(text)}
        </div>
        <div class="text-xs text-gray-400 mt-1.5 text-right pr-1">${formatTime()}</div>
      </div>
    </div>
  `);
}

function addThinkingMessage() {
  showChat();
  state.isThinking = true;
  const id = `thinking-${Date.now()}`;
  appendToChat(`
    <div class="flex gap-3 message-in" id="${id}">
      <div class="ai-avatar flex-shrink-0">AI</div>
      <div class="mt-1">
        <div class="text-xs font-semibold text-gray-400 mb-2">AI Advisory</div>
        <div class="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm inline-block">
          <div class="thinking-dots"><span></span><span></span><span></span></div>
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
  const isA = data.category === 'A';
  const time = formatTime();

  const warningsHTML = (data.calibration_warnings || []).map(w => `
    <div class="flex gap-2 text-xs bg-blue-50 border border-blue-100 text-blue-700 rounded-xl px-3 py-2.5 mb-3 leading-relaxed">
      <svg class="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
      </svg>
      <span>${escapeHtml(w)}</span>
    </div>
  `).join('');

  appendToChat(`
    <div class="flex gap-3 message-in">
      <div class="ai-avatar flex-shrink-0">AI</div>
      <div class="flex-1 min-w-0">
        <div class="flex items-center mb-2.5">
          <span class="text-xs font-semibold text-gray-400">AI Advisory</span>
          <span class="text-xs text-gray-400 ml-auto">${time}</span>
        </div>
        ${warningsHTML}
        <div class="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm prose-response">
          ${formatResponse(data.response)}
        </div>
      </div>
    </div>
  `);
}

function addSystemMessage(text) {
  showChat();
  appendToChat(`
    <div class="flex justify-center message-in">
      <div class="text-xs text-gray-400 bg-gray-50 border border-gray-100 rounded-full px-4 py-1.5">
        ${escapeHtml(text)}
      </div>
    </div>
  `);
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
  try { await fetch(`${API_BASE}/api/clear`, { method: 'POST' }); } catch (_) {}

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
}

// ─── Response Formatter ────────────────────────────────────────────────────────

function formatResponse(text) {
  if (!text) return '';

  let html = escapeHtml(text);

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
  setText('load-btn-text', loading ? '…' : 'Load');
  loading ? showEl('load-spinner') : hideEl('load-spinner');
}

function setCustomBtnLoading(loading) {
  $('custom-btn').disabled = loading;
  if (loading) { showEl('custom-spinner'); hideEl('send-icon'); }
  else         { hideEl('custom-spinner'); showEl('send-icon'); }
}

function shakeQuoteInput() {
  const el = $('quote-input');
  el.classList.add('shake');
  setTimeout(() => el.classList.remove('shake'), 500);
}
