/* Small shared helpers for the pages that talk to the JSON endpoints (journey, Gold application). */

export function csrfToken() {
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : '';
}

export async function getJson(url) {
  const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
  if (!response.ok) throw Object.assign(new Error(`GET ${url} ${response.status}`), { status: response.status });
  return response.json();
}

/** POST JSON. Resolves { ok, status, data }. Network errors reject. */
export async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRFToken': csrfToken() },
    body: JSON.stringify(body),
  });
  let data = null;
  try { data = await response.json(); } catch { /* an empty or non-JSON body */ }
  return { ok: response.ok, status: response.status, data };
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const RETRY_DELAYS_MS = [400, 1200, 2500]; // quiet retries, then the caller shows its message

/** POST with up to three quiet retries for network trouble and server errors. Client errors (4xx) are not retried. */
export async function postWithRetry(url, body) {
  let last = null;
  for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt += 1) {
    try {
      last = await postJson(url, body);
      if (last.ok || last.data?.needs_email || (last.status >= 400 && last.status < 500 && last.status !== 429 && last.status !== 403)) return last;
    } catch { last = null; }
    if (attempt < RETRY_DELAYS_MS.length) await sleep(RETRY_DELAYS_MS[attempt]);
  }
  return last || { ok: false, status: 0, data: null };
}

/** Option labels are "Label (second line)". Mirrors pages/templatetags/pages_tags.py. */
export function splitLabel(label) {
  const index = (label || '').indexOf(' (');
  if (index === -1) return { main: label || '', sub: '' };
  return { main: label.slice(0, index).trim(), sub: label.slice(index + 2).replace(/\)\s*$/, '').trim() };
}

export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on')) node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, value);
  }
  children.flat().forEach((child) => { if (child !== null && child !== undefined && child !== false) node.append(child); });
  return node;
}
