/* FinSight AI — thin REST client. All paths are relative so this works whether the
   page is served by frontend/serve.py's same-origin proxy (recommended — see that
   file's docstring for why) or, in the future, mounted directly by the FastAPI app
   itself. No backend behavior is assumed beyond what's documented by the routes.

   Phase 7.3: the backend now derives the acting user from a verified JWT, not a
   client-supplied user_id — every call here automatically attaches the token
   stored by login.html/signup.html (see main.js's getSession()), and none of the
   Api.* functions accept a user_id anymore (the backend no longer reads one). */

const Api = (() => {
  function qs(params) {
    const clean = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
    return clean.length ? "?" + new URLSearchParams(clean).toString() : "";
  }

  function authHeaders() {
    const token = localStorage.getItem("finsight-token");
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  async function request(path, options = {}) {
    const res = await fetch(path, {
      ...options,
      headers: { ...authHeaders(), ...(options.headers || {}) },
    });
    let body = null;
    try { body = await res.json(); } catch (_) { /* empty body */ }
    if (!res.ok) {
      // FastAPI/Pydantic validation errors (422) send `detail` as an array of
      // {msg, loc, ...} objects, not a string — surface something readable for
      // both shapes instead of "[object Object]".
      let detail = `HTTP ${res.status}`;
      if (body) {
        if (typeof body.detail === "string") detail = body.detail;
        else if (Array.isArray(body.detail)) {
          detail = body.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
        } else if (body.message) detail = body.message;
      }
      const err = new Error(detail);
      err.status = res.status;
      err.body = body;
      throw err;
    }
    return body;
  }

  const get = (path, params = {}) => request(path + qs(params));
  const post = (path, jsonBody, params = {}) =>
    request(path + qs(params), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonBody !== undefined ? JSON.stringify(jsonBody) : undefined,
    });
  const patch = (path, jsonBody) =>
    request(path, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(jsonBody),
    });
  const del = (path, params = {}) => request(path + qs(params), { method: "DELETE" });

  return {
    health: () => get("/health"),
    healthDb: () => get("/health/db"),

    summary: (p) => get("/api/v1/analytics/summary", p),
    spendingByCategory: (p) => get("/api/v1/analytics/spending-by-category", p),
    monthlyTrends: (p) => get("/api/v1/analytics/monthly-trends", p),
    topMerchants: (p) => get("/api/v1/analytics/top-merchants", p),
    forecast: (p) => get("/api/v1/analytics/forecast/expenses", p),
    anomalies: (p) => get("/api/v1/analytics/anomalies", p),
    recurringList: (p) => get("/api/v1/analytics/recurring", p),
    recurringDetect: () => post("/api/v1/analytics/recurring/detect"),
    snapshotsGenerate: () => post("/api/v1/analytics/snapshots/generate"),

    listTransactions: (p) => get("/api/v1/transactions", p),
    deleteTransaction: (id) => del(`/api/v1/transactions/${id}`),
    correctCategory: (id, newCategory) =>
      patch(`/api/v1/transactions/${id}/category`, { new_category: newCategory }),
    cleanMerchants: () => post("/api/v1/transactions/clean-merchants"),

    uploadCsv: (file, accountId, currency) => {
      const form = new FormData();
      form.append("file", file);
      form.append("account_id", accountId);
      form.append("currency", currency);
      return request("/api/v1/transactions/upload", { method: "POST", body: form });
    },
    runPipeline: (file, accountId, currency) => {
      const form = new FormData();
      form.append("file", file);
      form.append("account_id", accountId);
      form.append("currency", currency);
      return request("/api/v1/pipeline/run", { method: "POST", body: form });
    },

    mlTrain: () => post("/api/v1/ml/train"),
    mlApply: () => post("/api/v1/ml/apply"),

    aiSummary: () => get("/api/v1/ai/summary"),
    chat: (conversationId, question) =>
      post("/api/v1/ai/chat", { conversation_id: conversationId, question }),
    chatHistory: (conversationId) => get(`/api/v1/ai/chat/${conversationId}/messages`),

    signup: (email, password, currency) => post("/api/v1/auth/signup", { email, password, currency }),
    login: (email, password) => post("/api/v1/auth/login", { email, password }),
    me: () => get("/api/v1/auth/me"),
  };
})();
