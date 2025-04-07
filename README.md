# Trading Bot Utilities Library (tbutilslib)

[![Python Versions](https://img.shields.io/badge/python-3.8%20%7C%203.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://pypi.org/project/tbutilslib/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A comprehensive library for algorithmic trading with utilities for data handling, model management, and API integration.

## Features

- MongoDB integration for storing and retrieving trading data
- Schema validation using Marshmallow
- RESTful API support with Flask
- Logging utilities with rotation
- Error handling and custom exceptions
- Command-line interface for common tasks

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/letspython3x/tbutilslib.git
cd tbutilslib

# Install the package
pip install .

# For development installation with extra dependencies
pip install -e ".[dev,docs]"
```

## Database Setup

### Using Docker (Recommended)

1. Pull the MongoDB Docker image:
   ```bash
   docker pull mongodb/mongodb-community-server
   ```

2. Run the MongoDB container:
   ```bash
   docker run -d -p 27017:27017 --name mongo-db mongodb/mongodb-community-server
   ```

3. Access the MongoDB shell (optional):
   ```bash
   docker exec -it mongo-db mongosh
   ```

4. Create database and collections:
   ```
   use Stockmarket
   show collections
   ```

### Setting up Database Indexes

You can use the built-in CLI to set up all required database indexes:

```bash
# Using the CLI
tbutilslib setup-db --host 0.0.0.0 --port 27017 --verbose
```

## Usage Examples

### Connecting to MongoDB

```python
from mongoengine import connect
from tbutilslib.config.database import MongoConfig

# Connect to MongoDB
connect(MongoConfig.MONGODB_DB, host='0.0.0.0', port=27017)
```

### Working with Collections

```python
from tbutilslib import (
    AdvanceDeclineCollection,
    NiftyEquityCollection,
    IndexCollection
)

# Create a new record
adv_decline = AdvanceDeclineCollection(
    advances=125,
    declines=75,
    unchanged=10,
    timestamp="2025-04-07T12:30:00Z"
)
adv_decline.save()

# Query records
today_data = AdvanceDeclineCollection.objects(
    timestamp__gte="2025-04-07T00:00:00Z"
).order_by("-timestamp")

# Print results
for item in today_data:
    print(f"Advances: {item.advances}, Declines: {item.declines}")
```

## Development

### Running Tests

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

### Code Formatting and Linting

```bash
# Format code
black src tests

# Sort imports
isort src tests

# Run linting
flake8 src tests
pylint src
```

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
