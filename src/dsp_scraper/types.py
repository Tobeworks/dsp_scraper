"""Shared data types."""
from dataclasses import dataclass, field


@dataclass
class ReleaseInfo:
    artist: str
    title: str
    release_type: str  # "album" | "track"
    url: str
    # Platform the source URL belongs to: "bandcamp", "apple_music", "deezer", "soundcloud", ...
    # "smart_link" for a link page (too.fm etc.), see sources._smartlink_source.
    # Set by the resolver that produced this object.
    platform: str | None = None
    # Direct platform URLs taken from a smart link page, keyed by platform name.
    # Empty for every other source. These are used as results without a search.
    links: dict[str, str] = field(default_factory=dict)
