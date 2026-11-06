# Tech Watch

A set-it-and-forget-it tech news digest at [tech.levine.io](https://tech.levine.io): AI, security, architecture, SDLC and regulation news, each item summarized in one sentence, plus five weekly "essentials" with a line on why they matter. Inspired by [watch.edebost.com](https://watch.edebost.com/).

**What's covered:**

- How it works
- Adding or removing feeds
- The reader
- Running it locally
- Setup

## How it works

Every four hours a GitHub Actions workflow runs `build.py`, which:

1. Fetches every feed in `feeds.opml`. A failing feed is skipped, never fatal.
2. Keeps dated entries from the last 3 days that haven't been seen before, up to 10 per feed.
3. Sends them to Ollama Cloud (`deepseek-v4.1-flash`) in batches of 20 for a category, a 1-10 relevance score and a one-sentence summary. Relevance is judged within each category, and only the notable stories are kept: 8+ for AI and Security, 7+ for the quieter categories. That lets the daily count follow the news, a handful on a big day and none on a slow one. The model also flags an item that repeats a story already on the site from the last 7 days (the same launch from another outlet, say), and repeats are dropped. A cap of 10 a day guards against an unusually big news day.
4. Once a day, asks the model to pick the week's five essentials.
5. Writes `site/data.json` and `site/rss.xml`, and remembers seen URLs in `state.json`.

The workflow commits those files and Cloudflare Pages deploys `site/` on the push. Items and seen URLs older than 90 days are pruned, so the data never grows unbounded.

To fill in history, run the Build workflow by hand with `backfill_days` set (say, 30). It looks back that far and takes up to 100 entries per feed, once. Everything already seen is skipped, so it's safe to rerun.

It looks after itself: a feed that's failed every fetch for 14 days gets listed in a single open "Dead feeds" issue, and a run where every LLM batch fails exits non-zero so GitHub emails you. Batches that fail are left unseen and retried on the next run.

## Adding or removing feeds

Edit `feeds.opml`; each feed is one `<outline>` line. The `text` attribute is the publisher name shown on the site. Some big publishers (Anthropic, Cohere, Reuters) don't publish RSS; Anthropic comes from a community-maintained feed, and the Hacker News 300+ feed catches most of the rest.

## The reader

Clicking an article opens it in a reader panel instead of a new tab. `functions/api/read.js`, a Cloudflare Pages Function, fetches the page on demand and extracts the article with Mozilla's Readability, the same approach as Firefox's reader view. If a site won't give up its text but allows framing, the panel shows the original page instead; otherwise you get a link to read it on the site. Ctrl/Cmd-click and middle-click still open the original. On a phone, swipe right to close the reader: it follows your finger and the feed slides back in underneath, like a native back gesture. Cmd/Ctrl+K opens a search palette from anywhere, even over an open article: type to filter every article on the site, ↑/↓ to choose, Enter to read it. Click the headline (or the publisher in the top bar) to open the original. Weekly picks show their "why it matters" line at the top. Each open article has its own `#read=` address, so a reload or a shared link reopens it.

A few things are remembered in your browser only (nothing leaves it): articles you've opened are dimmed, and anything added since your last visit gets a "New" badge. A visit ends when you leave or reload the page. On a keyboard, `j`/`k` or →/← move between articles (and switch articles inside the reader), Enter opens one, `/` jumps to the search bar, and Escape closes the reader. On Android, Chrome's "Install app" puts Tech Watch on the home screen as a full-screen app; the system back gesture closes the reader.

Nothing is stored or cached: responses are `no-store`, and only URLs already on the site are fetched, so it can't be used as an open proxy. Extracted HTML is cleaned on the server (no scripts, frames, styles or event handlers) and rendered in a sandboxed frame with no access to the page. The only script that frame may run is the site's own swipe and keyboard relay, allowed by a per-render nonce; the article's scripts are stripped before it gets there. There's no login; the reader works for every visitor.

## Running it locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/pytest -q
OLLAMA_API_KEY=... .venv/bin/python build.py
python3 -m http.server -d site 8000
```

The reader needs the Pages runtime, so run it with Wrangler instead of `http.server`:

```bash
npm ci
node --test 'tests/*.test.js'
npx wrangler pages dev site
```

The build writes real data, so don't commit a local run's output unless you mean to.

## Setup

- **Secret:** `OLLAMA_API_KEY` in the repo's Actions secrets.
- **Cloudflare Pages:** project `levine-tech-watch` (`tech-watch.pages.dev` is taken), connected to this repo, production branch `main`, no build command, output directory `site`.
- **Domain:** `tech.levine.io` is a proxied CNAME to `levine-tech-watch.pages.dev`, managed in [homelab-iac](https://github.com/davelevine/homelab-iac) (`terraform/modules/cloudflare/data/dns_zones.yaml`), and added as a custom domain on the Pages project.
