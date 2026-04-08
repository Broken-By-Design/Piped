import os

from dotenv import load_dotenv

load_dotenv()  # Reads .env into environmental vars

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TEST_GUILD_ID = int(os.getenv("TEST_GUILD_ID", "0"))
TIDAL_PROXY_URL = os.getenv("TIDAL_PROXY_URL")
BOT_PREFIX = os.getenv("BOT_PREFIX", "!")
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8000"))

# Meme search tearms
MEME_SEARCH_TERMS = [
    t.strip()
    for t in os.getenv("MEME_SEARCH_TERMS", "never gonna give you up").split(",")
]
