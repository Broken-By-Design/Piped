import asyncio
import hashlib
import os
import random
import shutil
from collections import deque
from dataclasses import dataclass
from typing import Callable, List, Optional

import aiohttp
import discord

# Configuration for local buffering to prevent cutouts
CACHE_DIR = "data/cache/audio"
os.makedirs(CACHE_DIR, exist_ok=True)


@dataclass
class Track:
    """One song, Everything the player and GUI need"""

    title: str
    artist: str
    thumbnail: str  # URL to cover art image
    duration: int  # length in seconds
    stream_url: str  # the actual audio stream URL
    source: str  # "tidal" or "yt-dlp"
    requested_by: str  # Discord username of who queued it
    youtube_url: Optional[str] = None  # For linking back
    local_path: Optional[str] = None  # Path to the buffered file

    def to_dict(self) -> dict:
        """Converts to dict for sending over websockets / REST API"""
        return {
            "title": self.title,
            "artist": self.artist,
            "thumbnail": self.thumbnail,
            "duration": self.duration,
            "source": self.source,
            "requested_by": self.requested_by,
        }

    def get_cache_filename(self) -> str:
        """Generate a unique filename based on the stream URL to avoid collisions."""
        hash_id = hashlib.md5(self.stream_url.encode()).hexdigest()
        return os.path.join(CACHE_DIR, f"{hash_id}.mp3")


class MusicPlayer:
    """The brain. Holds all playback state and logic with background pre-downloading."""

    def __init__(self, bot):
        self.bot = bot
        self.queue: deque = deque()
        self.current: Optional[Track] = None
        self.voice_client: Optional[discord.VoiceClient] = None
        self.loop_mode: str = "off"
        self.shuffle: bool = False
        self.volume: float = 0.5
        self._lock = asyncio.Lock()
        self._download_tasks = {}  # Track active downloads to prevent duplicates

        # Clean cache on startup
        if os.path.exists(CACHE_DIR):
            try:
                shutil.rmtree(CACHE_DIR)
            except:
                pass
        os.makedirs(CACHE_DIR, exist_ok=True)

    # --- Queue management -----------------------
    async def add_to_queue(self, track: Track):
        """Add a track. If nothing is playing, start immediately."""
        self.queue.append(track)

        # Start pre-downloading this track immediately
        asyncio.create_task(self._buffer_track(track))

        is_busy = self.voice_client and (
            self.voice_client.is_playing() or self.voice_client.is_paused()
        )

        if not is_busy:
            await self._play_next()
        else:
            await self._broadcast_state()

    def get_queue(self) -> List[Track]:
        return list(self.queue)

    def shuffle_queue(self):
        items = list(self.queue)
        random.shuffle(items)
        self.queue = deque(items)

    def set_loop(self, mode: str):
        if mode not in ("off", "one", "queue"):
            raise ValueError(f"Invalid loop mode: {mode}")
        self.loop_mode = mode

    def set_volume(self, vol: int):
        self.volume = max(0, min(100, vol)) / 100
        if self.voice_client and isinstance(
            self.voice_client.source, discord.PCMVolumeTransformer
        ):
            self.voice_client.source.volume = self.volume

    # --- Buffering / Pre-downloading Logic ------
    async def _buffer_track(self, track: Track):
        """Download a track's stream to a local file to prevent cutouts."""
        if track.local_path and os.path.exists(track.local_path):
            return  # Already buffered

        if track.stream_url.endswith(".mpd"):
            if os.path.exists(track.stream_url):
                track.local_path = track.stream_url
            return

        target_path = track.get_cache_filename()

        if target_path in self._download_tasks:
            await self._download_tasks[target_path]
            return

        task = asyncio.create_task(self._do_download(track, target_path))
        self._download_tasks[target_path] = task
        try:
            await task
        finally:
            if target_path in self._download_tasks:
                del self._download_tasks[target_path]

    async def _do_download(self, track: Track, path: str):
        """Internal helper to stream data to disk."""
        print(f"[BUFFER] Starting download for: {track.title}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    track.stream_url, timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        with open(path, "wb") as f:
                            while True:
                                chunk = await resp.content.read(
                                    64 * 1024
                                )  # 64KB chunks
                                if not chunk:
                                    break
                                f.write(chunk)
                        track.local_path = path
                        print(f"[BUFFER] Successfully buffered: {track.title}")
                    else:
                        print(f"[BUFFER] Download failed with status {resp.status}")
        except Exception as e:
            print(f"[BUFFER] Error downloading {track.title}: {e}")

    # --- Playback controls ---------------------
    async def skip(self):
        """Skip the current song. Triggers _on_track_end."""
        if self.voice_client and (
            self.voice_client.is_playing() or self.voice_client.is_paused()
        ):
            # The 'after' callback in voice_client.play handles the logic
            self.voice_client.stop()

    async def pause(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            await self._broadcast_state()

    async def resume(self):
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            await self._broadcast_state()

    async def stop(self):
        self.queue.clear()
        self.current = None
        if self.voice_client:
            self.voice_client.stop()
        await self._broadcast_state()

    async def disconnect(self):
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
        await self._broadcast_state()

    # --- Core playback logic -------------------
    async def _play_next(self):
        """Called when a track ends or when something is first queued. Protected by a lock."""
        async with self._lock:
            # 1. Determine the next track
            last_track = self.current
            track = None

            # Handle Looping
            if self.loop_mode == "one" and last_track:
                track = last_track
            elif self.loop_mode == "queue" and last_track:
                self.queue.append(last_track)
                track = self.queue.popleft() if self.queue else None
            elif self.queue:
                track = self.queue.popleft()
            else:
                # Queue empty -> autoplay a meme
                try:
                    from audio.resolver import get_meme_track

                    track = await get_meme_track()
                except Exception as e:
                    print(f"Meme autoplay failed: {e}")
                    self.current = None
                    await self._broadcast_state()
                    return

            if not track or not self.voice_client:
                self.current = None
                await self._broadcast_state()
                return

            # STATE FIX: Ensure current is updated BEFORE we start potential sleeps
            self.current = track

            # Wait up to 5s for buffering to finish if it's currently downloading
            buffer_wait = 0
            while not track.local_path and buffer_wait < 5:
                await asyncio.sleep(1)
                buffer_wait += 1

            # Pre-download the NEXT track in the queue for seamless transition
            if self.queue:
                asyncio.create_task(self._buffer_track(self.queue[0]))

            # 2. Setup FFmpeg source
            # Ensure existing audio is stopped (redundant safety)
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()

            play_url = (
                track.local_path
                if (track.local_path and os.path.exists(track.local_path))
                else track.stream_url
            )

            # Build FFmpeg options dynamically
            # b_opts = ['-user_agent "piped bot"']

            # # If streaming from network OR playing a local .mpd (which fetches chunks from network)
            # if play_url.startswith("http") or play_url.endswith(".mpd"):
            #     b_opts.append("-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5")

            # # FIX: If playing an MPD, we MUST whitelist network protocols so it can fetch the segments!
            # if play_url.endswith(".mpd"):
            #     b_opts.append("-protocol_whitelist file,http,https,tcp,tls,crypto,data")

                        # Build FFmpeg options dynamically
            b_opts = []

            if play_url.startswith("http"):
                b_opts.append('-user_agent "piped bot"')
                b_opts.append("-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5")

            if play_url.endswith(".mpd"):
                b_opts.append("-protocol_whitelist file,http,https,tcp,tls,crypto,data")

            ffmpeg_opts = {
                "before_options": " ".join(b_opts),
                "options": "-vn",
            }

            try:
                source = discord.FFmpegPCMAudio(play_url, **ffmpeg_opts)
                source = discord.PCMVolumeTransformer(source, volume=self.volume)

                self.voice_client.play(
                    source,
                    after=lambda err: asyncio.run_coroutine_threadsafe(
                        self._on_track_end(err), self.bot.loop
                    ),
                )
            except Exception as e:
                print(f"Playback error: {e}")
                # Use call_soon to avoid recursion in the lock
                self.bot.loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._on_track_end(None))
                )

            await self._broadcast_state()

    async def _on_track_end(self, error):
        """Internal callback when a track finishes."""
        if error:
            print(f"Track error callback: {error}")

        # Cleanup the buffered file of the song that just finished to save space
        # Note: We check if it's not the same track being looped in 'one'
        if (
            self.current
            and self.current.local_path
            and os.path.exists(self.current.local_path)
        ):
            if self.loop_mode != "one":
                try:
                    # Small delay to ensure FFmpeg has closed the file handle
                    await asyncio.sleep(1)
                    os.remove(self.current.local_path)
                except:
                    pass

        # Small delay to ensure voice_client state updates and prevent busy-looping
        await asyncio.sleep(0.5)
        await self._play_next()

    # --- State / Websocket ---------------------
    def get_state(self) -> dict:
        is_playing = bool(self.voice_client and self.voice_client.is_playing())
        is_paused = bool(self.voice_client and self.voice_client.is_paused())
        return {
            "current": self.current.to_dict() if self.current else None,
            "queue": [t.to_dict() for t in self.queue],
            "is_playing": is_playing,
            "is_paused": is_paused,
            "loop_mode": self.loop_mode,
            "shuffle": self.shuffle,
            "volume": int(self.volume * 100),
        }

    async def _broadcast_state(self):
        try:
            from api.ws import manager

            await manager.broadcast(self.get_state())
        except:
            pass
