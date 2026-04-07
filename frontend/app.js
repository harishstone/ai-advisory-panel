/**
 * AI Advisory Panel — Frontend Logic
 * Vanilla JS. No frameworks, no build step.
 * Calls FastAPI backend at the same origin (served by StaticFiles mount).
 */

const API_BASE = '';  // Same origin — FastAPI serves both frontend and API

// ─── State ─────────────────────────────────────────────────────────────────────

const state = {
  quoteLoaded: false,
  quoteNumber: null,
  activeQuestionId: null,
};

// ─── DOM Helpers ───────────────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);

function showEl(id)  { $(id).classList.remove('hidden'); }
function hideEl(id)  { $(id).classList.add('hidden'); }
function setText(id, text) { $(id).textContent = text; }
function setHTML(id, html) { $(id).innerHTML = html; }

function setLoading(btnId, spinnerId, textId, loading, defaultText) {
  $(btnId).disabled = loading;
  loading ? showEl(spinnerId) : hideEl(spinnerId);
  setText(textId, loading ? 'Please wait…' : defaultText);
  $(btnId).classList.toggle('opacity-60', loading);
  $(btnId).classList.toggle('cursor-not-allowed', loading);
}

// ─── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadQuestionList();

  // Allow Enter key in quote input
  $('quote-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') loadQuote();
  });
});

// ─── Load Quote ────────────────────────────────────────────────────────────────

async function loadQuote() {
  const quoteNumber = $('quote-input').value.trim();
  if (!quoteNumber) {
    showError('quote-error', 'Please enter a quote number.');
    return;
  }

  hideEl('quote-error');
  setLoading('load-btn', 'load-spinner', 'load-btn-text', true, 'Load Quote');

  try {
    const res = await fetch(`${API_BASE}/api/load-quote`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quote_number: quoteNumber })
    });

    const data = await res.json();

    if (!res.ok) {
      showError('quote-error', data.detail || 'Failed to load quote.');
      return;
    }

    state.quoteLoaded = true;
    state.quoteNumber = quoteNumber;
    renderConfigSummary(data);
    showSessionBadge(quoteNumber);

  } catch (err) {
    showError('quote-error', 'Network error — is the backend running?');
  } finally {
    setLoading('load-btn', 'load-spinner', 'load-btn-text', false, 'Load Quote');
  }
}

// ─── Render Config Summary ─────────────────────────────────────────────────────

const SECTION_LABELS = {
  profile:        { label: 'Appliance Profile',    icon: '🖥️' },
  compute:        { label: 'Compute (CPU/RAM)',     icon: '⚡' },
  storage_media:  { label: 'Storage Media',         icon: '💾' },
  storage_config: { label: 'RAID & Storage Config', icon: '🔧' },
  network:        { label: 'Network',               icon: '🌐' },
  veeam:          { label: 'Veeam',                 icon: '📦' },
  environment:    { label: 'Environment',           icon: '🌡️' },
};

const ALL_SECTIONS = Object.keys(SECTION_LABELS);

function renderConfigSummary(data) {
  const loaded = new Set(data.sections_loaded || []);

  $('quote-number-badge').textContent = `Quote #${data.quote_number}`;

  const grid = $('sections-grid');
  grid.innerHTML = ALL_SECTIONS.map(key => {
    const { label, icon } = SECTION_LABELS[key];
    const isLoaded = loaded.has(key);
    return `
      <div class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${
        isLoaded
          ? 'bg-green-50 border border-green-200 text-green-800'
          : 'bg-slate-50 border border-slate-200 text-slate-400'
      }">
        <span>${icon}</span>
        <span class="font-medium truncate">${label}</span>
        <span class="ml-auto">${isLoaded ? '✓' : '—'}</span>
      </div>
    `;
  }).join('');

  showEl('config-summary-section');
}

// ─── Session Badge ─────────────────────────────────────────────────────────────

function showSessionBadge(quoteNumber) {
  setText('session-quote-label', `Quote #${quoteNumber}`);
  $('session-badge').classList.remove('hidden');
  $('session-badge').classList.add('flex');
}

function hideSessionBadge() {
  $('session-badge').classList.add('hidden');
  $('session-badge').classList.remove('flex');
}

// ─── Clear Session ─────────────────────────────────────────────────────────────

async function clearSession() {
  try {
    await fetch(`${API_BASE}/api/clear`, { method: 'POST' });
  } catch (_) { /* best effort */ }

  state.quoteLoaded = false;
  state.quoteNumber = null;
  state.activeQuestionId = null;

  $('quote-input').value = '';
  hideEl('config-summary-section');
  hideEl('response-section');
  hideEl('quote-error');
  hideSessionBadge();

  // Deactivate all question buttons
  document.querySelectorAll('.q-btn').forEach(btn => {
    btn.classList.remove('q-btn-active');
    btn.classList.add('q-btn-inactive');
  });
}

// ─── Load Question List ────────────────────────────────────────────────────────

async function loadQuestionList() {
  try {
    const res = await fetch(`${API_BASE}/api/questions`);
    const data = await res.json();
    renderQuestionGrid(data.questions);
  } catch (err) {
    setHTML('questions-grid', '<div class="col-span-full text-sm text-red-500">Failed to load questions. Is the backend running?</div>');
  }
}

function renderQuestionGrid(questions) {
  const grid = $('questions-grid');
  grid.innerHTML = questions.map(q => `
    <button
      class="q-btn q-btn-inactive text-left px-4 py-3 rounded-lg border text-sm transition-all"
      data-id="${q.id}"
      onclick="askPreselected(${q.id}, this)"
    >
      <span class="font-semibold text-brand-700 mr-2">Q${q.id}.</span>
      <span>${q.text}</span>
    </button>
  `).join('');
}

// ─── Ask Pre-selected Question ─────────────────────────────────────────────────

async function askPreselected(questionId, buttonEl) {
  if (!state.quoteLoaded) {
    scrollToQuoteInput();
    showError('quote-error', 'Load a quote first before asking questions.');
    return;
  }

  // Highlight active button
  document.querySelectorAll('.q-btn').forEach(btn => {
    btn.classList.remove('q-btn-active');
    btn.classList.add('q-btn-inactive');
  });
  buttonEl.classList.remove('q-btn-inactive');
  buttonEl.classList.add('q-btn-active');

  state.activeQuestionId = questionId;

  // Get question text from button
  const questionText = buttonEl.querySelector('span:last-child').textContent;
  showResponseLoading(questionText, 'A');

  try {
    const res = await fetch(`${API_BASE}/api/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question_id: questionId })
    });

    const data = await res.json();

    if (!res.ok) {
      showResponseError(data.detail || 'Failed to get a response.');
      return;
    }

    renderResponse(data);

  } catch (err) {
    showResponseError('Network error — is the backend running?');
  }
}

// ─── Ask Custom Question ────────────────────────────────────────────────────────

async function askCustom() {
  const question = $('custom-input').value.trim();

  if (!question) {
    $('custom-input').focus();
    return;
  }

  if (!state.quoteLoaded) {
    scrollToQuoteInput();
    showError('quote-error', 'Load a quote first before asking questions.');
    return;
  }

  // Deactivate pre-selected buttons
  document.querySelectorAll('.q-btn').forEach(btn => {
    btn.classList.remove('q-btn-active');
    btn.classList.add('q-btn-inactive');
  });

  setLoading('custom-btn', 'custom-spinner', 'custom-btn-text', true, 'Ask Custom Question');
  showResponseLoading(question, 'B');

  try {
    const res = await fetch(`${API_BASE}/api/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ custom_question: question })
    });

    const data = await res.json();

    if (!res.ok) {
      showResponseError(data.detail || 'Failed to get a response.');
      return;
    }

    renderResponse(data);

  } catch (err) {
    showResponseError('Network error — is the backend running?');
  } finally {
    setLoading('custom-btn', 'custom-spinner', 'custom-btn-text', false, 'Ask Custom Question');
  }
}

// ─── Response Rendering ────────────────────────────────────────────────────────

function showResponseLoading(questionText, category) {
  showEl('response-section');
  hideEl('response-error');
  setHTML('response-body', '');
  setHTML('calibration-warnings', '');
  hideEl('calibration-warnings');

  setCategoryBadge(category);
  setText('response-question', questionText);
  showEl('response-loading-badge');

  $('response-section').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function renderResponse(data) {
  hideEl('response-loading-badge');
  setCategoryBadge(data.category);
  setText('response-question', data.question);

  // Calibration warnings
  const warnings = data.calibration_warnings || [];
  if (warnings.length > 0) {
    const warningsHTML = warnings.map(w => `
      <div class="flex gap-2 text-sm bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-4 py-2.5">
        <span class="shrink-0">⚠️</span>
        <span>${escapeHtml(w)}</span>
      </div>
    `).join('');
    setHTML('calibration-warnings', warningsHTML);
    showEl('calibration-warnings');
  }

  // Format response text — convert markdown-like sections to styled HTML
  setHTML('response-body', formatResponse(data.response));
}

function showResponseError(message) {
  hideEl('response-loading-badge');
  setHTML('response-body', '');
  hideEl('calibration-warnings');
  setText('response-error', message);
  showEl('response-error');
}

function setCategoryBadge(category) {
  const badge = $('response-category-badge');
  if (category === 'A') {
    badge.textContent = 'Category A — High Confidence';
    badge.className = 'text-xs font-semibold px-2.5 py-0.5 rounded-full bg-green-100 text-green-800 border border-green-200';
  } else {
    badge.textContent = 'Category B — Medium Confidence';
    badge.className = 'text-xs font-semibold px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-200';
  }
}

// ─── Response Formatter ────────────────────────────────────────────────────────
// Converts the plain-text structured response from Claude into readable HTML.

function formatResponse(text) {
  if (!text) return '';

  // Escape HTML first
  let html = escapeHtml(text);

  // Section headers: lines in ALL CAPS or starting with ## → styled header
  html = html.replace(/^(#{1,3}\s+.+)$/gm, (match, heading) => {
    const clean = heading.replace(/^#+\s+/, '');
    return `<h4 class="response-heading">${clean}</h4>`;
  });

  // Bold: **text**
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // Bullet points: lines starting with - or •
  html = html.replace(/^[-•]\s+(.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/gs, (match) => `<ul class="response-list">${match}</ul>`);

  // Numbered lists: lines starting with 1. 2. etc
  html = html.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');

  // CONFIDENCE LEVEL line — highlight
  html = html.replace(
    /(CONFIDENCE(?: LEVEL)?:?\s*)(High|Medium|Low)/gi,
    (_, prefix, level) => {
      const colors = {
        high:   'confidence-high',
        medium: 'confidence-medium',
        low:    'confidence-low',
      };
      const cls = colors[level.toLowerCase()] || '';
      return `<span class="confidence-label ${cls}">${prefix}${level}</span>`;
    }
  );

  // Paragraph breaks: double newlines
  html = html.replace(/\n\n+/g, '</p><p class="response-para">');
  html = `<p class="response-para">${html}</p>`;

  // Single newlines to <br> inside paragraphs
  html = html.replace(/(?<!>)\n(?!<)/g, '<br>');

  return html;
}

// ─── Utilities ─────────────────────────────────────────────────────────────────

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function showError(elementId, message) {
  setText(elementId, message);
  showEl(elementId);
}

function scrollToQuoteInput() {
  $('quote-input').scrollIntoView({ behavior: 'smooth', block: 'center' });
  $('quote-input').focus();
}
