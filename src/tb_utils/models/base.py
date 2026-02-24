"""Base SQLAlchemy Declarative module.

This module provides the base declarative class for all PostgreSQL tables in the library.
It includes common functionality and an UPSERT mixin for bulk insert/updates.
"""

import logging
from typing import Any, Dict, List, TypeVar, Union

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import DeclarativeBase, Session

logger = logging.getLogger("tb-utils.models.base")

T = TypeVar("T", bound="Base")


class Base(DeclarativeBase):
    """Base SQL Model class.

    This class serves as the declarative base for all ORM models.
    """


class PostgresUpsertMixin:
    """Provides a native PostgreSQL UPSERT (INSERT ON CONFLICT DO UPDATE)."""

    @classmethod
    def upsert_native(
        cls: type[T],
        session: Session,
        constraint_name: str,
        data: Union[Dict[str, Any], List[Dict[str, Any]]],
        update_fields: List[str],
    ) -> int:
        """Perform a PostgreSQL specific UPSERT operation.

        Args:
            session: SQLAlchemy session
            constraint_name: The name of the unique constraint to conflict on
            data: A single dict or list of dicts representing the records
            update_fields: List of column names to update on conflict

        Returns:
            Number of rows affected (inserted + updated)
        """
        if not data:
            return 0

        if isinstance(data, dict):
            data = [data]

        stmt = insert(cls).values(data)

        # Determine the columns to update
        update_dict = {c.name: c for c in stmt.excluded if c.name in update_fields}

        if not update_dict:
            # If no fields to update, just do DO NOTHING
            stmt = stmt.on_conflict_do_nothing(constraint=constraint_name)
        else:
            stmt = stmt.on_conflict_do_update(
                constraint=constraint_name, set_=update_dict
            )

        try:
            result = session.execute(stmt)
            return result.rowcount
        except Exception as e:
            logger.error(
                "UPSERT operation failed for %s: %s", cls.__tablename__, str(e)
            )
            raise
