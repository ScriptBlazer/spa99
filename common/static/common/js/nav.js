/* The mobile menu: a full-screen dialog (focus is trapped by the browser, Escape closes, focus returns to "Menu").
   It opens and closes instantly (BRAND section 7: navigation is not animated). */

export function initNav() {
  const menu = document.querySelector('[data-menu]');
  if (!menu) return;
  const opener = document.querySelector('[data-menu-open]');
  const close = () => { if (menu.open) menu.close(); };
  opener?.addEventListener('click', () => {
    if (!menu.open) menu.showModal();
    opener.setAttribute('aria-expanded', 'true');
  });
  menu.querySelector('[data-menu-close]')?.addEventListener('click', close);
  menu.addEventListener('close', () => { opener?.setAttribute('aria-expanded', 'false'); opener?.focus(); });
  menu.addEventListener('click', (event) => { if (event.target.closest('a')) close(); }); // same-page links
  // Growing past the phone layout with the menu open: close it.
  window.matchMedia('(min-width: 64em)').addEventListener('change', (event) => { if (event.matches) close(); });
}
