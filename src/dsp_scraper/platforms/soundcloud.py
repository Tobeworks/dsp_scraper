"""Search SoundCloud for a release."""
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
        lines = [l for l in row.inner_text().split("\n") if l.strip()]
        artist_text = lines[0] if lines else ""
        # album/set cards append " · <year>" to the title line - tracks don't,
        # and splitting on "·" is a harmless no-op when it's absent
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
    across the combined pool.
    ponytail: an earlier version of this function tried to actively prefer
    album/set candidates whenever one cleared the normal match threshold on
    its own, to surface the set instead of an individual track for the same
    release. Verified live (2026-08-24) that this trades one fix for two
    new false positives elsewhere: a short, common-word title (e.g. "Glow")
    can make an unrelated artist's same-named album clear the threshold too
    ("Moon Glow" by Benny Goodman for reference "Glow"), and there's no
    text-similarity signal available to tell those apart - the wrong
    artist's SET candidate can score just as well as the right one (proven
    empirically: a genuinely wrong "Electric Moon Pearl" scored HIGHER as
    an artist match than the genuinely correct "Chitra Records" label
    credit did for a real release). User chose to keep plain merged scoring
    (no false positives found) over that trade-off - see git history if
    revisiting this."""
    query = quote(f"{artist} {title}")
    with new_page() as page:
        albums = _candidates_from(page, ALBUM_SEARCH_URL.format(query=query))
        tracks = _candidates_from(page, TRACK_SEARCH_URL.format(query=query))
        return albums + tracks
