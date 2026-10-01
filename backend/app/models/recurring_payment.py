"""RecurringPayment model (Phase 3.1). See docs/database-schema.md.

UniqueConstraint(user_id, merchant) isn't in the original schema doc's bullet list but
is added here deliberately: detection is re-run over time, and this makes storing
results an idempotent upsert per merchant rather than accumulating duplicate rows.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class RecurringPayment(Base):
    __tablename__ = "recurring_payments"
    __table_args__ = (
        UniqueConstraint("user_id", "merchant", name="uq_recurring_payments_user_merchant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    merchant: Mapped[str] = mapped_column(String(255), nullable=False)
    avg_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    interval_days: Mapped[int] = mapped_column(nullable=False)
    last_seen: Mapped[date] = mapped_column(Date, nullable=False)
