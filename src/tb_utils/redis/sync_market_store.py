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
    get_market_data_candle_key,
    get_market_data_subscription_key,
    get_regime_channel,
    get_regime_current_key,
    get_upstox_token_key,
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

    def get_instrument_spot(self, symbol: str) -> dict | None:
        """Retrieve instrument spot data payload from Redis."""
        key = get_instrument_spot_key(symbol)
        data = self.client.get(key)
        if not data:
            return None
        try:
            return json.loads(data)
        except Exception as e:
            logger.error("Error reading spot data for %s: %s", symbol, e)
            return None

    def get_spot_price(self, symbol: str) -> float | None:
        """Retrieve latest spot price for symbol from Redis."""
        data = self.get_instrument_spot(symbol)
        if data and "price" in data:
            try:
                return float(data["price"])
            except (ValueError, TypeError):
                return None
        return None

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

    def get_watchlist_focus(self) -> list[dict]:
        """Retrieve the daily focus watchlist entries stored by ``store_watchlist``."""
        data = self.client.get(get_watchlist_key())
        if not data:
            return []
        try:
            return json.loads(data).get("entries", [])
        except Exception as e:
            logger.error("Error reading watchlist focus: %s", e)
            return []

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

    # ─── Market Data Hub: Subscriptions & 1m Candle Cache ─────────────────────

    def subscribe_market_data(
        self,
        symbol: str,
        security_type: str = "EQUITY",
        isin: str = "",
        instrument_key: str = "",
        subscriber: str = "unknown",
        expiry_seconds: int = 86400,
    ) -> None:
        """Register active demand subscription for market data in Redis."""
        key = get_market_data_subscription_key(symbol, security_type)
        if not instrument_key and isin:
            instrument_key = f"NSE_EQ|{isin}" if security_type == "EQUITY" else f"NSE_FO|{isin}"
        elif not instrument_key:
            instrument_key = symbol

        payload = {
            "symbol": symbol,
            "security_type": security_type,
            "isin": isin,
            "instrument_key": instrument_key,
            "subscriber": subscriber,
            "subscribed_at": datetime.now(IST).isoformat(),
        }
        self.client.setex(key, expiry_seconds, json.dumps(payload))
        logger.debug("Subscribed to market data for %s (%s).", symbol, security_type)

    def get_active_market_subscriptions(self) -> list[dict[str, Any]]:
        """Scan and retrieve all active market data subscriptions from Redis."""
        subscriptions = []
        try:
            for key in self.client.scan_iter("market_data:sub:*"):
                data = self.client.get(key)
                if data:
                    subscriptions.append(json.loads(data))
        except Exception as e:
            logger.error("Error retrieving market data subscriptions: %s", e)
        return subscriptions

    def get_cached_market_candles(
        self, symbol: str, security_type: str = "EQUITY"
    ) -> dict[str, Any] | None:
        """Retrieve cached 1-minute candle document for a symbol."""
        key = get_market_data_candle_key(symbol, security_type)
        data = self.client.get(key)
        if not data:
            return None
        try:
            return json.loads(data)
        except Exception as e:
            logger.error("Error reading cached market candles for %s: %s", symbol, e)
            return None

    def set_cached_market_candles(
        self,
        symbol: str,
        security_type: str = "EQUITY",
        candles: list[list[Any]] | None = None,
        instrument_key: str = "",
        expiry_seconds: int = 172800,
    ) -> None:
        """Cache 1-minute candle payload in Redis with 2-day TTL."""
        key = get_market_data_candle_key(symbol, security_type)
        payload = {
            "symbol": symbol,
            "security_type": security_type,
            "instrument_key": instrument_key,
            "updated_at": datetime.now(IST).isoformat(),
            "candles": candles or [],
        }
        self.client.setex(key, expiry_seconds, json.dumps(payload))
        logger.debug("Cached %d candles for %s (%s).", len(candles or []), symbol, security_type)

    def get_upstox_access_token(self) -> str | None:
        """Retrieve shared Upstox OAuth2 access token."""
        raw = self.client.get(get_upstox_token_key())
        if raw:
            return raw if isinstance(raw, str) else raw.decode("utf-8")
        return None

    def set_upstox_access_token(self, token: str, expiry_seconds: int = 86400) -> None:
        """Store shared Upstox OAuth2 access token."""
        self.client.setex(get_upstox_token_key(), expiry_seconds, token)
