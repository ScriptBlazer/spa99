/* Entry point for the Office (every Office page). Shared behaviour first (buttons, toasts and the modal, reveal), then the Office's own.
   Analytics adds office-charts.js on top of this. */
import { initButtons } from './buttons.js';
import { initFeedback } from './feedback.js';
import { initReveal } from './reveal.js';
import { initFormProblems } from './form-problems.js';
import { initOfficeUi } from './office-ui.js';
import { initSwap } from './office-swap.js';
import { initCounts } from './office-dashboard.js';
import { initTools } from './office-tools.js';
import { initClamp } from './office-clamp.js';
import { initApp } from './office-app.js';
import { initMobileDialog } from './office-mobile.js';

initButtons();
initFeedback();
initFormProblems();
initReveal();
initOfficeUi();
initSwap();
initCounts();
initTools();
initClamp();
initApp();
initMobileDialog();
