/* Entry point: wires up the shared behaviour on every page. Include once via common/_assets.html.
   Page-specific modules (journey, register, ...) are loaded by their own templates. */
import { initButtons } from './buttons.js';
import { initConfirm } from './modal.js';
import { initMessages } from './messages.js';
import { initValidation } from './validate.js';
import { initReveal } from './reveal.js';
import { initNav } from './nav.js';

initButtons();
initConfirm();
initMessages();
initValidation();
initReveal();
initNav();
