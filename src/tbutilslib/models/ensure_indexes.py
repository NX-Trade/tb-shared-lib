"""Database index management module.

This module provides functions to create and manage database indexes
for all MongoDB collections in the tbutilslib package. These indexes
improve query performance and enforce data constraints.
"""

import logging

from tbutilslib.models import (
    AdvanceDeclineCollection,
    CumulativeDerivativesCollection,
    EquityDerivatesCollection,
    EventsCollection,
    FiiDiiCollection,
    HistoricalDerivatesCollection,
    IndexCollection,
    IndexDerivativesCollection,
    NiftyEquityCollection,
    OptionMetaDataCollection,
    OrdersCollection,
    PositionsCollection,
)

COLL_INDEXES = [
    {"collection": AdvanceDeclineCollection, "index": ["timestamp"]},
    {
        "collection": CumulativeDerivativesCollection,
        "index": ["security", "expiry_date", "-on_date", "-timestamp"],
    },
    {
        "collection": EquityDerivatesCollection,
        "index": [
            "security",
            "strike_price",
            "option_type",
            "expiry_date",
            "-timestamp",
        ],
    },
    {"collection": EventsCollection, "index": ["security", "purpose", "-event_date"]},
    {"collection": FiiDiiCollection, "index": ["category", "-on_date"]},
    {
        "collection": HistoricalDerivatesCollection,
        "index": ["security", "-on_date", "+expiry_date"],
    },
    {
        "collection": IndexDerivativesCollection,
        "index": [
            "security",
            "strike_price",
            "option_type",
            "expiry_date",
            "-timestamp",
        ],
    },
    {"collection": NiftyEquityCollection, "index": ["identifier", "-timestamp"]},
    {"collection": IndexCollection, "index": ["security", "-timestamp"]},
    {"collection": OptionMetaDataCollection, "index": ["+security", "-on_date"]},
    {"collection": OrdersCollection, "index": ["+security", "-timestamp"]},
    {
        "collection": PositionsCollection,
        "index": ["+security", "-on_date", "-timestamp"],
    },
]


def ensure_index(collection_indexes=None):
    """Set indexes for specified collections.

    Args:
        collection_indexes: List of collection index configurations.
            Defaults to COLL_INDEXES if not provided.

    Returns:
        int: Number of indexes created
    """
    logger = logging.getLogger(__name__)

    collection_indexes = collection_indexes or COLL_INDEXES
    created_count = 0

    for item in collection_indexes:
        collection = item["collection"]
        index = item["index"]
        unique = item.get("unique", True)

        try:
            collection.create_index(index, unique=unique)
            logger.info("Created index %s for %s", index, collection.__name__)
            created_count += 1
        except Exception as e:
            logger.error("Error creating index for %s: %s", collection.__name__, str(e))

    return created_count


def ensure_all_indexes():
    """Create all indexes for all collections in the library.

    This function should be called during application initialization
    to ensure all necessary indexes are created.

    Returns:
        int: Number of indexes created
    """
    logger = logging.getLogger(__name__)

    logger.info("Creating indexes for all collections...")
    count = ensure_index()
    logger.info("Created %d indexes successfully", count)

    return count
