"""Search Napster for a release.

DISABLED as of 2026-08-23: excluded from core.PLATFORMS. Napster's product
appears to have pivoted away from music search for anonymous visitors (see
RESULT_SELECTOR note below). Module kept importable/testable for when a
workaround is found - see README "known limitations".
"""
from urllib.parse import quote, urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from dsp_scraper.matching import Candidate
from dsp_scraper.platforms._common import SEARCH_TIMEOUT_MS, new_page

SEARCH_URL = "https://app.napster.com/search?query={query}"
# ponytail: as of 2026-08-23, Napster's search page no longer shows music
# results for anonymous visitors - the app now fronts an "AI experts" product
# and the search UI seems to have been repurposed/removed. This selector is
# an untested best guess; search() will likely just return [] consistently,
# which is an acceptable outcome per spec (platform shows up with url: null).
RESULT_SELECTOR = 'a[href*="/album/"], a[href*="/track/"]'
ORIGIN = "https://napster.com"


def search(artist: str, title: str) -> list[Candidate]:
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
