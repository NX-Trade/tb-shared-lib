"""Trading Bot Utilities Library (tbutilslib).

A comprehensive library for algorithmic trading with utilities for
data handling, model management, and API integration.
"""

__version__ = "0.1.0"

from tbutilslib.config.database import MongoConfig

# Import key components to make them available at the package level
from tbutilslib.models import (
    AdvanceDeclineCollection,
    EquityMetaCollection,
    FiiDiiCollection,
    IndexCollection,
    NiftyEquityCollection,
)

# Define what's available when using `from tbutilslib import *`
__all__ = [
    "MongoConfig",
    "AdvanceDeclineCollection",
    "NiftyEquityCollection",
    "EquityMetaCollection",
    "IndexCollection",
    "FiiDiiCollection",
]
