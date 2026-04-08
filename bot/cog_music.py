import discord
from discord.ext import commands

from audio.resolver import resolve


class MusicCog(commands.Cog, name="Music"):
    def __init__(self, bot, player):
        self.bot = bot
        self.player = player  # same instance the web API uses

    # ── Helper ────────────────────────────────────────────────────

    async def _ensure_voice(self, ctx) -> bool:
        """Make sure bot is in the same voice channel as the user.
        Returns True if ready, False if we replied with an error."""
        if not ctx.author.voice:
            await ctx.reply("❌ You need to be in a voice channel first.")
            return False

        channel = ctx.author.voice.channel

        if not self.player.voice_client:
            # Not connected — join
            self.player.voice_client = await channel.connect()

        elif self.player.voice_client.channel != channel:
            # In a different channel — move
            await self.player.voice_client.move_to(channel)

        return True

    def _now_playing_embed(self, track) -> discord.Embed:
        """Build a nice embed for the current track."""
        source_emoji = "🌊" if track.source == "tidal" else "📺"
        source_label = "Tidal" if track.source == "tidal" else "YouTube"

        mins, secs = divmod(track.duration, 60)
        duration_str = f"{mins}:{secs:02d}"

        embed = discord.Embed(
            title=track.title,
            url=track.youtube_url or None,
            color=0xBF00FF,
        )
        embed.set_author(name="▶ Now Playing")
        embed.set_thumbnail(url=track.thumbnail)
        embed.add_field(name="Artist", value=track.artist, inline=True)
        embed.add_field(name="Duration", value=duration_str, inline=True)
        embed.add_field(
            name="Source", value=f"{source_emoji} {source_label}", inline=True
        )
        embed.set_footer(text=f"Requested by {track.requested_by}")
        return embed

    # ── Commands ─────────────────────────────────────────────────

    @commands.hybrid_command(name="play", description="Play a song (search or URL)")
    async def play(self, ctx, *, query: str):
        await ctx.defer()  # tell Discord we're working — gives us 15 mins

        if not await self._ensure_voice(ctx):
            return

        try:
            track = await resolve(query, requested_by=str(ctx.author))
        except Exception as e:
            await ctx.reply(f"❌ Could not find that track: {e}")
            return

        await self.player.add_to_queue(track)

        if self.player.current and self.player.current != track:
            # Track queued (something already playing)
            embed = discord.Embed(
                title=track.title,
                description=f"Added to queue — position #{len(self.player.queue)}",
                color=0x8B3FFF,
            )
            embed.set_thumbnail(url=track.thumbnail)
            await ctx.reply(embed=embed)
        else:
            await ctx.reply(embed=self._now_playing_embed(track))

    @commands.hybrid_command(name="skip", description="Skip the current track")
    async def skip(self, ctx):
        if not self.player.current:
            await ctx.reply("❌ Nothing is playing.")
            return
        skipped = self.player.current.title
        await self.player.skip()
        await ctx.reply(f"⏭ Skipped **{skipped}**")

    @commands.hybrid_command(name="pause", description="Pause playback")
    async def pause(self, ctx):
        await self.player.pause()
        await ctx.reply("⏸ Paused.")

    @commands.hybrid_command(name="resume", description="Resume playback")
    async def resume(self, ctx):
        await self.player.resume()
        await ctx.reply("▶ Resumed.")

    @commands.hybrid_command(name="stop", description="Stop and disconnect")
    async def stop(self, ctx):
        await self.player.stop()
        await ctx.reply("⏹ Stopped and disconnected.")

    @commands.hybrid_command(name="nowplaying", description="Show current track")
    async def nowplaying(self, ctx):
        if not self.player.current:
            await ctx.reply("❌ Nothing is playing right now.")
            return
        await ctx.reply(embed=self._now_playing_embed(self.player.current))

    @commands.hybrid_command(name="queue", description="Show the upcoming queue")
    async def queue(self, ctx):
        q = self.player.get_queue()
        if not q and not self.player.current:
            await ctx.reply("📭 Queue is empty.")
            return

        embed = discord.Embed(title="📋 Queue", color=0xBF00FF)

        if self.player.current:
            embed.add_field(
                name="▶ Now Playing",
                value=f"`{self.player.current.title}`",
                inline=False,
            )

        if q:
            lines = [f"`{i + 1}.` {t.title}" for i, t in enumerate(q[:10])]
            embed.add_field(name="Up Next", value="\n".join(lines), inline=False)
            if len(q) > 10:
                embed.set_footer(text=f"...and {len(q) - 10} more")

        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="shuffle", description="Toggle shuffle mode")
    async def shuffle(self, ctx):
        self.player.shuffle = not self.player.shuffle
        if self.player.shuffle:
            self.player.shuffle_queue()
        state = "on 🔀" if self.player.shuffle else "off"
        await ctx.reply(f"Shuffle is now {state}")

    @commands.hybrid_command(
        name="loop", description="Set loop mode: off / one / queue"
    )
    async def loop(self, ctx, mode: str = "off"):
        mode = mode.lower()
        try:
            self.player.set_loop(mode)
            icons = {"off": "➡️", "one": "🔂", "queue": "🔁"}
            await ctx.reply(f"Loop set to {icons[mode]} **{mode}**")
        except ValueError:
            await ctx.reply("❌ Valid modes: `off`, `one`, `queue`")

    @commands.hybrid_command(name="volume", description="Set volume 0–100")
    async def volume(self, ctx, vol: int):
        self.player.set_volume(vol)
        await ctx.reply(f"🔊 Volume set to {max(0, min(100, vol))}%")
