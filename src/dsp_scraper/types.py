"""Shared data types."""
from dataclasses import dataclass


@dataclass
class ReleaseInfo:
    artist: str
    title: str
    release_type: str  # "album" | "track"
    url: str
    # Platform the source URL belongs to: "bandcamp", "apple_music", "deezer", "soundcloud", ...
    # Set by the resolver that produced this object.
    platform: str | None = None
