# dsp_scraper

Takes a release URL from one streaming platform, finds the same release
(artist + album/track) on the other platforms by scraping them, and writes
it all out as JSON — either to a file or to stdout (for piping into another
tool, e.g. a DB writer).

Version 2.0: the starting point is no longer Bandcamp only. Supported source
URLs are listed under [Supported source URLs](#supported-source-urls). The
source platform itself is not searched, its entry is the source URL at
confidence 100. This replaces Odesli (song.link) for our use case: no API key,
no external service.

Deliberately kept minimal: no plugin registry, no abstract base classes, no
real database. Design and open phases are in
[docs/specs/source-agnostic-lookup.md](docs/specs/source-agnostic-lookup.md).

## Supported source URLs

The URL you pass in decides the source platform. Each source is resolved to
artist, title and release type, then searched on every other active
platform.

| Source | Example | Resolved via | Status |
|---|---|---|---|
| Bandcamp | `https://logicmoon.bandcamp.com/album/atlas` | JSON-LD / `og:title` | ✅ phase 1 |
| Apple Music | `https://music.apple.com/us/album/<slug>/<id>` | `og:title` | ✅ phase 1 |
| Deezer | `https://www.deezer.com/de/album/<id>` | `og:title` + `api.deezer.com` (no key) | ✅ phase 1, album URLs only |
| SoundCloud | `https://soundcloud.com/<artist>/sets/<slug>` | `og:title` + URL slug | ✅ phase 1 (artist from slug, collab accounts may differ) |
| Spotify | `https://open.spotify.com/album/<id>` | needs a browser | ⏳ phase 2 |
| Beatport | `https://www.beatport.com/release/<slug>/<id>` | needs a browser (Cloudflare) | ⏳ phase 2 |
| Smart links (too.fm etc.) | `https://too.fm/<id>` | needs a browser | ⏳ phase 2 |
| Amazon Music | `https://music.amazon.com/albums/<id>` | not yet checked | ⏳ phase 2 |

Any other host fails with an error that lists the supported hosts. Deezer
track URLs and Spotify URLs are rejected for now, the error says so.

## Supported platforms

6 platforms are active by default (`core.PLATFORMS`). Match rates below are
from the last full run against 15 real releases from logic-moon.de's own
catalog (`uv run tests/test_full_pipeline.py`) - they reflect how much of an
artist's real catalog actually turns up per platform, not scraper
correctness alone (a release genuinely not on a platform is a correct miss).

| Platform | Match rate | Status |
|---|---|---|
| Spotify | 13/15 | ✅ works reliably |
| Apple Music | 12/15 | ✅ works reliably |
| Amazon Music | 12/15 | ✅ works reliably |
| SoundCloud | 11/15 | ✅ works reliably |
| Deezer | 4/15 | ✅ works, but recall is low - result rows are clientside-routed `<div>`s with no `href`, we only reliably reach the "top result" + album-grid cards (see Known limitations) |
| Beatport | 4/15 | ✅ works, low match rate mostly reflects Beatport's dance/DJ-focused catalog, not every release is there |

4 more platforms are written but **disabled** - excluded from
`core.PLATFORMS`, kept in `platforms/` for when a workaround is found (each
file is marked `DISABLED as of <date>` at the top):

| Platform | Blocker |
|---|---|
| YouTube Music | EU cookie-consent wall blocks anonymous search |
| Tidal | anonymous search renders no usable result DOM |
| Napster | product appears to have pivoted away from music search |
| Pandora | US/AU/NZ only, redirects other regions to `/restricted` |

A platform failing doesn't abort the run - it shows up in the JSON with
`"url": null` and an `error` explaining why, while every other platform
still runs independently.

## Setup

Requires [uv](https://docs.astral.sh/uv/) as the package/environment manager.

```bash
uv sync                              # installs dependencies into .venv
uv run playwright install chromium   # downloads the Chromium browser for Playwright (once)
```

`uv run <script>` automatically uses the project-local `.venv` - no manual
activation needed.

Since `pyproject.toml` declares a proper build backend, dsp_scraper is
also installable as a dependency of another project directly from GitHub:
`pip install git+https://github.com/Tobeworks/dsp_scraper.git`, then
`from dsp_scraper import find_release`. The installing project still
needs its own Playwright browser install step
(`playwright install --with-deps chromium`) - installing dsp_scraper
doesn't run that automatically.

## Usage

```bash
# write to a file (default: results.json)
uv run cli.py https://logicmoon.bandcamp.com/album/atlas

# custom output path
uv run cli.py https://logicmoon.bandcamp.com/album/atlas -o out.json

# print JSON to stdout instead of writing a file (e.g. to pipe into a DB tool)
uv run cli.py --stdout https://logicmoon.bandcamp.com/album/atlas > release.json

# no URL argument -> interactive prompt
uv run cli.py

# adjust the pause between platform searches (default: 1.5s)
uv run cli.py --delay 3 https://logicmoon.bandcamp.com/album/atlas

# any supported source URL works, e.g. Apple Music
uv run cli.py --stdout https://music.apple.com/us/album/it-may-never-coming-back-single/6804971310
```

Progress/status messages go to stderr, so `--stdout` always produces clean,
directly parseable JSON on stdout.

### Output schema

```json
{
  "source": {
    "artist": "Logic Moon",
    "title": "Atlas",
    "release_type": "album",
    "url": "https://logicmoon.bandcamp.com/album/atlas",
    "platform": "bandcamp"
  },
  "results": {
    "spotify": {
      "url": "https://open.spotify.com/album/...",
      "matched_title": "Atlas",
      "matched_artist": "Logic Moon",
      "confidence": 100.0,
      "error": null
    },
    "beatport": {
      "url": null,
      "matched_title": null,
      "matched_artist": null,
      "confidence": null,
      "error": "no candidates found"
    }
  }
}
```

`source.platform` is the platform of the URL you passed in (`bandcamp`,
`apple_music`, `deezer`, `soundcloud`). Before version 2.0 it was always
`"bandcamp"`. The source platform's own entry is the source URL with
`confidence` 100.0, it is not searched.

Every platform always has the same 5 fields (`url`, `matched_title`,
`matched_artist`, `confidence`, `error`), whether or not a match was found.

## Programmatic use

The core logic is separated from the CLI and directly importable, e.g. for
a future DB writer:

```python
from dsp_scraper import find_release

result = find_release("https://music.apple.com/us/album/it-may-never-coming-back-single/6804971310")
# result is a dict in the schema above - write it to a DB here, for example
```

To resolve just the source URL without searching anything:

```python
from dsp_scraper.sources import resolve_source

info = resolve_source("https://www.deezer.com/de/album/854570502")
# info.artist, info.title, info.release_type, info.url, info.platform
```

## Architecture

```
dsp_scraper/
  pyproject.toml       # project/dependency definition (uv) + build-system (hatchling)
  cli.py                # CLI entry point (argparse, --stdout/--output/--delay)
  src/dsp_scraper/
    __init__.py           # exposes find_release
    core.py                # find_release(), PLATFORMS
    sources.py             # resolve_source(url) -> ReleaseInfo, one resolver per source host
    types.py               # ReleaseInfo (artist, title, release_type, url, platform)
    bandcamp.py            # scrape_release(url) -> ReleaseInfo (Bandcamp resolver)
    matching.py            # Candidate/MatchResult, score(), pick_best()
    platforms/
      _common.py             # shared Playwright new_page() context manager
      spotify.py, apple_music.py, deezer.py, amazon_music.py, soundcloud.py,
      beatport.py            # active (in core.PLATFORMS)
      youtube_music.py, tidal.py, napster.py, pandora.py
                              # written but disabled, see Supported platforms above
  tests/
    test_sources.py        # offline unit tests: resolvers (saved fixtures, mocked HTTP) + source-platform handling in core
    fixtures/              # saved <head> sections and Deezer API response for the offline tests
    test_bandcamp.py       # smoke test: bandcamp.py against 15 real Bandcamp URLs
    test_platform.py       # smoke test: one platform's search() against the same 15 releases
    test_full_pipeline.py  # smoke test: full find_release() (all active platforms) against the same 15
```

Run the offline tests with `uv run tests/test_sources.py` (no network needed).

Every platform module follows the same shape: a `search(artist: str, title:
str) -> list[Candidate]` function that uses Playwright to open the
platform's own search UI and extract result links along with their
title/artist text.

### Matching

`matching.pick_best()` scores every candidate with rapidfuzz, **title and
artist scored separately** (weighted 70/30 in favor of the title), and picks
the highest score. The best match has to clear `DEFAULT_THRESHOLD = 70.0`,
otherwise the platform counts as "no match". Scoring title and artist
separately (instead of one combined string) avoids two classes of false
positive found during live testing:

- A short reference title being a *substring* of an unrelated candidate's
  title (e.g. reference "Atlas" vs. candidate "Atlas in Motion" by a
  completely different artist) can score deceptively high on a naive
  combined-string comparison.
- Artist name words overlapping with an unrelated title (e.g. artist "Logic
  Moon" + wrong title "Logic") inflate a combined score even though the
  titles don't match at all.

A related bug found live: several platform modules fell back to the
*reference* artist whenever the real artist text couldn't be scraped from
the page, which silently faked a 100% artist match for any candidate with
missing artist data. Fixed by falling back to an empty string instead, so a
missing artist correctly drags the candidate's score down rather than
propping it up.

**Two more root causes found through live testing, both worth knowing about
before touching a platform module:**

- **`urllib.parse.quote_plus` (space → `+`) silently corrupted Apple Music's
  search ranking** - the exact same query encoded with `%20` (`quote`)
  consistently returned the correct top result; encoded with `+` it
  consistently returned a wrong one. Not a timeout, not an empty result -
  a *plausible-looking wrong match*, the worst kind of scraping bug. Fixed
  by switching every platform module from `quote_plus` to `quote`, since
  the same failure mode could plausibly affect any of them even where it
  isn't obviously visible as zero results.
- **Deezer's result rows are `<div>`s with no `href` at all** (client-side
  routing via `onClick`/`pushState`, not real anchor tags) - a generic
  `a[href*="/track/"]` scrape mostly picked up unrelated promo links
  elsewhere on the page instead of erroring out, which is worse than
  finding nothing. Fixed by targeting the specific `data-testid`s Deezer
  uses for its top-result card and album grid instead of a generic href
  pattern. Even after the fix, Deezer's "top result" card only seems to
  render for fairly confident matches, so recall stays lower than the
  other platforms - a good target for **`uv run tests/test_platform.py deezer`**
  the next time someone wants to push on it.

### Known limitations & maintenance notes

- **Selectors are live-site snapshots**, not stable APIs. Every platform
  module carries a `ponytail:` comment with a verification date or a note
  that the selector is still untested. If `search()` suddenly returns `[]`
  for a query known to have results: open the search URL manually, inspect
  a result, and update the selector constant in that module.
- **No retry/backoff, no caching, no logging framework** - left out on
  purpose for v1 (YAGNI). A single `try/except Exception` per platform in
  `core.find_release()` is enough to isolate a failing run.
- **User-agent spoofing** in `platforms/_common.py`, since several
  platforms otherwise flag headless Chromium as a bot and show a
  captcha/block page.
- **Pause between platform searches** (`--delay`, default 1.5s) so the
  active platforms aren't hit back-to-back.

### Planned extension: reverse lookup

Right now Bandcamp is the only source. The plan is to later support the
reverse direction too - starting from any platform URL (e.g. Spotify) and
finding the others. The module shape is deliberately chosen so this can be
added without a redesign: `bandcamp.py` would need a `search()`, and each
DSP module a `scrape_release(url)` - then "source" becomes just another
interchangeable module from the same set.

## Testing

```bash
uv run matching.py                          # matching-logic self-test (asserts, no network)
uv run tests/test_bandcamp.py               # bandcamp.py against 15 real Bandcamp URLs from
                                             # logic-moon.de's own catalog, writes results to
                                             # tests/test_bandcamp_results.json
uv run tests/test_platform.py apple_music   # one platform's search() against the same
                                             # 15 releases - the fast way to re-check a
                                             # single module after tuning its selectors
                                             # (defaults to apple_music if no name given)
uv run tests/test_full_pipeline.py          # full run() (all active platforms) against the
                                             # same 15 releases, writes per-release results to
                                             # tests/test_full_pipeline_results.json and prints
                                             # a per-platform match-rate summary - takes several
                                             # minutes (6 platforms x 15 releases)
```

The platform modules (`platforms/*.py`) deliberately have no unit tests -
they depend on third-party live JS SPAs that can change without notice, so
`test_platform.py`/`test_full_pipeline.py` above (real network calls against
a known catalog) are the actual regression check. For a single one-off
query:

```bash
uv run python3 -c "from platforms import spotify; print(spotify.search('Logic Moon', 'Atlas'))"
```

## License

MIT, see [LICENSE](LICENSE).
