# Quick Start Guide

This guide will help you get started with the Trading Bot Utilities Library (tbutilslib) quickly. We'll cover the basic setup and show you how to perform common operations.

## Installation

First, install the library:

```bash
pip install tbutilslib
```

Or from source:

```bash
git clone https://github.com/letspython3x/tbutilslib.git
cd tbutilslib
pip install .
```

## Database Connection

tbutilslib uses MongoDB for data storage. Connect to your MongoDB instance:

```python
from mongoengine import connect
from tbutilslib.config.database import MongoConfig

# Connect to MongoDB
connect(MongoConfig.MONGODB_DB, host='0.0.0.0', port=27017)
```

## Creating and Querying Data

### Working with Market Data

```python
from tbutilslib import AdvanceDeclineCollection, NiftyEquityCollection

# Create a new market data record
adv_decline = AdvanceDeclineCollection(
    advances=125,
    declines=75,
    unchanged=10,
    timestamp="2025-04-07T12:30:00Z"
)
adv_decline.save()

# Query market data
today_data = AdvanceDeclineCollection.objects(
    timestamp__gte="2025-04-07T00:00:00Z"
).order_by("-timestamp")

# Print results
for item in today_data:
    print(f"Advances: {item.advances}, Declines: {item.declines}")
```

### Working with Equity Data

```python
from tbutilslib import NiftyEquityCollection

# Create a new equity record
equity = NiftyEquityCollection(
    identifier="RELIANCE",
    open_price=2500.0,
    high_price=2550.0,
    low_price=2490.0,
    close_price=2530.0,
    volume=1000000,
    timestamp="2025-04-07T15:30:00Z"
)
equity.save()

# Query equity data
reliance_data = NiftyEquityCollection.objects(
    identifier="RELIANCE",
    timestamp__gte="2025-04-01T00:00:00Z"
).order_by("-timestamp")

# Calculate average closing price
avg_close = sum(item.close_price for item in reliance_data) / reliance_data.count()
print(f"Average closing price: {avg_close}")
```

## Using the CLI

tbutilslib comes with a command-line interface for common tasks:

```bash
# Set up database indexes
tbutilslib setup-db --host 0.0.0.0 --port 27017 --verbose

# Show version
tbutilslib --version
```

## Logging Configuration

Configure logging for your application:

```python
from tbutilslib.logger import get_logger

# Get a logger with both console and file output
logger = get_logger(
    "my_trading_app",
    log_file="trading_app.log",
    console_level=logging.INFO,
    file_level=logging.DEBUG
)

logger.info("Application started")
logger.debug("Detailed debug information")
```

## Next Steps

Now that you're familiar with the basics, check out these guides for more detailed information:

- [Database Setup Guide](database.md) for advanced MongoDB configuration
- [Working with Models Guide](models.md) for detailed model usage
- [API Integration Guide](api.md) for connecting to external services
