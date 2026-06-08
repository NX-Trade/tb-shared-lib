# tb-shared-lib

A shared Python library for the nx-trade platform providing SQLAlchemy ORM models, Pydantic schemas, and external API clients.

## Test and Build Commands
```bash
# Run tests
pytest

# Code formatting and linting
pre-commit run --all-files
```

## Critical Pointers
- **Database**: Uses PostgreSQL + SQLAlchemy. All models inherit from `DeclarativeBase` (or `Base` with `PostgresUpsertMixin`).
- **Migrations**: Uses Alembic. Schema is in `docs/DATABASE_SCHEMA.sql` or `alembic/versions`.
- **Validation**: Pydantic v2 schemas. Responses use `from_attributes=True`.
- **Session Management**: Fastapi dependency via `get_db()`.
- **API Client**: Use `RequestMaker` for circuit breaking logic on external requests.

For detailed model structures and usage, refer to `README.md`.

## 🤖 Agent Guidelines (Shared Lib)
- **Execution**: Coding only. Nothing runs locally; all runs on algoserver.
- **Git**: Separate repo. Commit locally (2-3+ lines descriptive message), push, pull on algoserver. No scp.
- **DB/Schemas**: Source of truth for SQLAlchemy models (`tb_utils/models/`) and Pydantic schemas. Re-install in services after changes.
- **Alerting**: Contains `tb_utils/notifications/telegram.py`. Use this for all Telegram bot notifications.
