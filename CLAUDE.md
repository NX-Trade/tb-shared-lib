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
├── options/            Option analytics — shared by backend, research-agent & trade-engine
│   ├── resolver.py     Single-contract resolution by target delta
│   ├── strategy_builder.py  Multi-leg construction (hedge-first ordering)
│   ├── payoff.py       Payoff curve (expiry + T+n), breakevens, max P/L, net greeks — pure, N-leg
│   ├── margin.py       SPAN scenarios, exposure, short-option minimum (estimate, `validated=False`)
│   ├── exit_rules.py   `exit_basis` — what exit percentages are applied to (T+n for non-verticals)
│   ├── ideas.py        `generate_ideas` — up to 3 diverse defined-risk baskets from a directional view + chain (pure selector)
│   ├── outcomes.py     `settle_idea` + `calibration_report` — settle a generated idea at expiry and check its odds (pure)
│   ├── probability.py  Exact POP and expected value at expiry (lognormal; market and view-tilted) — pure
│   └── templates.py    Named structures as strike-step offsets (`resolve_template`) — shared by the builder picker and the generator
├── greeks.py           Black-Scholes greeks + implied_volatility solver
└── notifications/
    └── telegram.py     The ONLY Telegram alert path across all services
```

## Option Analytics Live Here

Payoff curves, max profit/loss, breakevens, net position greeks and margin estimation belong in
`src/tb_utils/options/` — **never** reimplemented in a service or in the frontend. Three
consumers need the identical numbers:

| Consumer | Needs it for |
|---|---|
| `tb-backend` | `POST /options/analyze-basket` powering the strategy-builder UI |
| `tb-research-agent` | EV gate; `strategy_builder` max P/L and R:R at construction |
| `tb-trade-engine` | `spread_risk_manager` exit thresholds; pre-trade margin checks |

Two rules:

- **Pure functions only.** No DB session, no Redis, no HTTP in `payoff.py` / `margin.py`. Plain
  dataclasses in and out, so they are callable from a request path, a Celery task and a backtest
  alike, and testable without infrastructure.
- **Compute server-side, never in TypeScript.** The UI calls the API. A second implementation in
  the frontend will drift from this one — the same failure that produced the
  `strategy_builder` / `resolver` keyword mismatch and the duplicated 15m/5m STC skills.

`strategy_builder.py` and `tb-trade-engine`'s `spread_risk_manager` both go through `payoff.py` /
`exit_rules.py` now. Exit percentages must be applied to `exit_basis(...)`, never to a stored
`max_profit` and never to the expiry maximum of a non-vertical structure (unreachable pre-expiry).
See `tb-ai-brain/upcoming/OPTION_STRATEGY_BUILDER_AND_MARGIN_DESIGN.md` §5A.3.

## Schema drift

A model column with no migration behind it breaks every query that selects the model
(`column trade.unrealized_pnl does not exist`) while the tests, which run on the models, stay green.
`python scripts/check_schema_drift.py` (read-only, uses `DATABASE_URL`, exits 1 on any gap) lists the
tables and columns the models declare that the live database lacks; `tb_utils.schema_drift.find_drift`
is the library form. Run it after every deploy, and fix a gap with an Alembic migration — never by hand.

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
- Option payoff / margin / greeks maths lives in `options/` + `greeks.py` — never duplicated in a
  service or the frontend (see *Option Analytics Live Here* above)
- After every model change → generate + review + apply an Alembic migration
- Redis keys → add builders to `redis/keys.py` — never hardcode in services
- Telegram → `notifications/telegram.py` is the only alert path
- **Credentials** → store them on `client_account` in an `EncryptedString` column
  (`models/types.py`), never in a plain `String`, and never in the environment.
  They are encrypted at rest with `CREDENTIALS_ENCRYPTION_KEY` and masked on the
  way out by `ClientAccountResponse`: settable through the API, never readable.
  Add a new credential to `CREDENTIAL_FIELDS` in `schema/account.py` so it is
  masked and flagged — a test fails if the column is left unencrypted.

## Credential Encryption

```bash
# Generate the key (back it up outside the host — losing it loses the credentials)
venv/bin/python -c "from tb_utils.security import generate_key; print(generate_key())"
```

Set `CREDENTIALS_ENCRYPTION_KEY` in `deployment/.env`; `env_file` passes it to
every container. To rotate, put the old key in `CREDENTIALS_ENCRYPTION_KEY_PREVIOUS`
while the new one is in `CREDENTIALS_ENCRYPTION_KEY`, re-save each account, then
drop the previous key. Rows written before encryption keep working — a value that
is not a Fernet token is returned as-is.

## Git

Separate sub-repo. Commit locally → push → `ssh optiplex "cd ~/nx-trade/libs/tb-shared-lib && git pull"`.
