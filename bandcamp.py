"""Scrape a Bandcamp release page for artist/title/release_type."""
import json
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


@dataclass
class ReleaseInfo:
    artist: str
    title: str
    release_type: str  # "album" | "track"
    url: str


def _release_type(url: str) -> str:
    return "album" if "/album/" in urlparse(url).path else "track"


def _from_json_ld(soup: BeautifulSoup) -> tuple[str, str] | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if data.get("@type") not in ("MusicAlbum", "MusicRecording"):
            continue
        title = data.get("name")
        by_artist = data.get("byArtist")
        if isinstance(by_artist, list):
            by_artist = by_artist[0] if by_artist else None
        artist = by_artist.get("name") if isinstance(by_artist, dict) else None
        if title and artist:
            return artist, title
    return None


def _from_og_title(soup: BeautifulSoup) -> tuple[str, str] | None:
    tag = soup.find("meta", property="og:title")
    if not tag or not tag.get("content"):
        return None
    content = tag["content"]
    if ", by " not in content:
        return None
    title, artist = content.split(", by ", 1)
    return artist.strip(), title.strip()


def _from_page_markup(soup: BeautifulSoup) -> tuple[str, str] | None:
    # ponytail: last-resort selectors - Bandcamp's markup has been stable for
    # years but isn't a contract, this is only reached if both structured
    # sources above are missing/malformed.
    title_tag = soup.select_one("h2.trackTitle")
    artist_tag = soup.select_one('#name-section span[itemprop="byArtist"] a')
    if not title_tag or not artist_tag:
        return None
    return artist_tag.get_text(strip=True), title_tag.get_text(strip=True)


def scrape_release(url: str) -> ReleaseInfo:
    """Fetch a Bandcamp release page and extract artist/title/release_type.
    Tries schema.org JSON-LD first, falls back to og:title, then to raw
    page markup. Raises RuntimeError if none of them yield both fields."""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    found = _from_json_ld(soup) or _from_og_title(soup) or _from_page_markup(soup)
    if not found:
        raise RuntimeError(f"could not parse release info from {url}")

    artist, title = found
    return ReleaseInfo(artist=artist, title=title, release_type=_release_type(url), url=url)


if __name__ == "__main__":
    import sys

    print(scrape_release(sys.argv[1]))
