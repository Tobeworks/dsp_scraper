"""Resolve a platform release URL to artist/title/release_type.

Phase 1 (spec: docs/specs/source-agnostic-lookup.md): Bandcamp, Apple Music,
Deezer (album), SoundCloud. All plain HTTP, no browser. Spotify, Beatport,
Amazon and smart links come in phase 2.
"""
import re
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from dsp_scraper.bandcamp import USER_AGENT, scrape_release
from dsp_scraper.types import ReleaseInfo

REQUEST_TIMEOUT_S = 10
SUPPORTED_HOSTS = ["bandcamp.com", "music.apple.com", "deezer.com", "soundcloud.com"]


def _fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _og_title(soup: BeautifulSoup) -> str | None:
    tag = soup.find("meta", property="og:title")
    if not tag or not tag.get("content"):
        return None
    return tag["content"].strip()


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


_DEEZER_ALBUM = re.compile(r"^/(?:[a-z]{2}/)?album/(\d+)")


def _deezer_source(url: str) -> ReleaseInfo:
    # Title from the page, artist from Deezer's public JSON API (no key).
    # The page itself carries no artist in og:title, so the API is needed.
    # Album URLs only in phase 1, track URLs raise.
    match = _DEEZER_ALBUM.match(urlparse(url).path)
    if not match:
        raise ValueError(f"only Deezer album URLs are supported in phase 1: {url}")
    title = _og_title(_fetch_soup(url))
    api = requests.get(
        f"https://api.deezer.com/album/{match.group(1)}",
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_S,
    )
    api.raise_for_status()
    data = api.json()
    if "error" in data:
        raise RuntimeError(f"Deezer API error for {url}: {data['error']}")
    artist = (data.get("artist") or {}).get("name")
    if not title or not artist:
        raise RuntimeError(f"could not parse Deezer release info from {url}")
    return ReleaseInfo(artist=artist, title=title, release_type="album", url=url, platform="deezer")


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


_HOST_RESOLVERS = {
    "music.apple.com": _apple_source,
    "deezer.com": _deezer_source,
    "www.deezer.com": _deezer_source,
    "soundcloud.com": _soundcloud_source,
    "m.soundcloud.com": _soundcloud_source,
}


def _resolver_for(hostname: str):
    if hostname == "bandcamp.com" or hostname.endswith(".bandcamp.com"):
        return _bandcamp_source
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
