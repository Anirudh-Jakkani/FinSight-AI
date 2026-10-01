"""Category model: the known/curated category taxonomy.

Note: transactions.category (docs/database-schema.md) is a denormalized string label,
not a foreign key here — transactions may be labeled by rules/ML before a category is
formally known, so it is intentionally not constrained to this table in Phase 2.1."""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
