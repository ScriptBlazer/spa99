/* An unsent email, kept in this browser only (docs/features/email-chat-design.md section 2: "in that browser"; no server drafts this round).
 * Keyed by staff member and thread (or `new`), gone after 7 days, cleared on send and on sign out. Every call is wrapped: private mode and a full disk never break the page. */
const PREFIX = 'em-draft:';
const WEEK = 7 * 86400000;

const keyOf = (staff, key) => `${PREFIX}${staff}:${key}`;

export function loadDraft(staff, key) {
  try {
    const raw = localStorage.getItem(keyOf(staff, key));
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || Date.now() - (data.at || 0) > WEEK) { localStorage.removeItem(keyOf(staff, key)); return null; }
    return data;
  } catch { return null; }
}

export function saveDraft(staff, key, data) {
  try { localStorage.setItem(keyOf(staff, key), JSON.stringify({ ...data, at: Date.now() })); } catch { /* private mode or full */ }
}

export function clearDraft(staff, key) {
  try { localStorage.removeItem(keyOf(staff, key)); } catch { /* private mode */ }
}

/** Sign out takes this browser's drafts with it. Called once, from every Office page. */
export function clearDraftsOnSignOut() {
  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !/\/logout\/?$/.test(new URL(form.action, location.href).pathname)) return;
    try {
      for (const key of Object.keys(localStorage)) if (key.startsWith(PREFIX)) localStorage.removeItem(key);
    } catch { /* private mode */ }
  });
}
