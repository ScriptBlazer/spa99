/* The one side panel (desktop) / bottom sheet (phone). Used for a room, a screen, a Library item, the music source picker and
   "More". On the Overview at a wide size a room opens in the right-hand column instead of over the page ("rail" mode). */
import { $, $$, MOTION, WIDE, XWIDE, clamp } from "./core.js";

let cur = null;  // { key, rail, onClose, lastFocus, node }
const FLICK = 0.11;  // px per ms

const panel = () => $("[data-panel]");
const body = () => $("[data-panel-body]");
const backdrop = () => $("[data-backdrop]");
const railHost = () => $("[data-rail-panel]");

export const panelKey = () => (cur ? cur.key : null);
export const panelNode = () => (cur ? cur.node : null);

export function openPanel({ key, node, size = "peek", rail = false, onClose = null }) {
  const same = cur && cur.key === key;
  const wasOpen = Boolean(cur);
  if (cur && !same) closeNow(false);  // switching panels: the old one closes quietly (it must not touch the address)
  const lastFocus = cur ? cur.lastFocus : document.activeElement;
  const useRail = rail && XWIDE.matches && railHost();
  cur = { key, rail: Boolean(useRail), onClose, lastFocus, node };
  if (useRail) {
    const host = railHost();
    host.replaceChildren(node);
    host.hidden = false;
    const main = $("[data-rail-main]");
    if (main) main.hidden = true;
    document.body.classList.add("has-rail-panel");
  } else {
    const box = panel();
    body().replaceChildren(node);
    box.hidden = false;
    // a phone sheet at peek height leaves the page above it visible and scrollable (the plan keeps re-lighting)
    const open = size === "peek" && !WIDE.matches;
    backdrop().hidden = open;
    box.classList.toggle("is-full", size === "full");
    box.classList.toggle("is-peek", size !== "full");
    box.dataset.size = size;
    document.body.classList.toggle("has-panel", !open);
    if (!wasOpen && !MOTION.matches) { box.classList.remove("is-in"); void box.offsetWidth; box.classList.add("is-in"); }
  }
  const title = $("#ctl-panel-title", node) || node;
  if (title) { if (!title.hasAttribute("tabindex")) title.setAttribute("tabindex", "-1"); title.focus({ preventScroll: true }); }
  return node;
}

function closeNow(restore) {
  if (!cur) return;
  const { rail, onClose, lastFocus } = cur;
  cur = null;
  if (rail) {
    const host = railHost();
    if (host) { host.hidden = true; host.replaceChildren(); }
    const main = $("[data-rail-main]");
    if (main) main.hidden = false;
    document.body.classList.remove("has-rail-panel");
  } else {
    const box = panel();
    box.hidden = true;
    box.style.transform = "";
    box.style.transition = "";
    body().replaceChildren();
    backdrop().hidden = true;
    document.body.classList.remove("has-panel");
  }
  if (onClose) onClose(!restore);  // true = closed quietly (a tab change or another panel opening): leave the address alone
  if (restore && lastFocus && document.contains(lastFocus)) lastFocus.focus({ preventScroll: true });
}

export function closePanel() { closeNow(true); }

/** The panel kept open across a page swap would point at removed nodes: close it quietly. */
export function closePanelQuietly() { closeNow(false); }

/* ---------- keep Tab inside the overlay ---------- */

function stops(box) {
  return $$("a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex='-1'])", box).filter((x) => {
    if (x.hidden || x.closest("[hidden]")) return false;
    if (x.type === "radio" && x.name) {
      const group = $$(`input[type="radio"][name="${x.name}"]`, box);
      const on = group.find((g) => g.checked);
      return on ? on === x : group[0] === x;
    }
    return true;
  });
}

export function trapTab(event) {
  if (!cur || cur.rail || event.key !== "Tab") return;
  const box = panel();
  const list = stops(box);
  if (!list.length) return;
  const first = list[0];
  const last = list[list.length - 1];
  const active = document.activeElement;
  if (!box.contains(active)) { event.preventDefault(); first.focus(); }
  else if (event.shiftKey && (active === first || active.id === "ctl-panel-title")) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && active === last) { event.preventDefault(); first.focus(); }
}

/* ---------- phone sheet: drag the grip up for full height, down to close ---------- */

export function initSheet() {
  const box = panel();
  const grip = $("[data-grip]", box);
  let drag = null;
  grip.addEventListener("pointerdown", (event) => {
    if (WIDE.matches || !cur || cur.rail) return;
    const H = innerHeight;
    const base = box.classList.contains("is-full") ? 0 : H * 0.36;
    drag = { y0: event.clientY, base, H, lastY: event.clientY, lastT: event.timeStamp, v: 0 };
    grip.setPointerCapture(event.pointerId);
    box.style.transition = "none";
  });
  grip.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const dt = event.timeStamp - drag.lastT;
    if (dt > 0) drag.v = (event.clientY - drag.lastY) / dt;
    drag.lastY = event.clientY;
    drag.lastT = event.timeStamp;
    box.style.transform = `translateY(${clamp(drag.base + event.clientY - drag.y0, 0, drag.H)}px)`;
  });
  const end = (event) => {
    if (!drag) return;
    const d = drag;
    drag = null;
    const y = clamp(d.base + event.clientY - d.y0, 0, d.H);
    box.style.transition = "";
    box.style.transform = "";
    const peek = d.H * 0.36;
    let target;
    if (d.v > FLICK) target = d.base === 0 ? "peek" : "close";
    else if (d.v < -FLICK) target = "full";
    else target = [["full", 0], ["peek", peek], ["close", d.H * 0.92]].sort((a, b) => Math.abs(a[1] - y) - Math.abs(b[1] - y))[0][0];
    if (target === "close") { closePanel(); return; }
    box.classList.toggle("is-full", target === "full");
    box.classList.toggle("is-peek", target === "peek");
    backdrop().hidden = target === "peek";
    document.body.classList.toggle("has-panel", target !== "peek");
  };
  grip.addEventListener("pointerup", end);
  grip.addEventListener("pointercancel", end);
}
