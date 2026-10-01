"""Pydantic schemas for user authentication (Phase 7.1)."""
import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Phase 8.2: tightened after a security audit found the previous pattern
# (`^[^@\s]+@[^@\s]+\.[^@\s]+$`) accepted values like `<script>x</script>@a.com` —
# not itself exploitable since the frontend now escapes all rendered user data,
# but there's no reason to let something that isn't a plausible email address
# into the database at all. This still isn't full RFC 5322 (no practical regex
# is), but it restricts the local part and domain to characters real mail
# systems use, which excludes HTML-special characters as a side effect.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    currency: str = Field(default="INR", min_length=3, max_length=3)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError("invalid email format")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    account_id: int | None = None
    email: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime
