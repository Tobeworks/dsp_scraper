"""Search SoundCloud for a release."""
import re
from urllib.parse import quote, urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from dsp_scraper.matching import Candidate
from dsp_scraper.platforms._common import SEARCH_TIMEOUT_MS, new_page

ORIGIN = "https://soundcloud.com"
# verified live 2026-08-24: SoundCloud represents a Bandcamp-style "release"
# as an album/set (a /<user>/sets/<slug> URL), not a single track - searching
# only /search/sounds surfaces individual tracks even when the artist's own
# album/EP exists as a set. /search/albums is the endpoint that actually
# finds it. Both searches share the same result-item class.
ALBUM_SEARCH_URL = "https://soundcloud.com/search/albums?q={query}"
TRACK_SEARCH_URL = "https://soundcloud.com/search/sounds?q={query}"
RESULT_SELECTOR = "li.searchList__item"
# each card's playable-item wrapper carries a clean, unpolluted
# "Playlist: <title> by <artist>" aria-label (used for both sets AND plain
# tracks, apparently every playable item is wrapped as a "stream context").
# The card's *visible* title text is not this clean - SoundCloud appends a
# release-type suffix to it (e.g. "Atlas EP") even when the item's real
# title is just "Atlas" (confirmed against the set's own page: its <h1> and
# aria-label both say "Atlas", nothing else) - so prefer the aria-label.
ARIA_LABEL_RE = re.compile(r"^(?:Playlist|Track): (.+) by (.+)$")


def _candidates_from(page, url: str) -> list[Candidate]:
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

        group = row.query_selector('[role="group"][aria-label]')
        label_match = ARIA_LABEL_RE.match(group.get_attribute("aria-label")) if group else None
        if label_match:
            title_text, artist_text = label_match.group(1), label_match.group(2)
        else:
            # ponytail: fallback for the rare row with no aria-label (verified
            # live 2026-08-24, a handful of rows lack it) - less reliable,
            # may carry the release-type-suffix pollution described above.
            lines = [l for l in row.inner_text().split("\n") if l.strip()]
            artist_text = lines[0] if lines else ""
            title_text = lines[1].split("·")[0].strip() if len(lines) > 1 else ""

        candidates.append(Candidate(title=title_text, artist=artist_text, url=urljoin(ORIGIN, href)))
    return candidates


def search(artist: str, title: str) -> list[Candidate]:
    """ponytail: RESULT_SELECTOR was verified against the live site once
    (2026-08-24). If search() silently returns [] for a query you know has
    results, SoundCloud likely renamed this class - open one of the
    SEARCH_URL constants manually and re-check.

    A Bandcamp album/EP is often a SoundCloud "set" (/<user>/sets/<slug>),
    not a single track - searches both and lets matching.pick_best() choose
    across the combined pool. Album candidates are listed first, so on an
    exact-match tie between a set and a same-named track (the common case
    for a real release: both score 100 once the title is extracted cleanly,
    see the ARIA_LABEL_RE comment above) the set wins. An earlier version of
    this function actively forced album preference above a score threshold
    to work around what looked like sets losing to tracks unfairly - that
    turned out to be caused entirely by the polluted visible-title bug
    (fixed by switching to the aria-label), not a real scoring gap. With
    clean titles, plain merged scoring already gets both right: real sets
    win their ties, and an unrelated artist's same-named album (e.g. "Moon
    Glow" by Benny Goodman for reference "Glow") no longer scores high
    enough to beat the correct track."""
    query = quote(f"{artist} {title}")
    with new_page() as page:
        albums = _candidates_from(page, ALBUM_SEARCH_URL.format(query=query))
        tracks = _candidates_from(page, TRACK_SEARCH_URL.format(query=query))
        return albums + tracks
