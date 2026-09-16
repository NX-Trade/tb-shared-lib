# tb-utils — Trading Bot Shared Library

A shared Python library for NX-Trade. Provides SQLAlchemy ORM models, Pydantic schemas, PostgreSQL session management, Redis market data stores, and a circuit-breaker HTTP client for external financial APIs.

---

## 🏛 Architecture Decisions & Conventions

- **ADR 001 — Single Migration Path**: All SQLAlchemy models live exclusively in `libs/tb-shared-lib/src/tb_utils/models/`. Never define SQLAlchemy models inside service directories (`tb-backend`, `tb-collector`, `tb-signal-bot`, `tb-execution`). After any model change, generate an Alembic migration from `tb-shared-lib`.
- **ADR 005 — Golden Record Retention**: Records at `timestamp = 15:30:00` in `option_chain` and `derivative_tick` are never deleted.
- **Singular Table Names**: All database tables in `nx_trade_db` use **singular** names (`trading_signal`, `trading_order`, `position`, `instrument`, `delivery_data`, `bulk_deals`, `block_deals`).

---

## 🗄 Core Database Models & Singular Tables

| Table Name | Model Class | Key Columns & Notes |
|---|---|---|
| `trading_signal` | `TradingSignal` | `signal_id`, `instrument_id`, `strategy_name`, `strategy_type`, `action` (`BUY`/`SELL`/`EXIT`), `timeframe`, `entry_price`, `confidence`, `indicators` (JSON), `metadata` (JSON) |
| `trading_order` | `TradingOrder` | `order_id`, `instrument_id`, `broker_id`, `symbol`, `side` (`BUY`/`SELL`), `order_type`, `status` (`PENDING`/`FILLED`/`REJECTED`/`CANCELLED`), `product` (`D`/`I`) |
| `position` | `Position` | `position_id`, `instrument_id`, `broker_id`, `net_quantity`, `average_price`, `unrealized_pnl`, `realized_pnl` |
| `instrument` | `Instrument` | `symbol`, `isin`, `ib_symbol`, `company_name` (**not `name`**), `sector`, `is_fno`, `is_index`, `is_nifty_50`, `is_nifty_100`, `is_nifty_500` |
| `delivery_data` | `DeliveryData` | `timestamp` (**date column is `timestamp`, not `trade_date`**), `symbol`, `traded_qty`, `deliverable_qty`, `delivery_pct` |
| `bulk_deals` | `BulkDeals` | `date`, `symbol`, `client_name`, `buy_sell`, `quantity_traded`, `trade_price` |
| `block_deals` | `BlockDeals` | `date`, `symbol`, `client_name`, `buy_sell`, `quantity_traded`, `trade_price` |
| `historical_equity_data` | `HistoricalEquityData` | `instrument_id`, `symbol`, `timeframe` (`1 day`, `1 week`), `timestamp`, `open`, `high`, `low`, `close`, `adj_close`, `volume` |
| `historical_index_data` | `HistoricalIndexData` | `instrument_id`, `symbol`, `timeframe`, `timestamp`, `open`, `high`, `low`, `close`, `volume` |
| `option_chain` | `OptionChain` | `timestamp`, `instrument_id`, `strike_price`, `option_type`, `open_interest`, `iv`, `delta` |
| `fiidii` | `FiiDii` | `trade_date`, `category` (`DII`/`FII`), `buy_value`, `sell_value`, `net_value` |
| `participant_oi` | `ParticipantOi` | `trade_date`, `client_type` (`Client`/`DII`/`FII`/`Pro`), `future_index_long`, `future_index_short`, etc. |

---

## 📦 Package Structure

```text
src/tb_utils/
├── __init__.py           # Public API surface
├── config/
│   ├── database.py       # DatabaseConfig (pydantic-settings)
│   └── db_session.py     # SQLAlchemy engine + session factory
├── models/               # SQLAlchemy Declarative Models (ADR 001)
│   ├── base.py           # Base, PostgresUpsertMixin
│   ├── broker.py         # Broker, ExternalApiRequest
│   ├── deals.py          # BulkDeals, BlockDeals
│   ├── delivery.py       # DeliveryData
│   ├── historical_data.py# HistoricalEquityData, HistoricalIndexData, OptionChain
│   ├── instrument.py     # Instrument, NseIndex, IndexConstituent
│   ├── market_data.py    # FiiDii, ParticipantOi, News
│   └── trading.py        # TradingSignal, TradingOrder, Position
├── redis/                # Redis Market Data Hub Helpers
│   ├── async_market_store.py  # AsyncMarketDataStore for FastAPI/asyncpg
│   ├── sync_market_store.py   # SyncMarketDataStore for Celery/workers
│   └── keys.py           # Standardized Redis key namespaces
├── schema/               # Pydantic v2 validation and API schemas
├── utils/
│   ├── dtu.py            # Date/time and IST timezone utilities
│   └── enums.py          # Domain enums (OrderSide, StrategyType, SecurityType)
└── requests.py           # RequestMaker (circuit breaker + telemetry)
```

---

## 🚀 Installation & Usage

### 1. Installation
In development mode from monorepo:
```bash
pip install -e libs/tb-shared-lib
```

### 2. Database Sessions
```python
from tb_utils import get_db, SessionLocal

# Context manager pattern (standard in workers & scripts):
with SessionLocal() as db:
    instruments = db.query(Instrument).filter(Instrument.is_nifty_50 == 1).all()

# FastAPI dependency injection:
def my_endpoint(db: Session = Depends(get_db)):
    ...
```

### 3. Redis Market Data Hub Store
```python
from tb_utils.redis.sync_market_store import SyncMarketDataStore

store = SyncMarketDataStore(redis_url="redis://localhost:6379/0")

# Fetch cached 1m candles for technical indicators
candles = store.get_candles(symbol="RELIANCE", security_type="EQUITY")
```

---

*NX-Trade Shared Library & Domain Foundation*
