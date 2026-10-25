/* Shared helpers for the Control modules: DOM shortcuts, formatting, a tiny event bus, toasts, the confirm dialog, icons.
   No network code lives here (only library.js talks to the server). */

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
export const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
export const rand = (low, high) => low + Math.random() * (high - low);
export const pad = (n) => String(n).padStart(2, "0");
export const DAY = 1440;
export const clock = (min) => `${pad(Math.floor((((min % DAY) + DAY) % DAY) / 60))}:${pad(((min % 60) + 60) % 60)}`;
export const MOTION = matchMedia("(prefers-reduced-motion: reduce)");
export const WIDE = matchMedia("(min-width: 48em)");
export const XWIDE = matchMedia("(min-width: 85em)");
export const FINE = matchMedia("(hover: hover) and (pointer: fine)");

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ESC[c]);

let counter = 0;
export const uid = (prefix = "u") => `${prefix}${Date.now().toString(36)}${(counter += 1).toString(36)}`;

/** 245 -> "4:05", 3725 -> "1:02:05" */
export function fmtDur(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`;
}
/** Words for a screen reader: "1 minute 42" style, "1 minute 42 of 4 minutes 5". */
export function spoken(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  const m = Math.floor(s / 60);
  return `${m} ${m === 1 ? "minute" : "minutes"} ${s % 60}`;
}
/** 2880 -> "48 min" */
export function fmtTotal(seconds) {
  const m = Math.round((Number(seconds) || 0) / 60);
  if (m >= 60) return `${Math.floor(m / 60)} h ${m % 60} min`;
  return `${m} min`;
}
export function fmtSize(bytes) {
  const b = Number(bytes) || 0;
  if (b >= 1024 ** 3) return `${(b / 1024 ** 3).toFixed(1)} GB`;
  if (b >= 1024 ** 2) return `${Math.round(b / 1024 ** 2)} MB`;
  return `${Math.max(1, Math.round(b / 1024))} KB`;
}
export const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** "evening-reel_v3.mp4" -> "Evening reel v3" */
export function tidyName(fileName) {
  const base = String(fileName).replace(/\.[A-Za-z0-9]{1,5}$/, "").replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
  return (base.charAt(0).toUpperCase() + base.slice(1)).slice(0, 120) || "Untitled";
}

export function icon(name, extra = "") {
  const sprite = document.body.dataset.icons || "";
  return `<svg class="icon ${extra}" aria-hidden="true" focusable="false"><use href="${sprite}#${name}"/></svg>`;
}

/* ---------- a tiny event bus ---------- */

const handlers = new Map();
export const bus = {
  on(name, fn) { if (!handlers.has(name)) handlers.set(name, new Set()); handlers.get(name).add(fn); return () => handlers.get(name).delete(fn); },
  emit(name, detail) { for (const fn of [...(handlers.get(name) || [])]) fn(detail); },
};

/* ---------- shared state holder, filled by state.js ---------- */

export const S = { st: null, server: null, save: () => {}, render: () => {} };

/* ---------- announce (one polite live region) ---------- */

export function announce(text) {
  const live = $("[data-live]");
  if (!live) return;
  live.textContent = "";
  setTimeout(() => { live.textContent = text; }, 30);
}

/* ---------- toast ---------- */

export function toast(text, onUndo, ms = 6000) {
  const host = $("[data-toasts]");
  if (!host) return;
  const el = document.createElement("div");
  el.className = "ctl-toast";
  el.setAttribute("role", "status");
  const span = document.createElement("span");
  span.textContent = text;
  el.append(span);
  let left = ms;
  let last = performance.now();
  let hover = false;
  let iv = 0;
  const remove = () => {
    clearInterval(iv);
    if (MOTION.matches) { el.remove(); return; }
    el.classList.add("is-out");
    setTimeout(() => el.remove(), 170);
  };
  if (onUndo) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = "Undo";
    b.addEventListener("click", () => { onUndo(); remove(); });
    el.append(b);
  }
  el.addEventListener("mouseenter", () => { hover = true; });
  el.addEventListener("mouseleave", () => { hover = false; });
  el.addEventListener("focusin", () => { hover = true; });
  el.addEventListener("focusout", () => { hover = false; });
  iv = setInterval(() => {
    const now = performance.now();
    if (!hover) left -= now - last;
    last = now;
    if (left <= 0) remove();
  }, 200);
  while (host.children.length >= 2) host.firstElementChild.remove();
  host.append(el);
}

/* ---------- the one generic dialog: confirm and small forms ---------- */

/** Resolves true when the primary button is chosen. */
export function confirmDialog({ title, body = "", ok = "OK", danger = false, cancel = "Cancel" }) {
  const dialog = $("[data-dialog]");
  const form = $("[data-dialog-form]");
  if (!dialog || !dialog.showModal) return Promise.resolve(window.confirm(`${title}\n${body}`));
  form.innerHTML = `<h2 id="ctl-dialog-h">${esc(title)}</h2>${body ? `<p>${esc(body)}</p>` : ""}
    <div class="ctl-dialog-actions"><button type="submit" value="cancel" class="ctl-btn">${esc(cancel)}</button>
    <button type="submit" value="ok" class="ctl-btn ${danger ? "ctl-btn-danger" : "ctl-btn-primary"}">${esc(ok)}</button></div>`;
  return new Promise((resolve) => {
    const done = () => { dialog.removeEventListener("close", done); resolve(dialog.returnValue === "ok"); };
    dialog.addEventListener("close", done);
    dialog.returnValue = "cancel";
    dialog.showModal();
    $("button[value=ok]", form).focus();
  });
}

/** A dialog with custom content. `build(form, close)` fills the form; resolves with whatever close() was given. */
export function formDialog(build) {
  const dialog = $("[data-dialog]");
  const form = $("[data-dialog-form]");
  return new Promise((resolve) => {
    form.innerHTML = "";
    let result = null;
    const done = () => { dialog.removeEventListener("close", done); resolve(result); };
    dialog.addEventListener("close", done);
    build(form, (value) => { result = value; dialog.close(); });
    dialog.returnValue = "cancel";
    dialog.showModal();
  });
}

/* ---------- time ---------- */

const clockFormat = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", hour: "2-digit", minute: "2-digit", hourCycle: "h23", weekday: "short", day: "numeric", month: "short" });
export function londonNow() {
  const p = Object.fromEntries(clockFormat.formatToParts(new Date()).map((x) => [x.type, x.value]));
  const min = (Number(p.hour) % 24) * 60 + Number(p.minute);
  return { min, clock: clock(min), date: `${p.weekday} ${p.day} ${p.month}` };
}

export function slug(text) {
  return String(text).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

/** Typographic cover colour fields (brand tokens only): index 0 to 5. */
export const FIELDS = 6;
