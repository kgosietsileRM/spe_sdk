"""Resolve live stream links into media URLs OpenCV can read."""

from __future__ import annotations

import re
import threading
import time
from typing import Any
from urllib.parse import urlparse

LIVE_CACHE_SECONDS = 300.0
_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
_LIVE_PROTOCOLS = ("rtsp://", "rtmp://", "rtmps://", "udp://", "http://", "https://")
_CACHE: dict[str, tuple[float, str, str]] = {}
_LOCK = threading.Lock()


def is_live_source(value: str) -> bool:
    """Return True for live-capable URLs rather than local files."""
    lowered = value.strip().lower()
    if lowered.startswith(("rtsp://", "rtmp://", "rtmps://", "udp://")):
        return True
    if not lowered.startswith(_LIVE_PROTOCOLS):
        return False
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host in _YOUTUBE_HOSTS:
        return True
    path = parsed.path.lower()
    return path.endswith((".m3u8", ".mpd")) or "live" in host or "stream" in host


def is_youtube(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower()
    return host in _YOUTUBE_HOSTS


def resolve_live(value: str) -> tuple[str, str]:
    """Resolve a live page or stream URL to a direct media URL and title."""
    with _LOCK:
        cached = _CACHE.get(value)
    if cached is not None and cached[0] > time.time():
        return cached[1], cached[2]

    if not is_youtube(value):
        title = urlparse(value).path.rsplit("/", 1)[-1] or "Live feed"
        with _LOCK:
            _CACHE[value] = (time.time() + LIVE_CACHE_SECONDS, value, title)
        return value, title

    try:
        from yt_dlp import YoutubeDL
    except ImportError as error:
        raise RuntimeError(
            "Live YouTube feeds require yt-dlp. Run bootstrap.ps1 to install requirements."
        ) from error

    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(value, download=False)
    if not isinstance(info, dict):
        raise RuntimeError("Could not resolve the live feed.")

    direct = info.get("url")
    if isinstance(direct, str) and direct.startswith(_LIVE_PROTOCOLS):
        url = direct
    else:
        formats = [
            item
            for item in info.get("formats") or []
            if isinstance(item, dict)
            and isinstance(item.get("url"), str)
            and item.get("vcodec") not in (None, "none")
        ]
        if not formats:
            raise RuntimeError("The live feed has no readable video stream.")
        capped = [item for item in formats if (item.get("height") or 0) <= 720]
        candidates = capped or formats
        candidates.sort(key=lambda item: (item.get("height") or 0, item.get("tbr") or 0))
        url = str(candidates[-1]["url"])

    raw_title = str(info.get("title") or "Live feed")
    title = re.sub(r"[^\x20-\x7E]+", " ", raw_title)
    title = re.sub(r"\s+", " ", title).strip() or "Live feed"
    title = title[:72]
    with _LOCK:
        _CACHE[value] = (time.time() + LIVE_CACHE_SECONDS, url, title)
    return url, title
