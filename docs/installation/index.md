# Installation Guide

This guide will help you install the Trading Bot Utilities Library (tbutilslib) and set up the required dependencies.

## Prerequisites

Before installing tbutilslib, ensure you have the following prerequisites:

- Python 3.8 or higher
- pip (Python package installer)
- MongoDB (for data storage)

## Installation Methods

### From Source (Recommended for Development)

```bash
# Clone the repository
git clone https://github.com/letspython3x/tbutilslib.git
cd tbutilslib

# Install the package
pip install .

# For development installation with extra dependencies
pip install -e ".[dev,docs]"
```

### Using pip (When Available)

```bash
pip install tbutilslib
```

## Verifying Installation

To verify that tbutilslib is installed correctly, run:

```python
import tbutilslib
print(tbutilslib.__version__)
```

You should see the version number of the installed package.

## MongoDB Setup

tbutilslib requires MongoDB for data storage. You can set up MongoDB in several ways:

### Using Docker (Recommended)

1. Pull the MongoDB Docker image:
   ```bash
   docker pull mongodb/mongodb-community-server
   ```

2. Run the MongoDB container:
   ```bash
   docker run -d -p 27017:27017 --name mongo-db mongodb/mongodb-community-server
   ```

3. Verify the MongoDB container is running:
   ```bash
   docker ps
   ```

### Using a Local MongoDB Installation

If you prefer to install MongoDB directly on your system, follow the [official MongoDB installation guide](https://www.mongodb.com/docs/manual/installation/).

## Setting Up Database Indexes

After installing tbutilslib and MongoDB, you should set up the required database indexes for optimal performance:

```bash
# Using the CLI
tbutilslib setup-db --host 0.0.0.0 --port 27017 --verbose
```

Or programmatically:

```python
from mongoengine import connect
from tbutilslib.config.database import MongoConfig
from tbutilslib.models.ensure_indexes import ensure_all_indexes

# Connect to MongoDB
connect(MongoConfig.MONGODB_DB, host='0.0.0.0', port=27017)

# Create all indexes
ensure_all_indexes()
```

## Troubleshooting

### Common Installation Issues

1. **Package not found**: Ensure you're using the correct Python environment.
2. **MongoDB connection issues**: Check that MongoDB is running and accessible on the specified host and port.
3. **Dependency conflicts**: Try installing in a fresh virtual environment.

For more detailed troubleshooting, see the [Troubleshooting Guide](../guides/troubleshooting.md).
