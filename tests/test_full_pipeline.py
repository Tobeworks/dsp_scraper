"""Full-pipeline smoke test: run main.run() (Bandcamp + every active
platform in main.PLATFORMS) against every sample URL, not just one release.

Hits the network heavily (active platforms x 15 releases) - not a unit
test, not run in CI, takes several minutes. Run manually:
    uv run tests/test_full_pipeline.py

Writes full per-release results to tests/test_full_pipeline_results.json
and prints a per-platform match-rate summary.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `import main` etc. find the project root

from main import run
from test_bandcamp import SAMPLE_URLS

RESULTS_FILE = Path(__file__).parent / "test_full_pipeline_results.json"


def main():
    all_results = []
    match_counts = {}
    total = len(SAMPLE_URLS)

    for i, url in enumerate(SAMPLE_URLS, 1):
        print(f"\n[{i}/{total}] {url}")
        try:
            result = run(url)
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
