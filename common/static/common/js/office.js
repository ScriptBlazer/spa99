/* Entry point for the Office (every Office page). Shared behaviour first (buttons, toasts and the modal, reveal), then the Office's own.
   Analytics adds office-charts.js on top of this. */
import { initButtons } from './buttons.js';
import { initFeedback } from './feedback.js';
import { initReveal } from './reveal.js';
import { initOfficeUi } from './office-ui.js';
import { initSwap } from './office-swap.js';
import { initCounts } from './office-dashboard.js';

initButtons();
initFeedback();
initReveal();
initOfficeUi();
initSwap();
initCounts();
