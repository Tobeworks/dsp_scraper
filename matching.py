"""Fuzzy matching of scraped DSP search candidates against a reference release."""
from dataclasses import dataclass

from rapidfuzz import fuzz

DEFAULT_THRESHOLD = 70.0  # ponytail: arbitrary starting point, tune after seeing real scores


@dataclass
class Candidate:
    title: str
    artist: str
    url: str


@dataclass
class MatchResult:
    url: str | None = None
    matched_title: str | None = None
    matched_artist: str | None = None
    confidence: float | None = None
    error: str | None = None


def score(candidate: Candidate, ref_artist: str, ref_title: str) -> float:
    """rapidfuzz WRatio on title and artist scored separately, then weighted
    (title matters more - it's the primary identifier of "same release").
    Scoring title+artist as one combined string was tried first and produced
    false positives: e.g. candidate ("Logic", "Logic Moon") scored ~95
    against ref ("Atlas", "Logic Moon") purely because "Logic Moon" overlaps
    the artist half of the combined string, even though the titles ("Logic"
    vs "Atlas") don't match at all. Scoring separately catches that."""
    title_score = fuzz.WRatio(candidate.title, ref_title)
    artist_score = fuzz.WRatio(candidate.artist, ref_artist)
    return 0.7 * title_score + 0.3 * artist_score


def pick_best(
    candidates: list[Candidate],
    ref_artist: str,
    ref_title: str,
    threshold: float = DEFAULT_THRESHOLD,
) -> MatchResult:
    """Score every candidate, keep the top scorer. Returns a populated
    MatchResult if it clears threshold, else url=None with confidence set
    and error explaining the miss. Empty candidate list -> error, no scoring."""
    if not candidates:
        return MatchResult(error="no candidates found")

    best = max(candidates, key=lambda c: score(c, ref_artist, ref_title))
    best_score = round(score(best, ref_artist, ref_title), 1)

    if best_score < threshold:
        return MatchResult(
            confidence=best_score,
            error=f"best candidate below threshold ({best_score} < {threshold})",
        )

    return MatchResult(
        url=best.url,
        matched_title=best.title,
        matched_artist=best.artist,
        confidence=best_score,
    )


def _demo():
    ref = ("Boards of Canada", "Music Has the Right to Children")
    good = Candidate("Music Has the Right to Children", "Boards of Canada", "https://x/1")
    bad = Candidate("Some Other Album", "Unrelated Artist", "https://x/2")

    result = pick_best([bad, good], *ref)
    assert result.url == "https://x/1", result
    assert result.confidence >= DEFAULT_THRESHOLD, result

    only_bad = pick_best([bad], *ref)
    assert only_bad.url is None and only_bad.error, only_bad

    empty = pick_best([], *ref)
    assert empty.error == "no candidates found", empty

    print("matching.py self-test OK")


if __name__ == "__main__":
    _demo()
