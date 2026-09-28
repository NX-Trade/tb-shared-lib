"""Persistence layer for TradingSignal records."""

# stdlib
import datetime as dt
import logging
from typing import Any, Optional

# third-party
from sqlalchemy.orm import Session

# internal
from tb_utils.models import TradingSignal
from tb_utils.models.signal import SignalCandidate
from tb_utils.time import sql_ist_day_range
from tb_utils.utils import get_instrument_map, resolve_instrument_id
from tb_utils.utils.enums import InstrumentTypeEnum, SignalActionEnum, StrategyClusterEnum

logger = logging.getLogger(__name__)


def positive_price(val: Any) -> Optional[float]:
    """Validate and return positive float, or None."""
    if val is None:
        return None
    try:
        f = float(val)
        return f if f > 0 else None
    except (ValueError, TypeError):
        return None


def persist_approved_signals(
    db: Session,
    approved_signals: list[dict[str, Any] | SignalCandidate],
    source: str,
    as_of: dt.date,
    default_instrument_type: InstrumentTypeEnum = InstrumentTypeEnum.STK,
    strategy_cluster: Optional[StrategyClusterEnum | str] = None,
) -> int:
    """Persist ensemble-approved signal candidates into the ``trading_signal`` DB table.

    Deduplicates candidates so that re-runs on the same trade date do not insert duplicate
    records for the same instrument, strategy_name, and action.

    Args:
        db: Active SQLAlchemy database session.
        approved_signals: List of signal dicts or SignalCandidate instances approved by EnsembleGate.
        source: Scanner source identifier (e.g. "delivery_scanner", "fno_scanner").
        as_of: Trade date of the scan.
        default_instrument_type: Fallback instrument type if not specified in candidate.
        strategy_cluster: High-level classification cluster.

    Returns:
        int: Count of TradingSignal records persisted.
    """
    if not approved_signals:
        return 0

    inst_map = get_instrument_map(db)

    # Load existing signal keys for this trade date to avoid inserting duplicates
    existing_records = (
        db.query(TradingSignal.instrument_id, TradingSignal.strategy_name, TradingSignal.action)
        .filter(sql_ist_day_range(TradingSignal.created_at, as_of))
        .all()
    )
    existing_keys = {
        (
            row.instrument_id,
            row.strategy_name,
            row.action.value if hasattr(row.action, "value") else str(row.action),
        )
        for row in existing_records
    }

    written = 0
    rejected = 0

    for item in approved_signals:
        s = item.to_dict() if isinstance(item, SignalCandidate) else item
        sym = s["symbol"]
        inst_id = resolve_instrument_id(sym, inst_map)

        strategy_name = s.get("strategy_name", f"{source}_signal")
        action_val = (
            s["action"].value
            if isinstance(s["action"], SignalActionEnum)
            else str(s["action"]).upper()
        )

        key = (inst_id, strategy_name, action_val)
        if key in existing_keys:
            logger.info(
                "Skipping duplicate signal for %s (strategy=%s, action=%s) on %s.",
                sym,
                strategy_name,
                action_val,
                as_of,
            )
            continue

        entry_px = positive_price(s.get("entry_price"))
        if entry_px is None:
            logger.warning(
                "Rejecting %s %s signal (strategy=%s): missing or non-positive entry_price=%r",
                action_val,
                sym,
                strategy_name,
                s.get("entry_price"),
            )
            rejected += 1
            continue

        target_px = float(s.get("target_price") or 0.0)
        if target_px <= 0:
            if action_val == SignalActionEnum.BUY.value:
                target_px = entry_px * 1.02
            elif action_val == SignalActionEnum.EXIT.value:
                target_px = entry_px * 0.98
            else:
                target_px = entry_px

        sl_px = float(s.get("stop_loss") or 0.0)
        if sl_px <= 0:
            if action_val == SignalActionEnum.BUY.value:
                sl_px = entry_px * 0.985
            elif action_val == SignalActionEnum.EXIT.value:
                sl_px = entry_px * 1.015
            else:
                sl_px = entry_px

        inst_type_val = s.get("instrument_type")
        if isinstance(inst_type_val, InstrumentTypeEnum):
            inst_type_val = inst_type_val.value
        elif not inst_type_val:
            inst_type_val = default_instrument_type.value

        timeframe_val = s.get("timeframe", "SWING")
        if hasattr(timeframe_val, "value"):
            timeframe_val = timeframe_val.value

        cluster_val = s.get("strategy_cluster") or strategy_cluster
        if hasattr(cluster_val, "value"):
            cluster_val = cluster_val.value
        elif not cluster_val:
            src_lower = (source or "").lower()
            strat_lower = (strategy_name or "").lower()
            if "stc" in src_lower or "stc" in strat_lower:
                cluster_val = StrategyClusterEnum.SHORT_TERM_CLUSTER.value
            else:
                cluster_val = StrategyClusterEnum.RESEARCH_CONFLUENCE.value
        elif isinstance(cluster_val, str):
            cluster_val = cluster_val.upper()

        record = TradingSignal(
            instrument_id=inst_id,
            strategy_name=strategy_name,
            strategy_cluster=cluster_val,
            instrument_type=inst_type_val,
            strategy_type=s.get("strategy_type", "scanner"),
            strike_price=s.get("strike_price"),
            expiry_date=s.get("expiry_date"),
            action=action_val,
            timeframe=timeframe_val,
            entry_price=round(entry_px, 2),
            target_price=round(target_px, 2),
            stop_loss=round(sl_px, 2),
            confidence=float(s["confidence"]),
            reason=str(s.get("reason", "")),
            indicators={"symbol": sym, **s.get("indicators", {})},
            metadata_={
                "source": source,
                "trade_date": str(as_of),
                **s.get("metadata", {}),
            },
            is_executed=False,
        )
        db.add(record)
        existing_keys.add(key)
        written += 1

    db.commit()
    logger.info(
        "Persisted %d signals for %s on %s (rejected=%d, duplicate=%d).",
        written,
        source,
        as_of,
        rejected,
        len(approved_signals) - written - rejected,
    )
    return written


__all__ = ["persist_approved_signals", "positive_price"]
