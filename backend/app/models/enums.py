"""Shared enums for ORM models. Stored as VARCHAR + CHECK constraint (native_enum=False)
so the constraint matches docs/database-schema.md literally and stays portable."""
import enum


class TransactionType(str, enum.Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class CategorySource(str, enum.Enum):
    RULE = "rule"
    ML = "ml"
    USER = "user"
