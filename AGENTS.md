# Agent instructions

## Commit messages

- **Conventional Commits**, short: `type: summary` (e.g. `feat: add Deezer album-grid candidates`, `fix: reject Apple Music false matches`, `chore: move platforms/ into src/dsp_scraper/`).
- One line. No body unless the change genuinely needs explaining beyond the summary - don't pad it out.

## Never `git push` without explicit permission

Commit freely, but never run `git push` (or trigger a rebuild/deploy) unless the user explicitly asks for it in that moment. This applies every time, not just once per session.


