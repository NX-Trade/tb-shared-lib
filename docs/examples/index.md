# Examples

This section provides practical examples of how to use the Trading Bot Utilities Library in real-world scenarios. These examples demonstrate common patterns and best practices.

## Basic Examples

- [Connecting to MongoDB](basic_connection.md)
- [Creating and Querying Data](basic_data_operations.md)
- [Setting Up Logging](basic_logging.md)

## Intermediate Examples

- [Building a Data Pipeline](data_pipeline.md)
- [Creating Custom Models](custom_models.md)
- [Working with Market Data](market_data.md)

## Advanced Examples

- [Implementing a Trading Strategy](trading_strategy.md)
- [Building a RESTful API](rest_api.md)
- [Backtesting Framework](backtesting.md)

## Example: Market Data Collection

Here's a simple example of collecting and storing market data:

```python
import datetime
import requests
from mongoengine import connect
from tbutilslib import AdvanceDeclineCollection, MongoConfig

# Connect to MongoDB
connect(MongoConfig.MONGODB_DB, host='0.0.0.0', port=27017)

# Fetch market data from an API
def fetch_advance_decline_data():
    # This is a placeholder - replace with actual API call
    response = requests.get('https://api.example.com/market/advance-decline')
    data = response.json()
    return data

# Process and store the data
def process_market_data():
    data = fetch_advance_decline_data()
    
    # Create a new record
    record = AdvanceDeclineCollection(
        advances=data['advances'],
        declines=data['declines'],
        unchanged=data['unchanged'],
        timestamp=datetime.datetime.now().isoformat()
    )
    
    try:
        record.save()
        print(f"Saved market data: Advances={data['advances']}, Declines={data['declines']}")
        return True
    except Exception as e:
        print(f"Error saving market data: {str(e)}")
        return False

if __name__ == "__main__":
    process_market_data()
```

## Example: Historical Data Analysis

Here's an example of analyzing historical market data:

```python
import pandas as pd
import matplotlib.pyplot as plt
from mongoengine import connect
from tbutilslib import NiftyEquityCollection, MongoConfig

# Connect to MongoDB
connect(MongoConfig.MONGODB_DB, host='0.0.0.0', port=27017)

# Fetch historical data for a specific stock
def analyze_stock_performance(symbol, start_date, end_date):
    # Query the database
    data = NiftyEquityCollection.objects(
        identifier=symbol,
        timestamp__gte=start_date,
        timestamp__lte=end_date
    ).order_by("+timestamp")
    
    # Convert to pandas DataFrame for analysis
    df = pd.DataFrame([
        {
            'date': item.timestamp,
            'open': item.open_price,
            'high': item.high_price,
            'low': item.low_price,
            'close': item.close_price,
            'volume': item.volume
        } for item in data
    ])
    
    # Calculate moving averages
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['MA50'] = df['close'].rolling(window=50).mean()
    
    # Plot the data
    plt.figure(figsize=(12, 6))
    plt.plot(df['date'], df['close'], label='Close Price')
    plt.plot(df['date'], df['MA20'], label='20-day MA')
    plt.plot(df['date'], df['MA50'], label='50-day MA')
    plt.title(f'{symbol} Price History')
    plt.xlabel('Date')
    plt.ylabel('Price')
    plt.legend()
    plt.grid(True)
    plt.savefig(f'{symbol}_analysis.png')
    
    return df

if __name__ == "__main__":
    analyze_stock_performance('RELIANCE', '2025-01-01', '2025-04-01')
```

These examples demonstrate how to use the library for common trading-related tasks. For more detailed examples, check the individual example files in this section.
