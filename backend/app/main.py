"""FastAPI app: serves the frontend and the agent websocket."""
import json
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from . import db, limits
from .agent import make_client, run_turn

load_dotenv()

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    app.state.llm = make_client()
    yield
    await db.disconnect()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/healthz")
async def healthz() -> dict:
    """Liveness for the Fly health check: the DB must actually answer."""
    async with db.pool().acquire() as conn:
        await conn.fetchval("SELECT 1")
    return {"ok": True, **limits.stats()}


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    await socket.accept()
    messages: list[dict] = []  # conversation history for this connection
    ip = limits.client_ip(socket)

    async def send(payload: dict) -> None:
        await socket.send_text(json.dumps(payload))

    async def refuse(text: str) -> None:
        await send({"type": "error", "text": text})
        await send({"type": "done"})

    try:
        while True:
            raw = await socket.receive_text()
            data = json.loads(raw)
            if data.get("type") != "user_message":
                continue
            text = data.get("text", "").strip()
            if not text:
                continue
            if len(text) > limits.MAX_MESSAGE_CHARS:
                await refuse(f"That message is too long — keep it under "
                             f"{limits.MAX_MESSAGE_CHARS} characters.")
                continue
            # Public demo: bound per-IP burst and total daily spend on the LLM key.
            if denied := limits.check(ip):
                await refuse(denied)
                continue
            try:
                await run_turn(app.state.llm, messages, text, send, db.pool())
            except Exception as exc:
                await send({"type": "error", "text": f"Agent error: {exc}"})
                await send({"type": "done"})
    except WebSocketDisconnect:
        pass
