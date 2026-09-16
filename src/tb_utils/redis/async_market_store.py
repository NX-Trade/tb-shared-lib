"""Asynchronous Redis Store for market data. Uncoupled from any calculation logic."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from redis.asyncio import Redis

from tb_utils.redis.keys import (
    get_contracts_key,
    get_derived_metrics_key,
    get_instrument_spot_key,
    get_market_breadth_key,
    get_market_data_candle_key,
    get_market_data_subscription_key,
    get_upstox_token_key,
)

IST = timezone(timedelta(hours=5, minutes=30))

logger = logging.getLogger(__name__)


class AsyncMarketStore:
    """Wrapper for asynchronous Redis caching logic."""

    def __init__(self, client: Redis):
        self.client = client

    async def get_cached_contracts(
        self, symbol: str, current_spot: float, deviation_threshold: float = 0.01
    ) -> list[dict[str, Any]] | None:
        key = get_contracts_key(symbol)
        data = await self.client.get(key)

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

    async def set_cached_contracts(
        self,
        symbol: str,
        contracts: list[dict[str, Any]],
        spot_price: float,
        expiry_seconds: int = 28800,
    ) -> None:
        key = get_contracts_key(symbol)
        payload = {"spot_price": spot_price, "contracts": contracts}
        await self.client.setex(key, expiry_seconds, json.dumps(payload))
        logger.debug("Cached %d contracts for %s at spot %s", len(contracts), symbol, spot_price)

    async def store_derived_metrics(
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
        await self.client.setex(key, expiry_seconds, json.dumps(payload))
        logger.info(
            "Stored derived metrics for %s: PCR=%s, MaxPain=%s, S=%s, R=%s",
            symbol,
            pcr,
            max_pain,
            support,
            resistance,
        )

    async def store_market_breadth(
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
        await self.client.setex(key, expiry_seconds, json.dumps(payload))

    async def store_instrument_spot(
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
        await self.client.setex(key, expiry_seconds, json.dumps(payload))

    # ─── Market Data Hub: Subscriptions & 1m Candle Cache ─────────────────────

    async def subscribe_market_data(
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
        await self.client.setex(key, expiry_seconds, json.dumps(payload))

    async def get_cached_market_candles(
        self, symbol: str, security_type: str = "EQUITY"
    ) -> dict[str, Any] | None:
        """Retrieve cached 1-minute candle document for a symbol."""
        key = get_market_data_candle_key(symbol, security_type)
        data = await self.client.get(key)
        if not data:
            return None
        try:
            return json.loads(data)
        except Exception as e:
            logger.error("Error reading cached market candles for %s: %s", symbol, e)
            return None

    async def set_cached_market_candles(
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
        await self.client.setex(key, expiry_seconds, json.dumps(payload))

    async def get_upstox_access_token(self) -> str | None:
        """Retrieve shared Upstox OAuth2 access token."""
        raw = await self.client.get(get_upstox_token_key())
        if raw:
            return raw if isinstance(raw, str) else raw.decode("utf-8")
        return None
