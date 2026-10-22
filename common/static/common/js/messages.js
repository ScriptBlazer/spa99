/* Success messages hide after 5 seconds; errors stay until closed. */

const SUCCESS_VISIBLE_MS = 5000;

function dismiss(element) {
  element.classList.add('is-hiding');
  setTimeout(() => element.remove(), 400);
}

function arm(element) {
  if (element.dataset.armed) return;
  element.dataset.armed = 'true';
  if (element.dataset.level === 'success') setTimeout(() => dismiss(element), SUCCESS_VISIBLE_MS);
  element.querySelector('[data-message-close]')?.addEventListener('click', () => dismiss(element));
}

export function showMessage(level, text) {
  const list = document.getElementById('messages');
  if (!list) return;
  const item = document.createElement('li');
  item.className = `message message-${level === 'success' ? 'success' : 'error'}`;
  item.dataset.level = level === 'success' ? 'success' : 'error';
  item.setAttribute('role', level === 'success' ? 'status' : 'alert');
  const span = document.createElement('span');
  span.textContent = text;
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'message-close';
  close.dataset.messageClose = '';
  close.setAttribute('aria-label', 'Close message');
  close.textContent = '×';
  item.append(span, close);
  list.append(item);
  arm(item);
}

export function initMessages(root = document) {
  root.querySelectorAll('[data-message]').forEach(arm);
}
