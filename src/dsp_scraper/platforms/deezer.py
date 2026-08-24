"""Search Deezer for a release."""
from urllib.parse import quote, urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from dsp_scraper.matching import Candidate
from dsp_scraper.platforms._common import SEARCH_TIMEOUT_MS, new_page

SEARCH_URL = "https://www.deezer.com/search/{query}"
ORIGIN = "https://www.deezer.com"
# verified live 2026-08-23: Deezer's result rows are clickable <div>s with no
# href at all (client-side routing) - a generic href scrape mostly picks up
# unrelated promo links elsewhere on the page. These two testids give real
# anchor tags with clean text instead:
# - album grid thumbnail: card text is "Title\n\nArtist\n\n..."
# - single top-result card: title + "Album • Artist" subtitle
ALBUM_GRID_SELECTOR = '[data-testid="album_thumbnail_grid"] [data-testid="album_thumbnail"]'
TOP_RESULT_TITLE_SELECTOR = '[data-testid="album_top_result_title"]'
TOP_RESULT_SUBTITLE_SELECTOR = '[data-testid="album_top_result_subtitle"]'


def _album_grid_candidates(page) -> list[Candidate]:
    candidates = []
    for thumb in page.query_selector_all(ALBUM_GRID_SELECTOR):
        link = thumb.query_selector("a[href]")
        if not link:
            continue
        href = link.get_attribute("href")
        title_block, _, rest = thumb.inner_text().partition("\n\n")
        artist_block, _, _ = rest.partition("\n\n")
        candidates.append(Candidate(title=title_block.strip(), artist=artist_block.strip(), url=urljoin(ORIGIN, href)))
    return candidates


def _top_result_candidate(page) -> list[Candidate]:
    title_el = page.query_selector(TOP_RESULT_TITLE_SELECTOR)
    if not title_el:
        return []
    link = title_el.query_selector("a[href]")
    if not link:
        return []
    href = link.get_attribute("href")
    subtitle_el = page.query_selector(TOP_RESULT_SUBTITLE_SELECTOR)
    subtitle = subtitle_el.inner_text() if subtitle_el else ""
    artist_text = subtitle.split("•")[-1].strip() if "•" in subtitle else subtitle.strip()
    return [Candidate(title=title_el.inner_text().strip(), artist=artist_text, url=urljoin(ORIGIN, href))]


def search(artist: str, title: str) -> list[Candidate]:
    """ponytail: selectors were verified against the live site once
    (2026-08-23). If search() silently returns [] for a query you know has
    results, Deezer likely changed one of the testids above - open
    SEARCH_URL manually and re-check."""
    query = quote(f"{artist} {title}")
    url = SEARCH_URL.format(query=query)
    with new_page() as page:
        page.goto(url, timeout=SEARCH_TIMEOUT_MS)
        try:
            page.wait_for_selector(TOP_RESULT_TITLE_SELECTOR, timeout=SEARCH_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            return []

        return _album_grid_candidates(page) + _top_result_candidate(page)
