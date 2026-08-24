"""Search Tidal for a release.

DISABLED as of 2026-08-23: excluded from core.PLATFORMS. Anonymous search
page consistently renders no usable result DOM (see RESULT_SELECTOR note
below). Module kept importable/testable for when a workaround is found -
see README "known limitations".
"""
from urllib.parse import quote, urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from dsp_scraper.matching import Candidate
from dsp_scraper.platforms._common import SEARCH_TIMEOUT_MS, new_page

SEARCH_URL = "https://tidal.com/search?q={query}"
# ponytail: highest-risk module of the 5 - Tidal may show a login wall or an
# entirely different DOM for anonymous visitors, so this may just always
# return []. That's an acceptable outcome per spec (platform shows up with
# url: null), not worth forcing further right now.
RESULT_SELECTOR = 'a[href*="/album/"], a[href*="/track/"]'
ORIGIN = "https://tidal.com"


def search(artist: str, title: str) -> list[Candidate]:
    """ponytail: RESULT_SELECTOR is an unverified guess against the live
    site. If search() silently returns [] for a query you know has results:
    open SEARCH_URL manually, inspect a result link, and update the
    selector constant above."""
    query = quote(f"{artist} {title}")
    url = SEARCH_URL.format(query=query)
    with new_page() as page:
        page.goto(url, timeout=SEARCH_TIMEOUT_MS)
        try:
            page.wait_for_selector(RESULT_SELECTOR, timeout=SEARCH_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            return []

        candidates = []
        for link in page.query_selector_all(RESULT_SELECTOR):
            href = link.get_attribute("href")
            text = link.inner_text().strip()
            if not href or not text:
                continue
            lines = [l for l in text.split("\n") if l.strip()]
            title_text = lines[0] if lines else text
            artist_text = lines[1] if len(lines) > 1 else ""
            candidates.append(Candidate(title=title_text, artist=artist_text, url=urljoin(ORIGIN, href)))
        return candidates
