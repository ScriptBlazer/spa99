/* Ask us: the chat pill and panel (docs/design/ASK-US-CHAT.md; backend contract in docs/features/ai-chat.md).
 *
 * Markup: chat/templates/chat/_chat.html (the pill, the <dialog>, and <template>s for the hand-off and email blocks).
 * Flow: the first open calls GET /chat/state/ (it sets the cookies every other call needs). A message is POSTed and the reply
 * streams back as server-sent events (fetch + ReadableStream, because EventSource cannot POST). Model text is never put into
 * innerHTML: replies are parsed into a small set of nodes (paragraphs, lists, bold, links) with textContent only.
 * The server keeps the conversation (conversation_id), so a refresh loses only the open panel, never the visitor's choices.
 */
import { csrfToken, el } from './api.js';

const COPY = {
  wait: 'One moment',
  failed: 'That answer did not come through.',
  retry: 'Try again',
  rate: 'You have asked a lot in a short time. Please wait a few minutes, or message our team.',
  full: 'This conversation is full. Start again, or message our team.',
  startAgain: 'Start again',
  unavailableLine: 'Our assistant is not available just now. Our team will answer you directly.',
  welcomeTitle: 'Ask us anything.',
  welcomeLine: 'The spa, memberships, hours or the Gold Card.',
  unavailableTitle: 'Ask us.',
  limitReached: 'That is the limit for one message.',
  emailSaveFailed: 'We couldn’t save that just now. Please try again.',
  emailDone: 'Thank you. Prices are now shown.',
  saving: 'One moment',
  you: 'You said: ',
  bot: 'Spa 99: ',
};
const MAX_FAILS = 2;

const root = document.querySelector('[data-chat]');
const pill = document.querySelector('[data-chat-open]');

if (root && pill && typeof root.showModal === 'function') start();

function start() {
  const $ = (selector) => root.querySelector(selector);
  const scroller = $('[data-chat-scroll]');
  const log = $('[data-chat-log]');
  const welcome = $('[data-chat-welcome]');
  const welcomeTitle = $('[data-chat-welcome-title]');
  const welcomeLine = $('[data-chat-welcome-line]');
  const chips = $('[data-chat-chips]');
  const person = $('[data-chat-person]');
  const form = $('[data-chat-form]');
  const input = $('[data-chat-input]');
  const send = $('[data-chat-send]');
  const limit = $('[data-chat-limit]');
  const privacy = $('[data-chat-privacy]');
  const offline = $('[data-chat-offline]');
  const live = $('[data-chat-live]');
  const newButton = $('[data-chat-new]');
  const title = $('#ask-us-title');
  const nameNode = $('[data-chat-name]');
  // the welcome words come from System > Assistant (rendered into the page); New chat puts them back
  COPY.welcomeTitle = welcomeTitle.textContent.trim() || COPY.welcomeTitle;
  COPY.welcomeLine = welcomeLine.textContent.trim() || COPY.welcomeLine;
  const urls = { state: root.dataset.stateUrl, message: root.dataset.messageUrl, email: root.dataset.emailUrl };
  const phone = matchMedia('(max-width: 63.99em)');
  const coarse = matchMedia('(pointer: coarse)');
  const initialChips = chips.innerHTML;

  const template = (name) => root.querySelector(`[data-chat-tpl="${name}"]`).content.firstElementChild.cloneNode(true);
  const baseHandoff = (() => {
    const block = template('handoff');
    return {
      whatsapp_url: block.querySelector('[data-chat-whatsapp]').getAttribute('href') || '',
      mailto: block.querySelector('[data-chat-mail]').getAttribute('href') || '',
      email: root.dataset.contactEmail || block.querySelector('[data-chat-address]').textContent.trim(),
    };
  })();

  const st = {
    loaded: false, loading: null, conversationId: null, maxChars: Number(input.getAttribute('maxlength')) || 500,
    busy: false, unavailable: false, ended: false, fails: 0, exchanges: 0, started: false, last: null, abort: null, handoff: { ...baseHandoff },
  };

  /* ---------- the pill: shown after the first half screen (or at once on a short page), then stays ---------- */
  let shown = false;
  const reveal = () => { if (shown) return; shown = true; pill.hidden = false; requestAnimationFrame(() => pill.setAttribute('data-shown', '')); };
  const checkScroll = () => { if (!shown && window.scrollY >= window.innerHeight * 0.5) reveal(); };
  const checkShort = () => { if (!shown && document.documentElement.scrollHeight < window.innerHeight * 1.5) reveal(); };
  window.addEventListener('scroll', checkScroll, { passive: true });
  window.addEventListener('resize', checkScroll, { passive: true });
  const afterLoad = () => { checkScroll(); setTimeout(() => { checkShort(); checkScroll(); }, 800); }; // pinned scenes settle their height first
  if (document.readyState === 'complete') afterLoad(); else window.addEventListener('load', afterLoad, { once: true });
  // on a touch screen the pill never floats over a page field above the keyboard
  const isField = (node) => node instanceof Element && node.matches('input:not([type=checkbox]):not([type=radio]), textarea, select, [contenteditable]') && !root.contains(node);
  document.addEventListener('focusin', (event) => { if (coarse.matches && isField(event.target)) pill.setAttribute('data-away', ''); });
  document.addEventListener('focusout', () => pill.removeAttribute('data-away'));

  /* ---------- small helpers ---------- */
  const announce = (text) => { live.textContent = ''; setTimeout(() => { live.textContent = text; }, 60); };
  const nearBottom = () => scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight <= 80;
  const toBottom = () => { scroller.scrollTop = scroller.scrollHeight; };
  const follow = (was) => { if (was) toBottom(); };
  const add = (node) => { const was = nearBottom(); log.append(node); follow(was); return node; };
  const note = (text, ...extra) => add(el('p', { class: 'chat-note', text }, ...extra));
  const linkButton = (label, onClick) => el('button', { type: 'button', class: 'chat-link', onClick, text: label });

  function setBusy(value) {
    st.busy = value;
    send.setAttribute('aria-disabled', String(value || !navigator.onLine));
    log.setAttribute('aria-busy', String(value));
  }
  function updateOffline() {
    const off = !navigator.onLine;
    offline.hidden = !off;
    send.setAttribute('aria-disabled', String(off || st.busy));
  }
  window.addEventListener('online', updateOffline);
  window.addEventListener('offline', updateOffline);

  /* ---------- light markdown, as nodes ---------- */
  /** Only our own pages, mail to our own address, and the WhatsApp link we gave the panel. Anything else is shown as plain text. */
  const WHATSAPP_HOSTS = new Set(['wa.me', 'api.whatsapp.com']);
  function safeLink(raw) {
    if (/^\/(?!\/)/.test(raw)) return { href: raw, external: false };
    try {
      const url = new URL(raw);
      if (url.protocol === 'mailto:') {
        const to = decodeURIComponent(url.pathname).toLowerCase();
        const own = [st.handoff.email, baseHandoff.email].filter(Boolean).map((a) => a.toLowerCase());
        return to && own.includes(to) ? { href: url.href, external: true } : null;
      }
      if (url.protocol !== 'https:' && url.protocol !== 'http:') return null;
      if (url.origin === location.origin) return { href: url.href, external: false };
      const given = [st.handoff.whatsapp_url, baseHandoff.whatsapp_url].filter(Boolean).map((u) => { try { return new URL(u).host; } catch { return ''; } });
      if (url.protocol === 'https:' && WHATSAPP_HOSTS.has(url.host) && given.some((h) => WHATSAPP_HOSTS.has(h) && h === url.host)) return { href: url.href, external: true };
    } catch { /* not a URL */ }
    return null;
  }
  function inline(text, parent) {
    const pattern = /\*\*([^*\n]+?)\*\*|\[([^\]\n]+)\]\(([^)\s]+)\)/g;
    let last = 0;
    let match;
    while ((match = pattern.exec(text))) {
      if (match.index > last) parent.append(text.slice(last, match.index));
      if (match[1] !== undefined) parent.append(el('strong', { text: match[1] }));
      else {
        const link = safeLink(match[3]);
        if (link) parent.append(el('a', { href: link.href, text: match[2], target: link.external ? '_blank' : false, rel: link.external ? 'noopener' : false, 'data-chat-link': link.external ? false : '' }));
        else parent.append(match[2]);
      }
      last = pattern.lastIndex;
    }
    if (last < text.length) parent.append(text.slice(last));
  }
  function renderMarkdown(container, text) {
    container.replaceChildren();
    let list = null;
    let para = null;
    for (const line of text.replace(/\r\n?/g, '\n').split('\n')) {
      if (!line.trim()) { list = null; para = null; continue; }
      const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
      const number = bullet ? null : /^\s*\d+[.)]\s+(.*)$/.exec(line);
      if (bullet || number) {
        const tag = bullet ? 'ul' : 'ol';
        if (!list || list.tagName.toLowerCase() !== tag) { list = el(tag); container.append(list); }
        para = null;
        const item = el('li');
        inline((bullet || number)[1], item);
        list.append(item);
        continue;
      }
      list = null;
      const heading = /^#{1,6}\s+(.*)$/.exec(line);
      if (heading) { para = null; const p = el('p'); const strong = el('strong'); inline(heading[1], strong); p.append(strong); container.append(p); continue; }
      if (!para) { para = el('p'); container.append(para); } else para.append(el('br'));
      inline(line.trim(), para);
    }
  }

  /* ---------- messages ---------- */
  function showConversation() {
    if (st.started) return;
    st.started = true;
    chips.hidden = true;
    person.hidden = true;
    if (!st.unavailable) welcome.hidden = true;
    newButton.hidden = st.unavailable;
  }
  function addYou(text) {
    showConversation();
    const node = el('div', { class: 'chat-msg chat-msg--you' }, el('span', { class: 'sr-only', text: COPY.you }), text);
    log.append(node);
    toBottom();
  }
  function addBot() {
    const body = el('div', { class: 'chat-msg-body' });
    const node = el('div', { class: 'chat-msg chat-msg--bot' }, el('span', { class: 'sr-only', text: COPY.bot }), body);
    add(node);
    return { node, body };
  }

  function handoffBlock(data) {
    log.querySelectorAll('.chat-handoff').forEach((old) => old.remove());
    const d = { ...st.handoff, ...(data || {}) };
    const block = template('handoff');
    const whatsapp = block.querySelector('[data-chat-whatsapp]');
    const mail = block.querySelector('[data-chat-mail]');
    const address = block.querySelector('[data-chat-address]');
    if (d.whatsapp_url) whatsapp.href = d.whatsapp_url; else { whatsapp.remove(); mail.classList.replace('btn-secondary', 'btn-primary'); }
    const mailto = d.mailto || (d.email ? `mailto:${d.email}?subject=A%20question%20for%20Spa%2099` : '');
    if (mailto) mail.href = mailto; else mail.remove();
    if (d.email) address.textContent = d.email; else address.remove();
    return add(block);
  }
  const startAgainButton = () => el('button', { type: 'button', class: 'btn btn-secondary', onClick: newChat, text: COPY.startAgain });

  function setUnavailable(handoff, { wipe = true } = {}) {
    st.unavailable = true;
    root.dataset.state = 'unavailable';
    if (wipe) {
      st.started = false;
      log.replaceChildren();
      welcome.hidden = false;
      welcomeTitle.textContent = COPY.unavailableTitle;
      welcomeLine.textContent = COPY.unavailableLine;
    }
    chips.hidden = true;
    person.hidden = true;
    form.hidden = true;
    newButton.hidden = true;
    handoffBlock(handoff);
  }

  /* ---------- the compose field ---------- */
  function grow() {
    input.style.height = 'auto';
    input.style.height = `${input.scrollHeight}px`;
  }
  function updateLimit() {
    const left = st.maxChars - input.value.length;
    if (left > 100) { limit.hidden = true; return; }
    limit.hidden = false;
    limit.textContent = left <= 0 ? COPY.limitReached : `${left} character${left === 1 ? '' : 's'} left`;
  }
  input.addEventListener('input', () => { grow(); updateLimit(); });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); form.requestSubmit(); }
  });
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || st.busy || !navigator.onLine || st.unavailable || st.ended) return;
    input.value = '';
    grow();
    updateLimit();
    ask(text);
  });

  chips.addEventListener('click', (event) => {
    const chip = event.target.closest('[data-chat-chip]');
    if (chip && !st.busy && navigator.onLine) ask(chip.textContent.trim());
  });
  root.querySelector('[data-chat-person-open]').addEventListener('click', () => {
    handoffBlock();
    const block = log.querySelector('.chat-handoff');
    block?.scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  });

  /* ---------- state (sets the cookies the other calls need) ---------- */
  function loadState() {
    if (st.loaded) return Promise.resolve();
    st.loading ||= fetch(urls.state, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(async (response) => {
        if (response.status === 404) { setUnavailable(null); st.loaded = true; return; }
        if (!response.ok) throw new Error(`state ${response.status}`);
        const data = await response.json();
        st.loaded = true;
        if (data.max_message_chars) { st.maxChars = data.max_message_chars; input.setAttribute('maxlength', String(st.maxChars)); }
        const assistant = data.assistant || data.chat_assistant;
        if (assistant) {
          if (assistant.name) nameNode.textContent = assistant.name;
          if (assistant.welcome_heading) COPY.welcomeTitle = assistant.welcome_heading;
          if (assistant.welcome_line) COPY.welcomeLine = assistant.welcome_line;
          if (!st.started && !st.unavailable) { welcomeTitle.textContent = COPY.welcomeTitle; welcomeLine.textContent = COPY.welcomeLine; }
        }
        if (data.handoff) st.handoff = { ...st.handoff, ...data.handoff };
        if (data.privacy_url && privacy.querySelector('a')) privacy.querySelector('a').href = `${data.privacy_url.replace(/#.*$/, '')}#chat`;
        if (data.enabled === false || data.capped) setUnavailable(data.handoff);
      })
      .finally(() => { st.loading = null; });
    return st.loading;
  }

  /* ---------- sending and streaming ---------- */
  function ask(text) {
    st.last = { text, retry: false };
    addYou(text);
    return run(st.last);
  }

  async function run(request, { sessionRetried = false } = {}) {
    setBusy(true);
    const controller = new AbortController();
    st.abort = controller;
    const bot = addBot();
    const turn = { reply: '', steps: [], handoff: null, offerEmail: false, error: null, done: null };
    let pending = 0;
    let waitNode = null;
    const waitTimer = setTimeout(() => {
      if (!turn.reply && !turn.error) { waitNode = el('p', { class: 'chat-wait', text: COPY.wait }); bot.body.append(waitNode); follow(true); }
    }, 300);
    const draw = () => {
      pending = 0;
      const was = nearBottom();
      if (turn.reply) renderMarkdown(bot.body, turn.reply);
      follow(was);
    };
    const schedule = () => { if (!pending) pending = requestAnimationFrame(draw); };
    const cleanup = () => { clearTimeout(waitTimer); if (pending) cancelAnimationFrame(pending); pending = 0; };
    const dropBot = () => { cleanup(); bot.node.remove(); };

    try {
      await loadState();
      if (st.unavailable) { dropBot(); return; }
      const body = request.retry ? { retry: true } : { message: request.text };
      if (st.conversationId) body.conversation_id = st.conversationId;
      const response = await fetch(urls.message, {
        method: 'POST', credentials: 'same-origin', signal: controller.signal,
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream, application/json', 'X-CSRFToken': csrfToken() },
        body: JSON.stringify(body),
      });
      const header = response.headers.get('X-Chat-Conversation');
      if (header) st.conversationId = header;
      if (!response.ok || !(response.headers.get('Content-Type') || '').includes('text/event-stream')) {
        dropBot();
        let data = null;
        try { data = await response.json(); } catch { /* not JSON */ }
        if (response.status === 403 && data?.code === 'no_session' && !sessionRetried) {
          st.loaded = false;
          return await run(request, { sessionRetried: true });
        }
        refusal(response.status, data);
        return;
      }
      await readStream(response, (name, data) => handle(name, data, turn, schedule));
      cleanup();
      draw();
      finish(bot, turn);
    } catch (error) {
      if (error?.name === 'AbortError') { dropBot(); return; }
      cleanup();
      if (turn.done) finish(bot, turn); else failed(bot, turn);
    } finally {
      cleanup();
      if (st.abort === controller) { st.abort = null; setBusy(false); }
    }
  }

  function handle(name, data, turn, schedule) {
    if (name === 'delta') { turn.reply += String(data.text ?? ''); schedule(); }
    else if (name === 'next_steps') turn.steps = Array.isArray(data.steps) ? data.steps.slice(0, 2) : [];
    else if (name === 'handoff') turn.handoff = data;
    else if (name === 'offer_email') turn.offerEmail = true;
    else if (name === 'error') turn.error = data;
    else if (name === 'done') turn.done = data;
  }

  /** Parses `event:` / `data:` lines out of the stream. Chunks can split anywhere: a line, a blank line, even a CRLF. */
  async function readStream(response, onEvent) {
    const dispatch = (block) => {
      let name = 'message';
      const dataLines = [];
      for (const line of block.split('\n')) {
        if (!line || line.startsWith(':')) continue;
        const colon = line.indexOf(':');
        const field = colon === -1 ? line : line.slice(0, colon);
        const value = colon === -1 ? '' : line.slice(colon + 1).replace(/^ /, '');
        if (field === 'event') name = value; else if (field === 'data') dataLines.push(value);
      }
      if (!dataLines.length) return;
      let data;
      try { data = JSON.parse(dataLines.join('\n')); } catch { return; }
      onEvent(name, data && typeof data === 'object' ? data : {});
    };
    let raw = '';
    let text = '';
    const feed = (chunk, final) => {
      raw += chunk;
      const keep = !final && raw.endsWith('\r') ? 1 : 0; // a lone CR may be the first half of CRLF
      text += raw.slice(0, raw.length - keep).replace(/\r\n?/g, '\n');
      raw = raw.slice(raw.length - keep);
      let end;
      while ((end = text.indexOf('\n\n')) !== -1) { dispatch(text.slice(0, end)); text = text.slice(end + 2); }
      if (final && text.trim()) { dispatch(text); text = ''; }
    };
    const decoder = new TextDecoder();
    if (!response.body?.getReader) { feed(await response.text(), true); return; }
    const reader = response.body.getReader();
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      feed(decoder.decode(value, { stream: true }), false);
    }
    feed(decoder.decode(), true);
  }

  function refusal(status, data) {
    const handoff = data?.handoff;
    if (status === 429) { note(COPY.rate); handoffBlock(handoff); announce(COPY.rate); return; }
    if (status === 409) {
      st.ended = true;
      note(COPY.full, startAgainButton());
      handoffBlock(handoff);
      form.hidden = true;
      announce(COPY.full);
      return;
    }
    if (status === 400) {
      if (data?.code === 'too_long') { limit.hidden = false; limit.textContent = COPY.limitReached; }
      if (data?.code === 'nothing_pending') log.querySelectorAll('.chat-email').forEach((node) => node.remove());
      return;
    }
    setUnavailable(handoff, { wipe: st.exchanges === 0 }); // 403 (other), 404, 503: the visitor never sees why
  }

  function failed(bot, turn) {
    st.fails += 1;
    if (!turn.reply) bot.node.remove();
    announce(COPY.failed);
    if (st.fails >= MAX_FAILS || st.last?.retry) { note(COPY.failed); handoffBlock(turn.handoff); return; }
    const retry = linkButton(COPY.retry, () => { notice.remove(); bot.node.remove(); run({ ...st.last }); });
    const notice = note(COPY.failed, ' ', retry);
  }

  function finish(bot, turn) {
    const { done } = turn;
    if (!done) { failed(bot, turn); return; }
    st.fails = 0;
    if (done.conversation_id) st.conversationId = done.conversation_id;
    if (turn.error && !turn.reply) { bot.body.replaceChildren(el('p', { text: String(turn.error.message || '') })); }
    if (!turn.reply && !turn.error) bot.node.remove();
    const text = turn.reply || turn.error?.message || '';
    if (text) announce(text.replace(/\*\*|\[([^\]]*)\]\([^)]*\)/g, '$1'));

    const unavailable = turn.error?.reason === 'unavailable';
    if (unavailable && st.exchanges === 0) { st.exchanges += 1; setUnavailable(turn.handoff, { wipe: true }); return; }
    st.exchanges += 1;

    if (turn.steps.length) {
      const steps = el('div', { class: 'chat-steps' });
      for (const step of turn.steps) {
        const link = safeLink(step.url || '');
        if (link && step.label) steps.append(el('a', { class: 'btn btn-secondary btn-sm', href: link.href, text: step.label, 'data-chat-link': '' }));
      }
      if (steps.children.length) bot.node.append(steps);
    }
    if (done.off_topic && Array.isArray(done.suggested) && done.suggested.length) {
      const list = el('ul', { class: 'chat-chips' }, done.suggested.slice(0, 4).map((q) => el('li', {}, el('button', { type: 'button', class: 'chat-chip', 'data-chat-chip': '', text: q }))));
      list.addEventListener('click', (event) => {
        const chip = event.target.closest('[data-chat-chip]');
        if (chip && !st.busy && navigator.onLine) { list.remove(); ask(chip.textContent.trim()); }
      });
      bot.node.append(list);
    }
    if (turn.offerEmail && !log.querySelector('.chat-email')) emailBlock();
    if (turn.handoff || done.ended || unavailable) handoffBlock(turn.handoff);
    if (done.ended) {
      st.ended = true;
      form.hidden = true;
      add(startAgainButton());
    }
    if (unavailable) { st.unavailable = true; form.hidden = true; root.dataset.state = 'unavailable'; }
  }

  /* ---------- email for prices ---------- */
  function emailBlock() {
    const block = template('email');
    const email = block.querySelector('[name=email]');
    const consent = block.querySelector('[name=consent]');
    const emailMsg = block.querySelector('[data-error-for=email]');
    const consentMsg = block.querySelector('[data-error-for=consent]');
    const save = block.querySelector('[data-chat-email-save]');
    const mark = (slot, message) => { slot.textContent = message || ''; slot.dataset.state = message ? 'error' : 'hint'; };
    email.addEventListener('input', () => { mark(emailMsg, ''); email.removeAttribute('aria-invalid'); });
    consent.addEventListener('change', () => { mark(consentMsg, ''); consent.removeAttribute('aria-invalid'); });
    block.querySelector('[data-chat-email-skip]').addEventListener('click', () => { block.remove(); input.focus({ preventScroll: true }); });
    block.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (save.disabled) return;
      const label = save.textContent;
      save.disabled = true;
      save.setAttribute('aria-busy', 'true');
      save.textContent = COPY.saving;
      let reply = null;
      try {
        const response = await fetch(urls.email, {
          method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRFToken': csrfToken() },
          body: JSON.stringify({ conversation_id: st.conversationId || undefined, email: email.value, consent: consent.checked, website: block.querySelector('[name=website]').value }),
        });
        let data = null;
        try { data = await response.json(); } catch { /* not JSON */ }
        reply = { ok: response.ok, status: response.status, data };
      } catch { /* network */ }
      save.disabled = false;
      save.removeAttribute('aria-busy');
      save.textContent = label;
      if (reply?.ok && reply.data?.saved) {
        if (reply.data.conversation_id) st.conversationId = reply.data.conversation_id;
        const thanks = el('p', { class: 'chat-note', text: COPY.emailDone });
        block.replaceWith(thanks);
        announce(COPY.emailDone);
        if (reply.data.retry && !st.busy) { st.last = { text: '', retry: true }; run(st.last); }
        return;
      }
      const errors = reply?.status === 400 ? reply.data?.errors || {} : null;
      if (errors) {
        mark(emailMsg, errors.email);
        mark(consentMsg, errors.consent);
        if (errors.email) { email.setAttribute('aria-invalid', 'true'); email.focus(); } else if (errors.consent) { consent.setAttribute('aria-invalid', 'true'); consent.focus(); }
      } else {
        mark(emailMsg, COPY.emailSaveFailed);
      }
    });
    add(block);
  }

  /* ---------- new chat ---------- */
  function newChat() {
    st.abort?.abort();
    st.abort = null;
    st.conversationId = null;
    st.started = false;
    st.ended = false;
    st.fails = 0;
    st.exchanges = 0;
    st.last = null;
    log.replaceChildren();
    setBusy(false);
    if (st.unavailable) { setUnavailable(null); return; }
    chips.innerHTML = initialChips;
    chips.hidden = false;
    person.hidden = false;
    welcome.hidden = false;
    welcomeTitle.textContent = COPY.welcomeTitle;
    welcomeLine.textContent = COPY.welcomeLine;
    form.hidden = false;
    newButton.hidden = true;
    scroller.scrollTop = 0;
    input.focus({ preventScroll: true });
  }
  newButton.addEventListener('click', newChat);

  /* ---------- open, close, keep the input above the keyboard ---------- */
  function fitViewport() {
    const vv = window.visualViewport;
    if (!vv || !phone.matches || !root.open) { root.style.removeProperty('--chat-vh'); root.style.removeProperty('--chat-top'); return; }
    const was = nearBottom();
    root.style.setProperty('--chat-vh', `${vv.height}px`);
    root.style.setProperty('--chat-top', `${vv.offsetTop}px`);
    if (was) toBottom();
  }
  window.visualViewport?.addEventListener('resize', fitViewport);
  window.visualViewport?.addEventListener('scroll', fitViewport);
  phone.addEventListener('change', fitViewport);

  function open() {
    if (root.open) return;
    document.querySelectorAll('dialog.menu[open]').forEach((menu) => menu.close());
    if (phone.matches) root.showModal(); else root.show(); // desktop: a floating card, the page stays scrollable (Moishe, 2026-10-28)
    fitViewport();
    pill.setAttribute('aria-expanded', 'true');
    if (coarse.matches || st.unavailable || form.hidden) title.focus({ preventScroll: true }); else input.focus({ preventScroll: true });
    updateOffline();
    loadState().catch(() => { /* the first message tries again and says so if it still fails */ });
  }
  const close = () => { if (root.open) root.close(); };
  pill.addEventListener('click', open);
  root.addEventListener('keydown', (event) => { if (event.key === 'Escape' && root.open && !phone.matches) { event.preventDefault(); close(); } }); // Esc for the non-modal card
  root.querySelector('[data-chat-close]').addEventListener('click', close);
  root.addEventListener('click', (event) => { if (event.target === root) close(); }); // the backdrop
  root.addEventListener('click', (event) => { if (event.target.closest('a[data-chat-link]')) close(); }); // same-site links: leave the panel, follow the link
  root.addEventListener('close', () => {
    pill.removeAttribute('aria-expanded');
    fitViewport();
    pill.focus({ preventScroll: true });
    if (document.activeElement !== pill) requestAnimationFrame(() => pill.focus({ preventScroll: true }));
  });
  input.addEventListener('focus', () => { setTimeout(() => { if (nearBottom() || st.busy) toBottom(); }, 250); });
  updateOffline();
  grow();
}
