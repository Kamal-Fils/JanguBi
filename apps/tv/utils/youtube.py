import logging
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger(__name__)

YOUTUBE_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_youtube_video_id(url: str) -> Optional[str]:
    if not url:
        return None

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path.strip("/")

    if "youtu.be" in host and path:
        candidate = path.split("/")[0]
        return candidate if YOUTUBE_ID_REGEX.match(candidate) else None

    if "youtube.com" in host or "youtube-nocookie.com" in host:
        if parsed.path == "/watch":
            query = parse_qs(parsed.query)
            values = query.get("v") or []
            video_id = values[0] if values else None
            return video_id if video_id and YOUTUBE_ID_REGEX.match(video_id) else None

        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live", "v"}:
            candidate = parts[1]
            return candidate if YOUTUBE_ID_REGEX.match(candidate) else None

    return None


def build_embed_url(video_id: str) -> str:
    return f"https://www.youtube.com/embed/{video_id}"


def fetch_youtube_metadata(video_id: str, api_key: str, timeout: int = 7) -> Optional[dict]:
    if not api_key or not video_id:
        return None

    endpoint = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,liveStreamingDetails",
        "id": video_id,
        "key": api_key,
    }

    try:
        response = requests.get(endpoint, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning("YouTube metadata request failed: %s", exc)
        return None

    items = payload.get("items") or []
    if not items:
        return None

    snippet = items[0].get("snippet") or {}
    live_content = (snippet.get("liveBroadcastContent") or "none").lower()

    return {
        "title": snippet.get("title") or "",
        "is_live": live_content == "live",
    }
