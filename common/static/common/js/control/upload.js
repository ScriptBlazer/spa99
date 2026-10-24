/* Library uploads: checked in the browser first (type and size, the same rules the server applies by content), then sent
   with XHR (fetch cannot report upload progress), two at a time, with cancel and retry. After the file is stored the browser
   measures it (length, size, audio waveform peaks, a video poster frame) and sends those to the duration endpoint, so the
   server needs no ffmpeg. Lives for the whole visit: a tab change does not stop an upload. */
import { $, $$, esc, fmtSize, icon, tidyName, uid, bus, MOTION } from "./core.js";
import { L, csrfToken, postForm, replaceAsset } from "./libdata.js";

const MB = 1024 * 1024;
export const limits = { audio: 50, video: 500, image: 20 };
const EXT = { mp3: "audio", m4a: "audio", wav: "audio", mp4: "video", webm: "video", jpg: "image", jpeg: "image", png: "image", webp: "image" };
const WORD = { audio: "Music", video: "Videos", image: "Pictures" };
const STOPPED = "Upload stopped. Check the connection and try again.";
const MAX_FILES = 20;
const jobs = [];
let running = 0;
let collapsed = false;
let closeTimer = 0;

export const uploading = () => jobs.some((j) => j.state === "waiting" || j.state === "uploading" || j.state === "preparing");

/** -> an error message for the file's row, or "" */
export function check(file) {
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if (["heic", "heif"].includes(ext) || /heic|heif/i.test(file.type)) return "HEIC pictures can't be shown on screens. Save it as JPG and try again.";
  const kind = EXT[ext];
  if (!kind) return "This type can't be used. For music use MP3, M4A or WAV.";
  if (!file.size) return "That file is empty.";
  if (file.size > limits[kind] * MB) return `This file is ${Math.round(file.size / MB)} MB. ${WORD[kind]} can be up to ${limits[kind]} MB.`;
  const used = L.summary.used_bytes + jobs.filter((j) => ["waiting", "uploading", "preparing"].includes(j.state)).reduce((n, j) => n + j.file.size, 0);
  if (L.summary.max_bytes && used + file.size > L.summary.max_bytes) return "The Library is full. Delete something to make room.";
  return "";
}

export const kindOf = (file) => EXT[(file.name.split(".").pop() || "").toLowerCase()] || "";

export function addFiles(list) {
  const files = [...list];
  if (!files.length) return;
  clearTimeout(closeTimer);
  files.forEach((file, n) => {
    const job = { id: uid("up"), file, name: tidyName(file.name), kind: kindOf(file), state: "waiting", pct: 0, error: "", xhr: null };
    const problem = n >= MAX_FILES ? `Up to ${MAX_FILES} files at a time. Add the rest in a second go.` : check(file);
    if (problem) { job.state = "stopped"; job.error = problem; job.final = true; }
    jobs.push(job);
  });
  renderTray(true);
  pump();
}

function pump() {
  while (running < 2) {
    const next = jobs.find((j) => j.state === "waiting");
    if (!next) break;
    running += 1;
    start(next).finally(() => { running -= 1; pump(); finishCheck(); });
  }
}

function sendFile(job) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    job.xhr = xhr;
    xhr.open("POST", "/library/assets/upload/");
    xhr.setRequestHeader("X-CSRFToken", csrfToken());
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) { job.pct = Math.round((e.loaded / e.total) * 100); paintRow(job); } };
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch (e) { data = {}; }
      if (xhr.status === 201) resolve({ ok: true, data });
      else resolve({ ok: false, message: data.error || STOPPED, final: xhr.status >= 400 && xhr.status < 500 });
    };
    xhr.onerror = () => resolve({ ok: false, message: STOPPED });
    xhr.onabort = () => resolve({ ok: false, message: "Stopped.", aborted: true });
    const form = new FormData();
    form.append("file", job.file);
    form.append("title", job.name);
    form.append("tags", job.kind === "audio" ? "music" : "screens");
    xhr.send(form);
  });
}

async function start(job) {
  job.state = "uploading";
  job.pct = 0;
  job.error = "";
  renderTray(true);
  const sent = await sendFile(job);
  job.xhr = null;
  if (!sent.ok) {
    job.state = "stopped";
    job.error = sent.message;
    job.final = Boolean(sent.final);
    renderTray(true);
    return;
  }
  job.state = "preparing";
  job.pct = 100;
  renderTray(true);
  let asset = sent.data;
  L.summary = sent.data.library || L.summary;
  try {
    const found = await measure(job.file, asset.kind);
    if (found) {
      const form = new FormData();
      if (found.duration) form.append("duration_seconds", String(found.duration));
      if (found.width) { form.append("width", String(found.width)); form.append("height", String(found.height)); }
      if (found.peaks) form.append("peaks", JSON.stringify(found.peaks));
      if (found.poster) form.append("poster", found.poster, "poster.jpg");
      if (found.duration) asset = await postForm(`/library/assets/${asset.id}/duration/`, form);
    }
  } catch (e) { /* the file is stored; it just has no length or waveform yet */ }
  replaceAsset({ ...asset, playlists: [] });
  job.state = "added";
  job.assetId = asset.id;
  renderTray(true);
  bus.emit("library-changed", { added: asset });
}

export function cancel(id) {
  const job = jobs.find((j) => j.id === id);
  if (!job) return;
  if (job.xhr) job.xhr.abort();
  else if (job.state === "waiting") { job.state = "stopped"; job.error = "Stopped."; renderTray(true); }
}

export function retry(id) {
  const job = jobs.find((j) => j.id === id);
  if (!job || job.final) return;
  job.state = "waiting";
  job.error = "";
  clearTimeout(closeTimer);
  renderTray(true);
  pump();
}

/* ---------- measuring in the browser ---------- */

function withTimeout(promise, ms) {
  return Promise.race([promise, new Promise((resolve) => setTimeout(() => resolve(null), ms))]);
}

async function measure(file, kind) {
  if (kind === "audio") return withTimeout(measureAudio(file), 60000);
  if (kind === "video") return withTimeout(measureVideo(file), 20000);
  return null;
}

async function measureAudio(file) {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  let duration = 0;
  let peaks = null;
  if (Ctx) {
    const ctx = new Ctx();
    try {
      const buffer = await ctx.decodeAudioData(await file.arrayBuffer());
      duration = buffer.duration;
      const bins = 200;
      const size = Math.max(1, Math.floor(buffer.length / bins));
      const out = new Array(bins).fill(0);
      for (let c = 0; c < buffer.numberOfChannels; c += 1) {
        const data = buffer.getChannelData(c);
        for (let b = 0; b < bins; b += 1) {
          let m = 0;
          const end = Math.min(data.length, (b + 1) * size);
          for (let i = b * size; i < end; i += Math.max(1, Math.floor(size / 200))) m = Math.max(m, Math.abs(data[i]));
          out[b] = Math.max(out[b], m);
        }
      }
      const top = Math.max(...out) || 1;
      peaks = out.map((v) => Math.round((v / top) * 1000) / 1000);
    } catch (e) { /* not decodable here: fall back to the media element for the length */ } finally { if (ctx.close) ctx.close(); }
  }
  if (!duration) duration = await elementDuration(file, "audio");
  return duration ? { duration, peaks } : null;
}

function elementDuration(file, tag) {
  return new Promise((resolve) => {
    const el = document.createElement(tag);
    const url = URL.createObjectURL(file);
    el.preload = "metadata";
    el.onloadedmetadata = () => { const d = el.duration; URL.revokeObjectURL(url); resolve(Number.isFinite(d) ? d : 0); };
    el.onerror = () => { URL.revokeObjectURL(url); resolve(0); };
    el.src = url;
  });
}

function measureVideo(file) {
  return new Promise((resolve) => {
    const video = document.createElement("video");
    const url = URL.createObjectURL(file);
    video.muted = true;
    video.preload = "auto";
    video.playsInline = true;
    const done = (value) => { URL.revokeObjectURL(url); resolve(value); };
    video.onerror = () => done(null);
    video.onloadedmetadata = () => {
      const duration = Number.isFinite(video.duration) ? video.duration : 0;
      const at = duration > 1.2 ? Math.min(1, duration * 0.1) : duration / 2;
      video.onseeked = () => {
        try {
          const w = Math.min(640, video.videoWidth || 640);
          const h = Math.round(w * ((video.videoHeight || 360) / (video.videoWidth || 640)));
          const canvas = document.createElement("canvas");
          canvas.width = w;
          canvas.height = h;
          canvas.getContext("2d").drawImage(video, 0, 0, w, h);
          canvas.toBlob((poster) => done({ duration, width: video.videoWidth, height: video.videoHeight, poster }), "image/jpeg", 0.8);
        } catch (e) { done({ duration, width: video.videoWidth, height: video.videoHeight, poster: null }); }
      };
      video.currentTime = at;
    };
    video.src = url;
  });
}

/* ---------- the tray ---------- */

const STATE_WORD = { waiting: "Waiting", uploading: "Uploading", preparing: "Preparing", added: "Added", stopped: "Stopped" };
const KIND_ICON = { audio: "music-notes", video: "film-strip", image: "image" };

function wordFor(job) {
  if (job.state === "uploading") return `Uploading ${job.pct}%`;
  return STATE_WORD[job.state];
}

function rowHtml(job) {
  const busy = job.state === "uploading" || job.state === "waiting";
  return `<li class="ctl-up" data-job="${job.id}" data-state="${job.state}">
    <span class="ctl-up-icon">${icon(KIND_ICON[job.kind] || "image")}</span>
    <span class="ctl-up-text"><span class="ctl-up-name">${esc(job.name)}</span><span class="ctl-soft"><span data-up-word>${esc(wordFor(job))}</span> · ${fmtSize(job.file.size)}</span>
      ${job.error ? `<span class="ctl-up-error">${esc(job.error)}</span>` : ""}</span>
    ${busy ? `<button type="button" class="ctl-link" data-up-cancel="${job.id}">Cancel</button>` : ""}
    ${job.state === "stopped" && !job.final ? `<button type="button" class="ctl-link" data-up-retry="${job.id}">Retry</button>` : ""}
    <span class="ctl-up-bar" aria-hidden="true"><span data-up-bar style="transform:scaleX(${job.state === "added" || job.state === "preparing" ? 1 : job.pct / 100})"></span></span></li>`;
}

function paintRow(job) {
  const row = $(`[data-job="${job.id}"]`);
  if (!row) return;
  const bar = $("[data-up-bar]", row);
  if (bar) bar.style.transform = `scaleX(${job.pct / 100})`;
  const word = $("[data-up-word]", row);
  if (word) word.textContent = wordFor(job);
}

function summary() {
  const total = jobs.length;
  const done = jobs.filter((j) => j.state === "added").length;
  const failed = jobs.filter((j) => j.state === "stopped").length;
  const active = jobs.filter((j) => ["waiting", "uploading", "preparing"].includes(j.state)).length;
  if (active) return `Uploading ${Math.min(total, done + failed + 1)} of ${total}`;
  if (failed) return `${done} added, ${failed} not added`;
  return done === 1 ? "1 file added." : `${done} files added.`;
}

export function renderTray(structural) {
  const tray = $("[data-tray]");
  if (!tray) return;
  if (!jobs.length) { tray.hidden = true; return; }
  tray.hidden = false;
  tray.classList.toggle("is-collapsed", collapsed);
  if (!structural) return;
  tray.innerHTML = `<header class="ctl-tray-head"><p class="ctl-tray-title" role="status">${esc(summary())}</p>
    <button type="button" class="ctl-iconbtn" data-tray-toggle aria-expanded="${!collapsed}" aria-label="${collapsed ? "Show uploads" : "Hide uploads"}">${icon(collapsed ? "caret-up" : "caret-down")}</button></header>
    <ul class="ctl-tray-list">${jobs.map(rowHtml).join("")}</ul>`;
}

function finishCheck() {
  if (uploading()) return;
  const failed = jobs.some((j) => j.state === "stopped");
  if (failed) return;
  clearTimeout(closeTimer);
  closeTimer = setTimeout(() => { if (!uploading() && !jobs.some((j) => j.state === "stopped")) { jobs.length = 0; renderTray(true); } }, 4000);
}

export function initUpload() {
  document.addEventListener("click", (event) => {
    const t = event.target instanceof Element ? event.target : null;
    if (!t) return;
    const c = t.closest("[data-up-cancel]");
    if (c) { cancel(c.dataset.upCancel); return; }
    const r = t.closest("[data-up-retry]");
    if (r) { retry(r.dataset.upRetry); return; }
    if (t.closest("[data-tray-toggle]")) { collapsed = !collapsed; renderTray(true); }
  });
  window.addEventListener("beforeunload", (event) => {
    if (uploading()) { event.preventDefault(); event.returnValue = ""; }
  });
}
