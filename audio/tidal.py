import hashlib
import html
import json
import os
import re
from typing import Optional

import aiohttp

import config

headers = {"User-Agent": "piped bot"}


# Directory for caching Tidal stream URLs to prevent repeated manifest lookups
CACHE_DIR = "data/cache"
os.makedirs(CACHE_DIR, exist_ok=True)


async def get_tidal_stream(title: str, artist: str, duration: int) -> Optional[str]:
    """
    Try to find a Tidal stream for this track.
    Includes caching and detailed logging to debug why Tidal might fail.
    """
    clean_title = re.sub(
        r"(\(|\[)(official|video|music|remastered|lyrics|4k|hd|audio|visualizer).*?(\)|\])",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    print(f"[TIDAL] Resolving: {clean_title} - {artist} ({duration}s)")

    # 1. Check Cache first
    cache_key = hashlib.md5(f"{clean_title}{artist}{duration}".encode()).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"tidal_{cache_key}.json")

    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                cached_data = json.load(f)
                # If the cache references a local mpd file, verify it exists
                cached_url = cached_data["url"]
                if cached_url.endswith(".mpd") and not os.path.exists(cached_url):
                    print("[TIDAL] Cached MPD file missing, resolving again.")
                else:
                    print(f"[TIDAL] Cache hit for {clean_title}")
                    return cached_url
        except Exception as e:
            print(f"[TIDAL] Cache read error: {e}")

    # 2. Search Tidal
    song_id = await _search(clean_title, artist, duration)
    if not song_id:
        if clean_title != title:
            print("[TIDAL] Search failed with clean title, trying original...")
            song_id = await _search(title, artist, duration)

        if not song_id:
            print(f"[TIDAL] No match found on Tidal for: {title}")
            return None

    # 3. Resolve Stream URL (or Local MPD Manifest Path)
    stream_url = await _stream_url(song_id)

    # 4. Save to Cache if successful
    if stream_url:
        try:
            with open(cache_path, "w") as f:
                json.dump({"url": stream_url, "title": title}, f)
            print("[TIDAL] Successfully resolved and cached Tidal stream.")
        except Exception as e:
            print(f"[TIDAL] Cache write error: {e}")

    return stream_url


async def _search(title: str, artist: str, duration: int) -> Optional[str]:
    """Search the Tidal proxy and find the closest match by duration."""
    url = f"{config.TIDAL_PROXY_URL}/search/"
    params = {"s": title, "a": artist, "limit": "5"}

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status != 200:
                    print(f"[TIDAL] Search API returned status {resp.status}")
                    return None

                raw_text = await resp.text()
                # Parse the JSON manually so aiohttp doesn't crash on text/plain content type
                data = json.loads(raw_text)

    except Exception as e:
        print(f"[TIDAL] Search request failed: {e}")
        return None

    items = data.get("data", {}).get("items", [])
    if not items:
        return None

    best = None
    best_diff = 999
    for item in items:
        diff = abs(item.get("duration", 0) - duration)
        if diff < best_diff:
            best_diff = diff
            best = item

    if best and best_diff <= 10:
        print(f"[TIDAL] Match found: {best.get('title')} (ID: {best.get('id')})")
        return best["id"]

    print(f"[TIDAL] No duration match within 10s (Best diff: {best_diff}s)")
    return None


async def _stream_url(song_id: str) -> Optional[str]:
    """Fetch the MPD manifest and extract the playable URL or save MPD locally."""
    manifest_api = f"{config.TIDAL_PROXY_URL}/stream/{song_id}"

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(manifest_api) as resp:
                if resp.status != 200:
                    print(f"[TIDAL] Manifest API error: {resp.status}")
                    return None

                raw_text = await resp.text()
                # Parse the JSON manually so aiohttp doesn't crash on text/plain content type
                data = json.loads(raw_text)

                # Case 1: Direct audio URL (FLAC/MP4)
                if data.get("type") == "direct":
                    return data.get("url")

                # Case 2: DASH manifest
                elif data.get("type") == "dash":
                    manifest_raw = data.get("manifest", "")

                    # Unescape HTML/Unicode characters so it's a valid XML string
                    manifest_xml = html.unescape(manifest_raw)

                    # Save the XML to a local .mpd file so FFmpeg can play it directly
                    mpd_path = os.path.join(CACHE_DIR, f"tidal_{song_id}.mpd")
                    with open(mpd_path, "w", encoding="utf-8") as f:
                        f.write(manifest_xml)

                    # Return the local path (FFmpeg treats this just like a URL)
                    return mpd_path

    except Exception as e:
        print(f"[TIDAL] Stream resolution failed: {e}")

    return None
