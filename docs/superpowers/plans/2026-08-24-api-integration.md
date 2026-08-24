# dsp_scraper API Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make dsp_scraper's `find_release()` callable as a pip-installable
dependency from the user's existing Flask API, exposed as a new
`/public/dsp-lookup` GET endpoint that returns the same JSON shape as the
CLI's `--stdout` mode.

**Architecture:** Two repos, two phases. Phase 1 (Tasks 1-6, this repo,
`dsp_scraper`) restructures the flat top-level modules into an installable
`src/dsp_scraper/` package with one public function, `find_release()` -
pure move/rename, no logic changes. Phase 2 (Tasks 7-8, the API repo)
installs dsp_scraper from its GitHub URL and adds one Flask-RESTful
Resource that calls `find_release()` in-process and returns its dict as
JSON, following the existing `SonglinkProxy` pattern.

**Tech Stack:** Python 3.12, hatchling (build backend), uv (dsp_scraper
package manager), Flask + Flask-RESTful (API repo, unchanged), Playwright.

**Spec:** `docs/superpowers/specs/2026-08-24-api-integration-design.md`

## Global Constraints

- Public API surface after the refactor is exactly one function:
  `dsp_scraper.find_release(bandcamp_url: str, platform_delay: float = 1.5) -> dict`
  - same signature and return shape as today's `main.run()`. Every task
  that imports it uses this name and signature - nothing else is
  re-exported from the package root.
- Tasks 1-6 (the packaging refactor) must not change any scraping,
  matching, or CLI behavior - verified by re-running the existing test
  suite and comparing output, not by re-deriving logic.
- The new API endpoint is `GET /public/dsp-lookup?url=<bandcamp_url>`, no
  auth, and returns `find_release()`'s dict **unmodified** as the JSON
  response body - no wrapping, no extra fields.
- dsp_scraper repo: `/Users/tobe/Sites/logic-moon.de/dsp_scraper`. API
  repo: `/Users/tobe/Sites/tobeworks_projects/api`. Every task below
  states which repo it's in.

---

## Task 1: Package scaffolding (dsp_scraper)

**Repo:** dsp_scraper

**Files:**
- Modify: `pyproject.toml`
- Create: `src/dsp_scraper/__init__.py`

**Interfaces:**
- Produces: an installable `dsp_scraper` package (currently empty) that
  `uv sync` puts into `.venv` in editable mode, importable as
  `import dsp_scraper`.

- [ ] **Step 1: Add the build-system config to `pyproject.toml`**

Append this to the end of `pyproject.toml` (the existing `[project]`
table and its `dependencies` list stay exactly as they are):

```toml

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/dsp_scraper"]
```

- [ ] **Step 2: Create the package directory with a placeholder `__init__.py`**

```bash
mkdir -p src/dsp_scraper
```

Create `src/dsp_scraper/__init__.py`:

```python
"""dsp_scraper: find a Bandcamp release on other DSPs by scraping."""
```

- [ ] **Step 3: Verify `uv sync` installs the package in editable mode**

Run: `uv sync`
Expected: completes without error, and `dsp-scraper` (or `dsp_scraper`)
appears in the "Installed" summary or `.venv/lib/python3.12/site-packages`
as an editable install (check with `uv pip show dsp-scraper` - it should
report a `Location`/`Editable project location` pointing at this repo).

Run: `uv run python3 -c "import dsp_scraper; print(dsp_scraper.__doc__)"`
Expected: prints `dsp_scraper: find a Bandcamp release on other DSPs by scraping.`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/dsp_scraper/__init__.py
git commit -m "Add hatchling build config and empty dsp_scraper package

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: Move bandcamp.py and matching.py into the package (dsp_scraper)

**Repo:** dsp_scraper

**Files:**
- Move: `bandcamp.py` → `src/dsp_scraper/bandcamp.py`
- Move: `matching.py` → `src/dsp_scraper/matching.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `dsp_scraper.bandcamp.scrape_release(url: str) -> ReleaseInfo`,
  `dsp_scraper.matching.Candidate`, `dsp_scraper.matching.MatchResult`,
  `dsp_scraper.matching.pick_best(candidates, ref_artist, ref_title, threshold=...) -> MatchResult` -
  unchanged signatures, just a new import path for later tasks.

Neither file imports anything from this project (only stdlib, `requests`,
`bs4`, `rapidfuzz`), so this is a pure `git mv` with no content changes.

- [ ] **Step 1: Move the files**

```bash
git mv bandcamp.py src/dsp_scraper/bandcamp.py
git mv matching.py src/dsp_scraper/matching.py
```

- [ ] **Step 2: Verify both import cleanly from the new location**

Run: `uv run python3 -c "from dsp_scraper.bandcamp import scrape_release; from dsp_scraper.matching import Candidate, MatchResult, pick_best; print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Run matching's self-test from its new location**

Run: `uv run python3 -m dsp_scraper.matching`
Expected: prints `matching.py self-test OK`

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Move bandcamp.py and matching.py into src/dsp_scraper/

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: Move platforms/ into the package and fix internal imports (dsp_scraper)

**Repo:** dsp_scraper

**Files:**
- Move: `platforms/` → `src/dsp_scraper/platforms/` (all 12 files:
  `__init__.py`, `_common.py`, `spotify.py`, `apple_music.py`,
  `deezer.py`, `amazon_music.py`, `soundcloud.py`, `beatport.py`,
  `youtube_music.py`, `tidal.py`, `napster.py`, `pandora.py`)

**Interfaces:**
- Consumes: `dsp_scraper.matching.Candidate` (Task 2).
- Produces: `dsp_scraper.platforms.<name>.search(artist: str, title: str) -> list[Candidate]`
  for all 10 platform modules, `dsp_scraper.platforms._common.new_page()` /
  `SEARCH_TIMEOUT_MS` - unchanged, just a new import path.

Every one of the 10 platform modules has exactly two internal import lines
that need their prefix changed - `from matching import Candidate` and
`from platforms._common import SEARCH_TIMEOUT_MS, new_page`. `_common.py`
and `__init__.py` have no internal imports to fix.

- [ ] **Step 1: Move the directory**

```bash
git mv platforms src/dsp_scraper/platforms
```

- [ ] **Step 2: Fix internal imports in all 10 platform modules**

```bash
cd src/dsp_scraper/platforms
sed -i '' 's/^from matching import Candidate$/from dsp_scraper.matching import Candidate/' \
  spotify.py apple_music.py deezer.py amazon_music.py soundcloud.py \
  beatport.py youtube_music.py tidal.py napster.py pandora.py
sed -i '' 's/^from platforms\._common import SEARCH_TIMEOUT_MS, new_page$/from dsp_scraper.platforms._common import SEARCH_TIMEOUT_MS, new_page/' \
  spotify.py apple_music.py deezer.py amazon_music.py soundcloud.py \
  beatport.py youtube_music.py tidal.py napster.py pandora.py
cd ../../..
```

- [ ] **Step 3: Verify no old-style imports remain**

Run: `grep -rn "^from matching import\|^from platforms\." src/dsp_scraper/platforms/`
Expected: no output (empty)

- [ ] **Step 4: Verify every platform module imports cleanly**

Run:
```bash
uv run python3 -c "
from dsp_scraper.platforms import (
    spotify, apple_music, deezer, amazon_music, soundcloud, beatport,
    youtube_music, tidal, napster, pandora,
)
print('all 10 platform modules import cleanly')
"
```
Expected: prints `all 10 platform modules import cleanly`

- [ ] **Step 5: Spot-check one platform's search() still works end to end**

Run: `uv run python3 -c "from dsp_scraper.platforms import spotify; print(spotify.search('Logic Moon', 'Atlas'))"`
Expected: prints a list containing at least one `Candidate(title='Atlas', artist='Logic Moon', url='https://open.spotify.com/album/...')`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Move platforms/ into src/dsp_scraper/ and fix internal imports

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: Split main.py into core.py (library) + cli.py (CLI shell) (dsp_scraper)

**Repo:** dsp_scraper

**Files:**
- Create: `src/dsp_scraper/core.py`
- Create: `cli.py` (repo root)
- Delete: `main.py` (repo root)
- Modify: `src/dsp_scraper/__init__.py`

**Interfaces:**
- Consumes: `dsp_scraper.bandcamp.scrape_release` (Task 2),
  `dsp_scraper.matching.{MatchResult, pick_best}` (Task 2),
  `dsp_scraper.platforms.{spotify, apple_music, deezer, amazon_music, soundcloud, beatport}` (Task 3).
- Produces: `dsp_scraper.find_release(bandcamp_url: str, platform_delay: float = DEFAULT_PLATFORM_DELAY_SECONDS) -> dict` -
  the one function the API integration (Task 7) imports. Same return
  shape as today's `main.run()`: `{"source": {...}, "results": {<platform>: {url, matched_title, matched_artist, confidence, error}, ...}}`.

`main.py` currently mixes two responsibilities: the scraping orchestration
(`run()`, `PLATFORMS`) and the CLI shell (`parse_args()`, `main()`,
stdout/file output). Split them: the orchestration becomes `core.py`
inside the package (renaming `run` to `find_release`), the CLI shell
becomes a new root-level `cli.py` that imports `find_release` from the
package - mirroring exactly what `main.py` does today, just calling the
relocated function.

- [ ] **Step 1: Create `src/dsp_scraper/core.py`**

```python
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
```

- [ ] **Step 2: Create root `cli.py`**

```python
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
```

- [ ] **Step 3: Delete root `main.py` and update the package `__init__.py`**

```bash
git rm main.py
```

Replace `src/dsp_scraper/__init__.py` with:

```python
"""dsp_scraper: find a Bandcamp release on other DSPs by scraping."""
from dsp_scraper.core import find_release

__all__ = ["find_release"]
```

- [ ] **Step 4: Verify the package's public function works**

Run: `uv run python3 -c "from dsp_scraper import find_release; print(callable(find_release))"`
Expected: prints `True`

- [ ] **Step 5: Verify the CLI still works end to end**

Run: `uv run cli.py --stdout https://logicmoon.bandcamp.com/album/atlas`
Expected: prints progress lines to stderr, then a JSON object on stdout
with `"source"` and `"results"` keys, `results.spotify.url` pointing at
an `open.spotify.com` URL.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Split main.py into dsp_scraper.core (library) and cli.py (CLI shell)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: Update the test suite for the new package layout (dsp_scraper)

**Repo:** dsp_scraper

**Files:**
- Modify: `tests/test_bandcamp.py`
- Modify: `tests/test_platform.py`
- Modify: `tests/test_full_pipeline.py`

**Interfaces:**
- Consumes: `dsp_scraper.bandcamp.scrape_release` (Task 2),
  `dsp_scraper.matching.pick_best` (Task 2), `dsp_scraper.find_release`
  (Task 4), `dsp_scraper.platforms.<name>` (Task 3).
- Produces: nothing new - same `SAMPLE_URLS` list, same CLI usage
  (`uv run tests/test_bandcamp.py`, etc.), now working against the
  package instead of loose root modules.

Since the package is installed editable via `uv sync` (Task 1), these
files no longer need the `sys.path.insert(...)` bootstrap they had as
loose root-level scripts - `import dsp_scraper` just works.

- [ ] **Step 1: Update `tests/test_bandcamp.py`**

Replace everything from the top of the file down to (and including) the
`RESULTS_FILE = ...` line with:

```python
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
```

(This drops the `sys.path.insert(...)` bootstrap and its `import sys` -
no longer needed now that `dsp_scraper` is an installed package. `json`,
`asdict`, and `Path` are all still used further down in the file and stay.)
Everything below `RESULTS_FILE = ...` (`SAMPLE_URLS`, `main()`) is unchanged.

- [ ] **Step 2: Update `tests/test_platform.py`**

Replace everything from the top of the file down to (and including) the
last `import`/`from` line with:

```python
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
```

(Drops the `sys.path.insert(...)` bootstrap and its `from pathlib import
Path`. `import sys` stays - `main()` still reads `sys.argv`. `import
importlib` stays - still used below.) Change the dynamic import line
inside `main()` from:

```python
platform = importlib.import_module(f"platforms.{platform_name}")
```

to:

```python
platform = importlib.import_module(f"dsp_scraper.platforms.{platform_name}")
```

- [ ] **Step 3: Update `tests/test_full_pipeline.py`**

Replace everything from the top of the file down to (and including) the
`RESULTS_FILE = ...` line with:

```python
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
```

(Drops the `sys.path.insert(...)` bootstrap and its `import sys`. `json`
and `Path` are still used further down and stay.) Change every call site
from `run(url)` to `find_release(url)` (there is exactly one, inside the
loop in `main()`).

- [ ] **Step 4: Run the fast checks**

Run: `uv run python3 -m dsp_scraper.matching`
Expected: prints `matching.py self-test OK`

Run: `uv run tests/test_bandcamp.py`
Expected: `15/15 passed`, writes `tests/test_bandcamp_results.json`

- [ ] **Step 5: Spot-check test_platform.py and test_full_pipeline.py import cleanly**

Run: `uv run python3 -c "import tests.test_platform, tests.test_full_pipeline; print('imports ok')"`

Note: this repo has no `tests/__init__.py`, so run it from the repo root
with the repo root itself as the working directory (matches how `uv run`
already invokes scripts) - if this import check fails on a missing
`__init__.py`/module-not-found error unrelated to `dsp_scraper`, fall back
to just running `uv run tests/test_platform.py apple_music` directly and
confirm it completes with a `N/15 matched` summary line instead.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Update tests/ imports for the src/dsp_scraper/ package layout

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: Update README and push (dsp_scraper)

**Repo:** dsp_scraper

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing new - this is the task that pushes Tasks 1-5 to
  GitHub, which Task 7 (API repo) depends on for its `pip install
  git+https://...` to see the new package.

- [ ] **Step 1: Update the Architecture file tree in README.md**

Replace the existing tree (currently showing `main.py`, `bandcamp.py`,
`matching.py`, `platforms/` at the repo root) with:

```
dsp_scraper/
  pyproject.toml       # project/dependency definition (uv) + build-system (hatchling)
  cli.py                # CLI entry point (argparse, --stdout/--output/--delay)
  src/dsp_scraper/
    __init__.py           # exposes find_release
    core.py                # find_release(), PLATFORMS
    bandcamp.py            # scrape_release(url) -> ReleaseInfo
    matching.py            # Candidate/MatchResult, score(), pick_best()
    platforms/
      _common.py             # shared Playwright new_page() context manager
      spotify.py, apple_music.py, deezer.py, amazon_music.py, soundcloud.py,
      beatport.py            # active (in core.PLATFORMS)
      youtube_music.py, tidal.py, napster.py, pandora.py
                              # written but disabled, see Supported platforms above
  tests/
    test_bandcamp.py       # smoke test: bandcamp.py against 15 real Bandcamp URLs
    test_platform.py       # smoke test: one platform's search() against the same 15 releases
    test_full_pipeline.py  # smoke test: full find_release() (all active platforms) against the same 15
```

- [ ] **Step 2: Update every `uv run main.py` / `uv run python3 -c "from main import run"` reference**

Find them: `grep -n "main.py\|from main import\|main\.run(" README.md`

Replace `uv run main.py` with `uv run cli.py` everywhere in the Setup,
Usage, and Programmatic use sections. Replace the "Programmatic use"
code example:

```python
from main import run

result = run("https://logicmoon.bandcamp.com/album/atlas")
```

with:

```python
from dsp_scraper import find_release

result = find_release("https://logicmoon.bandcamp.com/album/atlas")
```

- [ ] **Step 3: Add an "Installing as a dependency" note**

Add this paragraph right after the "## Setup" section's code block:

```markdown
Since `pyproject.toml` declares a proper build backend, dsp_scraper is
also installable as a dependency of another project directly from GitHub:
`pip install git+https://github.com/Tobeworks/dsp_scraper.git`, then
`from dsp_scraper import find_release`. The installing project still
needs its own Playwright browser install step
(`playwright install --with-deps chromium`) - installing dsp_scraper
doesn't run that automatically.
```

- [ ] **Step 4: Verify no stale references remain**

Run: `grep -n "main\.py\|from main import\|main\.run(" README.md`
Expected: no output (empty)

- [ ] **Step 5: Commit and push**

```bash
git add README.md
git commit -m "Update README for the src/dsp_scraper/ package layout

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
git push
```

---

## Task 7: Install dsp_scraper as a dependency in the API repo (api)

**Repo:** api (`/Users/tobe/Sites/tobeworks_projects/api`)

**Files:**
- Modify: `requirements.txt`
- Modify: `Dockerfile`

**Interfaces:**
- Consumes: `dsp_scraper.find_release` (published to GitHub by Task 6).
- Produces: `dsp_scraper` importable inside this repo's virtualenv, for
  Task 8 to use.

- [ ] **Step 1: Add the dependency to `requirements.txt`**

Append this line to `requirements.txt`:

```
dsp_scraper @ git+https://github.com/Tobeworks/dsp_scraper.git
```

- [ ] **Step 2: Add the Playwright browser install step to `Dockerfile`**

In `Dockerfile`, right after the existing line
`RUN pip3 install --no-cache-dir -r requirements.txt`, add:

```dockerfile
RUN playwright install --with-deps chromium
```

- [ ] **Step 3: Verify the package installs and imports locally**

This repo's virtualenv lives at the project root (see `pyvenv.cfg`), not
`.venv`. Activate it and install:

```bash
source bin/activate
pip install -r requirements.txt
python3 -m playwright install --with-deps chromium
python3 -c "from dsp_scraper import find_release; print(callable(find_release))"
deactivate
```

Expected: the pip install completes without error (it clones dsp_scraper
from GitHub), the playwright install completes, and the final line prints
`True`.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt Dockerfile
git commit -m "Add dsp_scraper dependency and Playwright browser install

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 8: Add the /public/dsp-lookup endpoint (api)

**Repo:** api (`/Users/tobe/Sites/tobeworks_projects/api`)

**Files:**
- Create: `api/api_dsp_scraper.py`
- Modify: `server.py`

**Interfaces:**
- Consumes: `dsp_scraper.find_release(bandcamp_url: str) -> dict` (Task 7).
- Produces: `GET /public/dsp-lookup?url=<bandcamp_url>` returning
  `find_release()`'s dict as the JSON response body.

- [ ] **Step 1: Create `api/api_dsp_scraper.py`**

```python
from flask import request
from flask_restful import Resource
from dsp_scraper import find_release


class DspLookupResource(Resource):
    def get(self):
        bandcamp_url = request.args.get('url')

        if not bandcamp_url:
            return {'error': 'No url provided'}, 400

        try:
            return find_release(bandcamp_url)
        except Exception as e:
            return {'error': str(e)}, 500
```

This mirrors `api/api_songlink.py`'s `SonglinkProxy` shape (GET with a
`url` query param, one broad try/except, dict returned straight as JSON) -
no auth, matching the user's explicit choice.

- [ ] **Step 2: Register the route in `server.py`**

Add the import near the other `api.*` imports (next to the existing
`from api.api_songlink import SonglinkProxy` line):

```python
from api.api_dsp_scraper import DspLookupResource
```

Add the route registration near the other `/public/*` resources (next to
the existing `api.add_resource(SonglinkProxy, '/public/songlink-proxy', endpoint='songlink-proxy')`
line, if that line is still present, otherwise near
`api.add_resource(get_bandcamp_id, ...)`):

```python
api.add_resource(DspLookupResource, '/public/dsp-lookup', endpoint='dsp-lookup')
```

- [ ] **Step 3: Verify locally**

Start the server (this repo's `server.py` runs on port 5001 in debug mode
when run directly):

```bash
source bin/activate
python3 server.py &
sleep 3
curl "http://localhost:5001/public/dsp-lookup?url=https://logicmoon.bandcamp.com/album/atlas"
kill %1
deactivate
```

Expected: a JSON response with `"source"` and `"results"` top-level keys,
`results.spotify.url` pointing at an `open.spotify.com` URL - the same
shape `uv run cli.py --stdout <url>` produces in the dsp_scraper repo.
This call takes roughly a minute (6 platforms, sequential, ~1.5s delay
between each) - that's expected, not a hang.

- [ ] **Step 4: Verify the missing-url error path**

```bash
source bin/activate
python3 server.py &
sleep 3
curl -i "http://localhost:5001/public/dsp-lookup"
kill %1
deactivate
```

Expected: HTTP 400 with body `{"error": "No url provided"}`.

- [ ] **Step 5: Commit**

```bash
git add api/api_dsp_scraper.py server.py
git commit -m "Add /public/dsp-lookup endpoint backed by dsp_scraper

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

Do not push or deploy - leave that to the user, since it changes a live
production API (`gcloud run deploy` via `deploy.sh`).

---

## Final verification (whole plan)

- [ ] All 8 tasks committed (dsp_scraper: 6 commits + push; api: 2 commits, not pushed).
- [ ] `uv run cli.py --stdout <bandcamp_url>` in dsp_scraper produces the
  same JSON shape it did before the refactor.
- [ ] `curl "http://localhost:5001/public/dsp-lookup?url=<bandcamp_url>"`
  against a locally-running API server returns that same JSON shape.
- [ ] Optional, slower double-check: `uv run tests/test_full_pipeline.py`
  in dsp_scraper still reports match rates in the same ballpark as the
  README's documented table (Spotify ~13/15, Apple Music ~12/15, etc.) -
  not required per-task since it takes 15-20 minutes, but worth one run
  before considering this integration done.
