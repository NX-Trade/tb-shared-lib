"""Where a broker's daily access token lives, resolved the same way everywhere.

A token belongs to the client account that authenticated, so it is cached per
(broker, client_code). The writer and every reader must agree on that key, and
the one thing they must not do is each work it out differently — the
``token_storage_key`` column once pointed at a key nothing wrote, and the only
reason orders kept working was a fallback nobody had noticed firing.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from tb_utils.models.account import ClientAccount
from tb_utils.redis.keys import get_broker_token_key, get_upstox_token_key

logger = logging.getLogger(__name__)


def get_active_broker_account(db: Session, broker_type: str = "UPSTOX") -> Optional[ClientAccount]:
    """The lowest-numbered active account for a broker, or None."""
    return (
        db.query(ClientAccount)
        .filter(
            ClientAccount.broker_type == broker_type.upper(),
            ClientAccount.is_active == 1,
        )
        .order_by(ClientAccount.account_id)
        .first()
    )


def resolve_broker_token_key(db: Session, broker_type: str = "UPSTOX") -> str:
    """The Redis key holding this broker's daily token.

    Derived from the active account rather than read from
    ``token_storage_key``, so it cannot drift from what the collector writes.
    Falls back to the platform-wide Upstox key when the broker has no active
    account — which is also what callers without any account context get.
    """
    account = get_active_broker_account(db, broker_type)
    if account is None:
        logger.warning(
            "No active %s account; falling back to the shared token key.", broker_type.upper()
        )
        return get_upstox_token_key()
    return get_broker_token_key(broker_type, account.client_code)
