"""CLI: find a release from a platform URL on the active DSPs and write/print the result as JSON."""
import argparse
import json
import sys

from dsp_scraper.core import DEFAULT_PLATFORM_DELAY_SECONDS, find_release


def parse_args():
    p = argparse.ArgumentParser(description="Find a release on other DSPs, starting from one platform URL")
    p.add_argument(
        "source_url",
        nargs="?",
        help="release URL on a supported platform: Bandcamp, Apple Music, Deezer (album), SoundCloud",
    )
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
    url = args.source_url or input("Release URL: ").strip()
    if not url:
        sys.exit("no URL given")

    try:
        result = find_release(url, platform_delay=args.delay)
    except (ValueError, RuntimeError) as exc:
        # unsupported host / unreadable metadata: the message already says what to do
        sys.exit(f"error: {exc}")

    if args.stdout:
        print(json.dumps(result, indent=2))
    else:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
