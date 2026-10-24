/* The music queue rules, with no DOM, so they can be tested on their own (control/tests/js/music-model.test.mjs).
   A zone is { queue: [entry], i: index of the current entry (-1 when empty), pos: seconds into it, playing, shuffle,
   repeat: "off" | "all" | "one", orig: [uid] (the order before shuffling) }. An entry is { uid, id, title, artist, dur, kind, ... }.
   "Up next" is queue.slice(i + 1). Nothing here touches the network or the page. */

let seq = 0;
export const entryUid = () => `q${Date.now().toString(36)}${(seq += 1).toString(36)}`;

export const current = (zone) => (zone.i >= 0 ? zone.queue[zone.i] || null : null);
export const upcoming = (zone) => zone.queue.slice(zone.i + 1);

export function shuffled(list, rnd = Math.random) {
  const a = list.slice();
  for (let n = a.length - 1; n > 0; n -= 1) {
    const k = Math.floor(rnd() * (n + 1));
    [a[n], a[k]] = [a[k], a[n]];
  }
  return a;
}

function reshuffleUpcoming(zone, rnd) {
  const head = zone.queue.slice(0, zone.i + 1);
  const tail = zone.queue.slice(zone.i + 1);
  zone.orig = tail.map((e) => e.uid);
  zone.queue = head.concat(shuffled(tail, rnd));
}

export function setShuffle(zone, on, rnd = Math.random) {
  zone.shuffle = on;
  if (on) { reshuffleUpcoming(zone, rnd); return; }
  const head = zone.queue.slice(0, zone.i + 1);
  const tail = zone.queue.slice(zone.i + 1);
  const rank = new Map((zone.orig || []).map((uid, n) => [uid, n]));
  tail.sort((a, b) => (rank.has(a.uid) ? rank.get(a.uid) : 1e9) - (rank.has(b.uid) ? rank.get(b.uid) : 1e9));
  zone.queue = head.concat(tail);
}

/** Replace the queue and start at `start`. `tracks` are plain tracks; each gets its own uid. */
export function playNow(zone, tracks, start = 0, rnd = Math.random) {
  zone.queue = tracks.map((t) => ({ ...t, uid: entryUid() }));
  zone.i = zone.queue.length ? Math.min(start, zone.queue.length - 1) : -1;
  zone.pos = 0;
  zone.playing = zone.queue.length > 0;
  zone.orig = zone.queue.slice(zone.i + 1).map((e) => e.uid);
  if (zone.shuffle) reshuffleUpcoming(zone, rnd);
}

export function enqueue(zone, tracks) {
  const added = tracks.map((t) => ({ ...t, uid: entryUid() }));
  zone.queue.push(...added);
  zone.orig = (zone.orig || []).concat(added.map((e) => e.uid));
  if (zone.i < 0) { zone.i = 0; zone.pos = 0; zone.playing = true; }
  return added.length;
}

/** Step to the next entry. `auto` = the track ended by itself. Returns false when there is nothing next. */
export function stepNext(zone, auto, rnd = Math.random) {
  if (zone.i < 0) return false;
  if (auto && zone.repeat === "one") { zone.pos = 0; return true; }
  if (zone.i + 1 < zone.queue.length) { zone.i += 1; zone.pos = 0; return true; }
  if (zone.repeat === "all" && zone.queue.length) {
    zone.i = 0;
    zone.pos = 0;
    if (zone.shuffle) reshuffleUpcoming(zone, rnd);
    return true;
  }
  return false;
}

export function stepPrev(zone) {
  if (zone.i < 0) return;
  if (zone.pos > 3 || zone.i === 0) { zone.pos = 0; return; }
  zone.i -= 1;
  zone.pos = 0;
}

/** Move the clock on by `dt` seconds. Returns "track" when the current entry changed, "ended" when the queue ran out. */
export function advance(zone, dt, rnd = Math.random) {
  let event = "";
  const cur = current(zone);
  if (!zone.playing || !cur) return event;
  zone.pos += dt;
  if (zone.repeat === "one") zone.pos %= Math.max(1, cur.dur || 1);
  else if (zone.repeat === "all") {
    const total = Math.max(1, zone.queue.reduce((n, e) => n + Math.max(1, e.dur || 1), 0));
    if (zone.pos > total * 2) zone.pos %= total;
  }
  for (let guard = 0; guard < 2000 && zone.playing; guard += 1) {
    const entry = current(zone);
    const length = Math.max(1, entry.dur || 1);
    if (zone.pos < length) break;
    const over = zone.pos - length;
    if (stepNext(zone, true, rnd)) { zone.pos = over; event = "track"; continue; }
    zone.playing = false;
    zone.pos = 0;
    event = "ended";
    break;
  }
  return event;
}

export function setPos(zone, seconds) {
  const cur = current(zone);
  if (cur) zone.pos = Math.max(0, Math.min(seconds, Math.max(0, (cur.dur || 0) - 0.5)));
}

/** Move an upcoming entry (indexes are positions inside Up next, 0-based). Returns true when something moved. */
export function moveUpcoming(zone, from, to) {
  const base = zone.i + 1;
  const tail = zone.queue.slice(base);
  if (from < 0 || from >= tail.length || to < 0 || to >= tail.length || from === to) return false;
  const [item] = tail.splice(from, 1);
  tail.splice(to, 0, item);
  zone.queue = zone.queue.slice(0, base).concat(tail);
  zone.orig = tail.map((e) => e.uid);
  return true;
}

export function removeUpcoming(zone, index) {
  const at = zone.i + 1 + index;
  if (index < 0 || at >= zone.queue.length) return null;
  const [gone] = zone.queue.splice(at, 1);
  return { entry: gone, at };
}

export function clearUpcoming(zone) {
  const removed = zone.queue.slice(zone.i + 1);
  zone.queue = zone.queue.slice(0, zone.i + 1);
  zone.orig = [];
  return removed;
}

/** Put entries back (for Undo). */
export function restoreUpcoming(zone, entries, at) {
  const base = zone.i + 1;
  zone.queue.splice(Math.max(base, Math.min(at ?? base, zone.queue.length)), 0, ...entries);
  zone.orig = zone.queue.slice(base).map((e) => e.uid);
}

/** A Library file was deleted: drop its entries. Returns { stopped } when the current entry went with it. */
export function dropAsset(zone, assetId) {
  const cur = current(zone);
  const wasCurrent = Boolean(cur && cur.assetId === assetId);
  const before = zone.queue.length;
  const keepUntil = zone.queue.slice(0, zone.i + 1).filter((e) => e.assetId !== assetId).length;
  zone.queue = zone.queue.filter((e) => e.assetId !== assetId);
  if (zone.queue.length === before) return { stopped: false, changed: false };
  zone.orig = zone.queue.slice(zone.i + 1).map((e) => e.uid);
  if (wasCurrent) {
    zone.i = keepUntil - 1 + (keepUntil < zone.queue.length ? 1 : 0) > zone.queue.length - 1 ? zone.queue.length - 1 : keepUntil;
    zone.pos = 0;
    zone.playing = false;
    if (zone.queue.length === 0) zone.i = -1;
    return { stopped: true, changed: true };
  }
  zone.i = Math.max(-1, keepUntil - 1);
  return { stopped: false, changed: true };
}

/** Total seconds of a list of tracks. */
export const totalDur = (tracks) => tracks.reduce((n, t) => n + (t.dur || 0), 0);
