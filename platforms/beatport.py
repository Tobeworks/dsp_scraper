"""Search Beatport for a release."""
from urllib.parse import quote, urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from matching import Candidate
from platforms._common import SEARCH_TIMEOUT_MS, new_page

SEARCH_URL = "https://www.beatport.com/search?q={query}"
# verified live 2026-08-23: each release link's closest <li> ancestor's text
# is "Title\nArtist(s)\nLabel"
RESULT_SELECTOR = 'a[href*="/release/"]'
ORIGIN = "https://www.beatport.com"


def search(artist: str, title: str) -> list[Candidate]:
    """ponytail: RESULT_SELECTOR was verified against the live site once
    (2026-08-23). If search() silently returns [] for a query you know has
    results, Beatport likely changed its release link paths - open
    SEARCH_URL manually and re-check."""
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
            container = link.evaluate_handle('e => e.closest("li") || e.parentElement')
            el = container.as_element()
            text = el.inner_text().strip() if el else ""
            if not href or not text:
                continue
            lines = [l for l in text.split("\n") if l.strip()]
            title_text = lines[0] if lines else ""
            artist_text = lines[1] if len(lines) > 1 else ""
            candidates.append(Candidate(title=title_text, artist=artist_text, url=urljoin(ORIGIN, href)))
        return candidates
