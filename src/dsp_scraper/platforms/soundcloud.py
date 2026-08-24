"""Search SoundCloud for a release."""
from urllib.parse import quote, urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from dsp_scraper.matching import Candidate
from dsp_scraper.platforms._common import SEARCH_TIMEOUT_MS, new_page

SEARCH_URL = "https://soundcloud.com/search/sounds?q={query}"
# verified live 2026-08-23: each result item text is "Artist\nTitle\n..."
RESULT_SELECTOR = "li.searchList__item"
ORIGIN = "https://soundcloud.com"


def search(artist: str, title: str) -> list[Candidate]:
    """ponytail: RESULT_SELECTOR was verified against the live site once
    (2026-08-23). If search() silently returns [] for a query you know has
    results, SoundCloud likely renamed this class - open SEARCH_URL manually
    and re-check."""
    query = quote(f"{artist} {title}")
    url = SEARCH_URL.format(query=query)
    with new_page() as page:
        page.goto(url, timeout=SEARCH_TIMEOUT_MS)
        try:
            page.wait_for_selector(RESULT_SELECTOR, timeout=SEARCH_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            return []

        candidates = []
        for row in page.query_selector_all(RESULT_SELECTOR):
            link = row.query_selector("a[href]")
            if not link:
                continue
            href = link.get_attribute("href")
            lines = [l for l in row.inner_text().split("\n") if l.strip()]
            artist_text = lines[0] if lines else ""
            title_text = lines[1] if len(lines) > 1 else ""
            candidates.append(Candidate(title=title_text, artist=artist_text, url=urljoin(ORIGIN, href)))
        return candidates
