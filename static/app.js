/* PDF Parser & Translator — frontend logic (vanilla JS, no build step) */
"use strict";

const $ = (sel) => document.querySelector(sel);

const state = {
  doc: null,          // document summary
  jobId: null,
  es: null,           // EventSource
  mode: "bilingual",
  languages: {},
  pairs: [],
  running: false,
};

/* ---------------- toasts ---------------- */
let toastTimer = null;
function toast(msg, isErr = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isErr ? " err" : "");
  el.textContent = msg;
  document.body.appendChild(el);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.remove(), 4200);
}

/* ---------------- bootstrap ---------------- */
async function init() {
  let health;
  try {
    health = await (await fetch("/api/health")).json();
  } catch (e) {
    toast("Cannot reach the server", true);
    return;
  }
  state.languages = health.languages;

  const badges = $("#engineBadges");
  badges.innerHTML = "";
  const addBadge = (txt) => {
    const s = document.createElement("span");
    s.className = "badge";
    s.textContent = txt;
    badges.appendChild(s);
  };
  addBadge(health.engine);
  addBadge(`${health.models.models_available} models`);
  if (health.ocr) addBadge("OCR ready");

  const langs = Object.entries(health.languages).sort((a, b) =>
    a[1].localeCompare(b[1]));
  const src = $("#srcLang"), tgt = $("#tgtLang");
  src.innerHTML = `<option value="auto">🔍 Auto-detect</option>` +
    langs.map(([c, n]) => `<option value="${c}">${n}</option>`).join("");
  tgt.innerHTML =
    langs.map(([c, n]) => `<option value="${c}">${n}</option>`).join("");
  tgt.value = "de";
  src.value = "auto";

  try {
    const langsInfo = await (await fetch("/api/languages")).json();
    state.pairs = langsInfo.pairs;
    $("#footPairs").textContent =
      langsInfo.pairs.map((p) => p.replace("-", "→")).join("  ·  ");
  } catch (e) { /* non-fatal */ }

  bindUI();
  updatePairHint();
}

/* ---------------- UI bindings ---------------- */
function bindUI() {
  const dz = $("#dropzone"), fi = $("#fileInput");
  dz.addEventListener("click", () => fi.click());
  $("#browseBtn").addEventListener("click", (e) => { e.stopPropagation(); fi.click(); });
  fi.addEventListener("change", () => fi.files[0] && uploadFile(fi.files[0]));
  ["dragenter", "dragover"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files[0];
    if (f) uploadFile(f);
  });

  $("#sampleBtn").addEventListener("click", loadSample);
  $("#clearBtn").addEventListener("click", clearDoc);

  $("#srcLang").addEventListener("change", updatePairHint);
  $("#tgtLang").addEventListener("change", updatePairHint);
  $("#modeSeg").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-mode]");
    if (!b) return;
    state.mode = b.dataset.mode;
    [...e.currentTarget.children].forEach((x) => x.classList.toggle("on", x === b));
  });

  $("#translateBtn").addEventListener("click", startTranslation);

  $("#tabs").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-tab]");
    if (!b) return;
    const tab = b.dataset.tab;
    [...e.currentTarget.querySelectorAll("button[data-tab]")].forEach((x) =>
      x.classList.toggle("on", x === b));
    ["sidebyside", "downloads", "data"].forEach((t) => {
      $(`#pane-${t}`).hidden = t !== tab;
    });
  });
}

function updatePairHint() {
  const src = $("#srcLang").value, tgt = $("#tgtLang").value;
  const el = $("#pairHint");
  el.classList.remove("warn");
  if (src === "auto") {
    el.textContent = "The source language will be detected automatically.";
    return;
  }
  if (src === tgt) { el.textContent = "Same language — the text will be copied."; return; }
  const direct = state.pairs.includes(`${src}-${tgt}`);
  el.textContent = direct
    ? "Direct model available."
    : "No direct model — will route via English if possible.";
}

/* ---------------- document upload ---------------- */
async function uploadFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    toast("Please choose a PDF file", true);
    return;
  }
  toast(`Uploading “${file.name}”…`);
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch("/api/documents", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    setDoc(data);
  } catch (e) {
    toast(`Upload failed: ${e.message}`, true);
  }
}

async function loadSample() {
  toast("Generating sample document…");
  try {
    const res = await fetch("/api/documents/sample", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    setDoc(data);
  } catch (e) {
    toast(`Sample failed: ${e.message}`, true);
  }
}

function setDoc(data) {
  state.doc = data;
  $("#docInfo").hidden = false;
  $("#clearBtn").hidden = false;
  $("#translateBtn").disabled = false;
  $("#docName").textContent = data.filename;
  $("#docMeta").textContent =
    `${data.pages} page${data.pages === 1 ? "" : "s"} · ` +
    `${data.word_count.toLocaleString()} words · ` +
    `${data.paragraph_count} paragraphs` +
    (data.title && data.title !== data.filename ? ` · “${data.title}”` : "");

  const scanned = data.scanned_pages || [];
  if (scanned.length) {
    const chip = $("#detectedLang");
    chip.hidden = false;
    chip.textContent = `⚠ ${scanned.length} scanned page(s)`;
    chip.style.background = "#fffbeb";
    chip.style.borderColor = "#fcd34d";
    chip.style.color = "#b45309";
  }

  renderThumbs(data);
}

function clearDoc() {
  state.doc = null;
  $("#docInfo").hidden = true;
  $("#clearBtn").hidden = true;
  $("#translateBtn").disabled = true;
  $("#thumbs").innerHTML = "";
}

async function renderThumbs(data) {
  const box = $("#thumbs");
  box.innerHTML = "";
  const scanned = new Set(data.scanned_pages || []);
  const shown = Math.min(data.pages, 14);
  for (let p = 1; p <= shown; p++) {
    const div = document.createElement("div");
    div.className = "thumb" + (scanned.has(p) ? " scan" : "");
    const label = document.createElement("div");
    label.className = "t-label";
    label.textContent = scanned.has(p) ? `p${p} · OCR` : `p${p}`;
    const img = new Image();
    img.loading = "lazy";
    img.src = `/api/documents/${data.id}/page/${p}`;
    img.alt = `Page ${p}`;
    div.appendChild(img);
    div.appendChild(label);
    box.appendChild(div);
  }
  if (data.pages > shown) {
    const more = document.createElement("div");
    more.className = "thumb";
    more.style.display = "grid";
    more.style.placeItems = "center";
    more.style.width = "62px";
    more.style.height = "84px";
    more.style.color = "var(--ink-3)";
    more.style.fontWeight = "700";
    more.textContent = `+${data.pages - shown}`;
    box.appendChild(more);
  }
}

/* ---------------- translation ---------------- */
async function startTranslation() {
  if (!state.doc || state.running) return;
  const body = {
    source: $("#srcLang").value,
    target: $("#tgtLang").value,
    mode: state.mode,
    pages: $("#pageRange").value.trim() || "all",
    ocr: $("#ocrChk").checked,
  };
  state.running = true;
  $("#translateBtn").disabled = true;
  $("#progressCard").hidden = false;
  setBar(0, "Starting…");

  try {
    const res = await fetch(`/api/documents/${state.doc.id}/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const job = await res.json();
    if (!res.ok) throw new Error(job.detail || res.statusText);
    state.jobId = job.id;
    connectSSE(job.id);
  } catch (e) {
    state.running = false;
    $("#translateBtn").disabled = false;
    toast(`Job failed: ${e.message}`, true);
  }
}

function connectSSE(jobId) {
  if (state.es) state.es.close();
  state.es = new EventSource(`/api/jobs/${jobId}/events`);
  state.es.onmessage = (ev) => {
    let data;
    try { data = JSON.parse(ev.data); } catch { return; }
    if (data.progress != null) setBar(data.progress, data.message || data.stage);
    if (data.status === "done" || data.event === "done") finishJob(jobId, false);
    if (data.status === "error" || data.event === "error")
      finishJob(jobId, true, data.error);
  };
  state.es.onerror = () => {
    // EventSource reconnects automatically; poll once as a safety net
    if (state.running) {
      fetch(`/api/jobs/${jobId}`).then((r) => r.json()).then((j) => {
        if (j.status === "done") finishJob(jobId, false);
        else if (j.status === "error") finishJob(jobId, true, j.error);
        else if (j.progress != null) setBar(j.progress, j.message);
      }).catch(() => {});
    }
  };
}

function finishJob(jobId, isErr, errMsg) {
  if (!state.running) return;
  state.running = false;
  if (state.es) { state.es.close(); state.es = null; }
  $("#translateBtn").disabled = false;
  if (isErr) {
    toast(`Error: ${errMsg || "unknown"}`, true);
    $("#tabStatus").textContent = "Job failed";
    setBar(100, "Failed");
    return;
  }
  setBar(100, "Done");
  loadResult(jobId);
}

function setBar(pct, msg) {
  $("#barFill").style.width = `${pct}%`;
  $("#stagePct").textContent = `${Math.round(pct)}%`;
  if (msg) {
    const stageNames = {
      parse: "Parsing text",
      ocr: "OCR (scanned pages)",
      detect: "Language detection",
      translate: "Translating",
      build: "Building PDFs",
      done: "Finished",
      error: "Error",
    };
    $("#stageLabel").textContent =
      (["parse", "ocr", "detect", "translate", "build"].includes(msg) ?
        stageNames[msg] : msg.split("…")[0]) || msg;
    $("#stageMsg").textContent = msg;
  }
}

/* ---------------- results ---------------- */
async function loadResult(jobId) {
  const res = await fetch(`/api/jobs/${jobId}/result`);
  const data = await res.json();
  if (data.status && data.status !== "done") return;
  $("#emptyState").hidden = true;
  const stats = (data.job && data.job.stats) || {};
  $("#tabStatus").textContent =
    `✓ ${stats.words ? stats.words.toLocaleString() : "?"} words · ` +
    `${(data.job.elapsed || 0).toFixed(1)}s` +
    (stats.route && stats.route.length ? ` · ${stats.route.join(" → ")}` : "");
  renderSideBySide(data);
  renderDownloads(data);
  $("#jsonView").textContent = JSON.stringify(data, null, 2);
  $("#tabs button[data-tab='sidebyside']").click();
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : s;
  return d.innerHTML;
}

function renderSideBySide(data) {
  const job = data.job || {};
  const srcName = state.languages[job.source_lang] || job.source_lang;
  const tgtName = state.languages[job.target_lang] || job.target_lang;
  const sbsHead = $("#sbsHead"), sbsBody = $("#sbsBody");
  sbsHead.hidden = sbsBody.hidden = false;
  $("#sbsSrcHead").textContent = `${srcName} (original)`;
  $("#sbsTgtHead").textContent = `${tgtName} (translated)`;
  sbsBody.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (const p of data.paragraphs) {
    const row = document.createElement("div");
    row.className =
      `sbs-row ${p.kind || "body"} ${p.align === "center" ? "center" : ""}` +
      `${p.align === "right" ? " right" : ""}`;
    const tags =
      `<span class="page-tag">p${(p.page || 0) + 1}</span>` +
      (p.source === "ocr" ? `<span class="ocr-tag">OCR</span>` : "");
    row.innerHTML =
      `<div class="sbs-cell">${tags}${esc(p.text)}</div>` +
      `<div class="sbs-cell">${tags}${esc(p.translation)}</div>`;
    frag.appendChild(row);
  }
  sbsBody.appendChild(frag);
}

function renderDownloads(data) {
  const list = $("#dlList");
  list.innerHTML = "";
  const jobId = data.job.id;
  const items = [
    ["bilingual", "📑", "Bilingual PDF", "Original + translation, side by side"],
    ["translated", "📄", "Translated PDF", "Document in the target language only"],
    ["txt-bilingual", "📝", "Bilingual text", "Plain-text pairs"],
    ["txt-translation", "📝", "Translated text", "Plain text"],
    ["json", "🧩", "JSON export", "Full structured result"],
  ];
  for (const [fmt, ico, name, sub] of items) {
    const div = document.createElement("div");
    div.className = "dl-item";
    div.innerHTML =
      `<div class="dl-ico">${ico}</div>
       <div><div class="dl-name">${name}</div>
       <div class="dl-sub">${sub}</div></div>`;
    const btn = document.createElement("a");
    btn.className = "btn";
    btn.href = `/api/jobs/${jobId}/download?format=${fmt}`;
    btn.textContent = "Download";
    div.appendChild(btn);
    list.appendChild(div);
  }
}

init();
