// Reader view: fetches one article that's on the site and returns its main content.
// Nothing is stored or cached, and only articles listed on the site are fetched.
import { Readability } from '@mozilla/readability';
import { parseHTML } from 'linkedom';

const UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';
const MAX_HTML = 3_000_000;
const MIN_TEXT = 500; // shorter "articles" are usually cookie walls or app shells
const DROP = 'script, style, noscript, iframe, object, embed, form, input, button, link, meta, svg';

const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
});

// Whether the site lets itself be shown in a frame on another origin.
export function frameable(headers) {
  const xfo = (headers.get('x-frame-options') || '').toLowerCase();
  if (xfo.includes('deny') || xfo.includes('sameorigin')) return false;
  const fa = /frame-ancestors([^;]*)/i.exec(headers.get('content-security-policy') || '');
  return !fa || fa[1].includes('*');
}

// Strips anything active and makes every link and image absolute.
export function clean(html, base) {
  const { document } = parseHTML(`<!doctype html><html><body><div id="root">${html}</div></body></html>`);
  const root = document.getElementById('root');
  root.querySelectorAll(DROP).forEach(el => el.remove());
  for (const el of root.querySelectorAll('*')) {
    for (const { name } of [...el.attributes]) {
      if (name.startsWith('on') || name === 'style' || name === 'srcset') el.removeAttribute(name);
    }
    for (const attr of ['href', 'src']) {
      const v = el.getAttribute(attr);
      if (v == null) continue;
      try {
        const abs = new URL(v, base);
        if (abs.protocol === 'http:' || abs.protocol === 'https:') el.setAttribute(attr, abs.href);
        else el.removeAttribute(attr);
      } catch { el.removeAttribute(attr); }
    }
    if (el.tagName === 'IMG') {
      const lazy = el.getAttribute('data-src') || el.getAttribute('data-lazy-src');
      if (!el.getAttribute('src') && lazy) try { el.setAttribute('src', new URL(lazy, base).href); } catch {}
      el.setAttribute('loading', 'lazy');
    }
    if (el.tagName === 'A') { el.setAttribute('target', '_blank'); el.setAttribute('rel', 'noopener noreferrer'); }
  }
  // Sites space out metadata spans with CSS ("Nov 04, 2026" + "Cloud Security"); without it the text runs together.
  for (const el of root.querySelectorAll('span, time, a')) {
    const next = el.nextSibling;
    if (next?.nodeType === 1 && !el.closest('pre, code') && /\S$/.test(el.textContent) && /^\S/.test(next.textContent)) {
      el.parentNode.insertBefore(document.createTextNode(' '), next);
    }
  }
  return root.innerHTML.replace(/[\uE000-\uF8FF]/g, ' ');  // icon-font glyphs (boxes without the site's fonts) often separate words
}

export async function onRequestGet({ request, env }) {
  const url = new URL(request.url).searchParams.get('url');
  // Only articles that are on the site, so this can't be used as an open proxy.
  const data = await (await env.ASSETS.fetch(new URL('/data.json', request.url))).json();
  if (!url || !data.items.some(i => i.url === url)) return json({ error: 'not a Triage article' }, 404);

  let res;
  try {
    res = await fetch(url, { headers: { 'User-Agent': UA, Accept: 'text/html,application/xhtml+xml' }, signal: AbortSignal.timeout(15000) });
  } catch {
    return json({ url, frameable: false });
  }
  const result = { url, frameable: frameable(res.headers) };
  if (!res.ok || !(res.headers.get('content-type') || '').includes('html')) return json(result);

  const html = (await res.text()).slice(0, MAX_HTML);
  const { document } = parseHTML(html);
  const article = new Readability(document).parse();
  if (article?.content && (article.textContent || '').trim().length >= MIN_TEXT) {
    Object.assign(result, {
      title: article.title, byline: article.byline, siteName: article.siteName,
      content: clean(article.content, res.url),
    });
  }
  return json(result);
}
