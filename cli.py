"""CLI: find a Bandcamp release on active DSPs and write/print the result as JSON."""
import argparse
import json
import sys

from dsp_scraper.core import DEFAULT_PLATFORM_DELAY_SECONDS, find_release


def parse_args():
    p = argparse.ArgumentParser(description="Find a Bandcamp release on other DSPs")
    p.add_argument("bandcamp_url", nargs="?", help="Bandcamp release URL")
    p.add_argument("-o", "--output", default="results.json", help="output JSON file path")
    p.add_argument("--stdout", action="store_true", help="print JSON to stdout instead of writing a file")
    p.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_PLATFORM_DELAY_SECONDS,
        help="seconds to wait between platform searches",
    )
    return p.parse_args()


def main():
    args = parse_args()
    url = args.bandcamp_url or input("Bandcamp release URL: ").strip()
    if not url:
        sys.exit("no URL given")

    result = find_release(url, platform_delay=args.delay)

    if args.stdout:
        print(json.dumps(result, indent=2))
    else:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
