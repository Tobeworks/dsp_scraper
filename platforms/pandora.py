"""Search Pandora for a release.

DISABLED as of 2026-08-23: excluded from main.PLATFORMS. Pandora is
US/AU/NZ-only and redirects other regions to /restricted. Module kept
importable/testable for when a workaround is found - see README "known
limitations".
"""
from urllib.parse import quote, urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from matching import Candidate
from platforms._common import SEARCH_TIMEOUT_MS, new_page

SEARCH_URL = "https://www.pandora.com/search/{query}"
# ponytail: as of 2026-08-23, Pandora redirects non-US visitors to
# /restricted (Pandora is US/AU/NZ-only). From a non-US IP this will always
# return [], which is an acceptable outcome per spec (platform shows up with
# url: null) - not worth fighting geo-blocking here.
RESULT_SELECTOR = 'a[href*="/album/"], a[href*="/artist/"]'
ORIGIN = "https://www.pandora.com"


def search(artist: str, title: str) -> list[Candidate]:
    """ponytail: RESULT_SELECTOR is an untested guess - Pandora couldn't be
    reached from this environment to verify (geo-restricted). Verify from a
    US IP before relying on this module."""
    query = quote(f"{artist} {title}")
    url = SEARCH_URL.format(query=query)
    with new_page() as page:
        page.goto(url, timeout=SEARCH_TIMEOUT_MS)
        if "/restricted" in page.url:
            return []
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
