"""FastAPI server for the chat interface."""

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.chat.engine import ChatEngine
from src.utils.logging import setup_logging


sessions: dict[str, ChatEngine] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield
    sessions.clear()


app = FastAPI(title="County GIS Chat", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid4())

    if session_id not in sessions:
        engine = ChatEngine()
        await engine.initialize()
        sessions[session_id] = engine

    engine = sessions[session_id]
    response = await engine.chat(req.message)

    return ChatResponse(response=response, session_id=session_id)


@app.post("/chat/reset")
async def reset_chat(req: ChatRequest):
    if req.session_id and req.session_id in sessions:
        del sessions[req.session_id]
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}
