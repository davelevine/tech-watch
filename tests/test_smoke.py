"""Browser smoke test: the feed, reader, palette and swipe work under the real CSP, with no CSP violations,
console errors or page errors. Runs against `wrangler pages dev site` (CI starts one); skipped without SMOKE_URL.
/api/read is stubbed so the test doesn't depend on outside sites; tests/read.test.js covers the function."""
import json
import os
import re
import urllib.parse

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
    return card, card.locator(".card-title").inner_text()


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
    assert pg.locator(".filter-btn").count() >= 7  # All + every category
    assert re.fullmatch(r"Updated (just now|\d+[mhd] ago)", pg.inner_text("#updated"))
    assert pg.problems == []


def test_phone_menu(browser):
    pg = open_site(browser, viewport={"width": 320, "height": 700}, has_touch=True, is_mobile=True)
    assert pg.locator("#updated").is_visible() and pg.locator("#theme").is_hidden()
    assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
    pg.tap("#menu-btn")
    assert pg.locator("#menu a[href='/rss.xml']").is_visible()
    theme = pg.evaluate("document.documentElement.dataset.theme")
    pg.tap("#theme")
    pg.wait_for_function("t => document.documentElement.dataset.theme !== t", arg=theme)  # swaps inside a view transition
    pg.keyboard.press("Escape")
    assert pg.locator("#theme").is_hidden()
    assert pg.problems == []


def test_wide_screens_keep_the_controls_in_the_header(browser):
    pg = open_site(browser, viewport={"width": 1300, "height": 900})
    assert pg.locator("#theme").is_visible() and pg.locator("#menu-btn").is_hidden()
    assert pg.problems == []


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
