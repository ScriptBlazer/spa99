/* The Library on the server: real files, real playlists. This (and library.js) are the only modules that talk to the server.
   Everything else reads the cache kept here. Writes are POSTs with the CSRF token. Pretend state never goes through here. */
import { bus } from "./core.js";

export const L = { assets: [], playlists: [], loaded: false, loading: null, loadedAt: 0, summary: { used_bytes: 0, max_bytes: 0 }, error: "" };
const URLS = { assets: "/library/assets/", playlists: "/library/playlists/" };

export function csrfToken() {
  const m = /(?:^|; )csrftoken=([^;]+)/.exec(document.cookie);
  if (m) return decodeURIComponent(m[1]);
  const input = document.querySelector("input[name=csrfmiddlewaretoken]");
  return input ? input.value : "";
}

async function parse(response) {
  let data = {};
  try { data = await response.json(); } catch (e) { data = {}; }
  if (!response.ok) throw Object.assign(new Error(data.error || "Something went wrong. Try again."), { status: response.status });
  return data;
}

export async function getJSON(url) {
  return parse(await fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" }));
}

export async function postJSON(url, body = {}) {
  return parse(await fetch(url, {
    method: "POST", credentials: "same-origin", body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(), Accept: "application/json" },
  }));
}

export async function postForm(url, form) {
  return parse(await fetch(url, { method: "POST", credentials: "same-origin", body: form, headers: { "X-CSRFToken": csrfToken(), Accept: "application/json" } }));
}

export function loadLibrary(force = false) {
  if (L.loading) return L.loading;
  const fresh = L.loaded && Date.now() - L.loadedAt < 45 * 60 * 1000;  // signed links last an hour on live
  if (fresh && !force) return Promise.resolve(L);
  L.loading = Promise.all([getJSON(URLS.assets), getJSON(URLS.playlists)]).then(([a, p]) => {
    L.assets = a.assets;
    L.playlists = p.playlists;
    L.summary = a.library || L.summary;
    L.loaded = true;
    L.loadedAt = Date.now();
    L.error = "";
    bus.emit("library", L);
    return L;
  }).catch((error) => { L.error = error.message; return L; }).finally(() => { L.loading = null; });
  return L.loading;
}

export const asset = (id) => L.assets.find((a) => a.id === id) || null;
export const playlist = (id) => L.playlists.find((p) => p.id === id) || null;

export function replaceAsset(data) {
  const i = L.assets.findIndex((a) => a.id === data.id);
  if (i >= 0) L.assets[i] = { ...L.assets[i], ...data, playlists: data.playlists || L.assets[i].playlists };
  else L.assets.unshift(data);
  L.loadedAt = Date.now();
}

export function replacePlaylist(data) {
  const i = L.playlists.findIndex((p) => p.id === data.id);
  if (i >= 0) L.playlists[i] = data; else L.playlists.push(data);
  L.playlists.sort((a, b) => a.name.localeCompare(b.name));
  refreshUsedIn();
}

/** The playlists a file is in, from the cached playlists (kept in step with every playlist change). */
export function refreshUsedIn() {
  for (const a of L.assets) {
    a.playlists = L.playlists.filter((p) => p.items.some((i) => i.asset.id === a.id)).map((p) => ({ id: p.id, name: p.name, kind: p.kind }));
  }
}

export function dropAsset(id) {
  L.assets = L.assets.filter((a) => a.id !== id);
  for (const p of L.playlists) p.items = p.items.filter((i) => i.asset.id !== id).map((i, n) => ({ ...i, position: n + 1 }));
  refreshUsedIn();
  bus.emit("asset-deleted", id);
}

export function dropPlaylist(id) {
  L.playlists = L.playlists.filter((p) => p.id !== id);
  refreshUsedIn();
  bus.emit("playlist-deleted", id);
}

/** Seconds for a track or picture: the browser-measured length; images use their time on screen. */
export const itemSeconds = (item) => (item.asset.kind === "image" ? item.seconds || 8 : item.asset.duration_seconds || 10);
export const playlistSeconds = (p) => p.items.reduce((n, i) => n + (p.kind === "music" ? i.asset.duration_seconds || 0 : itemSeconds(i)), 0);
