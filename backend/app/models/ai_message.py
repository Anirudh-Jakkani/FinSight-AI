"""AIMessage model + MessageRole enum (Phase 4.2). See docs/database-schema.md.

Enum column uses values_callable so Postgres stores the lowercase .value ("user",
"assistant") rather than SQLAlchemy's default of the member .name — the same fix
applied to CategorySource in Phase 2.3 after finding the default behavior stores
member names, not values.
"""
from datetime import datetime
from typing import Any
import enum

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(
            MessageRole,
            native_enum=False,
            validate_strings=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # The verified data bundle the assistant was shown when producing this message —
    # an audit trail proving it only had access to retrieved, real data.
    context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped["AIConversation"] = relationship(back_populates="messages")
