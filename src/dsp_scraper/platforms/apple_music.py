"""Search Apple Music for a release."""
import re
from urllib.parse import quote, urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from dsp_scraper.matching import Candidate
from dsp_scraper.platforms._common import SEARCH_TIMEOUT_MS, new_page

SEARCH_URL = "https://music.apple.com/us/search?term={query}"
# verified live 2026-08-23: a "song" link carries a "?i=<track id>" query
# string on top of its parent album's URL; filtering those out leaves only
# genuine album/EP links, found consistently across every result shelf
# (Top Results, Albums, ...) without needing to target a specific shelf.
RESULT_SELECTOR = 'a[href*="/album/"]:not([href*="?i="])'
ORIGIN = "https://music.apple.com"


def _artist_from_container(text: str) -> str:
    # Apple Music's layout varies by shelf and viewport. The card text is
    # "Title\nAlbum · Artist" (Top Results), "Title\nTitle\n\nArtist" (grid),
    # or on some widths all on one line, separated by runs of spaces:
    # "Title          Title          Artist". Splitting on newlines, "·" and
    # runs of 2+ spaces leaves the artist as the last piece in every case.
    pieces = [p.strip() for p in re.split(r"\n|·|\s{2,}", text)]
    pieces = [p for p in pieces if p and p != "\xa0"]
    return pieces[-1] if pieces else ""


def search(artist: str, title: str) -> list[Candidate]:
    """ponytail: RESULT_SELECTOR was verified against the live site once
    (2026-08-23). If search() silently returns [] for a query you know has
    results, Apple Music likely changed its album link paths - open
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
            # the album's cover link has no text, the title link next to it does
            title_text = link.inner_text().strip()
            if not href or not title_text:
                continue
            container = link.evaluate_handle('e => e.closest("li") || e.parentElement.parentElement')
            el = container.as_element()
            artist_text = _artist_from_container(el.inner_text() if el else "")
            candidates.append(Candidate(title=title_text, artist=artist_text, url=urljoin(ORIGIN, href)))
        return candidates
