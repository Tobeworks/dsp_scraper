"""Core orchestration: scrape Bandcamp, search every active platform, match."""
import sys
import time
from dataclasses import asdict

from dsp_scraper.bandcamp import scrape_release
from dsp_scraper.matching import MatchResult, pick_best
from dsp_scraper.platforms import (
    amazon_music,
    apple_music,
    beatport,
    deezer,
    soundcloud,
    spotify,
)

# ponytail: youtube_music, tidal, napster, pandora are written and importable
# (src/dsp_scraper/platforms/youtube_music.py etc.) but left out of the
# active run - each hits a structural blocker outside our control (EU
# cookie-consent wall, no public search DOM, product pivot away from
# music, US-only geo-block - see README "known limitations"), not a
# scraper bug we can fix by tuning a selector. Re-add to PLATFORMS below
# if a workaround is found.
PLATFORMS = {
    "spotify": spotify,
    "apple_music": apple_music,
    "deezer": deezer,
    "amazon_music": amazon_music,
    "soundcloud": soundcloud,
    "beatport": beatport,
}

DEFAULT_PLATFORM_DELAY_SECONDS = 1.5  # ponytail: fixed default, overridable via --delay


def find_release(bandcamp_url: str, platform_delay: float = DEFAULT_PLATFORM_DELAY_SECONDS) -> dict:
    """Scrape Bandcamp + all active DSPs, return the finished result dict
    (same shape as the JSON output). Does not write anything itself, but
    prints progress. Sleeps `platform_delay` seconds between platform
    searches (none before the first) so the active platforms aren't hit
    back-to-back like a bot."""
    # ponytail: progress goes to stderr, not stdout - CLI --stdout must
    # produce nothing but the JSON on stdout so it stays pipeable (e.g.
    # into a DB writer), even though this same function is also used for
    # the file-output path where it wouldn't otherwise matter.
    print(f"Scraping Bandcamp: {bandcamp_url}", file=sys.stderr)
    release = scrape_release(bandcamp_url)  # fatal if this fails - nothing to search for
    print(f"  -> {release.artist} - {release.title} ({release.release_type})", file=sys.stderr)

    results = {}
    for i, (name, module) in enumerate(PLATFORMS.items()):
        if i > 0:
            time.sleep(platform_delay)
        print(f"Searching {name} ...", file=sys.stderr)
        try:
            candidates = module.search(release.artist, release.title)
            match = pick_best(candidates, release.artist, release.title)
        except Exception as exc:
            # ponytail: one broad catch per platform - isolation matters more
            # than precise exception typing here, a single bad site must not
            # kill the run
            match = MatchResult(error=f"{type(exc).__name__}: {exc}")
        results[name] = asdict(match)
        print(f"  -> {'matched' if match.url else f'no match ({match.error})'}", file=sys.stderr)

    return {"source": {"platform": "bandcamp", **asdict(release)}, "results": results}
