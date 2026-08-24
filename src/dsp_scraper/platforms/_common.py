"""Shared Playwright setup for platform search modules."""
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

SEARCH_TIMEOUT_MS = 15_000  # ponytail: single hardcoded timeout, no retry/backoff framework
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# ^ without UA spoofing, Spotify/Apple Music & co. sometimes flag headless
#   Chromium as a bot and show a captcha/block page instead of results.


@contextmanager
def new_page():
    """Launch headless chromium, yield one Page (with a realistic user agent),
    always close the browser afterwards."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(user_agent=USER_AGENT)
            yield context.new_page()
        finally:
            browser.close()
