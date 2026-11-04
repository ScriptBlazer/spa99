/* "Add a mobile" / "Change the mobile" on the lead and person pages (docs/features/whatsapp-design.md section 6).
 * The dialog posts in the background; a wrong number is told under the field, and a number that already belongs to someone says who.
 * When it saves, the Reach out card and the Mobile lines are swapped for the server's new ones, so the button becomes WhatsApp without a reload. */
import { toast } from './feedback.js';

export function initMobileDialog() {
  const form = document.querySelector('[data-mobile-form]');
  if (!form) return;
  const dialog = form.closest('dialog');
  const error = form.querySelector('[data-mobile-error]');
  const input = form.elements.mobile;
  const submit = form.querySelector('[type="submit"]');
  const show = (message, owner) => {
    error.replaceChildren();
    error.hidden = !message;
    if (!message) { input.removeAttribute('aria-invalid'); return; }
    error.append(document.createTextNode(message));
    if (owner && owner.url) {
      error.append(document.createTextNode(' '));
      const link = document.createElement('a');
      link.href = owner.url;
      link.textContent = `Open ${owner.name || 'him'}`;
      error.append(link);
    }
    input.setAttribute('aria-invalid', 'true');
    input.focus();
  };
  input.addEventListener('input', () => show(''));
  dialog.addEventListener('close', () => { show(''); });
  dialog.addEventListener('close', () => { input.value = ''; });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (submit.disabled) return;
    if (!input.value.trim()) { show('That does not look like a mobile number.'); return; }
    submit.disabled = true;
    submit.setAttribute('aria-busy', 'true');
    const label = submit.textContent;
    submit.textContent = 'Saving';
    try {
      const response = await fetch(form.action, { method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json', 'X-Requested-With': 'fetch' }, body: new FormData(form) });
      const data = await response.json().catch(() => null);
      if (response.ok && data && data.ok) {
        await refresh();
        dialog.close();
        toast('Mobile saved.');
        setTimeout(() => document.querySelector('[data-whatsapp-open]')?.focus(), 0); // the grey line he used is gone: focus goes to the new button
      } else {
        const errors = (data && data.errors) || {};
        const owner = errors.owner;
        const text = errors.mobile || errors.first_name || 'That does not look like a mobile number.';
        show(owner ? `This number is already on ${owner.name}.` : (text.includes('valid mobile') ? 'That does not look like a mobile number.' : text), owner);
      }
    } catch {
      show('That could not be saved. Try again.');
    } finally {
      submit.disabled = false;
      submit.removeAttribute('aria-busy');
      submit.textContent = label;
    }
  });

  /** Fetch this page again and take the parts that show the mobile. */
  async function refresh() {
    try {
      const response = await fetch(location.href, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
      const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
      for (const selector of ['[data-person-reach]', '[data-person-details]', '[data-person-line]', '[data-gold-more]']) {
        const fresh = doc.querySelector(selector);
        const old = document.querySelector(selector);
        if (fresh && old) old.replaceWith(document.importNode(fresh, true));
      }
      const newDialog = doc.querySelector('dialog[data-dialog="mobile"] h2');
      const title = dialog.querySelector('h2');
      if (newDialog && title) title.textContent = newDialog.textContent;
      const hint = doc.querySelector('dialog[data-dialog="mobile"] .o-mobile-hint');
      const here = dialog.querySelector('.o-mobile-hint');
      if (hint && here) here.textContent = hint.textContent;
    } catch { location.reload(); }
  }
}
