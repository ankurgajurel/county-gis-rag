"""FastAPI server for the chat interface."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

from src.chat.engine import ChatEngine
from src.db.engine import async_session, engine
from src.db.models import ChatSession, ChatMessage
from src.utils.logging import setup_logging

logger = logging.getLogger(__name__)

sessions: dict[str, ChatEngine] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield
    sessions.clear()
    await engine.dispose()


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
    user_email: str | None = None


async def _restore_engine(session_id: str) -> ChatEngine | None:
    """Restore a ChatEngine from DB if the session exists."""
    async with async_session() as db:
        result = await db.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id)
        )
        chat_session = result.scalar_one_or_none()
        if not chat_session:
            return None

        engine = ChatEngine()
        await engine.initialize()
        engine.last_response_id = chat_session.last_response_id

        for msg in chat_session.messages:
            engine.conversation_input.append({"role": msg.role, "content": msg.content})

        return engine


def _fallback_title(user_message: str) -> str:
    """Quick title from the user message."""
    title = user_message[:50].strip()
    if len(user_message) > 50:
        title = title.rsplit(" ", 1)[0] + "..."
    return title


async def _generate_title_bg(session_id: str, user_message: str):
    """Generate a better title in the background and update DB."""
    try:
        from openai import AsyncOpenAI
        from src.config import settings

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Generate a concise title (max 6 words) for this chat. No quotes, no punctuation at the end."},
                {"role": "user", "content": user_message},
            ],
            max_tokens=20,
        )
        title = (resp.choices[0].message.content or "").strip()
        if title:
            async with async_session() as db:
                await db.execute(
                    update(ChatSession).where(ChatSession.id == session_id).values(title=title)
                )
                await db.commit()
    except Exception as e:
        logger.warning("Failed to generate title for %s: %s", session_id, e)


@app.post("/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid4())
    is_new_session = session_id not in sessions and req.session_id is None

    if session_id not in sessions:
        # Try restoring from DB
        engine = await _restore_engine(session_id)
        if engine is None:
            engine = ChatEngine()
            await engine.initialize()
        sessions[session_id] = engine

    engine = sessions[session_id]

    async def event_stream():
        yield f"data: {json.dumps({'session_id': session_id})}\n\n"

        full_text = ""
        reasoning_blocks = []
        last_geojson = None

        try:
            async for event in engine.chat_stream(req.message):
                if event["type"] == "reasoning_delta":
                    yield f"data: {json.dumps({'reasoning_delta': event['content']})}\n\n"
                elif event["type"] == "reasoning_done":
                    reasoning_blocks = event["blocks"]
                    yield f"data: {json.dumps({'reasoning_done': {'blocks': event['blocks']}})}\n\n"
                elif event["type"] == "token":
                    full_text += event["content"]
                    yield f"data: {json.dumps({'token': event['content']})}\n\n"
                elif event["type"] == "tool_status":
                    yield f"data: {json.dumps({'tool_status': {'tools': event['tools']}})}\n\n"
                elif event["type"] == "tool_status_end":
                    yield f"data: {json.dumps({'tool_status_end': True})}\n\n"
                elif event["type"] == "map_data":
                    last_geojson = event["geojson"]
                    yield f"data: {json.dumps({'map_data': event['geojson']})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        # Persist to DB before signaling done
        try:
            async with async_session() as db:
                if is_new_session:
                    db.add(ChatSession(
                        id=session_id,
                        user_email=req.user_email or "anonymous",
                        title=_fallback_title(req.message),
                    ))
                    await db.flush()

                db.add(ChatMessage(session_id=session_id, role="user", content=req.message))
                if full_text:
                    db.add(ChatMessage(
                        session_id=session_id,
                        role="assistant",
                        content=full_text,
                        reasoning=reasoning_blocks if reasoning_blocks else None,
                    ))

                update_values = {"last_response_id": engine.last_response_id}
                if last_geojson:
                    update_values["map_geojson"] = last_geojson

                await db.execute(
                    update(ChatSession)
                    .where(ChatSession.id == session_id)
                    .values(**update_values)
                )
                await db.commit()

            if is_new_session:
                asyncio.create_task(_generate_title_bg(session_id, req.message))
        except Exception as e:
            logger.error("Failed to persist chat: %s", e)

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/chat/reset")
async def reset_chat(req: ChatRequest):
    if req.session_id and req.session_id in sessions:
        del sessions[req.session_id]
    return {"status": "ok"}


@app.get("/chat/history")
async def get_chat_history(user_email: str):
    async with async_session() as db:
        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.user_email == user_email)
            .order_by(ChatSession.updated_at.desc())
            .limit(50)
        )
        chat_sessions = result.scalars().all()

    return [
        {
            "id": s.id,
            "title": s.title,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in chat_sessions
    ]


@app.get("/chat/history/{session_id}")
async def get_chat_session(session_id: str):
    async with async_session() as db:
        result = await db.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id)
        )
        chat_session = result.scalar_one_or_none()

    if not chat_session:
        return {"error": "Session not found"}, 404

    return {
        "session": {
            "id": chat_session.id,
            "title": chat_session.title,
            "map_geojson": chat_session.map_geojson,
        },
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "reasoning": m.reasoning,
            }
            for m in chat_session.messages
        ],
    }


@app.delete("/chat/history/{session_id}")
async def delete_chat_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]

    async with async_session() as db:
        await db.execute(
            delete(ChatSession).where(ChatSession.id == session_id)
        )
        await db.commit()

    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}
