/* PDF Parser & Translator — frontend logic (vanilla JS, no build step) */
"use strict";

const $ = (sel) => document.querySelector(sel);

const state = {
  doc: null,          // document summary
  jobId: null,
  es: null,           // EventSource
  mode: "bilingual",
  languages: {},
  localLangs: {},
  onlineLangs: {},
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
function langOptions(selected) {
  const local = Object.entries(state.localLangs)
    .sort((a, b) => a[1].localeCompare(b[1]));
  const online = Object.entries(state.onlineLangs)
    .sort((a, b) => a[1].localeCompare(b[1]));
  let html = "";
  if (selected) html += `<option value="auto">🔍 Auto-detect</option>`;
  if (local.length) {
    html += `<optgroup label="Offline models (local)">` +
      local.map(([c, n]) => `<option value="${c}">${n}</option>`).join("") +
      `</optgroup>`;
  }
  if (online.length) {
    html += `<optgroup label="Online — more languages (internet)">` +
      online.map(([c, n]) => `<option value="${c}">${n}</option>`).join("") +
      `</optgroup>`;
  }
  return html;
}

async function init() {
  let health;
  try {
    health = await (await fetch("/api/health")).json();
  } catch (e) {
    toast("Cannot reach the server", true);
    return;
  }
  state.languages = health.languages;
  state.localLangs = health.local_languages || {};
  state.onlineLangs = health.online_languages || {};

  const badges = $("#engineBadges");
  badges.innerHTML = "";
  const addBadge = (txt) => {
    const s = document.createElement("span");
    s.className = "badge";
    s.textContent = txt;
    badges.appendChild(s);
  };
  addBadge(health.engine);
  addBadge(`${health.models.models_available} local models`);
  if (health.ocr) addBadge("OCR ready");

  const src = $("#srcLang"), tgt = $("#tgtLang");
  src.innerHTML = langOptions(true);
  tgt.innerHTML = langOptions(false);
  const hasTr = "tr" in state.localLangs || "tr" in state.onlineLangs;
  tgt.value = hasTr ? "tr" : "de";
  src.value = "auto";

  try {
    const langsInfo = await (await fetch("/api/languages")).json();
    state.pairs = langsInfo.pairs || [];
    if (!state.localLangs || !Object.keys(state.localLangs).length)
      state.localLangs = langsInfo.local_languages || {};
    $("#footPairs").textContent =
      (state.pairs || []).map((p) => p.replace("-", "→")).join("  ·  ") +
      `   ·   online: +${Object.keys(state.onlineLangs).length} languages`;
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

function localRouteExists(src, tgt) {
  if (src === tgt) return true;
  if (state.pairs.includes(`${src}-${tgt}`)) return true;
  return state.pairs.includes(`${src}-en`) && state.pairs.includes(`en-${tgt}`);
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
  if (localRouteExists(src, tgt)) {
    el.textContent = state.pairs.includes(`${src}-${tgt}`)
      ? "Offline model available (fast, no internet)."
      : "Offline — routed via English.";
    return;
  }
  el.classList.add("warn");
  el.textContent = "No offline model — will translate online via your browser (needs internet).";
}

/* parse "all" / "1-3,5" → [1..n] or null (all) */
function parsePageRange(value, pageCount) {
  value = (value || "").trim();
  if (!value || value.toLowerCase() === "all") return null;
  const out = [];
  for (const part of value.replace(";", ",").split(",")) {
    const p = part.trim();
    if (!p) continue;
    const m = p.match(/^(\d+)\s*-\s*(\d+)$/);
    if (m) {
      for (let i = Math.max(1, +m[1]); i <= Math.min(pageCount, +m[2]); i++) out.push(i);
    } else if (/^\d+$/.test(p)) out.push(+p);
    else throw new Error(`Bad page range: ${p}`);
  }
  return [...new Set(out.filter((p) => p >= 1 && p <= pageCount))];
}

/* Browser-side online translation (free Google web endpoint). */
async function browserTranslate(paras, src, tgt, onProgress) {
  const out = new Array(paras.length).fill("");
  let detected = src;
  for (let i = 0; i < paras.length; i += 12) {
    const chunk = paras.slice(i, i + 12);
    const qs = new URLSearchParams();
    qs.set("client", "gtx");
    qs.set("sl", src === "auto" ? "auto" : src);
    qs.set("tl", tgt);
    qs.set("dt", "t");
    chunk.forEach((t) => qs.append("q", t));
    let res;
    try {
      res = await fetch(
        "https://translate.googleapis.com/translate_a/single?" + qs.toString());
    } catch (e) {
      throw new Error("Cannot reach the online translation service from your browser.");
    }
    if (!res.ok) throw new Error(`Online translation failed (HTTP ${res.status}).`);
    const data = await res.json();
    if (src === "auto" && data[2]) detected = data[2];
    chunk.forEach((t, j) => {
      out[i + j] = t.trim() ? (data[0][j] || []).map((s) => s[0]).join("") : t;
    });
    onProgress(Math.min(i + 12, paras.length), paras.length, detected);
    await new Promise((r) => setTimeout(r, 150));
  }
  return { translations: out, detected };
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
  const source = $("#srcLang").value;
  const target = $("#tgtLang").value;
  let pages;
  try {
    pages = parsePageRange($("#pageRange").value, state.doc.pages);
  } catch (e) {
    toast(e.message, true);
    return;
  }

  state.running = true;
  $("#translateBtn").disabled = true;
  $("#progressCard").hidden = false;
  setBar(0, "Starting…");

  // local (offline) engine when a model covers the pair, else browser online
  const useLocal = source === "auto"
    ? (target in state.localLangs)
    : localRouteExists(source, target);

  try {
    if (useLocal) {
      const body = {
        source, target, mode: state.mode,
        pages: $("#pageRange").value.trim() || "all",
        ocr: $("#ocrChk").checked,
        engine: "auto",
      };
      const res = await fetch(`/api/documents/${state.doc.id}/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const job = await res.json();
      if (!res.ok) throw new Error(job.detail || res.statusText);
      state.jobId = job.id;
      connectSSE(job.id);
    } else {
      await runOnlineFlow(source, target, pages);
    }
  } catch (e) {
    state.running = false;
    $("#translateBtn").disabled = false;
    toast(`Job failed: ${e.message}`, true);
    setBar(0, "Failed");
  }
}

async function runOnlineFlow(source, target, pages) {
  if ((state.doc.scanned_pages || []).length) {
    throw new Error(
      "Scanned pages need the offline engine — choose one of the 9 local " +
      "languages for OCR documents.");
  }
  let paras = state.doc.paragraphs || [];
  if (pages) paras = paras.filter((p) => pages.includes((p.page || 0) + 1));
  if (!paras.length) throw new Error("No text found on the selected pages.");

  const { translations, detected } = await browserTranslate(
    paras.map((p) => p.text), source, target,
    (done, total, det) => {
      setBar(5 + 80 * (done / total),
             `Translating online (browser)… ${done}/${total} chunks` +
             (det && det !== "auto" ? ` · src=${det}` : ""));
    });

  setBar(90, "Building PDFs on the server…");
  const body = {
    source: detected, target, mode: state.mode,
    paragraphs: paras.map((p, i) => ({
      text: p.text,
      translation: translations[i],
      kind: p.kind,
      align: p.align,
      page: p.page,
      source: p.source,
    })),
  };
  const res = await fetch(`/api/documents/${state.doc.id}/build`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const job = await res.json();
  if (!res.ok) throw new Error(job.detail || res.statusText);
  const doneJob = await pollJob(job.id);
  state.jobId = job.id;
  state.running = false;
  $("#translateBtn").disabled = false;
  setBar(100, "Done");
  await loadResult(job.id);
}

async function pollJob(jobId) {
  for (let i = 0; i < 60; i++) {
    const j = await (await fetch(`/api/jobs/${jobId}`)).json();
    if (j.status === "done") return j;
    if (j.status === "error") throw new Error(j.error || "Build failed");
    setBar(90 + Math.min(9, i * 0.5), j.message || "Building…");
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error("Build timed out");
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

async function downloadFile(jobId, fmt, btn) {
  const names = {
    bilingual: "bilingual.pdf",
    translated: "translated.pdf",
    "txt-bilingual": "bilingual.txt",
    "txt-translation": "translated.txt",
    json: "result.json",
  };
  try {
    btn.disabled = true;
    const res = await fetch(`/api/jobs/${jobId}/download?format=${fmt}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    let name = names[fmt] || fmt;
    const m = (res.headers.get("Content-Disposition") || "")
      .match(/filename="?([^";]+)"?/);
    if (m) name = m[1];
    // object-URL + download attribute → saved as a file even when the
    // proxy drops Content-Disposition
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch (e) {
    toast(`Download failed: ${e.message}`, true);
  } finally {
    btn.disabled = false;
  }
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
    const btn = document.createElement("button");
    btn.className = "btn";
    btn.textContent = "Download";
    btn.addEventListener("click", () => downloadFile(jobId, fmt, btn));
    div.appendChild(btn);
    list.appendChild(div);
  }
}

init();
