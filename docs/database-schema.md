# Database schema (design; SQLAlchemy models arrive in Phase 2)

Schema changes are applied via Alembic migrations (`backend/app/db/migrations/`,
Phase 8.7) — run `alembic upgrade head` from `backend/` to create or update the
schema. `backend/app/models/` is still the source of truth for what the schema
*should* look like; a migration is how that gets applied to an actual database.
New schema changes: edit the models, then `alembic revision --autogenerate -m "..."`
and review the generated migration before committing it.

- **users**(id PK, email UNIQUE, created_at)
- **accounts**(id PK, user_id FK, name, currency, created_at)
- **categories**(id PK, name UNIQUE)
- **transactions**(id PK, user_id FK, account_id FK, transaction_date, description_raw,
  description_clean, merchant, amount NUMERIC(14,2) always positive, transaction_type
  CHECK IN ('CREDIT','DEBIT'), category, category_confidence, category_source
  ('rule'|'ml'|'user'), needs_review BOOL, currency, source_file, dedupe_hash, created_at)
  - Indexes: user_id, transaction_date, category, merchant; UNIQUE(user_id, dedupe_hash)
  - `description_raw` is never modified (audit requirement).
- **category_corrections**(id PK, transaction_id FK, merchant, old_category, new_category, created_at)
  - stored for future training; no live retraining is claimed.
- **recurring_payments**(id PK, user_id FK, merchant, avg_amount, interval_days, last_seen)
- **financial_snapshots**(id PK, user_id FK, period 'YYYY-MM', income, expenses, savings, savings_rate; UNIQUE(user_id, period))
- **ai_conversations**(id PK, user_id FK, created_at)
- **ai_messages**(id PK, conversation_id FK, role, content, context_json, created_at)

Choices: amount stored positive with an explicit CREDIT/DEBIT type (no sign ambiguity);
dedupe_hash = hash(date, amount, raw description, account) for duplicate detection.
