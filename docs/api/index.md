# API Reference

This section provides detailed documentation for all public classes, functions, and modules in the Trading Bot Utilities Library.

## Modules Overview

- [Models](#models): Data models for various trading entities
- [Config](#config): Configuration utilities
- [Utils](#utils): General utility functions
- [Schema](#schema): Data validation schemas
- [Errors](#errors): Custom exceptions
- [Logger](#logger): Logging utilities
- [CLI](#cli): Command-line interface

## Models

The `tbutilslib.models` package contains MongoDB document models for various trading data.

### Base Collection

```python
from tbutilslib.models.base import BaseCollection
```

**BaseCollection** is an abstract base class that all collection models inherit from. It provides common functionality such as enhanced error handling and index management.

#### Methods

- `save()`: Save the document with enhanced error handling
- `create_indexes()`: Create all indexes defined in the model's meta configuration

### Market Data Collections

```python
from tbutilslib import (
    AdvanceDeclineCollection,
    FiiDiiCollection,
    IndexCollection
)
```

- **AdvanceDeclineCollection**: Tracks market-wide advance/decline data
- **FiiDiiCollection**: Foreign Institutional Investor and Domestic Institutional Investor data
- **IndexCollection**: Major market index data

### Equity Collections

```python
from tbutilslib import (
    NiftyEquityCollection,
    EquityMetaCollection
)
```

- **NiftyEquityCollection**: Price and volume data for Nifty stocks
- **EquityMetaCollection**: Metadata about equity securities

### Derivatives Collections

```python
from tbutilslib.models.nse.derivatives import (
    CumulativeDerivativesCollection,
    EquityDerivatesCollection,
    IndexDerivativesCollection,
    HistoricalDerivatesCollection,
    OptionMetaDataCollection
)
```

- **CumulativeDerivativesCollection**: Aggregated derivatives data
- **EquityDerivatesCollection**: Stock options and futures data
- **IndexDerivativesCollection**: Index options and futures data
- **HistoricalDerivatesCollection**: Historical derivatives data
- **OptionMetaDataCollection**: Metadata about options

## Config

The `tbutilslib.config` package contains configuration utilities.

### Database Configuration

```python
from tbutilslib.config.database import MongoConfig
```

**MongoConfig** provides database connection settings.

## Utils

The `tbutilslib.utils` package contains general utility functions.

### Common Utilities

```python
from tbutilslib.utils.common import TODAY
```

- **TODAY**: Current date in the format YYYYMMDD

## Schema

The `tbutilslib.schema` package contains data validation schemas using Marshmallow.

## Errors

The `tbutilslib.errors` module contains custom exceptions.

```python
from tbutilslib.errors import (
    TradingBotAPIException,
    InvalidSecurityError,
    DuplicateRecordError,
    ValidationError
)
```

- **TradingBotAPIException**: Base exception for all API-related errors
- **InvalidSecurityError**: Raised when an invalid security identifier is used
- **DuplicateRecordError**: Raised when attempting to insert a duplicate record
- **ValidationError**: Raised when data validation fails

## Logger

The `tbutilslib.logger` module provides logging utilities.

```python
from tbutilslib.logger import get_logger
```

**get_logger()** configures and returns a logger with console and/or file handlers.

## CLI

The `tbutilslib.cli` module provides a command-line interface.

```python
from tbutilslib.cli import main
```

**main()** is the entry point for the CLI.
