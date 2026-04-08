import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from audio.resolver import resolve

router = APIRouter()


# --- Request bodies ----------------------------
class PlayRequest(BaseModel):
    query: str
    requested_by: str = "web-user"


class VolumeRequest(BaseModel):
    volume: int  # 0 - 100


class LoopRequest(BaseModel):
    mode: str  # "off | "one" | "queue


class MemeRequest(BaseModel):
    url: str
    submitted_by: str = "web-user"


class MemeActionRequest(BaseModel):
    meme_id: str


# --- Playback routes ---------------------------
@router.post("/play")
async def play(req: PlayRequest, request: Request):
    player = request.app.state.player
    try:
        track = await resolve(req.query, req.requested_by)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    await player.add_to_queue(track)
    return {"status": "queued", "track": track.to_dict()}


@router.post("/skip")
async def skip(request: Request):
    await request.app.state.player.skip()
    return {"status": "ok"}


@router.post("/pause")
async def pause(request: Request):
    await request.app.state.player.pause()
    return {"status": "ok"}


@router.post("/resume")
async def resume(request: Request):
    await request.app.state.player.resume()
    return {"status": "ok"}


@router.post("/stop")
async def stop(request: Request):
    await request.app.state.player.stop()
    return {"status": "ok"}


@router.post("/volume")
async def volume(req: VolumeRequest, request: Request):
    request.app.state.player.set_volume(req.volume)
    return {"status": "ok", "volume": req.volume}


@router.post("/loop")
async def loop(req: LoopRequest, request: Request):
    try:
        request.app.state.player.set_loop(req.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "loop_mode": req.mode}


@router.post("/shuffle")
async def shuffle(request: Request):
    player = request.app.state.player
    player.shuffle = not player.shuffle
    if player.shuffle:
        player.shuffle_queue()
    return {"status": "ok", "shuffle": player.shuffle}


# ── State / queue routes ───────────────────────────────────────


@router.get("/state")
async def state(request: Request):
    return request.app.state.player.get_state()


@router.get("/queue")
async def queue(request: Request):
    return [t.to_dict() for t in request.app.state.player.get_queue()]


# ── Meme routes ────────────────────────────────────────────────


@router.get("/memes/pending")
async def memes_pending():
    with open("data/pending_memes.json") as f:
        return json.load(f)


@router.get("/memes/approved")
async def memes_approved():
    with open("data/meme_songs.json") as f:
        return json.load(f)
