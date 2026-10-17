"""Offline unit tests for sources.resolve_source() and core.find_release()'s
source-platform handling (spec: docs/specs/source-agnostic-lookup.md, sec. 8).

No network: requests.get is mocked with saved page heads (tests/fixtures/).
Run manually:
    uv run tests/test_sources.py
"""
import json
import unittest
from pathlib import Path
from unittest import mock

import requests

from dsp_scraper import core
from dsp_scraper.sources import resolve_source
from dsp_scraper.types import ReleaseInfo

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, text: str = "", status: int = 200, payload=None):
        self.text = text
        self.status_code = status
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        return self._payload


def _fake_get(page_html: str, api_payload=None):
    """Routes page URLs to page_html and api.deezer.com URLs to api_payload."""

    def get(url, **kwargs):
        if "api.deezer.com" in url:
            return FakeResponse(payload=api_payload)
        return FakeResponse(text=page_html)

    return get


class ResolveSourceTests(unittest.TestCase):
    def test_apple_album(self):
        url = "https://music.apple.com/us/album/it-may-never-coming-back-single/6804971310"
        with mock.patch("requests.get", _fake_get(_fixture("apple_album_head.html"))):
            info = resolve_source(url)
        self.assertEqual(info.platform, "apple_music")
        self.assertEqual(info.artist, "Logic Moon")
        self.assertEqual(info.title, "It May Never Coming Back - Single")
        self.assertEqual(info.release_type, "album")
        self.assertEqual(info.url, url)

    def test_apple_track_via_query_param(self):
        url = "https://music.apple.com/us/album/it-may-never-coming-back-single/6804971310?i=1234567"
        with mock.patch("requests.get", _fake_get(_fixture("apple_album_head.html"))):
            info = resolve_source(url)
        self.assertEqual(info.release_type, "track")

    def test_deezer_album_with_language_prefix(self):
        url = "https://www.deezer.com/de/album/854570502"
        payload = json.loads(_fixture("deezer_album_api.json"))
        with mock.patch("requests.get", _fake_get(_fixture("deezer_album_head.html"), payload)):
            info = resolve_source(url)
        self.assertEqual(info.platform, "deezer")
        self.assertEqual(info.artist, "Logic Moon")
        self.assertEqual(info.title, "Memories Of Tomorrow")
        self.assertEqual(info.release_type, "album")

    def test_deezer_api_error_payload_raises(self):
        url = "https://www.deezer.com/de/album/854570502"
        payload = {"error": {"type": "QuotaException", "message": "rate limit"}}
        with mock.patch("requests.get", _fake_get(_fixture("deezer_album_head.html"), payload)):
            with self.assertRaises(RuntimeError):
                resolve_source(url)

    def test_deezer_track(self):
        url = "https://www.deezer.com/track/123"
        payload = {"title": "Ewiger Wald", "artist": {"name": "Logic Moon"}}
        with mock.patch("requests.get", _fake_get("", payload)):
            info = resolve_source(url)
        self.assertEqual(info.release_type, "track")
        self.assertEqual(info.title, "Ewiger Wald")
        self.assertEqual(info.artist, "Logic Moon")

    def test_deezer_non_release_url_rejected(self):
        with self.assertRaises(ValueError):
            resolve_source("https://www.deezer.com/de/artist/123")

    def test_soundcloud_set_artist_from_slug(self):
        url = "https://soundcloud.com/logic-moon/sets/it-may-never-coming-back"
        with mock.patch("requests.get", _fake_get(_fixture("soundcloud_set_head.html"))):
            info = resolve_source(url)
        self.assertEqual(info.platform, "soundcloud")
        self.assertEqual(info.artist, "Logic Moon")
        self.assertEqual(info.title, "It May Never Coming Back")
        self.assertEqual(info.release_type, "album")

    def test_bandcamp_album(self):
        url = "https://logicmoon.bandcamp.com/album/the-north"
        with mock.patch("requests.get", _fake_get(_fixture("bandcamp_album_head.html"))):
            info = resolve_source(url)
        self.assertEqual(info.platform, "bandcamp")
        self.assertEqual(info.artist, "Logic Moon")
        self.assertEqual(info.title, "The North")
        self.assertEqual(info.release_type, "album")

    def test_unsupported_host_lists_supported_hosts(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_source("https://www.beatport.com/release/the-north/5594159")
        self.assertIn("Supported:", str(ctx.exception))
        self.assertIn("music.apple.com", str(ctx.exception))

    def test_http_error_surfaces(self):
        with mock.patch("requests.get", lambda url, **kw: FakeResponse(status=404)):
            with self.assertRaises(requests.HTTPError):
                resolve_source("https://music.apple.com/us/album/x/1")

    def test_missing_metadata_raises_runtime_error(self):
        with mock.patch("requests.get", _fake_get("<html><head></head><body></body></html>")):
            with self.assertRaises(RuntimeError):
                resolve_source("https://music.apple.com/us/album/x/1")

    def test_soundcloud_url_without_release_segment_raises(self):
        with mock.patch("requests.get", _fake_get(_fixture("soundcloud_set_head.html"))):
            with self.assertRaises(RuntimeError):
                resolve_source("https://soundcloud.com/logic-moon")


class AppleCardArtistTests(unittest.TestCase):
    """Apple Music search cards come in three layouts (see apple_music.py)."""

    def test_artist_from_each_card_layout(self):
        from dsp_scraper.platforms.apple_music import _artist_from_container

        self.assertEqual(
            _artist_from_container("Memories Of Tomorrow - EP\nAlbum · Logic Moon"), "Logic Moon"
        )  # top results
        self.assertEqual(
            _artist_from_container("Echoes of Tomorrow\nEchoes of Tomorrow\n\nLegaG6"), "LegaG6"
        )  # grid
        self.assertEqual(
            _artist_from_container("Reminiscence - Single          Reminiscence - Single          Logic Moon"),
            "Logic Moon",
        )  # one line


class FakePage:
    def __init__(self, title: str):
        self._title = title

    def goto(self, url, timeout=None):
        pass

    def wait_for_function(self, expression, timeout=None):
        pass

    def title(self):
        return self._title


def _with_fake_page(doc_title: str):
    """Patch the browser so sources.py sees a page with this document title."""
    from contextlib import contextmanager

    @contextmanager
    def fake_new_page():
        yield FakePage(doc_title)

    return mock.patch("dsp_scraper.sources.new_page", fake_new_page)


class SpotifyResolverTests(unittest.TestCase):
    """Browser is faked: only the title parsing is under test here."""

    ALBUM = "https://open.spotify.com/intl-de/album/5eWWBbvppe4J2ZgKd2yLDV?si=ck4ei6EsSaG1PUETB77f0w"
    TRACK = "https://open.spotify.com/track/7kTKqDWQ3z5XR8HIahtGBa"

    def test_album_title_and_artists_from_document_title(self):
        with _with_fake_page("Listen to Miracles - EP by Logic Moon, Diogene | Spotify"):
            info = resolve_source(self.ALBUM)
        self.assertEqual(info.platform, "spotify")
        self.assertEqual(info.title, "Miracles - EP")
        self.assertEqual(info.artist, "Logic Moon, Diogene")
        self.assertEqual(info.release_type, "album")

    def test_track_title_and_artists_from_document_title(self):
        with _with_fake_page("The Golden Dawn - song and lyrics by Logic Moon | Spotify"):
            info = resolve_source(self.TRACK)
        self.assertEqual(info.title, "The Golden Dawn")
        self.assertEqual(info.artist, "Logic Moon")
        self.assertEqual(info.release_type, "track")

    def test_unexpected_title_raises(self):
        with _with_fake_page("Spotify – Web Player"):
            with self.assertRaises(RuntimeError):
                resolve_source(self.ALBUM)


class AmazonResolverTests(unittest.TestCase):
    def test_album_title_and_artists_from_document_title(self):
        with _with_fake_page("Play Miracles by Logic Moon & Diogene on Amazon Music Unlimited"):
            info = resolve_source("https://music.amazon.com/albums/B0GY5W4M3J")
        self.assertEqual(info.platform, "amazon_music")
        self.assertEqual(info.title, "Miracles")
        self.assertEqual(info.artist, "Logic Moon & Diogene")

    def test_other_wording_raises_instead_of_guessing(self):
        with _with_fake_page("Miracles von Logic Moon auf Amazon Music"):
            with self.assertRaises(RuntimeError):
                resolve_source("https://music.amazon.de/albums/B0GY5W4M3J")


class SmartLinkTests(unittest.TestCase):
    URL = "https://too.fm/2mozry1"

    @staticmethod
    def _cd(payload: dict) -> str:
        import base64

        raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        return raw

    def _href(self, payload: dict) -> str:
        return f"https://api.ffm.to/sl/e/c/2mozry1?cd={self._cd(payload)}"

    def test_destinations_parsed_from_rendered_links(self):
        from contextlib import contextmanager

        hrefs = [
            self._href({"srvc": "spotify", "destUrl": "https://open.spotify.com/album/5eWW?1100ljU3P"}),
            self._href({"srvc": "apple", "destUrl": "https://geo.music.apple.com/de/album/miracles-ep/1895325249?app=music&ct=x"}),
            self._href({"srvc": "deezer", "destUrl": "https://www.deezer.com/album/97000438"}),
            self._href({"srvc": "tidal", "destUrl": "http://www.tidal.com/album/51835788"}),
        ]

        class LinkPage:
            def goto(self, url, timeout=None):
                pass

            def wait_for_selector(self, selector, timeout=None):
                pass

            def eval_on_selector_all(self, selector, script):
                return hrefs

        @contextmanager
        def fake_new_page():
            yield LinkPage()

        with mock.patch("dsp_scraper.sources.new_page", fake_new_page):
            from dsp_scraper.sources import _smartlink_destinations

            dests = _smartlink_destinations(self.URL)
        self.assertEqual(dests["spotify"], "https://open.spotify.com/album/5eWW")
        self.assertEqual(dests["apple_music"], "https://music.apple.com/de/album/miracles-ep/1895325249")
        self.assertEqual(dests["deezer"], "https://www.deezer.com/album/97000438")
        self.assertNotIn("tidal", dests)  # not one of our platforms

    def test_release_resolved_from_first_working_destination(self):
        dests = {
            "apple_music": "https://music.apple.com/de/album/miracles-ep/1895325249",
            "deezer": "https://www.deezer.com/album/97000438",
        }
        resolved = ReleaseInfo(artist="Logic Moon, Diogene", title="Miracles - EP", release_type="album",
                               url=dests["deezer"], platform="deezer")

        def fake_resolve(url):
            if "apple" in url:
                raise RuntimeError("apple metadata broken")
            return resolved

        with mock.patch("dsp_scraper.sources._smartlink_destinations", return_value=dests), \
                mock.patch("dsp_scraper.sources.resolve_source", side_effect=fake_resolve):
            from dsp_scraper.sources import _smartlink_source

            info = _smartlink_source(self.URL)
        self.assertEqual(info.platform, "smart_link")
        self.assertEqual(info.url, self.URL)
        self.assertEqual(info.title, "Miracles - EP")
        self.assertEqual(info.links, dests)

    def test_cd_token_roundtrip_handles_missing_padding(self):
        from dsp_scraper.sources import _decode_cd

        self.assertEqual(_decode_cd(self._cd({"srvc": "deezer", "destUrl": "x"})), {"srvc": "deezer", "destUrl": "x"})


class FindReleaseSmartLinkTests(unittest.TestCase):
    def test_smart_link_destinations_are_taken_not_searched(self):
        info = ReleaseInfo(
            artist="Logic Moon, Diogene", title="Miracles - EP", release_type="album",
            url="https://too.fm/2mozry1", platform="smart_link",
            links={"deezer": "https://www.deezer.com/album/97000438", "spotify": "https://open.spotify.com/album/5eWW"},
        )
        fakes = {name: FakePlatform() for name in core.PLATFORMS}
        with mock.patch("dsp_scraper.core.PLATFORMS", fakes), \
                mock.patch("dsp_scraper.core.resolve_source", return_value=info):
            result = core.find_release(info.url, platform_delay=0)
        self.assertEqual(fakes["deezer"].calls, [])
        self.assertEqual(fakes["spotify"].calls, [])
        self.assertEqual(len(fakes["apple_music"].calls), 1)
        self.assertEqual(result["results"]["deezer"]["url"], "https://www.deezer.com/album/97000438")
        self.assertEqual(result["results"]["deezer"]["confidence"], 100.0)
        self.assertEqual(result["source"]["platform"], "smart_link")


class FakePlatform:
    """Stands in for a platforms.* module: records search calls, finds nothing."""

    def __init__(self):
        self.calls = []

    def search(self, artist, title):
        self.calls.append((artist, title))
        return []


class FindReleaseSourceHandlingTests(unittest.TestCase):
    def _run(self, info: ReleaseInfo):
        fakes = {name: FakePlatform() for name in core.PLATFORMS}
        with mock.patch("dsp_scraper.core.PLATFORMS", fakes), \
                mock.patch("dsp_scraper.core.resolve_source", return_value=info):
            result = core.find_release(info.url, platform_delay=0)
        return result, fakes

    def test_source_platform_is_not_searched_and_taken_from_url(self):
        info = ReleaseInfo(
            artist="Logic Moon", title="It May Never Coming Back - Single",
            release_type="album", url="https://music.apple.com/us/album/x/1", platform="apple_music",
        )
        result, fakes = self._run(info)
        self.assertEqual(fakes["apple_music"].calls, [])
        self.assertEqual(result["results"]["apple_music"]["url"], info.url)
        self.assertEqual(result["results"]["apple_music"]["confidence"], 100.0)
        self.assertEqual(result["results"]["apple_music"]["matched_artist"], "Logic Moon")
        for name in core.PLATFORMS:
            if name != "apple_music":
                self.assertEqual(len(fakes[name].calls), 1, name)

    def test_bandcamp_source_searches_all_platforms(self):
        info = ReleaseInfo(
            artist="Logic Moon", title="The North", release_type="album",
            url="https://logicmoon.bandcamp.com/album/the-north", platform="bandcamp",
        )
        result, fakes = self._run(info)
        for name in core.PLATFORMS:
            self.assertEqual(len(fakes[name].calls), 1, name)
        self.assertEqual(result["source"]["platform"], "bandcamp")
        self.assertEqual(set(result["results"]), set(core.PLATFORMS))

    def test_output_keeps_five_fields_per_platform(self):
        info = ReleaseInfo(
            artist="Logic Moon", title="The North", release_type="album",
            url="https://logicmoon.bandcamp.com/album/the-north", platform="bandcamp",
        )
        result, _ = self._run(info)
        for name, entry in result["results"].items():
            self.assertEqual(
                set(entry), {"url", "matched_title", "matched_artist", "confidence", "error"}, name
            )


if __name__ == "__main__":
    unittest.main()
