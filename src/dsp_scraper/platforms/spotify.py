"""Search Spotify for a release."""
from urllib.parse import quote, urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from dsp_scraper.matching import Candidate
from dsp_scraper.platforms._common import SEARCH_TIMEOUT_MS, new_page

SEARCH_URL = "https://open.spotify.com/search/{query}"
ORIGIN = "https://open.spotify.com"
# verified live 2026-08-23, anonymous (logged-out) search:
# - the "Albums" shelf renders real album cards, each card's text is
#   "Title\n\nYear • Artist" - reliable title+artist extraction.
# - "top-result-card" is Spotify's own single best-match guess (often a
#   track, even when a matching album exists) - kept as a fallback
#   candidate, not the primary source, so a same-named track can't shadow
#   the actual album release.
ALBUM_SHELF_SELECTOR = '[data-testid="albums-search-entity-shelf"] a[href^="/album/"]'
TOP_RESULT_SELECTOR = '[data-testid="top-result-card"]'


def _album_shelf_candidates(page) -> list[Candidate]:
    candidates = []
    for link in page.query_selector_all(ALBUM_SHELF_SELECTOR):
        href = link.get_attribute("href")
        parent = link.evaluate_handle("e => e.parentElement")
        el = parent.as_element()
        text = el.inner_text().strip() if el else ""
        if not href or not text:
            continue
        title_line, _, meta_line = text.partition("\n\n")
        _, _, artist_text = meta_line.partition(" • ")
        candidates.append(Candidate(title=title_line.strip(), artist=artist_text.strip(), url=urljoin(ORIGIN, href)))
    return candidates


def _top_result_candidate(page) -> list[Candidate]:
    card = page.query_selector(TOP_RESULT_SELECTOR)
    if not card:
        return []
    link = card.query_selector("a[href]")
    if not link:
        return []
    href = link.get_attribute("href")
    lines = [l for l in card.inner_text().split("\n") if l.strip()]
    title_text = lines[0] if lines else ""
    artist_text = lines[-1] if len(lines) > 1 else ""
    return [Candidate(title=title_text, artist=artist_text, url=urljoin(ORIGIN, href))]


def search(artist: str, title: str) -> list[Candidate]:
    """ponytail: selectors were verified against the live site once
    (2026-08-23). If search() silently returns [] for a query you know has
    results, Spotify likely changed one of the testids above - open
    SEARCH_URL manually and re-check. Album-shelf candidates are listed
    before the top-result fallback so a tie in matching.pick_best() favors
    the real album over a same-named track."""
    query = quote(f"{artist} {title}")
    url = SEARCH_URL.format(query=query)
    with new_page() as page:
        page.goto(url, timeout=SEARCH_TIMEOUT_MS)
        try:
            page.wait_for_selector(TOP_RESULT_SELECTOR, timeout=SEARCH_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            return []

        return _album_shelf_candidates(page) + _top_result_candidate(page)
