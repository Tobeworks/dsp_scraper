"""Run one platform's search() against all sample Bandcamp releases.

Faster than test_full_pipeline.py when only one platform needs re-checking
(e.g. after tuning its selectors). Hits the network, not run in CI:
    uv run tests/test_platform.py apple_music
    uv run tests/test_platform.py            # defaults to apple_music
"""
import importlib
import sys

from dsp_scraper.bandcamp import scrape_release
from dsp_scraper.matching import pick_best
from test_bandcamp import SAMPLE_URLS


def main():
    platform_name = sys.argv[1] if len(sys.argv) > 1 else "apple_music"
    platform = importlib.import_module(f"dsp_scraper.platforms.{platform_name}")

    matched = 0
    for url in SAMPLE_URLS:
        release = scrape_release(url)
        candidates = platform.search(release.artist, release.title)
        match = pick_best(candidates, release.artist, release.title)
        status = f"MATCH  {match.url}" if match.url else f"MISS   {match.error}"
        print(f"{release.artist} - {release.title}\n  {status}\n  {url}")
        if match.url:
            matched += 1

    print(f"\n{matched}/{len(SAMPLE_URLS)} matched on {platform_name}")


if __name__ == "__main__":
    main()
