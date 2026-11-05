"""Fetch feeds, classify + summarize new items with an LLM, write the static site data."""
import gzip
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import feedparser

ROOT = Path(__file__).parent
SITE = ROOT / "site"
STATE = ROOT / "state.json"
SITE_URL = "https://tech.levine.io"
MODEL = os.environ.get("OLLAMA_MODEL", "deepseek-v4.1-flash")
CATEGORIES = ["ai", "security", "architecture", "sdlc", "regulation", "other"]
KEEP_DAYS = 90        # items and seen-URLs older than this are pruned
FRESH_DAYS = int(os.environ.get("FRESH_DAYS", 3))  # ignore feed entries published longer ago than this
PER_FEED = int(os.environ.get("PER_FEED", 10))     # newest N entries per feed per run (caps huge feeds)
MIN_RELEVANCE = 3     # 1-5; below this the item is dropped
DAILY_MAX = 8         # keep at most the N most relevant items per day (~5/day on average)
DEAD_AFTER_DAYS = 14  # a feed failing this long gets reported
BATCH = 20
UA = "tech-watch/1.0 (+https://github.com/davelevine/tech-watch)"
TRACKING = re.compile(r"^(utm_|ref$|source$|fbclid$|gclid$)")


def now():
    return datetime.now(timezone.utc)


def read_opml(path):
    return [(o.get("text"), o.get("xmlUrl")) for o in ET.parse(path).iter("outline") if o.get("xmlUrl")]


def normalize_url(url):
    p = urllib.parse.urlsplit(url.strip())
    query = urllib.parse.urlencode([(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not TRACKING.match(k)])
    return urllib.parse.urlunsplit((p.scheme, p.netloc.lower(), p.path, query, ""))


def clean_text(s, limit=600):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()[:limit]


def fetch(feed):
    title, url = feed
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read()
    if body[:2] == b"\x1f\x8b":  # some servers gzip regardless of Accept-Encoding
        body = gzip.decompress(body)
    parsed = feedparser.parse(body)
    if not parsed.entries and parsed.bozo:
        raise ValueError(f"unparseable feed: {parsed.bozo_exception}")
    return title, parsed.entries


def entry_time(e):
    t = e.get("published_parsed") or e.get("updated_parsed")
    return datetime(*t[:6], tzinfo=timezone.utc) if t else None


def candidates(publisher, entries, seen, cutoff):
    """New, dated, recent entries from one feed, newest first, capped at PER_FEED."""
    out = []
    for e in entries:
        link, when = e.get("link"), entry_time(e)
        if not link or not e.get("title") or not when or when < cutoff:
            continue
        url = normalize_url(link)
        if not url.startswith(("https://", "http://")) or url in seen:  # links render as hrefs
            continue
        out.append({
            "url": url,
            "title": clean_text(e["title"], 300),
            "publisher": publisher,
            "date": when.date().isoformat(),
            "excerpt": clean_text(e.get("summary") or e.get("description")),
        })
    return sorted(out, key=lambda i: i["date"], reverse=True)[:PER_FEED]


def llm(system, user, schema):
    """Returns the list of result objects."""
    body = json.dumps({
        "model": MODEL,
        "stream": False,
        "think": False,
        "format": schema,
        "options": {"temperature": 0},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request("https://ollama.com/api/chat", data=body, headers={
        "Authorization": f"Bearer {os.environ['OLLAMA_API_KEY']}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=300) as resp:
        content = json.loads(resp.read())["message"]["content"]
    # The model sometimes returns the bare array instead of the schema's wrapper object.
    res = json.loads(content.strip().removeprefix("```json").removesuffix("```"))
    return res if isinstance(res, list) else next(v for v in res.values() if isinstance(v, list))


CLASSIFY_PROMPT = f"""You curate a tech news digest for a senior infrastructure/platform engineer
interested in AI, security, architecture, software delivery (sdlc) and tech regulation.
For each item return:
- category: one of {", ".join(CATEGORIES)}
- relevance: 1-5. 5 = major release, incident or shift practitioners must know about;
  3 = genuinely useful; 1 = marketing, hiring, events, webinars, customer stories, off-topic.
- summary: one plain factual sentence (max 30 words) saying what happened. No hype, no "this article".
Return JSON: {{"items": [{{"id", "category", "relevance", "summary"}}, ...]}} covering every input id."""

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "category": {"type": "string", "enum": CATEGORIES},
            "relevance": {"type": "integer"},
            "summary": {"type": "string"},
        },
        "required": ["id", "category", "relevance", "summary"],
    }}},
    "required": ["items"],
}


def classify(batch):
    """Returns {url: result} for the batch; items the model skipped are simply absent."""
    payload = [{"id": n, "title": i["title"], "publisher": i["publisher"], "excerpt": i["excerpt"]}
               for n, i in enumerate(batch)]
    res = llm(CLASSIFY_PROMPT, json.dumps(payload), CLASSIFY_SCHEMA)
    return {batch[r["id"]]["url"]: r for r in res if 0 <= r["id"] < len(batch)}


WEEKLY_PROMPT = """From this week's tech news, pick the 5 items a busy senior engineer most needs to know about.
Prefer concrete releases, incidents and shifts over opinion. Avoid picking two items about the same story.
For each give the item id and "why": one sentence (max 25 words) on why it matters.
Return JSON: {"picks": [{"id", "why"}, ...]}."""

WEEKLY_SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "why": {"type": "string"}},
        "required": ["id", "why"],
    }}},
    "required": ["picks"],
}


def pick_weekly(items, today):
    start = (today - timedelta(days=6)).isoformat()
    week = [i for i in items if i["date"] >= start]
    if not week:
        return None
    payload = [{"id": n, "title": i["title"], "publisher": i["publisher"], "summary": i["summary"]}
               for n, i in enumerate(week)]
    res = llm(WEEKLY_PROMPT, json.dumps(payload), WEEKLY_SCHEMA)
    picks = [{"url": week[p["id"]]["url"], "why": p["why"]} for p in res if 0 <= p["id"] < len(week)]
    return {"window_start": start, "window_end": today.isoformat(), "selected_on": today.isoformat(), "items": picks[:5]}


def rss(items):
    def esc(s):
        return html.escape(s, quote=False)
    entries = "".join(
        f"<item><title>{esc(i['title'])}</title><link>{esc(i['url'])}</link><guid>{esc(i['url'])}</guid>"
        f"<description>{esc(i['summary'])}</description><category>{i['category']}</category>"
        f"<pubDate>{format_datetime(datetime.fromisoformat(i['date']).replace(tzinfo=timezone.utc))}</pubDate></item>"
        for i in items[:50]
    )
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Tech Watch</title>'
            f"<link>{SITE_URL}/</link><description>AI, security and architecture news, summarized.</description>"
            f"{entries}</channel></rss>\n")


def cap_per_day(items):
    """Newest day first; within a day, the DAILY_MAX most relevant (ties keep their order)."""
    by_day = {}
    for i in items:
        by_day.setdefault(i["date"], []).append(i)
    return [i for day in sorted(by_day, reverse=True)
            for i in sorted(by_day[day], key=lambda i: -i.get("relevance", MIN_RELEVANCE))[:DAILY_MAX]]


def update_feed_health(health, results, today):
    """health: {feed_url: first_failure_date}. Returns feeds dead for DEAD_AFTER_DAYS+."""
    for url, ok in results.items():
        if ok:
            health.pop(url, None)
        else:
            health.setdefault(url, today.isoformat())
    limit = (today - timedelta(days=DEAD_AFTER_DAYS)).isoformat()
    return sorted(u for u, since in health.items() if since <= limit)


def main():
    today = now().date()
    state = json.loads(STATE.read_text()) if STATE.exists() else {"seen": {}, "failing_since": {}}
    data_path = SITE / "data.json"
    data = json.loads(data_path.read_text()) if data_path.exists() else {"items": [], "weekly": None}
    seen = state["seen"]
    feeds = read_opml(ROOT / "feeds.opml")

    def safe_fetch(feed):
        try:
            return feed[1], fetch(feed)
        except Exception as e:
            print(f"::warning::feed failed: {feed[1]}: {e}")
            return feed[1], None

    with ThreadPoolExecutor(12) as ex:
        fetched = dict(ex.map(safe_fetch, feeds))
    dead = update_feed_health(state["failing_since"], {u: r is not None for u, r in fetched.items()}, today)
    # Feeds removed from the OPML stop being tracked.
    state["failing_since"] = {u: d for u, d in state["failing_since"].items() if u in fetched}

    cutoff = now() - timedelta(days=FRESH_DAYS)
    new, urls = [], set()
    for res in fetched.values():
        if res:
            for c in candidates(*res, seen, cutoff):
                if c["url"] not in urls:
                    urls.add(c["url"])
                    new.append(c)
    print(f"{len(feeds)} feeds, {sum(r is None for r in fetched.values())} failed, {len(new)} new items")

    batches = [new[n:n + BATCH] for n in range(0, len(new), BATCH)]
    failed = 0
    for batch in batches:
        try:
            results = classify(batch)
        except Exception as e:  # leave the batch unseen so the next run retries it
            print(f"::warning::classify failed: {e}")
            failed += 1
            continue
        for item in batch:
            r = results.get(item["url"])
            if not r:
                continue
            seen[item["url"]] = item["date"]
            if r["relevance"] >= MIN_RELEVANCE:
                data["items"].append({k: item[k] for k in ("date", "title", "url", "publisher")}
                                     | {"category": r["category"], "summary": r["summary"], "relevance": r["relevance"]})

    keep = (today - timedelta(days=KEEP_DAYS)).isoformat()
    data["items"] = cap_per_day([i for i in data["items"] if i["date"] >= keep])
    state["seen"] = {u: d for u, d in seen.items() if d >= keep}

    weekly = data.get("weekly")
    if not weekly or weekly["selected_on"] != today.isoformat():
        try:
            data["weekly"] = pick_weekly(data["items"], today) or weekly
        except Exception as e:
            print(f"::warning::weekly pick failed: {e}")

    data["generated_at"] = now().isoformat(timespec="seconds")
    SITE.mkdir(exist_ok=True)
    data_path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    (SITE / "rss.xml").write_text(rss(data["items"]))
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    (ROOT / "dead-feeds.txt").write_text("".join(f"{u}\n" for u in dead))

    if batches and failed == len(batches):
        sys.exit("every classify batch failed; check OLLAMA_API_KEY / Ollama Cloud")


if __name__ == "__main__":
    main()
