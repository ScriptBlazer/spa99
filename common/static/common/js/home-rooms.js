/* Home "What's inside": hovering or focusing a room in the index swaps the preview picture (desktop, fine pointer). The index itself
   is plain links; without this script the preview simply stays on the first room. */
const frame = document.querySelector('[data-preview]');
const fine = matchMedia('(min-width: 64em) and (hover: hover) and (pointer: fine)');

if (frame) {
  const pics = [...frame.querySelectorAll('[data-preview-pic]')];
  const show = (slug) => {
    const next = pics.find((p) => p.dataset.previewPic === slug);
    if (!next || !fine.matches) return; // rooms without a picture keep the current one
    pics.forEach((p) => p.classList.toggle('is-active', p === next));
  };
  document.querySelectorAll('[data-room]').forEach((link) => {
    link.addEventListener('pointerenter', () => show(link.dataset.room));
    link.addEventListener('focus', () => show(link.dataset.room));
  });
}
