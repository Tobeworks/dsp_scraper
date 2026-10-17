"""Core orchestration: resolve the source URL, search every active platform, match."""
import sys
import time
from dataclasses import asdict

from dsp_scraper.matching import MatchResult, pick_best
from dsp_scraper.platforms import (
    amazon_music,
    apple_music,
    beatport,
    deezer,
    soundcloud,
    spotify,
)
from dsp_scraper.sources import resolve_source

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


def find_release(source_url: str, platform_delay: float = DEFAULT_PLATFORM_DELAY_SECONDS) -> dict:
    """Resolve the source URL (any supported platform, see sources.py), search
    every active DSP except the source's own platform, return the finished
    result dict (same shape as the JSON output). The source platform's entry
    is the source URL itself at confidence 100, it is not searched. Does not
    write anything itself, but prints progress. Sleeps `platform_delay`
    seconds between actual platform searches (none before the first) so the
    active platforms aren't hit back-to-back like a bot."""
    # ponytail: progress goes to stderr, not stdout - CLI --stdout must
    # produce nothing but the JSON on stdout so it stays pipeable (e.g.
    # into a DB writer), even though this same function is also used for
    # the file-output path where it wouldn't otherwise matter.
    print(f"Resolving source: {source_url}", file=sys.stderr)
    release = resolve_source(source_url)  # fatal if this fails - nothing to search for
    print(f"  -> {release.artist} - {release.title} ({release.release_type}, {release.platform})", file=sys.stderr)

    results = {}
    searched_before = False
    for name, module in PLATFORMS.items():
        # a link the source itself gives us (source platform, or a smart link's
        # destination) is taken as-is, no search needed
        direct_url = release.url if name == release.platform else release.links.get(name)
        if direct_url:
            results[name] = asdict(
                MatchResult(
                    url=direct_url,
                    matched_title=release.title,
                    matched_artist=release.artist,
                    confidence=100.0,
                )
            )
            print(f"{name}: taken from source ({'source URL' if name == release.platform else 'smart link'})", file=sys.stderr)
            continue
        if searched_before:
            time.sleep(platform_delay)
        searched_before = True
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

    return {"source": asdict(release), "results": results}
