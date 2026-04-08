import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Optional

import aiohttp

import config

# Directory for caching Tidal stream URLs to prevent repeated manifest lookups
CACHE_DIR = "data/cache"
os.makedirs(CACHE_DIR, exist_ok=True)


async def get_tidal_stream(title: str, artist: str, duration: int) -> Optional[str]:
    """
    Try to find a Tidal stream for this track.
    Includes caching and detailed logging to debug why Tidal might fail.
    """
    # Clean the title to remove YouTube-specific suffixes that break Tidal search
    # e.g., "Song Name (Official Video)" -> "Song Name"
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
                print(f"[TIDAL] Cache hit for {clean_title}")
                return cached_data["url"]
        except Exception as e:
            print(f"[TIDAL] Cache read error: {e}")

    # 2. Search Tidal
    song_id = await _search(clean_title, artist, duration)
    if not song_id:
        # If clean title fails, try original title as fallback
        if clean_title != title:
            print(f"[TIDAL] Search failed with clean title, trying original...")
            song_id = await _search(title, artist, duration)

        if not song_id:
            print(f"[TIDAL] No match found on Tidal for: {title}")
            return None

    # 3. Resolve Stream URL from Manifest
    stream_url = await _stream_url(song_id)

    # 4. Save to Cache if successful
    if stream_url:
        try:
            with open(cache_path, "w") as f:
                json.dump({"url": stream_url, "title": title}, f)
            print(f"[TIDAL] Successfully resolved and cached Tidal stream.")
        except Exception as e:
            print(f"[TIDAL] Cache write error: {e}")

    return stream_url


async def _search(title: str, artist: str, duration: int) -> Optional[str]:
    """Search the Tidal proxy and find the closest match by duration."""
    url = f"{config.TIDAL_PROXY_URL}/search/"
    params = {"s": title, "a": artist, "limit": "5"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status != 200:
                    print(f"[TIDAL] Search API returned status {resp.status}")
                    return None
                data = await resp.json()
    except Exception as e:
        print(f"[TIDAL] Search request failed: {e}")
        return None

    items = data.get("data", {}).get("items", [])
    if not items:
        return None

    best = None
    best_diff = 999
    for item in items:
        # Match by duration within 10 seconds (YouTube durations can vary slightly from studio tracks)
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
    """Fetch the MPD manifest and extract the playable BaseURL."""
    manifest_api = f"{config.TIDAL_PROXY_URL}/trackManifests/?id={song_id}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(manifest_api) as resp:
                if resp.status != 200:
                    print(f"[TIDAL] Manifest API error: {resp.status}")
                    return None

                data = await resp.json()
                manifest_url = (
                    data.get("data", {})
                    .get("data", {})
                    .get("attributes", {})
                    .get("uri")
                )

                if not manifest_url:
                    print("[TIDAL] No manifest URI in API response")
                    return None

                print(f"[TIDAL] Fetching manifest: {manifest_url}")
                async with session.get(manifest_url) as manifest_resp:
                    if manifest_resp.status != 200:
                        print(
                            f"[TIDAL] Manifest download failed: {manifest_resp.status}"
                        )
                        return None

                    manifest_text = await manifest_resp.text()

                    # Parse the MPEG-DASH XML (.mpd)
                    # We MUST handle the XML namespace correctly to find the BaseURL
                    try:
                        root = ET.fromstring(manifest_text)

                        # The namespace is usually the first part of the tag in '{uri}tag' format
                        # or we can search specifically for it.
                        namespace = ""
                        if root.tag.startswith("{"):
                            namespace = root.tag.split("}")[0] + "}"

                        # Find BaseURL using the discovered namespace
                        base_url_node = root.find(f".//{namespace}BaseURL")

                        if base_url_node is not None and base_url_node.text:
                            return base_url_node.text.strip()

                        print("[TIDAL] <BaseURL> not found in manifest XML")
                        # Debug: Print first 200 chars of manifest to see why it failed
                        print(f"[TIDAL] Manifest Snippet: {manifest_text[:200]}")

                    except ET.ParseError as e:
                        print(f"[TIDAL] XML Parse Error: {e}")

    except Exception as e:
        print(f"[TIDAL] Stream resolution failed: {e}")

    return None
