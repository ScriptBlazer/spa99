/* Reorder a vertical list by dragging a handle (pointer) or with the handle focused and Up / Down (keyboard).
   The lifted row follows the pointer (transform), the others shift over 200ms. The caller re-renders after onMove. */
import { $$, MOTION, announce } from "./core.js";

export function sortable(list, { itemSel = ":scope > li", handleSel = "[data-handle]", onMove, describe }) {
  const items = () => $$(itemSel, list);

  list.addEventListener("pointerdown", (event) => {
    const handle = event.target instanceof Element && event.target.closest(handleSel);
    if (!handle || event.button > 0) return;
    const rows = items();
    const row = handle.closest(itemSel.replace(":scope > ", ""));
    const from = rows.indexOf(row);
    if (from < 0) return;
    event.preventDefault();
    const rects = rows.map((r) => r.getBoundingClientRect());
    const step = rows.length > 1 ? rects[1].top - rects[0].top : rects[0].height;
    const y0 = event.clientY;
    let to = from;
    handle.setPointerCapture(event.pointerId);
    row.classList.add("is-lifted");
    list.classList.add("is-sorting");
    for (const r of rows) if (r !== row && !MOTION.matches) r.style.transition = "transform 200ms var(--ease-soft)";
    const move = (e) => {
      const dy = e.clientY - y0;
      row.style.transform = `translateY(${dy}px)`;
      to = Math.max(0, Math.min(rows.length - 1, from + Math.round(dy / step)));
      rows.forEach((r, n) => {
        if (r === row) return;
        let shift = 0;
        if (from < to && n > from && n <= to) shift = -step;
        if (from > to && n < from && n >= to) shift = step;
        r.style.transform = shift ? `translateY(${shift}px)` : "";
      });
    };
    const end = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", end);
      handle.removeEventListener("pointercancel", end);
      for (const r of rows) { r.style.transform = ""; r.style.transition = ""; r.classList.remove("is-lifted"); }
      list.classList.remove("is-sorting");
      if (to !== from) {
        onMove(from, to);
        const hs = $$(handleSel, list);
        if (hs[to]) hs[to].focus({ preventScroll: true });
        if (describe) announce(describe(to));
      }
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  });

  list.addEventListener("keydown", (event) => {
    const handle = event.target instanceof Element && event.target.closest(handleSel);
    if (!handle || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return;
    event.preventDefault();
    const rows = items();
    const from = rows.indexOf(handle.closest(itemSel.replace(":scope > ", "")));
    const to = from + (event.key === "ArrowUp" ? -1 : 1);
    if (from < 0 || to < 0 || to >= rows.length) return;
    onMove(from, to);
    const hs = $$(handleSel, list);
    if (hs[to]) hs[to].focus({ preventScroll: true });
    if (describe) announce(describe(to));
  });
}
