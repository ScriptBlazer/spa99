/* System sign-in and unlock (no shell): the shared toasts and modal, and the form-problems dialog. */
import { initFeedback } from './feedback.js';
import { initFormProblems } from './form-problems.js';

initFeedback();
initFormProblems();

/* Wrong-try wait (docs/features/system.md): the server renders the seconds left; this only ticks them and re-enables the
   form at 0 without a reload. The server stays the judge: a try is checked there again. Announced once, not every second. */
document.querySelectorAll('[data-lockout]').forEach((box) => {
  const seconds = Number(box.dataset.seconds) || 0;
  const time = box.querySelector('[data-lockout-time]');
  const form = document.querySelector('form[data-problems]');
  const end = performance.now() + seconds * 1000; // the browser's own clock, never the wall clock
  const clock = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  const timer = setInterval(() => {
    const left = Math.max(0, Math.ceil((end - performance.now()) / 1000));
    if (time) time.textContent = clock(left);
    if (left > 0) return;
    clearInterval(timer);
    form?.querySelectorAll('input:disabled, button:disabled').forEach((el) => { el.disabled = false; });
    form?.querySelector('input:not([type=hidden])')?.focus();
    box.querySelector('[data-lockout-announce]').textContent = 'You can try again now.';
    box.querySelector('[data-lockout-visible]').textContent = 'You can try again now.';
    box.classList.remove('error');
  }, 250);
});
