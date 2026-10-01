"""Pydantic schema for the Gemini AI financial-assistant endpoint (Phase 4.1)."""
from pydantic import BaseModel


class AISummaryResponse(BaseModel):
    success: bool
    model: str | None
    summary: str | None
    error: str | None
    based_on: dict
