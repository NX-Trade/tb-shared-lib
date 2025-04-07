"""Base Collection module.

This module provides the base document class for all MongoDB collections in the library.
It includes common functionality and error handling for database operations.
"""

import logging
from typing import Any, Dict, List, Optional

from mongoengine import Document, ValidationError
from mongoengine.errors import NotUniqueError
from pymongo.errors import DuplicateKeyError

from ..errors import DuplicateRecordError

logger = logging.getLogger("tbutilslib.models.base")

BASE_META = {
    "strict": False,
    "ordered": True,
    "index_background": True,
    "auto_create_index": False,  # To avoid index creation on every insert
    "indexes": [],
}


class BaseCollection(Document):
    """Base DB collection with enhanced error handling and common functionality.

    This class serves as the base for all collection models in the application.
    It provides common functionality such as improved error handling for save operations
    and standardized metadata configuration.

    Attributes:
        meta: Document metadata configuration with abstract=True to prevent direct instantiation
    """

    meta = {"abstract": True, "allow_inheritance": True}

    @classmethod
    def create_indexes(cls) -> None:
        """Create all indexes defined in the model's meta configuration.

        This method should be called during application initialization to ensure
        all necessary indexes are created.
        """
        logger.info("Creating indexes for %s", cls.__name__)
        cls.ensure_indexes()

    def save(
        self,
        force_insert: bool = False,
        validate: bool = True,
        clean: bool = True,
        write_concern: Optional[Dict[str, Any]] = None,
        cascade: bool = None,
        cascade_kwargs: Optional[Dict[str, Any]] = None,
        _refs: List = None,
        save_condition: Dict = None,
        signal_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> "BaseCollection":
        """Save the document to the database with enhanced error handling.

        This method extends the standard Document.save() method with better error handling
        for duplicate records and validation errors.

        Args:
            force_insert: If True, always insert as a new document
            validate: If True, validate this document before saving
            clean: Call clean() before saving
            write_concern: Extra write concern options
            cascade: Override the default cascade setting
            cascade_kwargs: Keyword arguments to pass to cascading save
            _refs: Internal parameter to track circular references
            save_condition: Condition to limit saving to certain circumstances
            signal_kwargs: Keyword arguments to pass to signals
            **kwargs: Additional keyword arguments to pass to the save operation

        Returns:
            The saved document instance

        Raises:
            DuplicateRecordError: When a duplicate record is detected
            ValidationError: When document validation fails
        """
        try:
            return super().save(
                force_insert=force_insert,
                validate=validate,
                clean=clean,
                write_concern=write_concern,
                cascade=cascade,
                cascade_kwargs=cascade_kwargs,
                _refs=_refs,
                save_condition=save_condition,
                signal_kwargs=signal_kwargs,
                **kwargs,
            )
        except (NotUniqueError, DuplicateKeyError) as e:
            logger.warning("Duplicate record detected: %s", self.__class__.__name__)
            raise DuplicateRecordError(f"Record already exists: {str(e)}") from e
        except ValidationError as e:
            logger.error("Validation error: %s", str(e))
            raise ValidationError(f"Validation error: {str(e)}") from e
