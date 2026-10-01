"""Importing this package registers every ORM model on Base.metadata, so Alembic's
autogenerate (see app/db/migrations/env.py) can diff the real database against it."""
from app.models.account import Account
from app.models.ai_conversation import AIConversation
from app.models.ai_message import AIMessage, MessageRole
from app.models.category import Category
from app.models.category_correction import CategoryCorrection
from app.models.enums import CategorySource, TransactionType
from app.models.financial_snapshot import FinancialSnapshot
from app.models.recurring_payment import RecurringPayment
from app.models.transaction import Transaction
from app.models.user import User

__all__ = [
    "User",
    "Account",
    "Category",
    "Transaction",
    "RecurringPayment",
    "FinancialSnapshot",
    "AIConversation",
    "AIMessage",
    "CategoryCorrection",
    "TransactionType",
    "CategorySource",
    "MessageRole",
]
