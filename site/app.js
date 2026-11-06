const CATS = { security: 'Security', ai: 'AI', architecture: 'Architecture', sdlc: 'SDLC', regulation: 'Regulation', other: 'Other' };
const SHORT = { architecture: 'Arch' };
const ORDER = ['ai', 'architecture', 'sdlc', 'security', 'regulation', 'other'];
const ARROW = '<svg viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>';
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const cat = c => (c in CATS ? c : 'other');
const domain = u => { try { return new URL(u).hostname.replace(/^www\./, ''); } catch { return ''; } };
const PAGE = 40;
const io = new IntersectionObserver(([e]) => { if (e.isIntersecting && limit < shown.length) { limit += PAGE; renderPage(); } }, { rootMargin: '800px' });
let items = [], filter = 'all', shown = [], limit = PAGE, generatedAt = null;

function dayLabel(iso) {
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(iso + 'T00:00:00')) / 864e5);
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  const d = new Date(iso + 'T12:00:00');
  return days < 7 ? d.toLocaleDateString('en-US', { weekday: 'long' }) : d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
}

function highlight(text, q) {
  const s = esc(text);
  if (!q) return s;
  const re = new RegExp(esc(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
  return s.replace(re, m => `<mark>${m}</mark>`);
}

function renderFilters() {
  const counts = {};
  for (const i of items) counts[cat(i.category)] = (counts[cat(i.category)] || 0) + 1;
  $('filters').innerHTML = [`<button class="filter-btn${filter === 'all' ? ' active' : ''}" data-f="all">All</button>`]
    .concat(ORDER.map(c => `<button class="filter-btn${filter === c ? ' active' : ''}" data-f="${c}">` +
      `<span class="dot" style="--c:var(--cat-${c})"></span>${SHORT[c] || CATS[c]} (${counts[c] || 0})</button>`)).join('');
}

function renderItems(keepLimit) {
  const ql = $('search').value.trim().toLowerCase();
  $('search-wrap').classList.toggle('has-value', !!ql);
  shown = items.filter(i => (filter === 'all' || cat(i.category) === filter) &&
    (!ql || `${i.title} ${i.summary} ${i.publisher} ${domain(i.url)}`.toLowerCase().includes(ql)));
  if (!keepLimit) limit = PAGE;
  renderPage();
}

// Renders the first `limit` matches; the sentinel below the list raises it as you scroll.
function renderPage() {
  const q = $('search').value.trim();
  const counts = {}, groups = {};
  for (const i of shown) counts[i.date] = (counts[i.date] || 0) + 1;
  for (const i of shown.slice(0, limit)) (groups[i.date] ||= []).push(i);
  $('items').innerHTML = shown.length ? Object.entries(groups).map(([d, list]) => `
    <div class="date-label"><span>${dayLabel(d)}</span><span class="count">${counts[d]}</span></div>
    ${list.map(i => { const c = cat(i.category); return `
    <a class="card${readSet.has(i.url) ? ' read' : ''}" href="${esc(i.url)}" target="_blank" rel="noopener">
      <span class="dot" style="--c:var(--cat-${c})"></span>
      <div class="card-body">
        <div class="card-title">${highlight(i.title, q)}</div>
        ${i.summary ? `<p class="card-summary">${highlight(i.summary, q)}</p>` : ''}
        <div class="card-meta">${isNew(i) ? '<span class="new">New</span>' : ''}<span class="card-cat">${CATS[c]}</span><span>·</span><span class="card-url">${esc(domain(i.url))}</span></div>
      </div>
      <span class="card-arrow">${ARROW}</span>
    </a>`; }).join('')}`).join('')
    : '<p class="empty">No articles match your search.</p>';
  io.unobserve($('sentinel'));
  io.observe($('sentinel'));
}

function renderWeekly(weekly) {
  const byUrl = Object.fromEntries(items.map(i => [i.url, i]));
  const picks = (weekly?.items || []).filter(p => byUrl[p.url]);
  if (!picks.length) return;
  $('rail').innerHTML = picks.map((p, n) => { const i = byUrl[p.url]; return `
    <a class="weekly-card" href="${esc(i.url)}" target="_blank" rel="noopener" title="${esc(p.why)}">
      <div class="weekly-top"><span class="rank">${n + 1}</span>
        <span class="weekly-meta"><span class="weekly-source">${esc(i.publisher)}</span><span>· ${CATS[cat(i.category)]} · ${dayLabel(i.date)}</span></span></div>
      <div class="weekly-card-title">${esc(i.title)}</div>
    </a>`; }).join('');
  $('weekly').hidden = false;
  const rail = $('rail');
  const step = () => rail.firstElementChild.offsetWidth + 10;
  const sync = () => { $('prev').disabled = rail.scrollLeft < 4; $('next').disabled = rail.scrollLeft + rail.clientWidth >= rail.scrollWidth - 4; };
  $('prev').onclick = () => rail.scrollBy({ left: -step() });
  $('next').onclick = () => rail.scrollBy({ left: step() });
  rail.onscroll = sync;
  sync();
}

const syncThemeColor = () => document.querySelector('meta[name="theme-color"]').setAttribute('content', css('--bg'));
$('theme').onclick = () => {
  const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = t;
  localStorage.setItem('theme', t);
  syncThemeColor();
};
$('info').onclick = e => {
  e.stopPropagation();
  const open = $('info-pop').hidden;
  $('info-pop').hidden = !open;
  $('info').setAttribute('aria-expanded', open);
};
document.addEventListener('click', () => { $('info-pop').hidden = true; $('info').setAttribute('aria-expanded', false); });
$('filters').onclick = e => {
  const b = e.target.closest('.filter-btn');
  if (!b) return;
  filter = b.dataset.f;
  renderFilters();
  renderItems();
};
$('search').oninput = () => renderItems();
io.observe($('sentinel'));
addEventListener('scroll', () => { $('top').hidden = scrollY < 800; }, { passive: true });
$('top').onclick = () => scrollTo({ top: 0, behavior: 'smooth' });
$('clear').onclick = () => { $('search').value = ''; renderItems(); $('search').focus(); };

// Read and "new since last visit" state lives only in this browser.
let weekly = null;
const readSet = new Set(JSON.parse(localStorage.getItem('read') || '[]'));
const seenUntil = localStorage.getItem('seenUntil');  // the build you'd seen by the end of your last visit
const isNew = i => !!(seenUntil && i.added && i.added > seenUntil && !readSet.has(i.url));
const saveRead = () => localStorage.setItem('read', JSON.stringify([...readSet]));
function pruneRead() {
  const urls = new Set(items.map(i => i.url));
  for (const u of readSet) if (!urls.has(u)) readSet.delete(u);
  saveRead();
}
const cardFor = url => [...document.querySelectorAll('a.card')].find(a => a.getAttribute('href') === url);
function markRead(url) {
  if (!readSet.has(url)) { readSet.add(url); saveRead(); }
  const card = cardFor(url);
  card?.classList.add('read');
  card?.querySelector('.new')?.remove();
}
const rememberSeen = () => { if (generatedAt) localStorage.setItem('seenUntil', generatedAt); };
addEventListener('pagehide', rememberSeen);
document.addEventListener('visibilitychange', () => { if (document.hidden) rememberSeen(); });

// Redraws only when a new build has landed, keeping the filter, search and loaded depth.
function load() {
  return fetch('data.json', { cache: 'no-cache' }).then(r => r.json()).then(data => {
    if (data.generated_at === generatedAt) return;
    const refresh = generatedAt !== null;
    generatedAt = data.generated_at;
    items = data.items || [];
    weekly = data.weekly;
    pruneRead();
    renderFilters();
    renderWeekly(data.weekly);
    renderItems(refresh);
    if (!refresh) syncFromHash();
  });
}
let readerFor = null;

const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
// Inside the article frame, the only script allowed is this one (by nonce): it reports rightward swipes to the
// page so the reader can follow the finger, and forwards Escape, j/k, ←/→ and Cmd/Ctrl+K. The frame has no same-origin access; it can only postMessage.
const SWIPE_REPORTER = `let s = null;
const send = (tw, t) => parent.postMessage({ tw, x: t && t.screenX }, '*');
addEventListener('touchstart', e => { const t = e.touches[0]; s = { x: t.screenX, y: t.screenY, ax: null }; }, { passive: true });
addEventListener('touchmove', e => {
  if (!s) return;
  const t = e.touches[0], dx = t.screenX - s.x, dy = t.screenY - s.y;
  if (!s.ax && Math.hypot(dx, dy) > 10) { s.ax = dx > Math.abs(dy) ? 'x' : 'y'; if (s.ax === 'x') send('start', { screenX: s.x }); }
  if (s.ax === 'x') { e.preventDefault(); send('move', t); }
}, { passive: false });
const end = () => { if (s && s.ax === 'x') send('end'); s = null; };
addEventListener('touchend', end); addEventListener('touchcancel', end);
addEventListener('keydown', e => {  // keys pressed while the article has focus never reach the page
  const k = e.key.toLowerCase();
  if (!e.altKey && ['escape', 'j', 'k', 'arrowleft', 'arrowright'].includes(k)) { e.preventDefault(); parent.postMessage({ tw: 'key', key: k, mod: e.metaKey || e.ctrlKey }, '*'); }
});`;

function articleDoc(i, html, nonce, why) {
  return `<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src https: http: data:; media-src https:; style-src 'unsafe-inline'; script-src 'nonce-${nonce}'">
<base target="_blank"><style>
:root { color-scheme: ${document.documentElement.dataset.theme}; }
body { margin: 0; background: ${css('--bg')}; color: ${css('--text')}; font: 1.125rem/1.75 "Iowan Old Style", Charter, Georgia, serif; overflow-wrap: break-word; }
main { max-width: 680px; margin: 0 auto; padding: 40px 24px 96px; }
h1 a { color: inherit; text-decoration: none; } h1 a:hover { text-decoration: underline; text-decoration-thickness: 2px; }
.why { margin: -1.2em 0 2.4em; padding: 12px 16px; border-left: 3px solid ${css('--accent')}; border-radius: 0 8px 8px 0; background: ${css('--bg-card')}; font: .95rem/1.5 Inter, system-ui, sans-serif; }
.why b { display: block; margin-bottom: 2px; color: ${css('--accent')}; font-size: .72rem; letter-spacing: .07em; text-transform: uppercase; }
h1 { font-size: 2.1rem; line-height: 1.2; letter-spacing: -.01em; margin: 0 0 .35em; }
.src { margin-bottom: 2.4em; color: ${css('--accent')}; font: 600 .78rem/1 Inter, system-ui, sans-serif; letter-spacing: .07em; text-transform: uppercase; }
h2, h3, h4 { line-height: 1.3; margin: 1.6em 0 .5em; }
a { color: ${css('--accent')}; }
img, video { max-width: 100%; height: auto; border-radius: 8px; }
figure { margin: 1.6em 0; } figcaption { color: ${css('--text-muted')}; font-size: .85em; }
blockquote { margin: 1.4em 0; padding-left: 1em; border-left: 3px solid ${css('--border-strong')}; color: ${css('--text-muted')}; }
pre { overflow: auto; padding: 12px 14px; border-radius: 8px; background: ${css('--bg-card')}; font-size: .82em; line-height: 1.5; }
code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .88em; }
table { display: block; overflow: auto; border-collapse: collapse; font-size: .9em; } th, td { padding: 4px 8px; border: 1px solid ${css('--border')}; }
hr { border: 0; border-top: 1px solid ${css('--border')}; }
@media (max-width: 600px) { main { padding: 24px 18px 80px; } h1 { font-size: 1.6rem; } body { font-size: 1.0625rem; } }
</style><script nonce="${nonce}">${SWIPE_REPORTER}<\/script></head><body><main><h1><a href="${esc(i.url)}" target="_blank" rel="noopener" title="Open the original">${esc(i.title)}</a></h1><div class="src">${esc(domain(i.url))}</div>${why ? `<div class="why"><b>Why it matters</b>${esc(why)}</div>` : ''}${html}</main></body></html>`;
}

const readHash = url => '#read=' + encodeURIComponent(url);
let readerPushed = false;  // false when the reader was opened from a #read= link, so closing mustn't go back off the site
function openReader(i, { fromHash = false } = {}) {
  const fresh = !document.body.classList.contains('reading');
  readerFor = i.url;
  markRead(i.url);
  const why = weekly?.items?.find(p => p.url === i.url)?.why;
  $('reader-source').textContent = `${i.publisher} · ${domain(i.url)}`;
  $('reader-source').href = i.url;
  $('reader-body').innerHTML = '<div class="reader-msg">Loading the article…</div>';
  document.body.classList.add('reading');
  $('reader').setAttribute('aria-hidden', 'false');
  document.querySelectorAll('.feed, #top').forEach(el => { el.inert = true; });
  if (fromHash) { history.replaceState({ reader: true }, '', readHash(i.url)); readerPushed = false; }
  else if (fresh) { history.pushState({ reader: true }, '', readHash(i.url)); readerPushed = true; }
  else history.replaceState({ reader: true }, '', readHash(i.url));
  if (fresh) $('reader-close').focus({ preventScroll: true });
  fetch('/api/read?url=' + encodeURIComponent(i.url), { cache: 'no-store' }).then(r => r.json()).then(r => {
    if (readerFor !== i.url) return;  // another article was opened meanwhile
    const frame = document.createElement('iframe');
    if (r.content) {
      // Scripts run only by nonce (the swipe reporter); without allow-same-origin the frame can't touch this page.
      frame.sandbox = 'allow-scripts allow-popups allow-popups-to-escape-sandbox';
      frame.srcdoc = articleDoc(i, r.content, crypto.randomUUID(), why);
    } else if (r.frameable) {
      frame.sandbox = 'allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-forms';
      frame.referrerPolicy = 'no-referrer';
      frame.src = i.url;
      $('reader-source').textContent += ' · original page';
    } else throw new Error('unreadable');
    frame.title = i.title;
    $('reader-body').replaceChildren(frame);
  }).catch(() => {
    if (readerFor !== i.url) return;
    $('reader-body').innerHTML = `<div class="reader-msg">${why ? `<p><b>Why it matters:</b> ${esc(why)}</p>` : ''}This site doesn’t allow a reader view.<a href="${esc(i.url)}" target="_blank" rel="noopener">Read it on ${esc(domain(i.url))}</a></div>`;
  });
}
function closeReader() {
  const url = readerFor;
  readerFor = null;
  document.body.classList.remove('reading');
  $('reader').setAttribute('aria-hidden', 'true');
  document.querySelectorAll('.feed, #top').forEach(el => { el.inert = false; });
  const card = url && cardFor(url);  // back to where you were, even after j/k through several articles
  if (card) { card.focus({ preventScroll: true }); card.scrollIntoView({ block: 'nearest' }); }
  setTimeout(() => { if (!readerFor) $('reader-body').replaceChildren(); }, 250);
}
function dismiss() {
  if (readerPushed && history.state?.reader) return history.back();
  history.replaceState(null, '', location.pathname + location.search);
  closeReader();
}
// Back/forward and #read= links: the URL decides whether the reader is open and on what.
function syncFromHash() {
  const url = location.hash.startsWith('#read=') ? decodeURIComponent(location.hash.slice(6)) : null;
  const i = url && items.find(x => x.url === url);
  if (i && readerFor !== url) openReader(i, { fromHash: true });
  else if (!i && document.body.classList.contains('reading')) closeReader();
}
addEventListener('popstate', syncFromHash);
// Swipe right to close: the reader follows the finger, then closes past a third of its width or on a flick
// (judged on the finger's speed at release, px/ms).
let drag = null;
const setDrag = f => document.documentElement.style.setProperty('--drag', f);
function dragStart(x) { drag = { x, dx: 0, lx: x, lt: performance.now(), v: 0 }; document.body.classList.add('dragging'); }
function dragMove(x) {
  if (!drag) return;
  const now = performance.now();
  if (now > drag.lt) drag.v = 0.6 * drag.v + 0.4 * (x - drag.lx) / (now - drag.lt);
  drag.lx = x; drag.lt = now;
  drag.dx = Math.max(0, x - drag.x);
  setDrag(Math.min(1, drag.dx / $('reader').offsetWidth));
}
function dragEnd() {
  if (!drag) return;
  const { dx, v } = drag, flick = dx > 40 && v > 0.4;
  drag = null;
  document.body.classList.remove('dragging');
  if (dx > $('reader').offsetWidth / 3 || flick) dismiss();
  setDrag(0);  // the closed state ignores --drag; the open state springs back
}
// Touches on the reader's own chrome (the bar, messages). Framed original pages can't report touches.
let touch = null;
$('reader').addEventListener('touchstart', e => { const t = e.touches[0]; touch = { x: t.screenX, y: t.screenY, ax: null }; }, { passive: true });
$('reader').addEventListener('touchmove', e => {
  if (!touch) return;
  const t = e.touches[0], dx = t.screenX - touch.x, dy = t.screenY - touch.y;
  if (!touch.ax && Math.hypot(dx, dy) > 10) { touch.ax = dx > Math.abs(dy) ? 'x' : 'y'; if (touch.ax === 'x') dragStart(touch.x); }
  if (touch.ax === 'x') { e.preventDefault(); dragMove(t.screenX); }
}, { passive: false });
$('reader').addEventListener('touchend', () => { if (touch?.ax === 'x') dragEnd(); touch = null; });
$('reader').addEventListener('touchcancel', () => { if (touch?.ax === 'x') dragEnd(); touch = null; });
// Swipes inside the article frame arrive as messages from the swipe reporter.
addEventListener('message', e => {
  const frame = $('reader-body').querySelector('iframe');
  if (!frame || e.source !== frame.contentWindow || typeof e.data?.tw !== 'string') return;
  if (e.data.tw === 'start') dragStart(e.data.x);
  else if (e.data.tw === 'move') dragMove(e.data.x);
  else if (e.data.tw === 'end') dragEnd();
  else if (e.data.tw === 'key') onKey(e.data.key, !!e.data.mod);
});

$('reader-close').onclick = dismiss;
$('reader-backdrop').onclick = dismiss;
// j/k or →/←: next/previous article (in the reader it switches articles in place); /: search bar; Cmd/Ctrl+K: search palette.
function step(dir) {
  if (document.body.classList.contains('reading')) {
    const next = shown[shown.findIndex(i => i.url === readerFor) + dir];
    if (!next) return;
    if (shown.indexOf(next) >= limit) { limit += PAGE; renderPage(); }
    return openReader(next);
  }
  const cards = [...document.querySelectorAll('a.card')];
  const at = cards.indexOf(document.activeElement);
  const target = cards[at < 0 ? 0 : Math.min(cards.length - 1, Math.max(0, at + dir))];
  target?.focus({ preventScroll: true });
  target?.scrollIntoView({ block: 'nearest' });
}
function onKey(key, mod, e) {
  const reading = document.body.classList.contains('reading');
  if (key === 'escape' && reading) return dismiss();
  if (key === 'k' && mod) { e?.preventDefault(); return openPalette(); }
  if (mod || e?.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName)) return;
  if (key === '/' && !reading) { e?.preventDefault(); $('search').focus(); }
  else if (key === 'j' || key === 'arrowright') { e?.preventDefault(); step(1); }
  else if (key === 'k' || key === 'arrowleft') { e?.preventDefault(); step(-1); }
}
addEventListener('keydown', e => onKey(e.key.toLowerCase(), e.metaKey || e.ctrlKey, e));
if (matchMedia('(pointer: fine)').matches) {
  $('search-kbd').textContent = /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘K' : 'Ctrl K';
  $('search-kbd').hidden = false;
}

// Cmd/Ctrl+K palette: find any article and open it in the reader. Works over the reader too.
const pal = { results: [], sel: 0, returnTo: null };
const LAYERS = '.feed, #top, #reader';
function openPalette() {
  if (!$('palette').hidden) return $('palette-q').select();
  pal.returnTo = document.activeElement;
  document.querySelectorAll(LAYERS).forEach(el => { el.dataset.wasInert = el.inert ? '1' : ''; el.inert = true; });
  $('palette').hidden = $('palette-backdrop').hidden = false;
  $('palette-q').value = '';
  renderPalette();
  $('palette-q').focus();
}
function closePalette(restoreFocus = true) {
  $('palette').hidden = $('palette-backdrop').hidden = true;
  document.querySelectorAll(LAYERS).forEach(el => { el.inert = el.dataset.wasInert === '1'; });
  if (restoreFocus) pal.returnTo?.focus?.({ preventScroll: true });
}
function renderPalette() {
  const q = $('palette-q').value.trim(), ql = q.toLowerCase();
  // Title matches rank above summary/publisher matches; within a rank, items stay newest first.
  const rank = i => {
    if (!ql) return 1;
    const t = i.title.toLowerCase();
    if (t.includes(ql)) return t.startsWith(ql) ? 3 : 2;
    return `${i.summary} ${i.publisher} ${domain(i.url)}`.toLowerCase().includes(ql) ? 1 : 0;
  };
  pal.results = items.map(i => [rank(i), i]).filter(([r]) => r).sort((a, b) => b[0] - a[0]).slice(0, 30).map(([, i]) => i);
  pal.sel = 0;
  $('palette-list').innerHTML = pal.results.length ? pal.results.map((i, n) => { const c = cat(i.category); return `
    <li role="option" id="p-${n}" data-n="${n}" aria-selected="${n === 0}">
      <span class="dot" style="--c:var(--cat-${c})"></span>
      <div><div class="p-title">${highlight(i.title, q)}</div><div class="p-meta">${esc(i.publisher)} · ${CATS[c]} · ${dayLabel(i.date)}</div></div>
    </li>`; }).join('') : `<li class="palette-empty">No articles match “${esc(q)}”.</li>`;
  $('palette-q').setAttribute('aria-activedescendant', pal.results.length ? 'p-0' : '');
}
function selectPalette(n, scroll = true) {
  if (!pal.results.length) return;
  pal.sel = (n + pal.results.length) % pal.results.length;
  $('palette-list').querySelectorAll('li[data-n]').forEach(li => li.setAttribute('aria-selected', +li.dataset.n === pal.sel));
  $('palette-q').setAttribute('aria-activedescendant', 'p-' + pal.sel);
  if (scroll) $('p-' + pal.sel).scrollIntoView({ block: 'nearest' });
}
function choosePalette(n = pal.sel) {
  const i = pal.results[n];
  if (!i) return;
  closePalette(false);
  openReader(i);
}
$('palette-q').addEventListener('input', renderPalette);
$('palette-q').addEventListener('keydown', e => {
  e.stopPropagation();  // keep page shortcuts (Escape closing the reader, j/k) out of the palette
  if (e.key === 'ArrowDown') { e.preventDefault(); selectPalette(pal.sel + 1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); selectPalette(pal.sel - 1); }
  else if (e.key === 'Enter') { e.preventDefault(); choosePalette(); }
  else if (e.key === 'Escape') { e.preventDefault(); closePalette(); }
  else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); $('palette-q').select(); }
});
$('palette-list').addEventListener('click', e => { const li = e.target.closest('li[data-n]'); if (li) choosePalette(+li.dataset.n); });
$('palette-list').addEventListener('mousemove', e => { const li = e.target.closest('li[data-n]'); if (li && +li.dataset.n !== pal.sel) selectPalette(+li.dataset.n, false); });
$('palette-backdrop').addEventListener('click', () => closePalette());
document.addEventListener('auxclick', e => { const a = e.target.closest('a.card, a.weekly-card'); if (a && e.button === 1) markRead(a.getAttribute('href')); });
// Plain clicks on an article open the reader; modified and middle clicks still open the site.
document.addEventListener('click', e => {
  const a = e.target.closest('a.card, a.weekly-card');
  if (!a) return;
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return markRead(a.getAttribute('href'));
  const i = items.find(x => x.url === a.getAttribute('href'));
  if (!i) return;
  e.preventDefault();
  openReader(i);
});

syncThemeColor();
load().catch(() => { $('items').innerHTML = '<p class="empty">Couldn’t load the news. Try again in a bit.</p>'; });
// Builds land every ~4h: check every 15 min while visible, and when the tab comes back into view.
const check = () => { if (!document.hidden) load().catch(() => {}); };
setInterval(check, 15 * 60e3);
document.addEventListener('visibilitychange', check);
