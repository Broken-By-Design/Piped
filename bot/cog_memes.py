import json
import uuid

import discord
from discord.ext import commands

from audio.ytdlp import get_metadata

MEME_FILE = "data/meme_songs.json"
PENDING_FILE = "data/pending_memes.json"


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _save(path: str, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


class MemeCog(commands.Cog, name="Memes"):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name="meme", description="Meme song commands")
    async def meme(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.reply(
                "Use: `/meme suggest`, `/meme pending`, `/meme approve`, `/meme deny`"
            )

    @meme.command(name="suggest", description="Suggest a meme song for approval")
    async def suggest(self, ctx, url: str):
        await ctx.defer()

        # Validate the URL by fetching metadata
        try:
            meta = await get_metadata(url)
        except Exception:
            await ctx.reply(
                "❌ Couldn't fetch that URL. Make sure it's a valid YouTube link."
            )
            return

        data = _load(PENDING_FILE)
        entry = {
            "id": str(uuid.uuid4())[:8],
            "url": url,
            "title": meta["title"],
            "submitted_by": str(ctx.author),
        }
        data["pending"].append(entry)
        _save(PENDING_FILE, data)

        await ctx.reply(
            f"✅ **{meta['title']}** submitted for approval.\n"
            f"ID: `{entry['id']}` — an admin will review it."
        )

    @meme.command(name="pending", description="List pending meme submissions (admin)")
    @commands.has_permissions(manage_guild=True)
    async def pending(self, ctx):
        data = _load(PENDING_FILE)
        items = data["pending"]

        if not items:
            await ctx.reply("📭 No pending submissions.")
            return

        embed = discord.Embed(title="🎲 Pending Meme Submissions", color=0xBF00FF)
        for item in items[:10]:
            embed.add_field(
                name=f"`{item['id']}` — {item['title']}",
                value=f"By {item['submitted_by']}\n{item['url']}",
                inline=False,
            )
        await ctx.reply(embed=embed)

    @meme.command(name="approve", description="Approve a pending meme song (admin)")
    @commands.has_permissions(manage_guild=True)
    async def approve(self, ctx, meme_id: str):
        pending = _load(PENDING_FILE)
        approved = _load(MEME_FILE)

        match = next((x for x in pending["pending"] if x["id"] == meme_id), None)
        if not match:
            await ctx.reply(f"❌ No pending submission with ID `{meme_id}`.")
            return

        # Move from pending → approved
        pending["pending"].remove(match)
        approved["songs"].append(
            {
                "title": match["title"],
                "url": match["url"],
                "added_by": match["submitted_by"],
            }
        )
        _save(PENDING_FILE, pending)
        _save(MEME_FILE, approved)

        await ctx.reply(
            f"✅ **{match['title']}** approved and added to the meme rotation!"
        )

    @meme.command(name="deny", description="Deny a pending meme song (admin)")
    @commands.has_permissions(manage_guild=True)
    async def deny(self, ctx, meme_id: str):
        data = _load(PENDING_FILE)
        match = next((x for x in data["pending"] if x["id"] == meme_id), None)
        if not match:
            await ctx.reply(f"❌ No pending submission with ID `{meme_id}`.")
            return

        data["pending"].remove(match)
        _save(PENDING_FILE, data)
        await ctx.reply(f"🗑 **{match['title']}** denied and removed.")

    @meme.command(name="list", description="Show approved meme songs")
    async def list_memes(self, ctx):
        data = _load(MEME_FILE)
        songs = data["songs"]
        if not songs:
            await ctx.reply("📭 No approved meme songs yet.")
            return
        lines = [f"`{i + 1}.` {s['title']}" for i, s in enumerate(songs[:15])]
        embed = discord.Embed(
            title="🎲 Approved Meme Songs", description="\n".join(lines), color=0xBF00FF
        )
        await ctx.reply(embed=embed)
