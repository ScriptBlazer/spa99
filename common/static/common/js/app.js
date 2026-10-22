/* Entry point: wires up the shared behaviour on every page. Include once via common/_assets.html. */
import { initButtons } from './buttons.js';
import { initConfirm } from './modal.js';
import { initMessages } from './messages.js';
import { initValidation } from './validate.js';

initButtons();
initConfirm();
initMessages();
initValidation();
