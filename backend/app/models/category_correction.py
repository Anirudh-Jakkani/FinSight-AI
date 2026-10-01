"""CategoryCorrection model (Phase 4.3). See docs/database-schema.md: "stored for
future training; no live retraining is claimed" — this table only records
corrections; no ML retraining is implemented by this phase."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class CategoryCorrection(Base):
    __tablename__ = "category_corrections"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    old_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_category: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
