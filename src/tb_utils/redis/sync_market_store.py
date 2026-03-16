"""Synchronous Redis Store for market data. Uncoupled from any calculation logic."""

import json
import logging
from datetime import datetime
from typing import Any

from redis import Redis

from tb_utils.redis.keys import (
    get_contracts_key,
    get_derived_metrics_key,
    get_instrument_spot_key,
    get_market_breadth_key,
)

logger = logging.getLogger(__name__)


class SyncMarketStore:
    """Wrapper for synchronous Redis caching logic."""

    def __init__(self, client: Redis):
        self.client = client

    def get_cached_contracts(
        self, symbol: str, current_spot: float, deviation_threshold: float = 0.01
    ) -> list[dict[str, Any]] | None:
        key = get_contracts_key(symbol)
        data = self.client.get(key)

        if not data:
            return None

        try:
            # We assume data is a string/bytes compatible with json.loads
            cache_payload = json.loads(data)
            cached_spot = cache_payload.get("spot_price")
            contracts = cache_payload.get("contracts")

            if not cached_spot or not contracts:
                return None

            deviation = abs(current_spot - cached_spot) / cached_spot
            if deviation > deviation_threshold:
                logger.debug(
                    "Cache miss for %s: spot deviated %.2f%% (Threshold: %s%%)",
                    symbol,
                    deviation * 100,
                    deviation_threshold * 100,
                )
                return None

            logger.debug("Cache hit for %s contracts (Spot dev: %.4f%%).", symbol, deviation * 100)
            return contracts

        except Exception as e:
            logger.error("Error reading cached contracts for %s: %s", symbol, e)
            return None

    def set_cached_contracts(
        self,
        symbol: str,
        contracts: list[dict[str, Any]],
        spot_price: float,
        expiry_seconds: int = 28800,
    ) -> None:
        key = get_contracts_key(symbol)
        payload = {"spot_price": spot_price, "contracts": contracts}
        self.client.setex(key, expiry_seconds, json.dumps(payload))
        logger.debug("Cached %d contracts for %s at spot %s", len(contracts), symbol, spot_price)

    def store_derived_metrics(
        self,
        symbol: str,
        spot_price: float,
        pcr: float | None,
        max_pain: float | None,
        support: float | None,
        resistance: float | None,
        total_ce_oi: float,
        total_pe_oi: float,
        expiry_seconds: int = 28800,
    ) -> None:
        """Store pre-calculated derived metrics."""
        payload = {
            "spot_price": spot_price,
            "pcr": pcr,
            "max_pain": max_pain,
            "support": support,
            "resistance": resistance,
            "total_ce_oi": total_ce_oi,
            "total_pe_oi": total_pe_oi,
            "updated_at": datetime.now().isoformat(),
        }

        key = get_derived_metrics_key(symbol)
        self.client.setex(key, expiry_seconds, json.dumps(payload))
        logger.info(
            "Stored derived metrics for %s: PCR=%s, MaxPain=%s, S=%s, R=%s",
            symbol,
            pcr,
            max_pain,
            support,
            resistance,
        )

    def store_market_breadth(
        self,
        exchange: str,
        advances: int,
        declines: int,
        unchanged: int,
        ad_ratio: float | None,
        expiry_seconds: int = 28800,
    ) -> None:
        key = get_market_breadth_key(exchange)
        payload = {
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "ad_ratio": ad_ratio,
            "updated_at": datetime.now().isoformat(),
        }
        self.client.setex(key, expiry_seconds, json.dumps(payload))

    def store_instrument_spot(self, symbol: str, price: float, expiry_seconds: int = 28800) -> None:
        key = get_instrument_spot_key(symbol)
        payload = {"price": price, "updated_at": datetime.now().isoformat()}
        self.client.setex(key, expiry_seconds, json.dumps(payload))
