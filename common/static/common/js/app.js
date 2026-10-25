/* Entry point: wires up the shared behaviour on every page. Include once via common/_assets.html.
   Page-specific modules (journey, register, ...) are loaded by their own templates. */
import { initButtons } from './buttons.js';
import { initFeedback } from './feedback.js';
import { initValidation } from './validate.js';
import { initFormProblems } from './form-problems.js';
import { initReveal } from './reveal.js';
import { initNav } from './nav.js';

initButtons();
initFeedback();
initValidation();
initFormProblems();
initReveal();
initNav();
