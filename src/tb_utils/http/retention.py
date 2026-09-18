"""Retention policy for external API telemetry (review 13, Q4).

Two classes of row, because they answer different questions:

* **Order-execution rows** (``/order``, ``/gtt``, ``/trade``) evidence what was
  sent to the exchange on our behalf. SEBI's algo-trading framework expects
  order instructions to be retained for years, and relying on the broker's own
  logs to prove our side is not a position worth defending — kept
  ``ORDER_AUDIT_RETENTION_DAYS`` (5 years).
* **Everything else** — quotes, candles, option chains, LLM calls — is
  debugging material that stops being useful within weeks and would otherwise
  dominate the table. Kept ``DATA_RETENTION_DAYS`` (30 days), matching the
  existing ``agent_verdict`` purge.

``purge_expired_telemetry`` is plain SQL so a service can schedule it from its
own beat without importing anything else from here.
"""

import datetime as dt
import logging
from dataclasses import dataclass

from sqlalchemy import and_, delete, not_, or_
from sqlalchemy.orm import Session

from tb_utils.http.providers import ORDER_AUDIT_FRAGMENTS
from tb_utils.models.broker import ExternalApiRequest

logger = logging.getLogger(__name__)

DATA_RETENTION_DAYS = 30
ORDER_AUDIT_RETENTION_DAYS = 365 * 5


@dataclass(frozen=True)
class PurgeResult:
    """How many rows each retention class removed."""

    data_rows: int = 0
    order_rows: int = 0

    @property
    def total(self) -> int:
        return self.data_rows + self.order_rows


def _order_audit_filter():
    """SQL predicate matching order-execution endpoints."""
    return or_(*[ExternalApiRequest.api_endpoint.ilike(f"%{f}%") for f in ORDER_AUDIT_FRAGMENTS])


def purge_expired_telemetry(
    db: Session,
    data_retention_days: int = DATA_RETENTION_DAYS,
    order_retention_days: int = ORDER_AUDIT_RETENTION_DAYS,
    now: dt.datetime | None = None,
) -> PurgeResult:
    """Delete telemetry past its retention window.

    Args:
        db: Session; the deletes are committed here.
        data_retention_days: Window for non-order rows.
        order_retention_days: Window for order-execution rows.
        now: Override the clock (tests).

    Returns:
        Counts per retention class.
    """
    now = now or dt.datetime.now(dt.UTC)
    data_cutoff = now - dt.timedelta(days=data_retention_days)
    order_cutoff = now - dt.timedelta(days=order_retention_days)

    data_deleted = db.execute(
        delete(ExternalApiRequest).where(
            and_(
                ExternalApiRequest.request_timestamp < data_cutoff,
                not_(_order_audit_filter()),
            )
        )
    ).rowcount
    order_deleted = db.execute(
        delete(ExternalApiRequest).where(
            and_(
                ExternalApiRequest.request_timestamp < order_cutoff,
                _order_audit_filter(),
            )
        )
    ).rowcount
    db.commit()

    result = PurgeResult(data_rows=data_deleted or 0, order_rows=order_deleted or 0)
    logger.info(
        "Purged API telemetry: %d data row(s) older than %dd, %d order row(s) older than %dd",
        result.data_rows,
        data_retention_days,
        result.order_rows,
        order_retention_days,
    )
    return result
