"""Synchronous Redis Store for market data. Uncoupled from any calculation logic."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from redis import Redis

from tb_utils.redis.keys import (
    get_contracts_key,
    get_derived_metrics_key,
    get_fno_ban_list_key,
    get_instrument_spot_key,
    get_macro_indicator_key,
    get_market_breadth_key,
    get_regime_channel,
    get_regime_current_key,
    get_watchlist_key,
)

IST = timezone(timedelta(hours=5, minutes=30))

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
            "updated_at": datetime.now(IST).isoformat(),
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
            "updated_at": datetime.now(IST).isoformat(),
        }
        self.client.setex(key, expiry_seconds, json.dumps(payload))

    def store_instrument_spot(
        self,
        symbol: str,
        price: float,
        change: float | None = None,
        p_change: float | None = None,
        expiry_seconds: int = 28800,
    ) -> None:
        key = get_instrument_spot_key(symbol)
        payload = {"price": price, "updated_at": datetime.now(IST).isoformat()}
        if change is not None:
            payload["change"] = change
        if p_change is not None:
            payload["p_change"] = p_change
        self.client.setex(key, expiry_seconds, json.dumps(payload))

    def store_fno_ban_list(self, banned_symbols: list[str], expiry_seconds: int = 86400) -> None:
        """Store the list of banned F&O symbols."""
        key = get_fno_ban_list_key()
        self.client.setex(key, expiry_seconds, json.dumps(banned_symbols))
        logger.info("Stored F&O ban list: %s", banned_symbols)

    def store_regime_state(
        self,
        symbol: str,
        state_label: str,
        state_index: int,
        state_probabilities: list[float],
        confidence: float,
        allocation_multiplier: float,
        expiry_seconds: int = 86400,
    ) -> None:
        """Store the current market regime state and publish a transition event."""
        payload = {
            "symbol": symbol,
            "state_label": state_label,
            "state_index": state_index,
            "state_probabilities": state_probabilities,
            "confidence": confidence,
            "allocation_multiplier": allocation_multiplier,
            "updated_at": datetime.now(IST).isoformat(),
        }
        serialized = json.dumps(payload)
        self.client.setex(get_regime_current_key(), expiry_seconds, serialized)
        self.client.publish(get_regime_channel(), serialized)
        logger.info(
            "Stored regime state for %s: %s (conf=%.3f, alloc=%.1fx)",
            symbol,
            state_label,
            confidence,
            allocation_multiplier,
        )

    def store_macro_indicator(
        self,
        symbol: str,
        indicator_type: str,
        price: float,
        change: float | None = None,
        pct_change: float | None = None,
        expiry_seconds: int = 7200,  # 2 hours — refreshed hourly
    ) -> None:
        """Cache a macro indicator snapshot (Crude Oil / USD-INR).

        Key: market_data:macro:{symbol}  e.g. market_data:macro:CL=F
        """
        key = get_macro_indicator_key(symbol)
        payload = {
            "symbol": symbol,
            "indicator_type": indicator_type,
            "price": price,
            "updated_at": datetime.now(IST).isoformat(),
        }
        if change is not None:
            payload["change"] = change
        if pct_change is not None:
            payload["pct_change"] = pct_change
        self.client.setex(key, expiry_seconds, json.dumps(payload))
        logger.info("Stored macro indicator %s (%s): %.4f", indicator_type, symbol, price)

    def store_watchlist(self, entries: list[dict], expiry_seconds: int = 86400) -> None:
        """Store the daily focus watchlist."""
        payload = {"entries": entries, "updated_at": datetime.now(IST).isoformat()}
        self.client.setex(get_watchlist_key(), expiry_seconds, json.dumps(payload))
        logger.info("Stored watchlist with %d entries.", len(entries))

    def get_regime_state(self) -> dict | None:
        """Retrieve the current regime state."""
        data = self.client.get(get_regime_current_key())
        if not data:
            return None
        try:
            return json.loads(data)
        except Exception as e:
            logger.error("Error reading regime state: %s", e)
            return None

    def get_fno_ban_list(self) -> list[str]:
        """Retrieve the list of banned F&O symbols."""
        key = get_fno_ban_list_key()
        data = self.client.get(key)
        if not data:
            return []
        try:
            return json.loads(data)
        except Exception as e:
            logger.error("Error reading F&O ban list: %s", e)
            return []
