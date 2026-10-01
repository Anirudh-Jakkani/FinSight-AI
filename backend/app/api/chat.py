"""FinSight AI chat endpoints (Phase 4.2). Business logic lives in
app/services/chat.py; this stays thin. Phase 7.3: user_id is derived from the
verified JWT, not a client-supplied parameter — including for the conversation
ownership check below, which now can't be spoofed by passing another user's id.

Phase 8.5: /chat is rate-limited per authenticated user (see app/rate_limit.py) —
it calls the same paid/quota-limited AI provider as /ai/summary. The message-
history read below isn't limited; it's a cheap local DB query with no external
cost."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.ai_conversation import AIConversation
from app.models.ai_message import AIMessage
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.chat import (
    ChatMessageOut,
    ChatRequest,
    ChatResponse,
    ConversationMessagesResponse,
)
from app.services.auth import get_current_user
from app.services.chat import ask

router = APIRouter(prefix="/api/v1/ai", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("15/minute")
def chat_endpoint(
    request: Request,
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    result = ask(
        db,
        user_id=current_user.id,
        conversation_id=payload.conversation_id,
        question=payload.question,
    )
    return ChatResponse(
        success=result.success,
        conversation_id=result.conversation_id,
        reply=result.reply,
        error=result.error,
    )


@router.get("/chat/{conversation_id}/messages", response_model=ConversationMessagesResponse)
def get_conversation_messages_endpoint(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationMessagesResponse:
    conversation = db.execute(
        select(AIConversation).where(
            AIConversation.id == conversation_id, AIConversation.user_id == current_user.id
        )
    ).scalar_one_or_none()
    if conversation is None:
        return ConversationMessagesResponse(conversation_id=conversation_id, messages=[])

    messages = db.execute(
        select(AIMessage).where(AIMessage.conversation_id == conversation_id).order_by(AIMessage.id)
    ).scalars()
    return ConversationMessagesResponse(
        conversation_id=conversation_id,
        messages=[
            ChatMessageOut(id=m.id, role=m.role.value, content=m.content, created_at=m.created_at)
            for m in messages
        ],
    )
