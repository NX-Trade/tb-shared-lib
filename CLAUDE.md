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
