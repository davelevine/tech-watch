import json
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

import build


def test_normalize_url_strips_tracking():
    assert build.normalize_url("https://Example.com/a?utm_source=x&id=1&ref=hn#top") == "https://example.com/a?id=1"


def test_opml_parses():
    feeds = build.read_opml(build.ROOT / "feeds.opml")
    assert feeds and all(url.startswith("https://") for _, url in feeds)


def test_candidates_filters_and_caps():
    now = datetime.now(timezone.utc)
    t = lambda d: (now - timedelta(days=d)).timetuple()
    entries = [{"link": f"https://x.test/{n}?utm_medium=rss", "title": f"T{n}", "published_parsed": t(0)} for n in range(15)]
    entries += [
        {"link": "https://x.test/old", "title": "old", "published_parsed": t(10)},
        {"link": "https://x.test/undated", "title": "undated"},
        {"link": "javascript:alert(1)", "title": "xss", "published_parsed": t(0)},
        {"link": "https://x.test/seen", "title": "seen", "published_parsed": t(0)},
    ]
    out = build.candidates("X", entries, {"https://x.test/seen": "2026-01-01"}, now - timedelta(days=3))
    urls = {c["url"] for c in out}
    assert len(out) == build.PER_FEED
    assert not urls & {"https://x.test/old", "https://x.test/undated", "javascript:alert(1)", "https://x.test/seen"}
    assert all("utm_" not in u for u in urls)


def test_feed_health_reports_only_long_failures():
    today = date(2026, 11, 20)
    health = {"https://a": "2026-11-01", "https://b": "2026-11-19", "https://c": "2026-10-01"}
    dead = build.update_feed_health(health, {"https://a": False, "https://b": False, "https://c": True, "https://d": False}, today)
    assert dead == ["https://a"]
    assert "https://c" not in health and health["https://d"] == "2026-11-20"


def test_rss_is_well_formed():
    xml = build.rss([{"date": "2026-11-05", "title": "A & B <c>", "url": "https://x.test/?a=1&b=2",
                      "category": "ai", "summary": "s"}])
    assert ET.fromstring(xml).find("channel/item/title").text == "A & B <c>"


def test_cap_per_day_keeps_most_relevant():
    items = [{"date": "2026-11-05", "url": f"https://x.test/{n}", "relevance": n % 10 + 1} for n in range(14)]
    items.append({"date": "2026-11-04", "url": "https://x.test/old"})
    out = build.cap_per_day(items)
    today = [i for i in out if i["date"] == "2026-11-05"]
    dropped = [i for i in items[:14] if i not in today]
    assert len(today) == build.DAILY_MAX
    assert min(i["relevance"] for i in today) >= max(i["relevance"] for i in dropped)
    assert out[-1]["url"] == "https://x.test/old"


def test_scoring_never_sees_recent_headlines(monkeypatch):
    sent = {}
    monkeypatch.setattr(build, "llm", lambda system, user, schema: sent.update(payload=json.loads(user)) or
                        [{"id": 0, "category": "ai", "relevance": 8, "summary": "s"}])
    out = build.classify([{"url": "https://x.test/a", "title": "T", "publisher": "P", "excerpt": "E"}])
    assert sent["payload"] == [{"id": 0, "title": "T", "publisher": "P", "excerpt": "E"}]
    assert out["https://x.test/a"]["relevance"] == 8


def test_find_repeats_sends_recent_headlines(monkeypatch):
    sent = {}
    monkeypatch.setattr(build, "llm", lambda system, user, schema: sent.update(json.loads(user)) or
                        [{"id": 0, "duplicate_of": "Old headline"}])
    out = build.find_repeats([{"url": "https://x.test/a", "title": "T", "publisher": "P", "excerpt": "E", "summary": "S"}],
                             ["Old headline"])
    assert sent["recent"] == ["Old headline"] and sent["items"][0]["summary"] == "S"
    assert out == {"https://x.test/a": "Old headline"}


def test_repeats_always_leaves_one_copy():
    recent = {build.norm("OpenSSH flaw  lets attackers in")}
    assert build.repeats("openssh flaw lets attackers in", 0, set(), recent)  # quoted, case/space-insensitive
    assert not build.repeats("OpenSSH flaw", 0, set(), recent)              # misquote is ignored
    assert build.repeats("0", 3, {0}, set())                                # earlier, covered batch item
    assert not build.repeats("0", 3, set(), set())                          # earlier item not covered
    assert not build.repeats("3", 3, {3}, set())                            # points at itself
    assert not build.repeats("5", 3, {5}, set())                            # points forward
    assert not build.repeats(None, 3, set(), set())
