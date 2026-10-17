"""Resolve a platform release URL to artist/title/release_type.

Spec: docs/specs/source-agnostic-lookup.md.
- plain HTTP (no browser): Bandcamp, Apple Music, Deezer (album + track), SoundCloud
- browser (Playwright): Spotify (album + track), Amazon Music (album), smart
  link pages (too.fm, ffm.to). Beatport is not supported: its pages answer
  with a Cloudflare challenge even in a real browser.
"""
import base64
import json
import re
from urllib.parse import parse_qs, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from dsp_scraper.bandcamp import USER_AGENT, scrape_release
from dsp_scraper.platforms._common import SEARCH_TIMEOUT_MS, new_page
from dsp_scraper.types import ReleaseInfo

REQUEST_TIMEOUT_S = 10
SMART_LINK_HOSTS = ["too.fm", "ffm.to"]
SUPPORTED_HOSTS = [
    "bandcamp.com",
    "music.apple.com",
    "deezer.com",
    "soundcloud.com",
    "open.spotify.com",
    "music.amazon.<tld>",
    *SMART_LINK_HOSTS,
]


def _fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _og_title(soup: BeautifulSoup) -> str | None:
    tag = soup.find("meta", property="og:title")
    if not tag or not tag.get("content"):
        return None
    return tag["content"].strip()


def _render_document_title(url: str, ready_js: str, error: str) -> str:
    """Open url in the browser, wait until ready_js is true, return the document title."""
    with new_page() as page:
        page.goto(url, timeout=SEARCH_TIMEOUT_MS)
        try:
            page.wait_for_function(ready_js, timeout=SEARCH_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            raise RuntimeError(f"{error}: {url}")
        return page.title()


def _bandcamp_source(url: str) -> ReleaseInfo:
    info = scrape_release(url)
    info.platform = "bandcamp"
    return info


def _apple_source(url: str) -> ReleaseInfo:
    # og:title is "<Title> by <Artist> on Apple Music", e.g.
    # "It May Never Coming Back - Single by Logic Moon on Apple Music".
    # The title keeps its " - Single" suffix on purpose, matching is fuzzy.
    parsed = urlparse(url)
    og = _og_title(_fetch_soup(url))
    body = og.removesuffix(" on Apple Music") if og else ""
    title, sep, artist = body.rpartition(" by ")
    if not sep or not title or not artist:
        raise RuntimeError(f"could not parse Apple Music release info from {url}")
    is_track = "/song/" in parsed.path or "i" in parse_qs(parsed.query)
    return ReleaseInfo(
        artist=artist.strip(),
        title=title.strip(),
        release_type="track" if is_track else "album",
        url=url,
        platform="apple_music",
    )


_DEEZER_PATH = re.compile(r"^/(?:[a-z]{2}/)?(album|track)/(\d+)")


def _deezer_source(url: str) -> ReleaseInfo:
    # Title and artist both come from Deezer's public JSON API (no key). The
    # HTML page has no reliable artist field, so the page is not fetched.
    match = _DEEZER_PATH.match(urlparse(url).path)
    if not match:
        raise ValueError(f"not a Deezer album or track URL: {url}")
    kind, dz_id = match.groups()
    api = requests.get(
        f"https://api.deezer.com/{kind}/{dz_id}",
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_S,
    )
    api.raise_for_status()
    data = api.json()
    if "error" in data:
        raise RuntimeError(f"Deezer API error for {url}: {data['error']}")
    title = data.get("title")
    artist = (data.get("artist") or {}).get("name")
    if not title or not artist:
        raise RuntimeError(f"could not parse Deezer release info from {url}")
    return ReleaseInfo(
        artist=artist,
        title=title,
        release_type="album" if kind == "album" else "track",
        url=url,
        platform="deezer",
    )


def _soundcloud_source(url: str) -> ReleaseInfo:
    # Artist comes from the URL slug ("logic-moon" -> "Logic Moon"). Known
    # limit: collab accounts whose slug differs from the display name. Title
    # matching still works because title carries 70% of the score.
    parts = [p for p in urlparse(url).path.split("/") if p]
    if len(parts) < 2:
        raise RuntimeError(f"not a SoundCloud artist/release URL: {url}")
    title = _og_title(_fetch_soup(url))
    if not title:
        raise RuntimeError(f"could not parse SoundCloud release info from {url}")
    artist = " ".join(w.capitalize() for w in parts[0].replace("-", " ").split())
    return ReleaseInfo(
        artist=artist,
        title=title,
        release_type="album" if parts[1] == "sets" else "track",
        url=url,
        platform="soundcloud",
    )


_SPOTIFY_ALBUM_TITLE = re.compile(r"^Listen to (?P<title>.+) by (?P<artist>.+) \| Spotify$")
_SPOTIFY_TRACK_TITLE = re.compile(r"^(?P<title>.+) - song and lyrics by (?P<artist>.+) \| Spotify$")


def _spotify_source(url: str) -> ReleaseInfo:
    # Spotify serves no metadata without JavaScript (no og:title, no JSON-LD).
    # The document title is set after render and has two shapes:
    #   album: "Listen to <Title> by <Artists> | Spotify"
    #   track: "<Title> - song and lyrics by <Artists> | Spotify"
    path = urlparse(url).path
    if "/album/" in path:
        pattern, release_type = _SPOTIFY_ALBUM_TITLE, "album"
    elif "/track/" in path:
        pattern, release_type = _SPOTIFY_TRACK_TITLE, "track"
    else:
        raise ValueError(f"not a Spotify album or track URL: {url}")
    doc_title = _render_document_title(
        url,
        "document.title.includes('| Spotify') && !document.title.includes('Web Player')",
        "could not read Spotify release info",
    )
    match = pattern.match(doc_title)
    if not match:
        raise RuntimeError(f"unexpected Spotify page title {doc_title!r} for {url}")
    return ReleaseInfo(
        artist=match["artist"].strip(),
        title=match["title"].strip(),
        release_type=release_type,
        url=url,
        platform="spotify",
    )


_AMAZON_ALBUM_TITLE = re.compile(r"^Play (?P<title>.+) by (?P<artist>.+) on Amazon Music Unlimited$")


def _amazon_source(url: str) -> ReleaseInfo:
    # Document title: "Play <Title> by <Artists> on Amazon Music Unlimited".
    # Album URLs only. The German storefront uses other wording, not handled yet.
    if "/albums/" not in urlparse(url).path:
        raise ValueError(f"only Amazon Music album URLs are supported: {url}")
    doc_title = _render_document_title(
        url,
        "document.title.startsWith('Play ')",
        "could not read Amazon Music release info",
    )
    match = _AMAZON_ALBUM_TITLE.match(doc_title)
    if not match:
        raise RuntimeError(f"unexpected Amazon Music page title {doc_title!r} for {url}")
    return ReleaseInfo(
        artist=match["artist"].strip(),
        title=match["title"].strip(),
        release_type="album",
        url=url,
        platform="amazon_music",
    )


# smart link services -> our platform names (only those that are in core.PLATFORMS
# or are the resolver's own platforms; others are kept out of results)
SMART_LINK_SERVICES = {
    "spotify": "spotify",
    "apple": "apple_music",
    "deezer": "deezer",
    "amazon": "amazon_music",
    "soundcloud": "soundcloud",
    "beatport": "beatport",
}
# which destination to resolve the release metadata from, first hit wins
SMART_LINK_PREFERENCE = ["apple_music", "deezer", "spotify"]


def _decode_cd(token: str) -> dict:
    """Smart link anchors carry their destination as base64url JSON in ?cd=."""
    padded = token + "=" * (-len(token) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def _clean_destination(platform: str, dest: str) -> str:
    # drop tracking queries; Apple keeps ?i= (track id), it's needed for tracks
    parsed = urlparse(dest)
    keep_query = platform == "apple_music" and "i" in parse_qs(parsed.query)
    host = "music.apple.com" if parsed.hostname == "geo.music.apple.com" else parsed.netloc
    query = parsed.query if keep_query else ""
    return urlunparse((parsed.scheme, host, parsed.path, "", query, ""))


def _smartlink_destinations(url: str) -> dict[str, str]:
    with new_page() as page:
        page.goto(url, timeout=SEARCH_TIMEOUT_MS)
        try:
            # "attached", not visible: the link list sits behind a cookie banner overlay
            page.wait_for_selector('a[href*="/sl/e/c/"]', state="attached", timeout=SEARCH_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            raise RuntimeError(f"no platform links found on smart link page {url}")
        hrefs = page.eval_on_selector_all('a[href*="/sl/e/c/"]', "els => els.map(a => a.href)")
    destinations: dict[str, str] = {}
    for href in hrefs:
        token = parse_qs(urlparse(href).query).get("cd", [None])[0]
        if not token:
            continue
        data = _decode_cd(token)
        platform = SMART_LINK_SERVICES.get(data.get("srvc"))
        dest = data.get("destUrl")
        if platform and dest and platform not in destinations:
            destinations[platform] = _clean_destination(platform, dest)
    return destinations


def _smartlink_source(url: str) -> ReleaseInfo:
    """Smart link page: read the platform links it offers, resolve the release
    from the first destination that resolves (Apple, Deezer, Spotify), and
    return those links as direct results via ReleaseInfo.links."""
    destinations = _smartlink_destinations(url)
    last_error: Exception | None = None
    for platform in SMART_LINK_PREFERENCE:
        if platform not in destinations:
            continue
        try:
            info = resolve_source(destinations[platform])
        except (RuntimeError, ValueError, requests.HTTPError) as exc:
            last_error = exc
            continue
        return ReleaseInfo(
            artist=info.artist,
            title=info.title,
            release_type=info.release_type,
            url=url,
            platform="smart_link",
            links=destinations,
        )
    raise RuntimeError(f"could not resolve the release behind {url}: {last_error or 'no usable platform link'}")


_HOST_RESOLVERS = {
    "music.apple.com": _apple_source,
    "deezer.com": _deezer_source,
    "www.deezer.com": _deezer_source,
    "soundcloud.com": _soundcloud_source,
    "m.soundcloud.com": _soundcloud_source,
    "open.spotify.com": _spotify_source,
}


def _resolver_for(hostname: str):
    if hostname == "bandcamp.com" or hostname.endswith(".bandcamp.com"):
        return _bandcamp_source
    if hostname.startswith("music.amazon."):
        return _amazon_source
    if hostname in SMART_LINK_HOSTS or any(hostname.endswith("." + h) for h in SMART_LINK_HOSTS):
        return _smartlink_source
    return _HOST_RESOLVERS.get(hostname)


def resolve_source(url: str) -> ReleaseInfo:
    """Resolve a supported platform URL to its artist/title/release_type.
    Raises ValueError for unsupported hosts, RuntimeError when metadata can't
    be read, requests.HTTPError for failed HTTP responses."""
    hostname = urlparse(url).hostname or ""
    resolver = _resolver_for(hostname)
    if resolver is None:
        raise ValueError(
            f"unsupported source host '{hostname}' in {url}. "
            f"Supported: {', '.join(SUPPORTED_HOSTS)}"
        )
    return resolver(url)
