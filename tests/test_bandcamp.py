"""Smoke-test bandcamp.scrape_release() against real releases.

Hits the network (not a unit test, not run in CI) - run manually:
    uv run tests/test_bandcamp.py

Writes the scraped results to tests/test_bandcamp_results.json for
inspection. URLs pulled from logic-moon.de's own release catalog
(logicmoon_astro/src/releases.js).
"""
import json
from dataclasses import asdict
from pathlib import Path

from dsp_scraper.bandcamp import scrape_release

RESULTS_FILE = Path(__file__).parent / "test_bandcamp_results.json"

SAMPLE_URLS = [
    "https://ambientcat.bandcamp.com/album/musica-universalis",
    "https://chitrarecords.bandcamp.com/album/ashes",
    "https://dronarivm.bandcamp.com/album/ewiger-wald",
    "https://logicmoon.bandcamp.com/album/atlas",
    "https://logicmoon.bandcamp.com/album/clockworks",
    "https://logicmoon.bandcamp.com/album/glow",
    "https://logicmoon.bandcamp.com/album/heim",
    "https://logicmoon.bandcamp.com/album/hello",
    "https://logicmoon.bandcamp.com/album/it-may-never-coming-back",
    "https://logicmoon.bandcamp.com/album/last-days",
    "https://logicmoon.bandcamp.com/album/lifelines",
    "https://logicmoon.bandcamp.com/album/memories-of-tomorrow",
    "https://logicmoon.bandcamp.com/album/metamorphosis",
    "https://logicmoon.bandcamp.com/album/reminiscence",
    "https://logicmoon.bandcamp.com/album/stellar-refuge",
]


def main():
    failures = []
    entries = []
    for url in SAMPLE_URLS:
        try:
            release = scrape_release(url)
            assert release.artist and release.title, "empty artist/title"
            status = f"OK   {release.artist} - {release.title} ({release.release_type})"
            entries.append({"url": url, "ok": True, "error": None, **asdict(release)})
        except Exception as exc:
            failures.append(url)
            status = f"FAIL {type(exc).__name__}: {exc}"
            entries.append({"url": url, "ok": False, "error": str(exc)})
        print(f"{status}\n     {url}")

    passed = len(SAMPLE_URLS) - len(failures)
    print(f"\n{passed}/{len(SAMPLE_URLS)} passed")

    with open(RESULTS_FILE, "w") as f:
        json.dump(entries, f, indent=2)
    print(f"Wrote {RESULTS_FILE}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
