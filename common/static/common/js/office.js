/* Entry point for the Office (every Office page). Shared behaviour first (buttons, confirm modal, messages, reveal), then the Office's own.
   Analytics adds office-charts.js on top of this. */
import { initButtons } from './buttons.js';
import { initConfirm } from './modal.js';
import { initMessages } from './messages.js';
import { initReveal } from './reveal.js';
import { initOfficeUi } from './office-ui.js';
import { initSwap } from './office-swap.js';
import { initCounts } from './office-dashboard.js';

initButtons();
initConfirm();
initMessages();
initReveal();
initOfficeUi();
initSwap();
initCounts();
