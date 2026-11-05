/* The phone keyboard, used by the WhatsApp chat (docs/features/whatsapp-design.md section 1).
 * `100dvh` is not enough: iOS does not shrink dvh for the keyboard and ignores interactive-widget. So a visualViewport listener sets --wa-vh and --wa-top on the
 * pane (the CSS reads them) and `data-keyboard` when the viewport shrank by more than 120px. Works the same on Android. One script, not two copies. */
const phone = () => window.matchMedia('(max-width: 63.99em)').matches;

/** Start following the keyboard for `root`. `onChange(keyboard, wasKeyboard)` runs when it comes or goes. Stops when `signal` aborts. */
export function bindKeyboard(root, { signal, onChange } = {}) {
  const vv = window.visualViewport;
  if (!vv) return;
  let fullH = window.innerHeight;
  const apply = () => {
    if (!phone()) {
      root.style.removeProperty('--wa-vh'); root.style.removeProperty('--wa-top');
      document.body.removeAttribute('data-keyboard'); root.removeAttribute('data-keyboard');
      return;
    }
    if (!root.contains(document.activeElement) || document.activeElement === document.body) fullH = Math.max(window.innerHeight, vv.height);
    const keyboard = fullH - vv.height > 120;
    const was = root.hasAttribute('data-keyboard');
    root.style.setProperty('--wa-vh', `${Math.round(vv.height)}px`);
    root.style.setProperty('--wa-top', `${Math.round(vv.offsetTop)}px`);
    root.toggleAttribute('data-keyboard', keyboard);
    document.body.toggleAttribute('data-keyboard', keyboard);
    if (keyboard !== was && onChange) onChange(keyboard, was);
  };
  vv.addEventListener('resize', apply, { signal });
  vv.addEventListener('scroll', apply, { signal });
  window.addEventListener('orientationchange', () => setTimeout(apply, 300), { signal });
  apply();
}

/** Leaving a pane: nothing of the keyboard handling stays on the page. */
export function releaseKeyboard() {
  document.body.removeAttribute('data-keyboard');
}
