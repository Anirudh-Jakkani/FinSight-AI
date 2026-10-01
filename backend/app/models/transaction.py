"""Transaction model. See docs/database-schema.md for the source-of-truth schema."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Boolean,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import CategorySource, TransactionType


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_hash", name="uq_transactions_user_dedupe_hash"),
        CheckConstraint("amount >= 0", name="ck_transactions_amount_positive"),
        Index("ix_transactions_user_id", "user_id"),
        Index("ix_transactions_transaction_date", "transaction_date"),
        Index("ix_transactions_category", "category"),
        Index("ix_transactions_merchant", "merchant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Never modified after ingestion — audit requirement (docs/database-schema.md).
    description_raw: Mapped[str] = mapped_column(Text, nullable=False)
    description_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(
            TransactionType,
            native_enum=False,
            validate_strings=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )

    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category_confidence: Mapped[float | None] = mapped_column(nullable=True)
    category_source: Mapped[CategorySource | None] = mapped_column(
        Enum(
            CategorySource,
            native_enum=False,
            validate_strings=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=True,
    )
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dedupe_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="transactions")
    account: Mapped["Account"] = relationship(back_populates="transactions")
