# dsp_scraper as an API endpoint — design

## Context

`dsp_scraper` (this repo) finds a Bandcamp release on other DSPs by
scraping and returns a JSON result. The user wants this available as an
endpoint on their existing Flask API
(`/Users/tobe/Sites/tobeworks_projects/api`), to build release-setup
tooling and their own service on top of it later — replacing a Songlink
(Odesli) proxy the API used previously, which the user reports is
deprecated. Goal: wire this up without duplicating dsp_scraper's scraping
logic into the API repo.

## Target API - relevant facts

- Flask + Flask-RESTful, deployed to Google Cloud Run
  (`gunicorn server:app --timeout 600 --workers 1`, 512Mi memory).
  **`--workers 1` means the whole API is effectively single-threaded** - a
  multi-minute request blocks every other endpoint (mailer, leads,
  licensing, rankings, ...) until it finishes.
- Already runs Selenium + Chrome in the same container for
  `ScreenshotsResource` (browser automation is an established pattern
  here).
- Existing precedent for exactly this shape of feature: `SonglinkProxy`
  (`api/api_songlink.py`), a thin Resource that proxies to the (now
  deprecated) `api.song.link` API and returns its JSON response as-is,
  registered as `api.add_resource(SonglinkProxy, '/public/songlink-proxy',
  endpoint='songlink-proxy')`.

## Decision

**Install dsp_scraper as an in-process pip dependency** (git URL), called
directly from a new Flask-RESTful Resource - no separate microservice.
User's explicit choice, made after trade-offs were raised (a scrape
blocks the API's single gunicorn worker for its duration; Playwright's
Chromium adds to the existing Selenium/Chrome footprint in the 512Mi
container). Documented here so the trade-off isn't silently forgotten,
not to relitigate it:

- **Mitigation available later, not applied now**: raising
  `--workers`/Cloud Run concurrency if the blocking becomes a real
  problem. Out of scope for this change - the user did not ask for it.

## Part 1: dsp_scraper packaging refactor

dsp_scraper is not currently pip-installable as a clean dependency:
`pyproject.toml` has no `[build-system]`, and `main.py`, `bandcamp.py`,
`matching.py`, `platforms/` are loose top-level modules - installing them
into another project's environment as-is would dump generically-named
top-level modules (`main`, `matching`, `platforms`) into that
environment, a real collision risk.

**Restructure into a `src/` layout:**

```
dsp_scraper/
  src/
    dsp_scraper/
      __init__.py        # exposes find_release
      bandcamp.py         # moved as-is (scrape_release, ReleaseInfo)
      matching.py         # moved as-is (Candidate, MatchResult, pick_best)
      core.py              # moved from main.py: find_release(), PLATFORMS,
                            # DEFAULT_PLATFORM_DELAY_SECONDS (renamed from run())
      platforms/           # moved as-is, all 10 modules incl. the 4 disabled
  cli.py                 # thin CLI wrapper: argparse + stdout/file output,
                          # calls dsp_scraper.find_release() - replaces
                          # today's main.py as the `uv run` entry point
  pyproject.toml          # add [build-system] (hatchling), keep deps
  ...
```

- `dsp_scraper.find_release(bandcamp_url: str, platform_delay: float = ...) -> dict`
  becomes the one public function other code imports - a rename of
  today's `main.run()`, same signature, same return shape (the exact JSON
  schema documented in the README).
- Internal imports across the package switch from bare (`from matching
  import Candidate`) to package-relative (`from dsp_scraper.matching
  import Candidate` or relative `from .matching import Candidate`) -
  touches every file in `platforms/` (mechanical rename, not a logic
  change) plus `bandcamp.py`, `matching.py`, `core.py`.
- `cli.py` **replaces** `main.py` at the repo root (`main.py` is deleted,
  not kept as a shim) - it keeps 100% of today's CLI behavior
  (`--output`, `--stdout`, `--delay`, interactive prompt), just calling
  `find_release()` from its new location instead of a same-file `run()`.
- Tests (`tests/test_*.py`) update their imports the same mechanical way;
  behavior and the 15-URL sample set are unchanged.
- README updated: install instructions, new file tree, `uv run cli.py`
  instead of `uv run main.py`.

No behavior changes in this part - pure move/rename for installability.

## Part 2: API repo changes

- `requirements.txt`: add `dsp_scraper @
  git+https://github.com/Tobeworks/dsp_scraper.git`
- `Dockerfile`: add `RUN playwright install --with-deps chromium` after
  the existing `pip3 install` step (Playwright's browser binary isn't
  pulled in by pip alone).
- New `api/api_dsp_scraper.py`:
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
  Returns `find_release()`'s dict untouched as the JSON response body -
  no extra wrapping, matching how the CLI's `--stdout` mode already
  behaves. This mirrors `SonglinkProxy`'s shape (GET with a `url` query
  param, plain-dict-to-JSON return, one broad try/except).
- `server.py`: import `DspLookupResource`, register
  `api.add_resource(DspLookupResource, '/public/dsp-lookup',
  endpoint='dsp-lookup')` - open access, no auth, matching
  `SonglinkProxy`'s convention (user's explicit choice).
- No changes to `CORS_ORIGINS` needed - `/public/*` isn't in the
  restricted CORS map in `server.py`, same as `songlink-proxy` and
  `get-bandcamp-id` today.

## Error handling

- `find_release()` raising (e.g. the Bandcamp URL 404s or isn't
  parseable) is the one case that's fatal for the whole request - caught
  by the Resource's `try/except`, returned as `{'error': ...}, 500`.
  Per-platform scraper failures are already handled *inside*
  `find_release()` (each platform's `error` field in the returned JSON) -
  the Resource doesn't need its own per-platform handling.

## Testing / verification

- dsp_scraper side: after the refactor, `uv run cli.py <url>` and
  `uv run tests/test_*.py` must behave identically to today (same
  15-release match rates) - the packaging move must not change any
  matching/scraping logic.
- API side: `pip install -r requirements.txt` picks up dsp_scraper from
  git; local `python server.py` (or the existing local dev flow) hits
  `GET /public/dsp-lookup?url=<bandcamp_url>` and gets back the same JSON
  shape as the CLI's `--stdout` output for the same URL.
- No new automated tests requested for the API side, consistent with
  `SonglinkProxy` having none either.
