/* FinSight AI — app orchestration: state, data loading, rendering, event wiring.
   Talks only to the REST API (via api.js) and Chart.js (via charts.js) — no
   framework, no build step, per docs/architecture.md's stated UI stack. */

const CATEGORY_TAXONOMY = [
  "Food", "Transport", "Shopping", "Bills", "Salary",
  "Rent", "Entertainment", "Healthcare", "Education", "Other",
];

const state = {
  // Phase 7.3: there is no user-id input anymore — the acting user is whoever
  // the stored JWT (see getSession()) says it is. accountId remains a plain
  // client-side filter (still always ANDed with the token's user server-side).
  accountId: 2,
  txn: { limit: 10, offset: 0, total: 0, filters: {} },
  conversationId: null,
};

// ---------- utilities ----------

function toast(message, type = "success") {
  const root = document.getElementById("toast-root");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  root.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

// Escapes both HTML-content and HTML-attribute contexts (quotes included) — used
// for any string that ultimately originates from user-controlled data (CSV
// upload content, account email, typed chat text) before it's inserted via
// innerHTML. AI-generated text has its own escaping in renderMarkdownLite below;
// this covers everywhere else.
function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function fmtMoney(v) { return Charts.money(v); }
function fmtPct(v) { return v === null || v === undefined ? "—" : (v * 100).toFixed(1) + "%"; }

function renderDelta(elId, current, previous, higherIsBetter = true) {
  const el = document.getElementById(elId);
  if (previous === undefined || previous === null || previous === 0 || current === undefined) {
    el.textContent = "";
    el.className = "stat-delta";
    return;
  }
  const diff = current - previous;
  const pct = (diff / Math.abs(previous)) * 100;
  const isUp = diff > 0;
  const good = higherIsBetter ? isUp : !isUp;
  el.className = "stat-delta " + (diff === 0 ? "flat" : good ? "up" : "down");
  const arrow = diff === 0 ? "→" : isUp ? "↑" : "↓";
  el.textContent = `${arrow} ${Math.abs(pct).toFixed(1)}% vs last month`;
}

function renderMarkdownLite(text) {
  if (!text) return "";
  const escaped = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const withBold = escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  const lines = withBold.split("\n");
  let html = "";
  let inList = false;
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      if (!inList) { html += "<ul style='margin:6px 0;padding-left:18px'>"; inList = true; }
      html += `<li>${trimmed.slice(2)}</li>`;
    } else {
      if (inList) { html += "</ul>"; inList = false; }
      html += trimmed ? `<p style="margin:6px 0">${trimmed}</p>` : "";
    }
  }
  if (inList) html += "</ul>";
  return html;
}

// ---------- theme ----------

function initTheme() {
  const saved = localStorage.getItem("finsight-theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
}

document.getElementById("theme-toggle").addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", current);
  localStorage.setItem("finsight-theme", current);
  // Re-render charts so Chart.js picks up the new CSS custom property values.
  loadTrendAndForecast();
  loadCategoryChart();
  loadMerchantsChart();
});

// ---------- health ----------

async function checkHealth() {
  const dot = document.getElementById("db-dot");
  const text = document.getElementById("db-status-text");
  try {
    const res = await Api.healthDb();
    if (res.database === "up") {
      dot.className = "status-dot ok";
      text.textContent = "API connected";
    } else {
      dot.className = "status-dot down";
      text.textContent = "DB down";
    }
  } catch (e) {
    dot.className = "status-dot down";
    text.textContent = "API unreachable";
  }
}

// ---------- KPI + trend + forecast ----------

async function loadSummary() {
  try {
    const [summary, monthly] = await Promise.all([
      Api.summary({ account_id: state.accountId }),
      Api.monthlyTrends({ account_id: state.accountId }),
    ]);
    document.getElementById("stat-income").textContent = fmtMoney(summary.total_income);
    document.getElementById("stat-expenses").textContent = fmtMoney(summary.total_expenses);
    document.getElementById("stat-savings").textContent = fmtMoney(summary.savings);
    document.getElementById("stat-rate").textContent = fmtPct(summary.savings_rate);
    document.getElementById("stat-rate-sub").textContent = `${summary.transaction_count} transactions`;
    document.getElementById("stat-rate-sub").className = "stat-delta flat";

    const items = monthly.items || [];
    if (items.length >= 2) {
      const last = items[items.length - 1];
      const prev = items[items.length - 2];
      renderDelta("stat-income-delta", Number(last.income), Number(prev.income), true);
      renderDelta("stat-expenses-delta", Number(last.expenses), Number(prev.expenses), false);
      renderDelta("stat-savings-delta", Number(last.savings), Number(prev.savings), true);
    }
  } catch (e) {
    toast("Failed to load summary: " + e.message, "error");
  }
}

async function loadTrendAndForecast() {
  try {
    const [monthly, forecast] = await Promise.all([
      Api.monthlyTrends({ account_id: state.accountId }),
      Api.forecast({ account_id: state.accountId, periods_ahead: 1 }),
    ]);
    Charts.renderTrendChart("trend-chart", "trend-legend", monthly.items || [], forecast);

    const methodLabels = {
      linear_regression: "Linear trend",
      moving_average: "Moving average",
      naive_last_month: "Naive (last month)",
      insufficient_data: "Insufficient data",
    };
    document.getElementById("forecast-method").textContent = methodLabels[forecast.method] || forecast.method;

    const body = document.getElementById("forecast-body");
    if (!forecast.forecast || !forecast.forecast.length) {
      body.innerHTML = `<div class="empty-state">${forecast.explanation || "No forecast available."}</div>`;
    } else {
      const rows = forecast.forecast
        .map((f) => `<div class="list-row"><div class="primary">${f.period}</div><div class="amount">${fmtMoney(f.predicted_expenses)}</div></div>`)
        .join("");
      const stats = forecast.slope !== null && forecast.slope !== undefined
        ? `<div class="card-subtitle" style="margin-top:8px;">Slope ${fmtMoney(forecast.slope)}/mo · R² ${forecast.r_squared}</div>`
        : "";
      body.innerHTML = `<div class="item-list">${rows}</div>${stats}<p style="font-size:12.5px;color:var(--text-secondary);margin-top:10px;">${forecast.explanation}</p>`;
    }
  } catch (e) {
    toast("Failed to load forecast: " + e.message, "error");
  }
}

// ---------- category + merchants charts ----------

async function loadCategoryChart() {
  try {
    const res = await Api.spendingByCategory({ account_id: state.accountId });
    Charts.renderCategoryChart("category-chart", res.items || []);
    populateCategoryFilter(res.items || []);
  } catch (e) {
    toast("Failed to load category breakdown: " + e.message, "error");
  }
}

async function loadMerchantsChart() {
  try {
    const res = await Api.topMerchants({ account_id: state.accountId, limit: 8 });
    Charts.renderMerchantsChart("merchants-chart", res.items || []);
  } catch (e) {
    toast("Failed to load top merchants: " + e.message, "error");
  }
}

function populateCategoryFilter() {
  const select = document.getElementById("filter-category");
  const current = select.value;
  select.innerHTML = '<option value="">All categories</option>' +
    CATEGORY_TAXONOMY.map((c) => `<option value="${c}">${c}</option>`).join("");
  select.value = current;
}

// ---------- recurring + anomalies ----------

async function loadRecurring() {
  const list = document.getElementById("recurring-list");
  try {
    const res = await Api.recurringList();
    const items = res.items || [];
    if (!items.length) {
      list.innerHTML = '<div class="empty-state">No recurring payments detected yet — click Detect.</div>';
      return;
    }
    list.innerHTML = items
      .map(
        (r) => `<div class="list-row">
          <div><div class="primary">${escapeHtml(r.merchant)}</div><div class="secondary">every ~${r.interval_days} days · last seen ${r.last_seen}</div></div>
          <div class="amount">${fmtMoney(r.avg_amount)}</div>
        </div>`
      )
      .join("");
  } catch (e) {
    list.innerHTML = '<div class="empty-state">Failed to load recurring payments.</div>';
  }
}

async function loadAnomalies() {
  const list = document.getElementById("anomalies-list");
  try {
    const res = await Api.anomalies({ account_id: state.accountId });
    const items = res.items || [];
    if (!items.length) {
      list.innerHTML = '<div class="empty-state">No anomalies detected — spending looks consistent.</div>';
      return;
    }
    list.innerHTML = items
      .map((a) => {
        const badge = Math.abs(a.z_score) > 10 ? "critical" : "warning";
        return `<div class="list-row">
          <div><div class="primary">${escapeHtml(a.description_raw)}</div><div class="secondary">${escapeHtml(a.category)} · ${a.transaction_date}</div></div>
          <div style="text-align:right"><div class="amount">${fmtMoney(a.amount)}</div>
          <span class="badge badge-${badge}">z ${a.z_score}</span></div>
        </div>`;
      })
      .join("");
  } catch (e) {
    list.innerHTML = '<div class="empty-state">Failed to load anomalies.</div>';
  }
}

// ---------- transactions table ----------

async function loadTransactions() {
  const tbody = document.getElementById("txn-tbody");
  try {
    const params = {
      account_id: state.accountId,
      limit: state.txn.limit,
      offset: state.txn.offset,
      ...state.txn.filters,
    };
    const res = await Api.listTransactions(params);
    state.txn.total = res.total;
    const items = res.items || [];

    document.getElementById("txn-count-subtitle").textContent = `${res.total} total`;

    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No transactions match these filters.</td></tr>';
    } else {
      tbody.innerHTML = items.map(renderTxnRow).join("");
      wireRowHandlers();
    }

    const from = res.total === 0 ? 0 : state.txn.offset + 1;
    const to = Math.min(state.txn.offset + state.txn.limit, res.total);
    document.getElementById("pagination-summary").textContent = `${from}–${to} of ${res.total}`;
    document.getElementById("prev-page-btn").disabled = state.txn.offset === 0;
    document.getElementById("next-page-btn").disabled = to >= res.total;
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-state">Failed to load transactions: ${escapeHtml(e.message)}</td></tr>`;
  }
}

function renderTxnRow(t) {
  const catOptions = CATEGORY_TAXONOMY
    .map((c) => `<option value="${c}" ${c === t.category ? "selected" : ""}>${c}</option>`)
    .join("");
  const amountClass = t.transaction_type === "DEBIT" ? "debit" : "credit";
  const sign = t.transaction_type === "DEBIT" ? "−" : "+";
  const reviewBadge = t.needs_review
    ? '<span class="badge badge-warning">Review</span>'
    : '<span class="badge badge-good">OK</span>';
  const descriptionRaw = escapeHtml(t.description_raw);
  const descriptionShort = escapeHtml((t.description_clean || t.description_raw).slice(0, 32));
  const merchant = escapeHtml(t.merchant) || "—";
  return `<tr data-id="${t.id}">
    <td>${t.transaction_date}</td>
    <td title="${descriptionRaw}">${descriptionShort}</td>
    <td>${merchant}</td>
    <td><select class="cat-select" data-id="${t.id}">${catOptions}</select></td>
    <td class="amount ${amountClass}">${sign}${fmtMoney(t.amount)}</td>
    <td>${t.transaction_type}</td>
    <td>${reviewBadge}</td>
    <td><button class="row-delete" data-id="${t.id}" title="Delete">✕</button></td>
  </tr>`;
}

function wireRowHandlers() {
  document.querySelectorAll(".cat-select").forEach((sel) => {
    sel.addEventListener("change", async (e) => {
      const id = e.target.dataset.id;
      try {
        await Api.correctCategory(id, e.target.value);
        toast(`Transaction #${id} recategorized to ${e.target.value}`);
        loadCategoryChart();
      } catch (err) {
        toast("Failed to update category: " + err.message, "error");
      }
    });
  });
  document.querySelectorAll(".row-delete").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      const id = e.target.dataset.id;
      if (!confirm(`Delete transaction #${id}? This cannot be undone.`)) return;
      try {
        await Api.deleteTransaction(id);
        toast(`Transaction #${id} deleted`);
        loadTransactions();
        loadSummary();
      } catch (err) {
        toast("Failed to delete: " + err.message, "error");
      }
    });
  });
}

function readFilters() {
  const category = document.getElementById("filter-category").value;
  const transaction_type = document.getElementById("filter-type").value;
  const needs_review = document.getElementById("filter-review").value;
  const date_from = document.getElementById("filter-date-from").value;
  const date_to = document.getElementById("filter-date-to").value;
  state.txn.filters = { category, transaction_type, needs_review, date_from, date_to };
  state.txn.offset = 0;
}

document.getElementById("filter-apply-btn").addEventListener("click", () => { readFilters(); loadTransactions(); });
document.getElementById("filter-clear-btn").addEventListener("click", () => {
  document.getElementById("filter-category").value = "";
  document.getElementById("filter-type").value = "";
  document.getElementById("filter-review").value = "";
  document.getElementById("filter-date-from").value = "";
  document.getElementById("filter-date-to").value = "";
  state.txn.filters = {};
  state.txn.offset = 0;
  loadTransactions();
});
document.getElementById("prev-page-btn").addEventListener("click", () => {
  state.txn.offset = Math.max(0, state.txn.offset - state.txn.limit);
  loadTransactions();
});
document.getElementById("next-page-btn").addEventListener("click", () => {
  state.txn.offset += state.txn.limit;
  loadTransactions();
});

// ---------- upload / pipeline / tools ----------

let selectedFile = null;

document.getElementById("csv-input").addEventListener("change", (e) => {
  selectedFile = e.target.files[0] || null;
  document.getElementById("upload-label").textContent = selectedFile ? selectedFile.name : "Click to choose a CSV, or drag one here";
});

const dropZone = document.getElementById("upload-drop");
["dragover", "dragleave", "drop"].forEach((evt) => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.toggle("dragover", evt === "dragover");
  });
});
dropZone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) {
    selectedFile = file;
    document.getElementById("upload-label").textContent = file.name;
  }
});

document.getElementById("run-pipeline-btn").addEventListener("click", async () => {
  if (!selectedFile) { toast("Choose a CSV file first", "error"); return; }
  const currency = document.getElementById("currency-input").value || "INR";
  const resultBox = document.getElementById("pipeline-result");
  resultBox.classList.add("visible");
  resultBox.innerHTML = "Running pipeline…";
  try {
    const res = await Api.runPipeline(selectedFile, state.accountId, currency);
    resultBox.innerHTML = `<dl>
      <dt>Rows processed</dt><dd>${res.rows_processed}</dd>
      <dt>Inserted</dt><dd>${res.inserted}</dd>
      <dt>Skipped duplicates</dt><dd>${res.skipped_duplicates}</dd>
      <dt>Failed</dt><dd>${res.failed}</dd>
      <dt>Merchants cleaned</dt><dd>${res.merchants_cleaned}</dd>
      <dt>Rows categorized</dt><dd>${res.rows_categorized}</dd>
      <dt>ML updated</dt><dd>${res.ml_updated} / ${res.ml_candidates}</dd>
    </dl>`;
    toast(`Pipeline complete: ${res.inserted} inserted, ${res.failed} failed`);
    reloadAll();
  } catch (e) {
    resultBox.innerHTML = `Pipeline failed: ${escapeHtml(e.message)}`;
    toast("Pipeline failed: " + e.message, "error");
  }
});

document.getElementById("detect-recurring-btn").addEventListener("click", async () => {
  try {
    await Api.recurringDetect();
    toast("Recurring payments detected");
    loadRecurring();
  } catch (e) { toast("Detection failed: " + e.message, "error"); }
});

document.getElementById("tool-snapshots").addEventListener("click", async () => {
  try {
    const res = await Api.snapshotsGenerate();
    toast(`Generated ${res.items.length} monthly snapshot(s)`);
  } catch (e) { toast("Snapshot generation failed: " + e.message, "error"); }
});

document.getElementById("tool-train-ml").addEventListener("click", async () => {
  try {
    const res = await Api.mlTrain();
    toast(res.trained ? `Trained on ${res.training_rows} rows (holdout acc ${res.holdout_accuracy ? (res.holdout_accuracy * 100).toFixed(1) + "%" : "n/a"})` : res.message, res.trained ? "success" : "error");
  } catch (e) { toast("Training failed: " + e.message, "error"); }
});

document.getElementById("tool-apply-ml").addEventListener("click", async () => {
  try {
    const res = await Api.mlApply();
    toast(res.message);
    loadTransactions();
  } catch (e) { toast("ML apply failed: " + e.message, "error"); }
});

document.getElementById("tool-clean").addEventListener("click", async () => {
  try {
    const res = await Api.cleanMerchants();
    toast(`Cleaned ${res.updated} merchant name(s)`);
    loadTransactions();
  } catch (e) { toast("Cleaning failed: " + e.message, "error"); }
});

// ---------- overview AI insight (small teaser; full analysis lives in Ask FinSight) ----------

function extractInsightTeaser(text) {
  // Flatten headers/bullets/newlines into one line first, so a short markdown
  // header ("**Financial Summary**") merges with the real sentence that follows
  // it instead of being returned alone as a useless teaser.
  const clean = text
    .replace(/\*\*/g, "")
    .replace(/^#+\s*/gm, "")
    .replace(/^[-*]\s+/gm, "")
    .replace(/\s*\n\s*/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
  const sentences = clean.split(/(?<=[.!?])\s+/).filter((s) => s.trim().length > 20);
  let teaser = sentences[0] || clean;
  if (sentences[1] && (teaser + " " + sentences[1]).length < 200) teaser += " " + sentences[1];
  return teaser.length > 220 ? teaser.slice(0, 217) + "…" : teaser;
}

document.getElementById("overview-insight-btn").addEventListener("click", async (e) => {
  const textEl = document.getElementById("overview-insight-text");
  const btn = e.currentTarget;
  btn.disabled = true;
  textEl.textContent = "Thinking…";
  try {
    const res = await Api.aiSummary();
    textEl.textContent = res.success
      ? extractInsightTeaser(res.summary)
      : `Unavailable right now: ${res.error}`;
  } catch (err) {
    textEl.textContent = "Failed to reach the AI service: " + err.message;
  } finally {
    btn.disabled = false;
  }
});

// ---------- AI summary + chat ----------

document.getElementById("ai-summary-btn").addEventListener("click", async () => {
  const body = document.getElementById("ai-summary-body");
  body.innerHTML = '<div class="skeleton">Asking the AI analyst… (grounded in the verified data above)</div>';
  try {
    const res = await Api.aiSummary();
    if (res.success) {
      body.innerHTML = `<div class="ai-summary-text">${renderMarkdownLite(res.summary)}</div>`;
    } else {
      body.innerHTML = `<div class="empty-state">AI summary unavailable: ${escapeHtml(res.error)}</div>`;
    }
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Failed to reach AI service: ${escapeHtml(e.message)}</div>`;
  }
});

// `text` may be user-typed (chat input) or a server/AI error string — never
// trusted HTML. Only the "assistant" class goes through renderMarkdownLite,
// which escapes first and then applies a small, fixed set of markdown
// transforms; every other class is set via textContent, which can't execute
// markup no matter what it contains.
function appendChatBubble(text, cls) {
  const win = document.getElementById("chat-window");
  const el = document.createElement("div");
  el.className = `chat-bubble ${cls}`;
  if (cls === "assistant") {
    el.innerHTML = renderMarkdownLite(text);
  } else {
    el.textContent = text;
  }
  win.appendChild(el);
  win.scrollTop = win.scrollHeight;
  return el;
}

// Separate from appendChatBubble on purpose: this HTML is a fixed literal this
// file authors itself, never user/API data, so it's fine to set via innerHTML
// directly — mixing that with the untrusted-text path above is exactly the
// kind of ambiguity that causes XSS bugs.
function appendTypingIndicator() {
  const win = document.getElementById("chat-window");
  const el = document.createElement("div");
  el.className = "chat-bubble assistant";
  el.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';
  win.appendChild(el);
  win.scrollTop = win.scrollHeight;
  return el;
}

async function sendChat() {
  const input = document.getElementById("chat-input");
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  appendChatBubble(question, "user");
  const typing = appendTypingIndicator();

  try {
    const res = await Api.chat(state.conversationId, question);
    typing.remove();
    if (res.success) {
      state.conversationId = res.conversation_id;
      appendChatBubble(res.reply, "assistant");
    } else {
      appendChatBubble(res.error || "The AI service returned an error.", "error");
    }
  } catch (e) {
    typing.remove();
    appendChatBubble(e.message, "error");
  }
}

document.getElementById("chat-send-btn").addEventListener("click", sendChat);
document.getElementById("chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });

// ---------- global reload ----------

function reloadAll() {
  loadSummary();
  loadTrendAndForecast();
  loadCategoryChart();
  loadMerchantsChart();
  loadRecurring();
  loadAnomalies();
  loadTransactions();
  checkHealth();
}

document.getElementById("reload-btn").addEventListener("click", () => {
  state.accountId = Number(document.getElementById("account-id-input").value) || 2;
  state.txn.offset = 0;
  state.conversationId = null;
  reloadAll();
});

// ---------- session (Phase 7.1 auth pages: login.html / signup.html) ----------
// The dashboard requires a signed-in session (see enforceAuthGate below): an
// unauthenticated visitor is redirected to login.html before any dashboard UI
// or data loads. Phase 7.3 made this a *real* security boundary, not just a
// navigation convenience: every API call now carries the stored JWT (see
// api.js's authHeaders()), and the backend derives the acting user from that
// token — there is no user_id parameter left to pass, client-side or
// otherwise (see app/api/transactions.py's module docstring).

function getSession() {
  const token = localStorage.getItem("finsight-token");
  const userId = localStorage.getItem("finsight-user-id");
  if (!token || !userId) return null;
  return {
    token,
    userId: Number(userId),
    accountId: localStorage.getItem("finsight-account-id"),
    email: localStorage.getItem("finsight-email") || "",
  };
}

function clearSession() {
  ["finsight-token", "finsight-user-id", "finsight-account-id", "finsight-email"].forEach((k) =>
    localStorage.removeItem(k)
  );
}

function renderAccountStatus() {
  const el = document.getElementById("account-status");
  const session = getSession();
  if (session) {
    const email = escapeHtml(session.email);
    el.innerHTML = `
      <span class="account-status-email" title="${email}">${email}</span>
      <div class="account-status-links"><button id="logout-btn">Log out</button></div>
    `;
    document.getElementById("logout-btn").addEventListener("click", () => {
      clearSession();
      window.location.href = "login.html";
    });
  } else {
    el.innerHTML = `
      <div class="account-status-links"><a href="login.html">Log in</a><a href="signup.html">Sign up</a></div>
    `;
  }
}

function applySessionToFields() {
  const session = getSession();
  if (!session || !session.accountId) return;
  document.getElementById("account-id-input").value = session.accountId;
  state.accountId = Number(session.accountId);
}

// ---------- auth gate ----------

async function enforceAuthGate() {
  const session = getSession();
  if (!session) {
    window.location.href = "login.html";
    return false;
  }
  try {
    // Verify the token server-side rather than trusting localStorage presence
    // alone — an expired or tampered token must also bounce to login. Api.me()
    // reads the token from localStorage itself (same as every other call).
    await Api.me();
    return true;
  } catch (err) {
    clearSession();
    window.location.href = "login.html";
    return false;
  }
}

// ---------- boot ----------

async function boot() {
  initTheme();
  const authenticated = await enforceAuthGate();
  if (!authenticated) return; // redirect already in flight; don't render/load anything
  document.documentElement.classList.remove("auth-checking");
  renderAccountStatus();
  applySessionToFields();
  reloadAll();
}

boot();
