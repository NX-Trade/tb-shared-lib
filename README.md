# tb-utils — Trading Bot Shared Library

A shared Python library for the NX-Trade Monorepo. Provides SQLAlchemy ORM models, Pydantic schemas, PostgreSQL session management, and a circuit-breaker HTTP client for external APIs (NSE, BSE, MoneyControl).

---

## Tech Stack

| Concern       | Old (`v0.x`)          | New (`v1.0.0`)                   |
| ------------- | --------------------- | -------------------------------- |
| Web Framework | Flask, Flask-RESTful  | FastAPI                          |
| Database      | MongoDB, MongoEngine  | PostgreSQL + TimescaleDB         |
| ORM           | MongoEngine Documents | SQLAlchemy `DeclarativeBase`     |
| Validation    | Marshmallow           | Pydantic v2                      |
| Migrations    | None                  | Alembic                          |
| External HTTP | Bare `requests`       | `RequestMaker` (circuit breaker) |

---

## Installation

```bash
pip install tb-utils
```

Or in development mode from the monorepo root:

```bash
pip install -e libs/tb-shared-lib
```

### Environment Variables

| Variable            | Default     | Description       |
| ------------------- | ----------- | ----------------- |
| `POSTGRES_USER`     | `postgres`  | Database user     |
| `POSTGRES_PASSWORD` | `postgres`  | Database password |
| `POSTGRES_HOST`     | `127.0.0.1` | Database host     |
| `POSTGRES_PORT`     | `5432`      | Database port     |
| `POSTGRES_DB`       | `nx_trade`  | Database name     |

Create a `.env` file in your project root or set these variables in your shell. The library reads them automatically via `pydantic-settings`.

---

## Package Structure

```
src/tb-utils/
├── __init__.py           # Public API surface (version 1.0.0)
├── apiwrapper/
│   └── tbapi.py          # Internal TradingBot HTTP API client
├── config/
│   ├── apiconfig.py      # NSE, TbApi URL config
│   ├── database.py       # PostgresConfig (pydantic-settings)
│   └── db_session.py     # SQLAlchemy engine + session factory
├── errors.py             # Custom exceptions
├── logger.py             # Logging helpers
├── models/
│   ├── base.py            # Base, PostgresUpsertMixin
│   ├── broker.py          # Broker, BrokerHealthLog, ExternalApiRequest
│   ├── corporate_event.py # CorporateEvent, TradingHoliday
│   ├── historical_data.py # HistoricalEquityData, HistoricalIndexData, Candle, OptionChain
│   ├── instrument.py      # Instrument
│   ├── market_data.py     # FiiDii, News, MarketBreadth
│   ├── system.py          # SystemMetric, SystemLog
│   └── trading.py         # TradingSignal, TradingOrder, Position, Trade
├── requests.py            # RequestMaker (circuit breaker + telemetry)
├── schema/
│   ├── base.py            # BaseSchema, GenericResponseSchema
│   ├── broker.py          # BrokerResponse, ExternalApiRequestResponse, ...
│   ├── corporate_event.py # CorporateEventResponse, TradingHolidayResponse
│   ├── historical_data.py # CandleResponse, OptionChainResponse, ...
│   ├── instrument.py      # InstrumentResponse
│   ├── market_data.py     # FiiDiiResponse, MarketBreadthResponse, NewsResponse
│   ├── system.py          # SystemMetricResponse, SystemLogResponse
│   └── trading.py         # TradingSignalCreate/Response, TradingOrderCreate/Response, ...
└── utils/
    ├── common.py
    ├── dtu.py             # Date/time utilities
    └── enums.py           # Domain enumerations
```

---

## Usage

### 1. Database Session

Use `get_db()` as a FastAPI dependency or call `SessionLocal()` directly in scripts.

```python
from tb_utils import get_db, SessionLocal

# FastAPI
from fastapi import Depends
from sqlalchemy.orm import Session

def my_route(db: Session = Depends(get_db)):
    ...

# Script / Celery task
db = SessionLocal()
try:
    ...
finally:
    db.close()
```

### 2. SQLAlchemy Models

All models use `Integer` auto-increment PKs and are mapped to the schema in `docs/DATABASE_SCHEMA.sql`.

```python
from tb_utils import Instrument, Candle, TradingOrder

# Query
from tb_utils import SessionLocal
from sqlalchemy import select

db = SessionLocal()
instruments = db.execute(select(Instrument).where(Instrument.is_fno == 1)).scalars().all()
```

### 3. UPSERT (PostgreSQL native)

Models that inherit `PostgresUpsertMixin` expose a class method `upsert_native()`:

```python
from tb_utils import FiiDii, get_db

db = next(get_db())
FiiDii.upsert_native(
    session=db,
    constraint_name="fiidii_trade_date_category_segment_key",
    data=[{"trade_date": "2025-02-20", "category": "FII", "segment": "CASH", ...}],
    update_fields=["buy_value", "sell_value", "net_value"],
)
db.commit()
```

### 4. Pydantic Schemas

All response schemas are configured with `from_attributes=True` for direct ORM → schema conversion.

```python
from tb_utils import InstrumentResponse, CandleResponse
from tb_utils import SessionLocal, Instrument
from sqlalchemy import select

db = SessionLocal()
rows = db.execute(select(Instrument)).scalars().all()
result = [InstrumentResponse.model_validate(r) for r in rows]
```

### 5. RequestMaker (Circuit Breaker)

Use `RequestMaker` to call external APIs (NSE, BSE, MoneyControl). It automatically:

- Opens the **circuit** after N consecutive failures.
- Logs all request/response telemetry to the `external_api_request` table.
- Resets automatically after a configurable timeout.

```python
from tb_utils import RequestMaker, CircuitBreakerError, get_db

db = next(get_db())
nse = RequestMaker(
    api_provider_id=1,   # 1 = NSE
    session=db,
    max_failures=5,
    reset_timeout_seconds=60
)

try:
    response = nse.request(
        method="GET",
        url="https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050",
        headers={"user-agent": "Mozilla/5.0"},
        correlation_id="req-abc-123",
    )
    data = response.json()
except CircuitBreakerError:
    print("NSE circuit is open, skipping request.")
```

### 6. Internal API Client

```python
from tb_utils.apiwrapper.tbapi import TbApi

api = TbApi()
orders = api.get_orders()
positions = api.get_positions()
```

---

## Versioning

This library follows [Semantic Versioning](https://semver.org/):

- `MAJOR` — breaking changes (like this `v0` → `v1` migration)
- `MINOR` — new backwards-compatible features
- `PATCH` — bug fixes

The version is defined in `tb_utils/__init__.py`:

```python
__version__ = "1.0.0"
```

---

## Migration from v0.x

| v0.x                                                  | v1.0.0                                                            |
| ----------------------------------------------------- | ----------------------------------------------------------------- |
| `from tb_utils.config.database import MongoConfig`  | `from tb_utils import PostgresConfig, db_settings`              |
| `from tb_utils.models import NiftyEquityCollection` | `from tb_utils import Candle, HistoricalEquityData`             |
| `from tb_utils.schema import OrdersSchema`          | `from tb_utils import TradingOrderCreate, TradingOrderResponse` |
| `BaseCollection` / `MongoEngine.Document`             | `Base` / `SQLAlchemy DeclarativeBase`                             |
| `flask-mongoengine` connection                        | `get_db()` / `SessionLocal()`                                     |

> No shim or compatibility layer is provided. All old MongoDB collections must be re-mapped to the new PostgreSQL tables defined in `docs/DATABASE_SCHEMA.sql`.

---

## Development

```bash
# Create and activate a virtual environment
python3 -m venv venv && source venv/bin/activate

# Install in editable mode with dev extras
pip install -e ".[dev]"

# Run pre-commit hooks
pre-commit run --all-files

# Run tests
pytest
```
