const SAMPLES = [
  {
    id: "genuine",
    title: "Genuine OTP",
    note: "Synthetic. Fictional Hela Bank.",
    text: "Hela Bank says the sign-in code 482913 expires on its own. Wait, do not message anyone.",
  },
  {
    id: "scam",
    title: "Scam",
    note: "Synthetic. Fictional Hela Bank.",
    text: "Final Hela Bank warning. Return the digits 482913 or the wallet closes tonight.",
  },
  {
    id: "singlish",
    title: "Singlish scam",
    note: "Synthetic. Fictional Hela Bank.",
    text: "Hela Bank: anee account eka lock wenawa. OTP eka 482913 mama ta danna dæn. Call denna epa.",
  },
  {
    id: "sludi",
    title: "Shifted SL-UDI",
    note: "Synthetic. Fictional SL-UDI Helpdesk. Shifted sender.",
    text: "SL-UDI Helpdesk: unusual sign-in on your profile. Forward the fresh code 193847 to this desk or the login closes tonight.",
  },
];

const state = { series: "all", lastFocus: null };
const $ = (selector) => document.querySelector(selector);

function api(path) {
  const base = String(window.OTP_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
  return base + path;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function percent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return `${Math.round(Number(value) * 1000) / 10}%`;
}

function verdictTitle(verdict) {
  if (verdict === "scam") return "Scam detected";
  if (verdict === "safe") return "Safe";
  return "Unsure — held for a person";
}

async function readJson(response) {
  const text = await response.text();
  try {
    return { payload: JSON.parse(text), text };
  } catch {
    return { payload: null, text };
  }
}

function toast(message, kind) {
  const item = document.createElement("p");
  item.className = kind === "err" ? "toast toast-err" : "toast";
  item.textContent = message;
  $("[data-toasts]").append(item);
  window.setTimeout(() => item.remove(), 4200);
}

function seriesList() {
  return [
    ["mean_oov", "Unfamiliar wording", "oov_share"],
    ["mean_confidence", "Mean confidence", "mean_confidence"],
    ["unsure_share", "Unsure share", "unsure_share"],
    ["language_tv", "Language mix shift", "language_tv"],
  ];
}

async function checkMessage(text) {
  const cleaned = text.trim();
  if (!cleaned) throw new Error("Paste a message before checking it.");
  if (cleaned.length > 1000) throw new Error("A message can be at most 1000 characters.");
  let response;
  try {
    response = await fetch(api("/predict"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: cleaned, source: "ui" }),
    });
  } catch {
    throw new Error("The checker is not running. Start the API, then try again. This page will not invent a verdict.");
  }
  const { payload } = await readJson(response);
  if (!payload) throw new Error("The checker did not return a result. This page will not invent a verdict.");
  if (!response.ok) {
    const detail = payload.detail || payload.error;
    throw new Error(typeof detail === "string" ? detail : "The checker rejected that message.");
  }
  return payload;
}

async function loadHealth() {
  const response = await fetch(api("/health"));
  const { payload } = await readJson(response);
  if (!response.ok || !payload) throw new Error("The status service did not answer.");
  return payload;
}

async function loadMonitor() {
  const [statusResponse, historyResponse] = await Promise.all([
    fetch(api("/monitor/status")),
    fetch(api("/monitor/history")),
  ]);
  const statusBody = await readJson(statusResponse);
  const historyBody = await readJson(historyResponse);
  if (!statusResponse.ok || !statusBody.payload) throw new Error("Drift status is not available.");
  const history = historyBody.payload && historyResponse.ok ? historyBody.payload : { points: [], thresholds: {} };
  return { status: statusBody.payload, history };
}

async function loadQueue() {
  const response = await fetch(api("/review/queue"));
  const { payload } = await readJson(response);
  if (!response.ok || !payload) throw new Error("The review queue is not available.");
  return payload.pending || [];
}

async function labelReview(id, label) {
  const response = await fetch(api(`/review/${encodeURIComponent(id)}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
  const { payload, text } = await readJson(response);
  if (!response.ok) throw new Error((payload && payload.detail) || text || "The review was not saved.");
  return payload;
}

function reviewMessage(payload, label) {
  const fromApi = payload && (payload.message || payload.detail || payload.note);
  if (typeof fromApi === "string" && fromApi.trim()) return fromApi;
  if (label === "scam" || label === "safe") return `Saved as ${label} by the API.`;
  return "Saved by the API.";
}

function syncCount() {
  const length = $("[data-message]").value.trim().length;
  const count = $("[data-count]");
  count.textContent = `${length}/1000`;
  count.classList.toggle("is-max", length >= 1000);
}

function clearDraft() {
  const field = $("[data-message]");
  field.value = "";
  field.removeAttribute("aria-invalid");
  $("[data-result]").innerHTML = "";
  $("[data-error]").textContent = "";
  syncCount();
}

function openModal() {
  state.lastFocus = document.activeElement;
  $("[data-modal]").hidden = false;
  document.body.classList.add("modal-open");
  $("[data-modal-confirm]").focus();
}

function closeModal() {
  const modal = $("[data-modal]");
  if (modal.hidden) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
  if (state.lastFocus && typeof state.lastFocus.focus === "function") state.lastFocus.focus();
}

function setMenu(open) {
  $(".nav").classList.toggle("is-open", open);
  const toggle = $(".menu-toggle");
  toggle.setAttribute("aria-expanded", open ? "true" : "false");
  toggle.textContent = open ? "Close" : "Menu";
}

async function refreshHealth(options = {}) {
  const box = $("[data-health]");
  try {
    const health = await loadHealth();
    const score = health.evaluation ? Number(health.evaluation.test_macro_f1).toFixed(4) : "—";
    box.removeAttribute("aria-busy");
    box.innerHTML = `
      <div class="system-head">
        <p class="system-label">System: ${health.status === "ok" ? "Online" : "Model not loaded"}</p>
        <span class="live ${health.status === "ok" ? "" : "is-off"}"></span>
      </div>
      <dl class="stats">
        <div><dt>Logged checks</dt><dd>${health.logged}</dd></div>
        <div><dt>Held-out macro-F1</dt><dd>${score}</dd></div>
        <div><dt>Drift</dt><dd>${health.drift_active ? "On" : "Off"}</dd></div>
        <div><dt>Waiting for review</dt><dd>${health.pending_reviews}</dd></div>
      </dl>
      <p class="note">These numbers come from the API. This page does not invent an accuracy score.</p>
    `;
  } catch (error) {
    box.removeAttribute("aria-busy");
    box.innerHTML = `<p class="banner banner-warn">${escapeHtml(error.message)} No live totals are shown until the API answers.</p>`;
    if (options.announce) toast(error.message, "err");
  }
}

function renderResult(result) {
  const reasons = (result.reasons || []).map((reason) => `<li>${escapeHtml(reason)}</li>`).join("");
  const fallback = result.fallback ? `<p>${escapeHtml(result.fallback)}</p>` : "";
  $("[data-result]").innerHTML = `
    <article class="verdict verdict-${escapeHtml(result.verdict)}">
      <p class="badge">${verdictTitle(result.verdict)}</p>
      <p>Confidence ${percent(result.confidence)} · scam score ${percent(result.scam_prob)} · unfamiliar ${percent(result.oov_share)}</p>
      <div class="meter" aria-hidden="true"><span style="width:${Math.max(0, Math.min(1, Number(result.confidence) || 0)) * 100}%"></span></div>
      <ul>${reasons}</ul>
      <p class="warning">${escapeHtml(result.warning || "Your bank will never ask for your OTP.")}</p>
      ${fallback}
      <p class="note">Result from the checker API. Model ${escapeHtml(result.model_version || "unknown")}.</p>
    </article>
  `;
}

function renderMonitor(report) {
  const status = report.status;
  const banner = $("[data-drift]");
  banner.className = status.drift_active ? "banner banner-alert" : "banner";
  banner.textContent = status.drift_active
    ? `Drift is on. ${(status.reasons || []).join(" · ") || "The recent window moved away from training."}`
    : status.note || "Drift is off.";
  const signals = $("[data-signals]");
  signals.removeAttribute("aria-busy");
  signals.innerHTML = (status.signals || []).map((signal, index) => {
    const hint = String(signal.hint || "").trim();
    const name = escapeHtml(signal.name);
    const title = hint
      ? `<button type="button" class="tip" aria-describedby="signal-tip-${index}">${name}<span class="tip-bubble" id="signal-tip-${index}" role="tooltip">${escapeHtml(hint)}</span></button>`
      : name;
    return `
      <article class="${signal.breach ? "is-breach" : ""}">
        <h3>${title}</h3>
        <p class="figure">${percent(signal.value)}</p>
        <p>Threshold ${percent(signal.threshold)}</p>
        ${hint ? `<p class="note">${escapeHtml(hint)}</p>` : ""}
      </article>
    `;
  }).join("");
  const points = (report.history && report.history.points) || [];
  const thresholds = (report.history && report.history.thresholds) || {};
  const chosen = seriesList().filter((item) => state.series === "all" || state.series === item[0]);
  $("[data-charts]").innerHTML = chosen.map(([field, label, thresholdKey]) => {
    if (!points.length) return `<figure><figcaption>${label}</figcaption><p class="muted">No points yet.</p></figure>`;
    const path = points.map((point, index) => {
      const x = points.length === 1 ? 50 : (index / (points.length - 1)) * 100;
      const y = 100 - Math.max(0, Math.min(1, Number(point[field]) || 0)) * 100;
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    }).join(" ");
    const y = 100 - Math.max(0, Math.min(1, Number(thresholds[thresholdKey]) || 0)) * 100;
    return `<figure><figcaption>${label}</figcaption><svg viewBox="0 0 100 100" role="img" aria-label="${escapeHtml(label)}"><line class="threshold" x1="0" x2="100" y1="${y}" y2="${y}"></line><path d="${path}"></path></svg></figure>`;
  }).join("");
}

async function refreshMonitor(options = {}) {
  try {
    renderMonitor(await loadMonitor());
  } catch (error) {
    const banner = $("[data-drift]");
    banner.className = "banner banner-warn";
    banner.textContent = error.message;
    const signals = $("[data-signals]");
    signals.removeAttribute("aria-busy");
    if (!signals.querySelector("article")) signals.innerHTML = "";
    if (options.announce) toast(error.message, "err");
  }
}

function renderQueue(items) {
  const list = $("[data-queue]");
  list.removeAttribute("aria-busy");
  if (!items.length) {
    list.innerHTML = `<li><p class="muted">The queue is empty. Unsure checks appear here.</p></li>`;
    return;
  }
  list.innerHTML = items.map((item) => `
    <li>
      <p>${escapeHtml(item.text_masked)}</p>
      <p class="note">${escapeHtml(item.verdict)} · confidence ${percent(item.confidence)} · unfamiliar ${percent(item.oov_share)}</p>
      <ul>${(item.reasons || []).map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>
      <div class="row">
        <button type="button" class="primary" data-label="scam" data-id="${escapeHtml(item.id)}">Scam</button>
        <button type="button" class="ghost" data-label="safe" data-id="${escapeHtml(item.id)}">Safe</button>
      </div>
    </li>
  `).join("");
}

async function refreshQueue(options = {}) {
  try {
    renderQueue(await loadQueue());
    if (!options.keepNote) $("[data-review-note]").textContent = "";
    return true;
  } catch (error) {
    const list = $("[data-queue]");
    list.removeAttribute("aria-busy");
    list.innerHTML = `<li><p class="banner banner-warn">${escapeHtml(error.message)}</p></li>`;
    $("[data-review-note]").textContent = error.message;
    if (options.announce) toast(error.message, "err");
    return false;
  }
}

async function retrain() {
  const button = $("[data-retrain]");
  const note = $("[data-retrain-note]");
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Retraining…";
  try {
    const response = await fetch(api("/retrain"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const { payload, text } = await readJson(response);
    if (!response.ok) {
      const detail = payload && (payload.detail || payload.error || payload.message);
      throw new Error(typeof detail === "string" ? detail : (text || `Retrain failed (${response.status}).`));
    }
    const message = payload && typeof payload.message === "string"
      ? payload.message
      : (text && text.trim() ? text.trim() : "The API accepted the retrain request.");
    note.textContent = message;
    toast(message, "ok");
  } catch (error) {
    const message = error.message || "Retrain failed.";
    note.textContent = message;
    toast(message, "err");
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function bind() {
  $("[data-samples]").innerHTML = SAMPLES.map((sample) => `
    <button type="button" data-sample="${sample.id}">
      <strong>${sample.title}</strong>
      <span>${sample.note}</span>
    </button>
  `).join("");

  $("[data-samples]").addEventListener("click", (event) => {
    const button = event.target.closest("[data-sample]");
    if (!button) return;
    const sample = SAMPLES.find((item) => item.id === button.dataset.sample);
    $("[data-message]").value = sample.text;
    $("[data-message]").removeAttribute("aria-invalid");
    $("[data-error]").textContent = "";
    syncCount();
  });

  $("[data-message]").addEventListener("input", syncCount);
  $("[data-clear]").addEventListener("click", () => {
    const hasText = $("[data-message]").value.trim().length > 0;
    const hasResult = $("[data-result]").textContent.trim().length > 0;
    if (!hasText && !hasResult) {
      toast("Nothing to clear.", "ok");
      return;
    }
    openModal();
  });

  $("[data-modal]").addEventListener("click", (event) => {
    if (event.target.closest("[data-modal-confirm]")) {
      clearDraft();
      closeModal();
      toast("Message cleared.", "ok");
      return;
    }
    if (event.target.closest("[data-modal-close]")) closeModal();
  });

  $("[data-form]").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("[data-analyze]");
    const label = button.textContent;
    button.disabled = true;
    button.textContent = "Checking…";
    $("[data-scan]").hidden = false;
    $("[data-error]").textContent = "";
    try {
      const result = await checkMessage($("[data-message]").value);
      $("[data-message]").removeAttribute("aria-invalid");
      renderResult(result);
      toast(`${verdictTitle(result.verdict)}. Result from the checker.`, "ok");
      await Promise.all([refreshHealth(), refreshMonitor(), refreshQueue()]);
    } catch (error) {
      $("[data-result]").innerHTML = "";
      $("[data-error]").textContent = error.message;
      $("[data-message]").setAttribute("aria-invalid", "true");
      toast(error.message, "err");
    } finally {
      button.disabled = false;
      button.textContent = label;
      $("[data-scan]").hidden = true;
    }
  });

  $("[data-filters]").addEventListener("click", (event) => {
    const button = event.target.closest("[data-series]");
    if (!button) return;
    state.series = button.dataset.series;
    $("[data-filters]").querySelectorAll("button").forEach((item) => {
      const on = item === button;
      item.classList.toggle("is-on", on);
      item.setAttribute("aria-pressed", on ? "true" : "false");
    });
    refreshMonitor({ announce: true });
  });

  $("[data-queue]").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-label]");
    if (!button) return;
    const label = button.textContent;
    button.disabled = true;
    button.textContent = "Saving…";
    try {
      const saved = await labelReview(button.dataset.id, button.dataset.label);
      const message = reviewMessage(saved, button.dataset.label);
      toast(message, "ok");
      const reloaded = await refreshQueue({ keepNote: true });
      await refreshHealth();
      if (reloaded) $("[data-review-note]").textContent = message;
    } catch (error) {
      button.disabled = false;
      button.textContent = label;
      $("[data-review-note]").textContent = error.message;
      toast(error.message, "err");
    }
  });

  $("[data-refresh]").addEventListener("click", () => Promise.all([
    refreshHealth({ announce: true }),
    refreshMonitor({ announce: true }),
    refreshQueue({ announce: true }),
  ]));
  $("[data-retrain]").addEventListener("click", retrain);

  $(".menu-toggle").addEventListener("click", () => setMenu(!$(".nav").classList.contains("is-open")));
  $("#site-nav").addEventListener("click", (event) => {
    if (event.target.closest("a")) setMenu(false);
  });
  document.addEventListener("click", (event) => {
    if (!$(".nav").classList.contains("is-open")) return;
    if (event.target.closest(".nav")) return;
    setMenu(false);
  });
  document.addEventListener("keydown", (event) => {
    const modal = $("[data-modal]");
    if (!modal.hidden) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeModal();
        return;
      }
      if (event.key !== "Tab") return;
      const items = [...modal.querySelectorAll("button")];
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
      return;
    }
    if (event.key === "Escape" && $(".nav").classList.contains("is-open")) setMenu(false);
  });

  const topButton = $("[data-top]");
  const syncTop = () => { topButton.hidden = window.scrollY < 480; };
  window.addEventListener("scroll", syncTop, { passive: true });
  syncTop();
  topButton.addEventListener("click", () => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById("overview").scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  });
}

document.documentElement.setAttribute("data-theme", "dark");
bind();
refreshHealth({ announce: true });
refreshMonitor({ announce: true });
refreshQueue({ announce: true });
window.setInterval(() => refreshHealth(), 15000);
