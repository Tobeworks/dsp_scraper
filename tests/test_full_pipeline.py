"""Full-pipeline smoke test: run dsp_scraper.find_release() (Bandcamp +
every active platform in dsp_scraper.core.PLATFORMS) against every sample
URL, not just one release.

Hits the network heavily (active platforms x 15 releases) - not a unit
test, not run in CI, takes several minutes. Run manually:
    uv run tests/test_full_pipeline.py

Writes full per-release results to tests/test_full_pipeline_results.json
and prints a per-platform match-rate summary.
"""
import json
from pathlib import Path

from dsp_scraper import find_release
from test_bandcamp import SAMPLE_URLS

RESULTS_FILE = Path(__file__).parent / "test_full_pipeline_results.json"


def main():
    all_results = []
    match_counts = {}
    total = len(SAMPLE_URLS)

    for i, url in enumerate(SAMPLE_URLS, 1):
        print(f"\n[{i}/{total}] {url}")
        try:
            result = find_release(url)
        except Exception as exc:
            print(f"  FATAL (bandcamp scrape failed): {type(exc).__name__}: {exc}")
            all_results.append({"source_url": url, "error": str(exc)})
            continue

        all_results.append(result)
        for platform, res in result["results"].items():
            match_counts.setdefault(platform, [0, 0])
            match_counts[platform][1] += 1
            if res["url"]:
                match_counts[platform][0] += 1

    with open(RESULTS_FILE, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n\n=== Match rate per platform ({total} releases) ===")
    for platform, (matched, seen) in match_counts.items():
        print(f"  {platform:15s} {matched}/{seen}")
    print(f"\nWrote {RESULTS_FILE}")


if __name__ == "__main__":
    main()
