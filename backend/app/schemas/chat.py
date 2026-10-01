"""Pydantic schemas for the FinSight AI chat endpoints (Phase 4.2)."""
from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    # Phase 7.3: user_id removed — the acting user is derived from the verified
    # JWT (see app/api/chat.py), never from a client-supplied value.
    conversation_id: int | None = None
    question: str


class ChatResponse(BaseModel):
    success: bool
    conversation_id: int | None
    reply: str | None
    error: str | None


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class ConversationMessagesResponse(BaseModel):
    conversation_id: int
    messages: list[ChatMessageOut]
