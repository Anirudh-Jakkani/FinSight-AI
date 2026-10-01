"""FinSight AI financial chat (Phase 4.2). Lets a user ask free-form questions about
their own financial data. Every answer is grounded in data retrieved from PostgreSQL
via this app's own verified analytics/transaction services (Phases 2-3) — the model
is instructed to use ONLY that retrieved data and never invent figures. Conversation
and message history is persisted in ai_conversations / ai_messages
(docs/database-schema.md).

The AI-provider call, JSON-default helper, and context-gathering mirror
app/services/ai_assistant.py (duplicated, not imported, to keep that completed
phase's module untouched — the same pattern used across Phases 3.1/3.2/3.3).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.ai_conversation import AIConversation
from app.models.ai_message import AIMessage, MessageRole
from app.services import analytics as analytics_service
from app.services.anomaly import detect_anomalies
from app.services.forecast import forecast_expenses
from app.services.recurring import list_recurring_payments
from app.services.transaction_query import list_transactions

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_OUTPUT_TOKENS = 1024
MAX_CONTEXT_TRANSACTIONS = 200  # dataset is small (90 rows); comfortably covers it

logger = logging.getLogger(__name__)


class ChatError(Exception):
    """Any problem serving a chat turn: unknown/wrong-owner conversation, missing AI
    key, network failure, bad status, or an unexpected response shape. Message is
    safe to surface to an API caller — no secrets, no raw exception internals."""


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _json_safe(data: dict) -> dict:
    """Round-trips through json.dumps/loads with _json_default so the result contains
    only JSON-native types — needed before storing in a JSON column, since Decimal
    isn't serializable by the driver's default JSON encoder."""
    return json.loads(json.dumps(data, default=_json_default))


def _gather_context_data(db: Session, *, user_id: int) -> dict:
    summary = analytics_service.get_summary(db, user_id=user_id)
    categories = analytics_service.get_spending_by_category(db, user_id=user_id)
    monthly = analytics_service.get_monthly_trends(db, user_id=user_id)
    top_merchants = analytics_service.get_top_merchants(db, user_id=user_id, limit=10)
    recurring = list_recurring_payments(db, user_id=user_id)
    anomalies = detect_anomalies(db, user_id=user_id)
    forecast = forecast_expenses(db, user_id=user_id, periods_ahead=1)
    transactions, _total = list_transactions(db, user_id=user_id, limit=MAX_CONTEXT_TRANSACTIONS)

    return {
        "summary": summary.__dict__,
        "spending_by_category": [c.__dict__ for c in categories],
        "monthly_trends": [m.__dict__ for m in monthly],
        "top_merchants": [t.__dict__ for t in top_merchants],
        "recurring_payments": [
            {"merchant": r.merchant, "avg_amount": r.avg_amount, "interval_days": r.interval_days}
            for r in recurring
        ],
        "anomalies": [
            {
                "description": a.description_raw,
                "category": a.category,
                "amount": a.amount,
                "z_score": a.z_score,
            }
            for a in anomalies
        ],
        "forecast": {
            "method": forecast.method,
            "explanation": forecast.explanation,
            "next_period": [
                {"period": p.period, "predicted_expenses": p.predicted_expenses}
                for p in forecast.forecast
            ],
        },
        "transactions": [
            {
                "date": t.transaction_date,
                "description": t.description_clean or t.description_raw,
                "amount": t.amount,
                "type": t.transaction_type.value,
                "category": t.category,
            }
            for t in transactions
        ],
    }


def _system_prompt(context_data: dict) -> str:
    data_json = json.dumps(context_data, indent=2, default=_json_default)
    return (
        "You are FinSight's financial assistant. The user will ask questions about "
        "their own personal finances. Every figure below was retrieved directly from "
        "the app's own database and verified analytics code — it is the ONLY source "
        "of financial facts you may use. Never invent, estimate, guess, or alter a "
        "number that isn't present in this data. If the data doesn't answer the "
        "question, say so plainly instead of guessing. Keep answers concise and "
        "specific. This is educational information only, not financial advice.\n\n"
        f"Verified data (JSON):\n{data_json}"
    )


def _call_ai(messages: list[dict]) -> str:
    if not settings.openrouter_api_key:
        raise ChatError("OpenRouter API key is not configured (set OPENROUTER_API_KEY in .env).")

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.openrouter_model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": MAX_OUTPUT_TOKENS,
        # See app/services/ai_assistant.py's _call_ai for why: this model spends part
        # of max_tokens on a hidden reasoning trace unless explicitly disabled.
        "reasoning": {"exclude": True, "enabled": False},
    }

    try:
        response = httpx.post(
            OPENROUTER_API_URL, headers=headers, json=body, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except httpx.TimeoutException as exc:
        raise ChatError("Timed out waiting for the AI provider.") from exc
    except httpx.RequestError as exc:
        raise ChatError("Could not reach the AI provider (network error).") from exc

    if response.status_code != 200:
        raise ChatError(f"AI provider returned an error (HTTP {response.status_code}).")

    try:
        payload = response.json()
    except ValueError as exc:
        raise ChatError("AI provider returned an unexpected response format.") from exc

    # OpenRouter sometimes reports an upstream failure — e.g. the free-tier
    # provider this app uses being temporarily overloaded — as an "error"
    # object inside an HTTP 200 body instead of a non-200 status (confirmed
    # directly against this model/provider). Left unhandled, the next block's
    # KeyError on the missing "choices" key surfaced as the misleading
    # "unexpected response format", hiding what was actually a transient,
    # retry-able upstream problem.
    error = payload.get("error")
    if error:
        message = error.get("message", "unknown error") if isinstance(error, dict) else str(error)
        raise ChatError(f"AI provider error: {message}")

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ChatError("AI provider returned an unexpected response format.") from exc

    # Some models/providers OpenRouter proxies return content as a list of
    # parts (e.g. [{"type": "text", "text": "..."}]) rather than a plain
    # string — support both shapes rather than assuming only the one this
    # app has observed so far.
    if isinstance(content, list):
        text = "".join(
            part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"
        )
    else:
        text = content

    if not text or not text.strip():
        raise ChatError("AI provider returned an empty response.")
    return text.strip()


def _get_or_create_conversation(
    db: Session, *, user_id: int, conversation_id: int | None
) -> AIConversation:
    if conversation_id is not None:
        conversation = db.execute(
            select(AIConversation).where(
                AIConversation.id == conversation_id, AIConversation.user_id == user_id
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise ChatError(f"conversation {conversation_id} not found for this user")
        return conversation

    conversation = AIConversation(user_id=user_id)
    db.add(conversation)
    db.flush()
    return conversation


@dataclass
class ChatResult:
    success: bool
    conversation_id: int | None
    reply: str | None
    error: str | None


def ask(db: Session, *, user_id: int, conversation_id: int | None, question: str) -> ChatResult:
    question = question.strip()
    if not question:
        return ChatResult(
            success=False, conversation_id=conversation_id, reply=None, error="question must not be empty"
        )

    try:
        conversation = _get_or_create_conversation(db, user_id=user_id, conversation_id=conversation_id)
    except ChatError as exc:
        return ChatResult(success=False, conversation_id=conversation_id, reply=None, error=str(exc))

    history = list(
        db.execute(
            select(AIMessage).where(AIMessage.conversation_id == conversation.id).order_by(AIMessage.id)
        ).scalars()
    )

    context_data = _gather_context_data(db, user_id=user_id)
    messages = [{"role": "system", "content": _system_prompt(context_data)}]
    messages.extend({"role": m.role.value, "content": m.content} for m in history)
    messages.append({"role": "user", "content": question})

    user_message = AIMessage(conversation_id=conversation.id, role=MessageRole.USER, content=question)
    db.add(user_message)
    db.commit()  # the question is recorded even if the AI call below fails

    try:
        reply_text = _call_ai(messages)
    except ChatError as exc:
        logger.warning("chat failed for user_id=%s conversation_id=%s: %s", user_id, conversation.id, exc)
        return ChatResult(success=False, conversation_id=conversation.id, reply=None, error=str(exc))

    assistant_message = AIMessage(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=reply_text,
        context_json=_json_safe(context_data),
    )
    db.add(assistant_message)
    db.commit()

    return ChatResult(success=True, conversation_id=conversation.id, reply=reply_text, error=None)
