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

    def test_deezer_track_url_rejected_in_phase_1(self):
        with self.assertRaises(ValueError):
            resolve_source("https://www.deezer.com/de/track/123")

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
            resolve_source("https://open.spotify.com/album/5cRFOsGT9aFprlVqCbRstu")
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
