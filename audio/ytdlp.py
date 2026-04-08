import asyncio
from typing import Any

import yt_dlp

YDL_OPTS: dict[str, Any] = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "extract_flat": False,
    "skip_download": True,
}


async def get_metadata(query: str) -> dict:
    """Searches youtube and return metadata for the best result.
    query can be a search term OR a direct URL."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract, query)


def _extract(querey: str) -> dict:
    """sync helper - runs in a thread via run_in_extactor"""
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:  # type: ignore
        # If it looks like a URL, use it directly, otherwise search YouTube
        search = querey if querey.startswith("http") else f"ytsearch1:{querey}"
        info = ydl.extract_info(search, download=False)

        # Search resukts come back as entries[]; direct URLs are the info itself
        entry = info["entries"][0] if "entries" in info else info

        return {
            "title": entry.get("title", "Unknown Title"),
            "artist": entry.get("uploader", "Unknown Artist"),
            "thumbnail": entry.get("thumbnail", ""),
            "duration": entry.get("duration", 0),
            "stream_url": entry.get("url", ""),
            "youtube_url": entry.get("webpage_url", ""),
        }
