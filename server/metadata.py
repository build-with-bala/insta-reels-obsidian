import re
import logging
from dataclasses import dataclass

import yt_dlp

logger = logging.getLogger(__name__)

REEL_URL_PATTERN = re.compile(
    r"instagram\.com/(?:reel|p)/([A-Za-z0-9_-]+)"
)


@dataclass
class ReelMetadata:
    reel_id: str
    caption: str | None
    creator_username: str | None
    creator_display_name: str | None
    thumbnail_url: str | None


def extract_reel_id(url: str) -> str | None:
    match = REEL_URL_PATTERN.search(url)
    return match.group(1) if match else None


def fetch_reel_metadata(url: str) -> ReelMetadata | None:
    reel_id = extract_reel_id(url)
    if not reel_id:
        return None

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return ReelMetadata(
                reel_id=info.get("id", reel_id),
                caption=info.get("description"),
                creator_username=info.get("uploader_id"),
                creator_display_name=info.get("uploader"),
                thumbnail_url=info.get("thumbnail"),
            )
    except Exception as e:
        logger.warning(f"Failed to fetch metadata for {url}: {e}")
        return None
