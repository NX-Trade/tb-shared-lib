# TB-Shared-Lib

Single source of truth for all SQLAlchemy models, Pydantic schemas, Alembic migrations, Redis key helpers, and the Telegram notifier. Every Python service depends on this library.

## Commands

```bash
venv/bin/pytest                                                 # tests
venv/bin/pre-commit run --all-files                             # lint + format
venv/bin/alembic revision --autogenerate -m "describe change"  # generate migration
venv/bin/alembic upgrade head                                   # apply migration

# Re-install in a service after changes
pip install -e ../../libs/tb-shared-lib   # run inside service venv
```

## Key Modules

```
src/tb_utils/
├── models/             SQLAlchemy ORM models (source of truth for all tables)
├── schemas/            Pydantic v2 schemas — use ConfigDict(from_attributes=True)
├── config/
│   ├── db_session.py   get_session_factory() + get_db() FastAPI dependency
│   └── settings.py     Base env-var config
├── redis/
│   ├── keys.py         Redis key builders — always use these, never hardcode strings
│   └── sync_market_store.py  store_regime_state(), store_watchlist(), get_regime_state()
└── notifications/
    └── telegram.py     The ONLY Telegram alert path across all services
```

## Adding a Model

```python
# src/tb_utils/models/my_model.py
from sqlalchemy import Column, Integer, String, Date
from tb_utils.models.base import Base, PostgresUpsertMixin

class MyModel(Base, PostgresUpsertMixin):
    __tablename__ = "my_table"
    id = Column(Integer, primary_key=True)
    # ...
```

## Migration Workflow

```bash
# 1. Modify model in src/tb_utils/models/
# 2. Generate
venv/bin/alembic revision --autogenerate -m "add my_table"
# 3. Review the generated file in alembic/versions/ — always review before applying
# 4. Apply
venv/bin/alembic upgrade head
# 5. Re-install in all affected services
```

## Session Lifecycle (non-FastAPI)

```python
session = get_session_factory()()
try:
    session.commit()
except Exception:
    session.rollback()
    raise
finally:
    session.close()
```

## Hard Rules

- All services import models from here — never define models locally in a service
- After every model change → generate + review + apply an Alembic migration
- Redis keys → add builders to `redis/keys.py` — never hardcode in services
- Telegram → `notifications/telegram.py` is the only alert path

## Git

Separate sub-repo. Commit locally → push → `ssh algoserver "cd /home/abhi-trade/nx-trade/libs/tb-shared-lib && git pull"`.
