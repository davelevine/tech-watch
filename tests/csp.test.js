import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const read = p => readFileSync(new URL(`../${p}`, import.meta.url), 'utf8');
const sha = text => `'sha256-${createHash('sha256').update(text).digest('base64')}'`;

// The two inline scripts the CSP allows by hash. Edit either and its hash in site/_headers must change too.
export function inlineScriptHashes() {
  const theme = /<script>([\s\S]*?)<\/script>/.exec(read('site/index.html'))[1];
  const literal = /const SWIPE_REPORTER = (`[\s\S]*?`);\n/.exec(read('site/app.js'))[1];
  const relay = Function(`return ${literal}`)();  // evaluate the template literal exactly as the browser will
  return { theme: sha(theme), relay: sha(relay) };
}

test('CSP allows exactly the current inline scripts', () => {
  const headers = read('site/_headers');
  for (const [name, hash] of Object.entries(inlineScriptHashes())) {
    assert.ok(headers.includes(hash), `site/_headers is missing the ${name} script hash; update it to ${hash}`);
  }
});
