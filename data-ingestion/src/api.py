"""FastAPI server for the chat interface."""

import json
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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


@app.post("/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid4())

    if session_id not in sessions:
        engine = ChatEngine()
        await engine.initialize()
        sessions[session_id] = engine

    engine = sessions[session_id]

    async def event_stream():
        yield f"data: {json.dumps({'session_id': session_id})}\n\n"
        try:
            async for event in engine.chat_stream(req.message):
                if event["type"] == "reasoning_delta":
                    yield f"data: {json.dumps({'reasoning_delta': event['content']})}\n\n"
                elif event["type"] == "reasoning_done":
                    yield f"data: {json.dumps({'reasoning_done': {'blocks': event['blocks']}})}\n\n"
                elif event["type"] == "token":
                    yield f"data: {json.dumps({'token': event['content']})}\n\n"
                elif event["type"] == "tool_status":
                    yield f"data: {json.dumps({'tool_status': {'tools': event['tools']}})}\n\n"
                elif event["type"] == "tool_status_end":
                    yield f"data: {json.dumps({'tool_status_end': True})}\n\n"
                elif event["type"] == "map_data":
                    yield f"data: {json.dumps({'map_data': event['geojson']})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/chat/reset")
async def reset_chat(req: ChatRequest):
    if req.session_id and req.session_id in sessions:
        del sessions[req.session_id]
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}
