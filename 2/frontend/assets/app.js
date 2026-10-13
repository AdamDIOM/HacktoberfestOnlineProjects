const app = document.getElementById("app");
const healthEl = document.getElementById("health");

let meta = {
  teams: [],
  categories: {},
  urgencies: {},
  statuses: {},
  model: "llama3.2:3b",
  org_email_domain: null,
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item) => item.msg || item).join("; ")
          : "Request failed";
    throw new Error(message);
  }
  return data;
}

function route() {
  const hash = location.hash.replace("#", "") || "/";
  document.querySelectorAll("[data-nav]").forEach((link) => {
    link.classList.toggle("active", hash.startsWith(`/${link.dataset.nav}`) || (link.dataset.nav === "submit" && hash === "/"));
  });
  if (hash.startsWith("/inbox")) {
    renderInbox();
  } else {
    renderSubmit();
  }
}

async function refreshHealth() {
  try {
    const health = await api("/api/health");
    healthEl.hidden = false;
    if (health.ollama) {
      healthEl.className = "health ok";
      healthEl.textContent = `Ollama · ${health.model}`;
    } else {
      healthEl.className = "health bad";
      healthEl.textContent = health.ok
        ? `Ollama up, missing ${health.model}`
        : "Ollama offline — requests still save";
    }
  } catch {
    healthEl.hidden = false;
    healthEl.className = "health bad";
    healthEl.textContent = "API unreachable";
  }
}

function fillSelect(select, entries, placeholder) {
  const extra = placeholder ? `<option value="">${placeholder}</option>` : "";
  select.innerHTML =
    extra +
    Object.entries(entries)
      .map(([value, label]) => `<option value="${value}">${label}</option>`)
      .join("");
}

function renderSubmit() {
  app.innerHTML = document.getElementById("tpl-submit").innerHTML;
  const teamSelect = app.querySelector("[name=team]");
  teamSelect.innerHTML = meta.teams.map((team) => `<option>${team}</option>`).join("");
  const hint = document.getElementById("submit-hint");
  hint.textContent = `Classification usually takes a few seconds on ${meta.model}.`;
  if (meta.org_email_domain) {
    app.querySelector("[name=requester_email]").placeholder = `you@${meta.org_email_domain}`;
  }
  document.getElementById("submit-form").addEventListener("submit", onSubmit);
}

async function onSubmit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = document.getElementById("submit-btn");
  const errorEl = document.getElementById("form-error");
  const resultEl = document.getElementById("submit-result");
  errorEl.hidden = true;
  button.disabled = true;
  button.textContent = "Classifying…";
  const payload = Object.fromEntries(new FormData(form).entries());
  try {
    const record = await api("/api/requests", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    resultEl.hidden = false;
    resultEl.innerHTML = ticketHtml(record, { compact: true });
    form.reset();
  } catch (error) {
    errorEl.hidden = false;
    errorEl.textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Send to IT";
  }
}

async function renderInbox() {
  app.innerHTML = document.getElementById("tpl-inbox").innerHTML;
  fillSelect(document.getElementById("filter-urgency"), meta.urgencies, "All urgency");
  fillSelect(document.getElementById("filter-category"), meta.categories, "All types");
  fillSelect(document.getElementById("filter-status"), meta.statuses, "All status");
  ["search", "filter-urgency", "filter-category", "filter-status"].forEach((id) => {
    document.getElementById(id).addEventListener("input", loadQueue);
    document.getElementById(id).addEventListener("change", loadQueue);
  });
  await Promise.all([loadStats(), loadQueue()]);
}

async function loadStats() {
  const stats = await api("/api/stats");
  const critical = stats.by_urgency.critical || 0;
  const high = stats.by_urgency.high || 0;
  document.getElementById("stats").innerHTML = `
    <div class="stat"><b>${stats.open}</b><span>Open</span></div>
    <div class="stat"><b>${critical}</b><span>Critical</span></div>
    <div class="stat"><b>${high}</b><span>High</span></div>
    <div class="stat"><b>${stats.total}</b><span>All time</span></div>
  `;
}

async function loadQueue() {
  const params = new URLSearchParams();
  const q = document.getElementById("search").value.trim();
  const urgency = document.getElementById("filter-urgency").value;
  const category = document.getElementById("filter-category").value;
  const status = document.getElementById("filter-status").value;
  if (q) params.set("q", q);
  if (urgency) params.set("urgency", urgency);
  if (category) params.set("category", category);
  if (status) params.set("status", status);
  const items = await api(`/api/requests?${params.toString()}`);
  const queue = document.getElementById("queue");
  if (!items.length) {
    queue.innerHTML = `<p class="empty">No requests match these filters.</p>`;
    return;
  }
  queue.innerHTML = items.map((item) => `<article class="card ticket-wrap">${ticketHtml(item)}</article>`).join("");
  queue.querySelectorAll("[data-status]").forEach((select) => {
    select.addEventListener("change", async (event) => {
      const id = event.currentTarget.dataset.status;
      await api(`/api/requests/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: event.currentTarget.value }),
      });
      await Promise.all([loadStats(), loadQueue()]);
    });
  });
  queue.querySelectorAll("[data-reclassify]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      const id = event.currentTarget.dataset.reclassify;
      event.currentTarget.disabled = true;
      event.currentTarget.textContent = "Re-running…";
      await api(`/api/requests/${id}/reclassify`, { method: "POST" });
      await loadQueue();
    });
  });
}

function ticketHtml(record, { compact = false } = {}) {
  const urgency = record.urgency || "unclassified";
  const urgencyLabel = meta.urgencies[urgency] || "Unclassified";
  const categoryLabel = meta.categories[record.category] || "Awaiting model";
  const statusOptions = Object.entries(meta.statuses)
    .map(
      ([value, label]) =>
        `<option value="${value}" ${value === record.status ? "selected" : ""}>${label}</option>`
    )
    .join("");
  const error = record.classification_error
    ? `<p class="form-error">Model note: ${escapeHtml(record.classification_error)}</p>`
    : "";
  const actions = compact
    ? `<p class="meta"><a href="#/inbox">Open in inbox</a></p>`
    : `<div class="actions">
        <select data-status="${record.id}">${statusOptions}</select>
        <button class="ghost" data-reclassify="${record.id}" type="button">Re-classify</button>
      </div>`;
  return `
    <div class="ticket">
      <div class="urgency-chip ${urgency}">
        <strong>${escapeHtml(urgencyLabel)}</strong>
        <span class="score">${record.urgency_score ?? "—"}/100</span>
      </div>
      <div>
        <h2>${escapeHtml(record.title)}</h2>
        <p class="meta">#${record.id} · ${escapeHtml(record.requester_name)} · ${escapeHtml(record.team)} · ${escapeHtml(record.requester_email)}</p>
        <div class="chips">
          <span class="cat-chip">${escapeHtml(categoryLabel)}</span>
          <span class="status-chip">${escapeHtml(meta.statuses[record.status] || record.status)}</span>
          ${record.suggested_owner ? `<span class="status-chip">Route: ${escapeHtml(record.suggested_owner)}</span>` : ""}
        </div>
        ${record.summary ? `<p class="rationale"><strong>${escapeHtml(record.summary)}</strong></p>` : ""}
        ${record.rationale ? `<p class="rationale">${escapeHtml(record.rationale)}</p>` : ""}
        ${compact ? "" : `<p class="meta">${escapeHtml(record.details)}</p><p class="meta">Impact: ${escapeHtml(record.impact)}</p>`}
        ${error}
      </div>
      ${actions}
    </div>
  `;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

window.addEventListener("hashchange", route);

(async function boot() {
  try {
    meta = { ...meta, ...(await api("/api/meta")) };
  } catch {
    /* health banner covers this */
  }
  await refreshHealth();
  route();
})();
