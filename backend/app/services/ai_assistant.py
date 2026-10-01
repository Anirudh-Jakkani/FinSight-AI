"""AI financial assistant (Phase 4.1). Turns already-verified FinSight analytics into
a natural-language summary — per docs/architecture.md's rule ("numbers are computed
in Python/SQL; the LLM only explains verified results"), the model is only ever shown
numbers this app already computed and is told not to invent or alter any.

Routes through OpenRouter (openrouter.ai) rather than calling a model provider's API
directly: OpenRouter exposes one OpenAI-compatible chat-completions endpoint in front
of many providers/models, which sidesteps the model-retirement and free-tier-quota
issues hit when calling Google's Gemini API directly.

Reads OPENROUTER_API_KEY / OPENROUTER_MODEL from app.config.settings (.env.example).
Calls the REST API directly via httpx (already a project dependency), no new SDK.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.services import analytics as analytics_service
from app.services.anomaly import detect_anomalies
from app.services.forecast import forecast_expenses
from app.services.recurring import list_recurring_payments

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_OUTPUT_TOKENS = 1024

logger = logging.getLogger(__name__)


class AIAssistantError(Exception):
    """Any problem calling the AI provider: missing key, network failure, bad status,
    or an unexpected response shape. Message is safe to surface to an API caller —
    no secrets, no raw exception internals."""


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _gather_analytics(db: Session, *, user_id: int) -> dict:
    summary = analytics_service.get_summary(db, user_id=user_id)
    categories = analytics_service.get_spending_by_category(db, user_id=user_id)
    monthly = analytics_service.get_monthly_trends(db, user_id=user_id)
    top_merchants = analytics_service.get_top_merchants(db, user_id=user_id, limit=5)
    recurring = list_recurring_payments(db, user_id=user_id)
    anomalies = detect_anomalies(db, user_id=user_id)
    forecast = forecast_expenses(db, user_id=user_id, periods_ahead=1)

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
    }


def _build_prompt(analytics: dict) -> str:
    data_json = json.dumps(analytics, indent=2, default=_json_default)
    return (
        "You are a personal-finance assistant for the FinSight app. All numbers below "
        "were already computed and verified by the application's own analytics code — "
        "treat them as ground truth. Do not invent, recompute, or alter any figures.\n\n"
        "Using ONLY this data, write:\n"
        "1. A concise financial summary (3-5 sentences).\n"
        "2. A short bulleted list (3-5 bullets) of practical, specific insights or "
        "observations (spending trends, recurring bills, anomalies, or the forecast).\n\n"
        "This is educational information only, not financial advice — do not claim to "
        "be a licensed financial advisor.\n\n"
        f"Verified data (JSON):\n{data_json}"
    )


def _call_ai(prompt: str) -> str:
    if not settings.openrouter_api_key:
        raise AIAssistantError(
            "OpenRouter API key is not configured (set OPENROUTER_API_KEY in .env)."
        )

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.openrouter_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": MAX_OUTPUT_TOKENS,
        # This model spends part of max_tokens on a hidden reasoning trace before the
        # visible answer (observed consuming the entire budget on the real prompt,
        # truncating the summary with finish_reason="length"). Restating
        # already-computed numbers needs no chain-of-thought, so disable it.
        "reasoning": {"exclude": True, "enabled": False},
    }

    try:
        response = httpx.post(
            OPENROUTER_API_URL, headers=headers, json=body, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except httpx.TimeoutException as exc:
        raise AIAssistantError("Timed out waiting for the AI provider.") from exc
    except httpx.RequestError as exc:
        raise AIAssistantError("Could not reach the AI provider (network error).") from exc

    if response.status_code != 200:
        raise AIAssistantError(f"AI provider returned an error (HTTP {response.status_code}).")

    try:
        payload = response.json()
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        raise AIAssistantError("AI provider returned an unexpected response format.") from exc

    if not text or not text.strip():
        raise AIAssistantError("AI provider returned an empty response.")
    return text.strip()


@dataclass
class AISummaryResult:
    success: bool
    model: str | None
    summary: str | None
    error: str | None
    based_on: dict


def generate_financial_summary(db: Session, *, user_id: int) -> AISummaryResult:
    analytics = _gather_analytics(db, user_id=user_id)

    if analytics["summary"]["transaction_count"] == 0:
        return AISummaryResult(
            success=True,
            model=None,
            summary="No transactions found for this user yet — nothing to summarize.",
            error=None,
            based_on=analytics,
        )

    prompt = _build_prompt(analytics)
    try:
        text = _call_ai(prompt)
    except AIAssistantError as exc:
        # This session hit OpenRouter's free-tier limits repeatedly during
        # development — previously that was invisible; now it's a log line.
        logger.warning("AI summary failed for user_id=%s: %s", user_id, exc)
        return AISummaryResult(success=False, model=None, summary=None, error=str(exc), based_on=analytics)

    return AISummaryResult(
        success=True, model=settings.openrouter_model, summary=text, error=None, based_on=analytics
    )
