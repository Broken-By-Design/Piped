import json
import random

import config
from audio.tidal import get_tidal_stream
from audio.ytdlp import get_metadata
from bot.player import Track


async def resolve(query: str, requested_by: str = "unknown") -> Track:
    """Main entry point. Takes a search querey or URL returns a Track."""

    # Step 1: Always get metadata from yt-dlp
    meta = await get_metadata(query)

    # Step 2: Try to upgrade the audio stream via tidal
    tidal_url = await get_tidal_stream(
        meta["title"],
        meta["artist"],
        meta["duration"],
    )

    # Step 3: use whichever stream we got
    stream_url = tidal_url or meta["stream_url"]
    source = "tidal" if tidal_url else "ytdlp"

    return Track(
        title=meta["title"],
        artist=meta["artist"],
        thumbnail=meta["thumbnail"],
        duration=meta["duration"],
        stream_url=stream_url,
        source=source,
        requested_by=requested_by,
        youtube_url=meta["youtube_url"],
    )


# Extension point - Meme autoplay sources


async def get_meme_track() -> Track:
    """Pick random meme track when queue is dry"""
    # 50% chance: pick from approved meme list
    if random.random() < 0.5:
        try:
            with open("data/meme_songs.json") as f:
                songs = json.load(f)["songs"]
                if songs:
                    pick = random.choice(songs)
                    return await resolve(pick["url"], requested_by="autoplay")
        except Exception:
            pass  # pass through to Yt search

    # 50% chance (or if list empty): search Yourube for random meme
    term = random.choice(config.MEME_SEARCH_TERMS)
    return await resolve(term, requested_by="autoplay")
