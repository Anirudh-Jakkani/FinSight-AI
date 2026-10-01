"""FinancialSnapshot model (Phase 3.2). See docs/database-schema.md: period 'YYYY-MM',
UNIQUE(user_id, period) — both already documented there (not an addition this phase)."""
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class FinancialSnapshot(Base):
    __tablename__ = "financial_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "period", name="uq_financial_snapshots_user_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # 'YYYY-MM'
    income: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    expenses: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    savings: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    savings_rate: Mapped[float | None] = mapped_column(nullable=True)
