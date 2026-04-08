from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.routes import router
from api.ws import ws_router


def create_app(player) -> FastAPI:
    """Create and configure the FastAPI app.
    player is the shared MusicPlayer instance."""
    app = FastAPI(title="Piped", version="1.0")

    # Attach the player so routes can access it via request.app.state.player
    app.state.player = player

    # REST API routes (e.g. POST /api/play)
    app.include_router(router, prefix="/api")

    # WebSocket route (ws://host/ws)
    app.include_router(ws_router)

    # Serve the web frontend (index.html, style.css, app.js) from web/
    app.mount("/", StaticFiles(directory="web", html=True), name="static")

    return app
