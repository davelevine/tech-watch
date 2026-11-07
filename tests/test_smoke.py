"""Browser smoke test: the feed, reader, palette and swipe work under the real CSP, with no CSP violations,
console errors or page errors. Runs against `wrangler pages dev site` (CI starts one); skipped without SMOKE_URL.
/api/read is stubbed so the test doesn't depend on outside sites; tests/read.test.js covers the function."""
import json
import os
import re
import urllib.parse
from datetime import date, datetime, timedelta, timezone

import pytest

URL = os.environ.get("SMOKE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set SMOKE_URL to a running `wrangler pages dev site`")

PIXEL = "data:image/gif;base64,R0lGODlhAQABAAAAACw="
BODY = "".join(f"<p>Paragraph {n} of the stub article, long enough to read like the real thing.</p>" for n in range(30))


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("PW_CHROMIUM") or None)
        yield b
        b.close()


def open_site(browser, **context):
    ctx = browser.new_context(**context)
    pg = ctx.new_page()
    pg.problems = []
    pg.on("pageerror", lambda e: pg.problems.append(f"page error: {e}"))
    pg.on("console", lambda m: pg.problems.append(f"console: {m.text}") if m.type == "error" else None)

    def stub(route):
        url = urllib.parse.parse_qs(urllib.parse.urlsplit(route.request.url).query)["url"][0]
        route.fulfill(content_type="application/json",
                      body=json.dumps({"url": url, "frameable": False, "content": f'<img src="{PIXEL}" alt="">{BODY}'}))
    ctx.route("**/api/read?*", stub)
    pg.goto(URL)
    pg.wait_for_selector("a.card")
    return pg


def first_card(pg):
    card = pg.locator("a.card").first
    return card, card.locator(".card-title").text_content()  # inner_text is empty until content-visibility renders the card


def reading(pg):
    return pg.evaluate("document.body.classList.contains('reading')")


def wait_until_closed(pg, timeout=5000):
    # Not page.wait_for_function: it evaluates a string, which the CSP (rightly) blocks.
    for _ in range(timeout // 100):
        if not reading(pg):
            return
        pg.wait_for_timeout(100)
    state = pg.evaluate("({ messages: window.__tw || null, drag: getComputedStyle(document.documentElement).getPropertyValue('--drag'),"
                        " frames: document.querySelectorAll('#reader-body iframe').length, hash: location.hash.slice(0, 40) })")
    raise AssertionError(f"the reader didn't close: {state}")


def test_csp_header_is_served(browser):
    pg = open_site(browser)
    csp = pg.request.get(URL).headers.get("content-security-policy", "")
    assert "script-src 'self' 'sha256-" in csp and "object-src 'none'" in csp
    assert pg.problems == []


def test_feed_renders(browser):
    pg = open_site(browser)
    assert pg.locator("a.card").count() > 0
    assert pg.locator(".filter-btn").count() >= 2  # All + each category with stories
    assert pg.locator(".filter-btn", has_text="(0)").count() == 0
    assert re.fullmatch(r"Updated (just now|\d+[mhd] ago)", pg.inner_text("footer #updated"))
    assert pg.locator("header #updated").count() == 0
    assert re.fullmatch(r"· \d+ stor(y|ies)( · \d+\+? min)?", pg.locator(".day-meta").first.inner_text())
    assert pg.locator(".card-arrow").count() == 0 and pg.locator(".card-time").count() == 0
    assert pg.locator(".weekly-why").first.inner_text() != ""
    assert pg.problems == []


def test_phone_menu(browser):
    pg = open_site(browser, viewport={"width": 320, "height": 700}, has_touch=True, is_mobile=True)
    assert pg.locator("#theme").is_hidden()
    assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
    pg.tap("#menu-btn")
    assert pg.locator("#menu a[href='/rss.xml']").is_visible()
    theme = pg.evaluate("document.documentElement.dataset.theme")
    pg.tap("#theme")
    pg.wait_for_function("t => document.documentElement.dataset.theme !== t", arg=theme)  # swaps inside a view transition
    pg.keyboard.press("Escape")
    pg.locator("#theme").wait_for(state="hidden")  # after the closing fade
    # Tapping away closes the menu without opening the article underneath.
    pg.tap("#menu-btn")  # before measuring: playwright's tap may scroll the page to reach the button
    x, y = pg.evaluate("""() => { const r = [...document.querySelectorAll('a.card')].map(c => c.getBoundingClientRect())
        .find(r => r.bottom > 340 && r.top < innerHeight - 40); return [r.left + r.width / 2, Math.max(r.top, 300) + 20]; }""")  # below the drawer
    assert pg.evaluate("document.getElementById('menu').getBoundingClientRect().width") == 320  # full width
    pg.wait_for_timeout(300)
    pg.touchscreen.tap(x, y)
    pg.locator("#theme").wait_for(state="hidden")
    assert not reading(pg)
    pg.touchscreen.tap(x, y)
    pg.wait_for_selector("#reader-body iframe")
    assert pg.problems == []


def test_animations_run_under_reduced_motion(browser):
    pg = open_site(browser, viewport={"width": 412, "height": 800}, has_touch=True, is_mobile=True, reduced_motion="reduce")
    running = "s => getComputedStyle(document.querySelector(s)).transitionDuration !== '0s' && getComputedStyle(document.querySelector(s)).transitionProperty !== 'none'"
    for selector in ("#menu", "#reader"):
        assert pg.evaluate(running, selector), selector
    pg.tap("#menu-btn")
    pg.wait_for_function("() => document.getElementById('menu').getAnimations().length > 0 || getComputedStyle(document.getElementById('menu')).clipPath.includes('-40px')")
    pg.evaluate("document.getElementById('theme').click()")
    pg.wait_for_function("() => document.getAnimations().some(a => a.effect.pseudoElement?.includes('view-transition'))")
    assert pg.problems == []


def test_phone_filter_drawer(browser):
    pg = open_site(browser, viewport={"width": 320, "height": 700}, has_touch=True, is_mobile=True)
    assert pg.locator("#filters .filter-btn").first.is_hidden() and pg.locator("#filter-label").inner_text() == ""
    assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
    pg.tap("#filter-toggle")
    pg.wait_for_function("() => !document.getElementById('filters').getAnimations().length")
    for chip in pg.locator("#filters .filter-btn").all():
        assert chip.is_visible() and chip.bounding_box()["x"] + chip.bounding_box()["width"] <= 320  # all reachable, wrapped
    assert pg.evaluate("Math.round(document.getElementById('filters').getBoundingClientRect().top) === Math.round(document.querySelector('.subheader').getBoundingClientRect().bottom)")
    pg.tap("#filters .filter-btn[data-f='security']")
    pg.locator("#filters .filter-btn").first.wait_for(state="hidden")
    assert pg.locator("#filter-label").inner_text() == "Security"
    assert pg.locator("#filter-toggle").get_attribute("aria-label") == "Filters: Security"
    assert pg.locator(".card-cat").evaluate_all("els => els.every(e => e.textContent === 'Security')")
    pg.tap("#filter-toggle")
    pg.tap("#filters .filter-btn[data-f='all']")
    pg.locator("#filters .filter-btn").first.wait_for(state="hidden")
    assert pg.locator("#filter-label").inner_text() == ""
    assert pg.problems == []


def test_essentials_card_layout(browser):
    pg = open_site(browser, viewport={"width": 1300, "height": 900})
    card = pg.locator(".weekly-card").first
    assert card.locator(".weekly-top .rank").count() == 1 and card.locator(".weekly-top .weekly-cat .dot").count() == 1
    assert card.locator(".weekly-top .weekly-source").count() == 0  # the publisher moved to the bottom line
    # A long publisher shortens before the date does, and the line stays inside the card.
    card.locator(".weekly-source").evaluate("e => { e.textContent = 'A Very Long Publisher Name That Cannot Possibly Fit Here' }")
    fits = """c => { const m = c.querySelector('.weekly-meta').getBoundingClientRect(), r = c.getBoundingClientRect(),
        d = c.querySelector('.weekly-meta > :last-child'); return m.right <= r.right && d.scrollWidth <= d.clientWidth && d.textContent.startsWith('·'); }"""
    assert card.evaluate(fits)
    assert pg.problems == []


def stale_site(browser, hours, **context):
    ctx = browser.new_context(**context)
    pg = ctx.new_page()
    def patched(route):
        data = route.fetch().json()
        data["generated_at"] = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
        route.fulfill(json=data)
    ctx.route("**/data.json*", patched)
    pg.goto(URL)
    pg.wait_for_selector("a.card")
    return pg


def test_stale_band_appears_after_twelve_hours(browser):
    pg = stale_site(browser, 11, viewport={"width": 1300, "height": 900})
    assert pg.locator("#stale").is_hidden()
    pg = stale_site(browser, 14, viewport={"width": 1300, "height": 900})
    assert pg.locator("#stale").inner_text() == "Last updated 14h ago · the build may be stalled"
    assert pg.get_attribute("#stale", "href").endswith("/actions/workflows/build.yml")


def test_stale_band_keeps_the_filter_drawer_under_the_search_row(browser):
    pg = stale_site(browser, 14, viewport={"width": 320, "height": 700}, has_touch=True, is_mobile=True)
    assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
    pg.tap("#filter-toggle")
    pg.wait_for_function("() => !document.getElementById('filters').getAnimations().length")
    assert pg.evaluate("Math.round(document.getElementById('filters').getBoundingClientRect().top) === Math.round(document.querySelector('.subheader').getBoundingClientRect().bottom)")


def test_day_minutes_show_only_when_every_story_has_one(browser):
    ctx = browser.new_context(viewport={"width": 1300, "height": 900}, timezone_id="UTC")
    pg = ctx.new_page()
    today = datetime.now(timezone.utc).date().isoformat()
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    def patched(route):
        data = route.fetch().json()
        a, b, c = data["items"][:3]
        data["items"] = [{**a, "date": today, "minutes": 4}, {**b, "date": today, "minutes": 3}, {**c, "date": yesterday, "minutes": 0}]
        route.fulfill(json=data)
    ctx.route("**/data.json*", patched)
    pg.goto(URL)
    pg.wait_for_selector("a.card")
    assert pg.locator(".day-meta").all_inner_texts()[:2] == ["· 2 stories · 7 min", "· 1 story"]


def test_wide_screens_keep_the_filter_row(browser):
    pg = open_site(browser, viewport={"width": 1300, "height": 900})
    assert pg.locator("#filter-toggle").is_hidden() and pg.locator("#filters .filter-btn").first.is_visible()
    pg.click("#filters .filter-btn[data-f='ai']")
    assert pg.locator("#filters .filter-btn.active").get_attribute("data-f") == "ai"
    assert pg.locator("#filters .filter-btn").first.is_visible()  # picking one leaves the row in place
    assert pg.problems == []


def test_wide_screens_keep_the_controls_in_the_header(browser):
    pg = open_site(browser, viewport={"width": 1300, "height": 900})
    assert pg.locator("#theme").is_visible() and pg.locator("#menu-btn").is_hidden()
    assert pg.problems == []


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_wcag(browser, scheme):
    from axe_playwright_python.sync_playwright import Axe
    tags = {"runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]}}
    pg = open_site(browser, viewport={"width": 412, "height": 915}, has_touch=True, is_mobile=True, color_scheme=scheme)
    def violations():
        return [(v["id"], v["nodes"][0]["html"][:80]) for v in Axe().run(pg, options=tags).response["violations"]]
    assert violations() == []
    # Every control on a phone is at least 44px. The info button reaches it through ::after, which a rect can't see.
    small = """() => [...document.querySelectorAll('a, button, input')].filter(e => e.id !== 'info').map(e => [e, e.getBoundingClientRect()])
        .filter(([, r]) => r.width && r.height && (r.width < 44 || r.height < 44)).map(([e, r]) => `${e.id || e.className} ${r.width}x${r.height}`)"""
    assert pg.evaluate(small) == []
    pg.tap("#menu-btn")
    pg.wait_for_function("() => !document.getElementById('menu').getAnimations().length")  # let the drawer finish opening
    assert violations() == [] and pg.evaluate(small) == []
    assert pg.get_attribute("#theme", "aria-label") == f"Switch to {'light' if scheme == 'dark' else 'dark'} mode"
    pg.keyboard.press("Escape")
    pg.tap("#filter-toggle")
    pg.wait_for_function("() => !document.getElementById('filters').getAnimations().length")
    assert violations() == [] and pg.evaluate(small) == []
    assert pg.problems == []


def test_one_today_section_when_utc_is_already_tomorrow(browser):
    ctx = browser.new_context(timezone_id="America/New_York")
    pg = ctx.new_page()
    today = pg.evaluate("new Date().toLocaleDateString('en-CA')")  # YYYY-MM-DD in that zone
    tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
    def patched(route):
        data = route.fetch().json()
        data["items"] = [{**item, "date": day} for item, day in zip(data["items"], [tomorrow, today, today])]
        route.fulfill(json=data)
    ctx.route("**/data.json*", patched)
    pg.goto(URL)
    pg.wait_for_selector("a.card")
    today_labels = pg.locator(".date-label", has_text="Today")
    assert today_labels.count() == 1
    assert today_labels.locator(".day-meta").inner_text().startswith("· 3 stories")


def test_reader_and_frame_relay_run_under_csp(browser):
    pg = open_site(browser, viewport={"width": 1300, "height": 900})
    card, title = first_card(pg)
    card.click()
    frame = pg.frame_locator("#reader-body iframe")
    assert frame.locator("h1").inner_text() == title
    assert frame.locator("h1 a").get_attribute("href") == card.get_attribute("href")
    assert frame.locator("p").count() == 30
    # Escape pressed inside the article only reaches the page through the frame's relay script,
    # so closing proves the CSP lets that hashed script run.
    frame.locator("p").first.click()
    pg.keyboard.press("Escape")
    wait_until_closed(pg)
    assert pg.problems == []


def test_search_palette(browser):
    pg = open_site(browser, viewport={"width": 1300, "height": 900})
    _, title = first_card(pg)
    pg.keyboard.press("Control+K")
    assert pg.locator("#palette").is_visible()
    pg.keyboard.type(title.split()[0])
    assert pg.locator("#palette-list li[data-n]").count() > 0
    pg.keyboard.press("Enter")
    pg.wait_for_selector("#reader-body iframe")
    assert reading(pg) and pg.locator("#palette").is_hidden()
    assert pg.problems == []


def test_swipe_back_on_a_phone(browser):
    pg = open_site(browser, viewport={"width": 412, "height": 915}, has_touch=True, is_mobile=True)
    card, _ = first_card(pg)
    card.scroll_into_view_if_needed()
    pg.wait_for_timeout(300)
    card.tap()
    pg.wait_for_selector("#reader-body iframe")
    pg.frame_locator("#reader-body iframe").locator("p").first.wait_for()
    # Wait for the slide-in to finish: until then the touch lands on the (inert) feed behind it.
    for _ in range(50):
        if pg.evaluate("new DOMMatrix(getComputedStyle(document.getElementById('reader')).transform).m41") == 0:
            break
        pg.wait_for_timeout(100)
    pg.evaluate("window.__tw = []; addEventListener('message', e => __tw.push(e.data && e.data.tw))")
    cdp = pg.context.new_cdp_session(pg)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": 80, "y": 600}]})
    for k in range(1, 13):
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": 80 + 22 * k, "y": 602}]})
        pg.wait_for_timeout(16)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    wait_until_closed(pg)
    assert pg.problems == []
