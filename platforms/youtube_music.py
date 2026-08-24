"""Search YouTube Music for a release.

DISABLED as of 2026-08-23: excluded from main.PLATFORMS. EU visitors hit a
Google cookie-consent wall that the best-effort dismiss below hasn't beaten
reliably (see _dismiss_consent_wall). Module kept importable/testable for
when a workaround is found - see README "known limitations".
"""
from urllib.parse import quote, urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from matching import Candidate
from platforms._common import SEARCH_TIMEOUT_MS, new_page

SEARCH_URL = "https://music.youtube.com/search?q={query}"
# custom element tag - more stable across deploys than generated class names
RESULT_SELECTOR = "ytmusic-responsive-list-item-renderer"
ORIGIN = "https://music.youtube.com"


def _dismiss_consent_wall(page):
    # ponytail: EU visitors get redirected to a Google cookie-consent page
    # before reaching music.youtube.com - click through it if it shows up.
    if "consent.youtube.com" not in page.url:
        return
    button = page.query_selector('button:has-text("Reject all")') or page.query_selector(
        'button:has-text("Accept all")'
    )
    if button:
        button.click()
        page.wait_for_url("**music.youtube.com**", timeout=SEARCH_TIMEOUT_MS)


def search(artist: str, title: str) -> list[Candidate]:
    """ponytail: RESULT_SELECTOR/inner selectors are a best-effort guess
    against the live site, not yet verified. If search() silently returns []
    for a query you know has results: open SEARCH_URL manually, inspect a
    result row, and update the selector constants above."""
    query = quote(f"{artist} {title}")
    url = SEARCH_URL.format(query=query)
    with new_page() as page:
        page.goto(url, timeout=SEARCH_TIMEOUT_MS)
        _dismiss_consent_wall(page)
        try:
            page.wait_for_selector(RESULT_SELECTOR, timeout=SEARCH_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            return []

        candidates = []
        for row in page.query_selector_all(RESULT_SELECTOR):
            link = row.query_selector("a[href]")
            title_el = row.query_selector(".title")
            artist_el = row.query_selector(".secondary-flex-columns")
            if not link or not title_el:
                continue
            href = link.get_attribute("href")
            title_text = title_el.inner_text().strip()
            artist_text = artist_el.inner_text().strip() if artist_el else ""
            candidates.append(Candidate(title=title_text, artist=artist_text, url=urljoin(ORIGIN, href)))
        return candidates
