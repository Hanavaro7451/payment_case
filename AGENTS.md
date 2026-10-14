# Repository guidance for coding assistants

- When helping the project owner learn, give hints and explain tradeoffs before
  offering a full implementation unless the owner explicitly requests one.
  In code review, start with what works, then prioritize actionable findings.
- Keep the layer directories `app/api/`, `app/schemas/`, `app/services/`,
  `app/repositories/`, and `app/models/`. Keep tariff and payment code in their
  separate modules in each layer. Do not move business rules into routes.
- Store money as integer kopecks. Preserve the status transition table, HMAC check
  over the raw webhook body, and atomic idempotency behavior.
- Change the database schema through Alembic migrations. Do not call `create_all()`
  in application startup.
- For behavioral changes, add a focused test. Run `ruff check .` and `pytest -q`.
  For schema changes, also run `alembic upgrade head` and `alembic check` on PostgreSQL.
- Do not commit real credentials or `.env`. Keep local Compose defaults clearly
  documented as demonstration values.
- Record substantive AI assistance and human review/corrections in `AI_LOG.md` as
  required by the assignment. Keep the account accurate and concise.
- Keep diffs and commits focused on the task; avoid unrelated changes.
