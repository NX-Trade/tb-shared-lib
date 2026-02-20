"""Base Pydantic Schema."""

from typing import Any
from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base generic schema with from_attributes=True enabled.

    This ensures that the model can be populated from a SQLAlchemy ORM object.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class GenericResponseSchema(BaseSchema):
    """A generic wrapper for API responses."""

    success: bool = True
    message: str = "SUCCESS"
    data: Any = None
