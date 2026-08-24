"""Search Apple Music for a release."""
from urllib.parse import quote, urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from matching import Candidate
from platforms._common import SEARCH_TIMEOUT_MS, new_page

SEARCH_URL = "https://music.apple.com/us/search?term={query}"
# verified live 2026-08-23: a "song" link carries a "?i=<track id>" query
# string on top of its parent album's URL; filtering those out leaves only
# genuine album/EP links, found consistently across every result shelf
# (Top Results, Albums, ...) without needing to target a specific shelf.
RESULT_SELECTOR = 'a[href*="/album/"]:not([href*="?i="])'
ORIGIN = "https://music.apple.com"


def _extract_title_artist(text: str) -> tuple[str, str]:
    # ponytail: Apple Music renders the same album link two different ways
    # depending on which shelf it's in - "Title\n\xa0\nAlbum · Artist" in
    # "Top Results", "Title\nTitle\n\nArtist" in the "Albums" grid. Both
    # reduce to "first non-empty line is the title, last is the artist
    # (stripping an 'Album · ' prefix if present)".
    lines = [l.strip() for l in text.split("\n") if l.strip() and l.strip() != "\xa0"]
    if not lines:
        return "", ""
    title = lines[0]
    last = lines[-1]
    artist = last.split("·")[-1].strip() if "·" in last else last
    return title, artist


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
            container = link.evaluate_handle('e => e.closest("li") || e.parentElement.parentElement')
            el = container.as_element()
            text = el.inner_text().strip() if el else ""
            if not href or not text:
                continue
            title_text, artist_text = _extract_title_artist(text)
            candidates.append(Candidate(title=title_text, artist=artist_text, url=urljoin(ORIGIN, href)))
        return candidates
