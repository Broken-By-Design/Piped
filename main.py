import asyncio

import discord
import uvicorn
from discord.ext import commands

import config
from api.app import create_app
from bot.cog_memes import MemeCog
from bot.cog_music import MusicCog
from bot.player import MusicPlayer


async def main():
    # Validation check
    if not config.DISCORD_TOKEN:
        print(" X ERROR: DISCORD_TOKEN is missing from the .env FILE!")
        return
    # 1. Set up discord bot with required intents
    intents = discord.Intents.default()
    intents.message_content = True  # Needed for !prefix commands
    intents.members = True  # Needed for role chacks

    bot = commands.Bot(
        command_prefix=config.BOT_PREFIX,
        intents=intents,
    )

    # 2. Create the shared player - passed to both cogs and the web API
    player = MusicPlayer(bot)

    # 4. Sync slash commands once the bot is logged in
    async def setup_hook():
        await bot.add_cog(MusicCog(bot, player))
        await bot.add_cog(MemeCog(bot))
        guild = discord.Object(id=config.TEST_GUILD_ID)

        # Add these two debug lines
        print(f"Cogs loaded: {[c for c in bot.cogs]}")
        print(f"Commands in tree: {[c.name for c in bot.tree.get_commands()]}")

        synced = await bot.tree.sync(guild=guild)
        print(
            f"⚡ Synced {len(synced)} slash command(s) to guild {config.TEST_GUILD_ID}"
        )

    bot.setup_hook = setup_hook

    @bot.event
    async def on_ready():
        if bot.user:
            print(f"✅ Logged in as {bot.user} ({bot.user.id})")
        print(f"🌐 Web GUI running at http://{config.WEB_HOST}:{config.WEB_PORT}")

    # 5. Create the FastAPI web server with the player attached
    app = create_app(player)
    uv_config = uvicorn.Config(
        app,
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        log_level="warning",  # Reduces noise, keep Discord Logs visable
    )
    server = uvicorn.Server(uv_config)

    # 6. Run the Discord bot and web server concurrently
    await asyncio.gather(
        bot.start(config.DISCORD_TOKEN),
        server.serve(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Piped stopped.")
