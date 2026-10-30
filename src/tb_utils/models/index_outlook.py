"""The AI commentary on an index (Nifty 50, Bank Nifty): one row per generation, kept as history."""

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.sql import func

from .base import Base


class IndexOutlook(Base):
    """One outlook for one index at one moment.

    ``evidence`` is exactly what the model was shown and ``output`` what it answered, so any outlook
    can be read back against the numbers behind it. A row where Gemini was unavailable or answered
    outside its vocabulary is still stored, with ``degraded`` set and a numbers-only ``output``, so
    the dashboard always has something honest to show.
    """

    __tablename__ = "index_outlook"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)  # NIFTY50 | BANKNIFTY
    as_of = Column(DateTime(timezone=True), nullable=False, index=True)  # the data's moment
    mode = Column(String(12), nullable=False)  # PREMARKET | CLOSE | MANUAL
    degraded = Column(Boolean, nullable=False, default=False, server_default="false")
    error_code = Column(String(64), nullable=True)
    model_name = Column(String(64), nullable=True)
    prompt_version = Column(String(16), nullable=True)
    evidence = Column(JSON, nullable=False, default=dict)
    output = Column(JSON, nullable=False, default=dict)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    cost_inr = Column(Float, nullable=True)
    requested_by = Column(Text, nullable=True)  # who pressed refresh; None for a scheduled run
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
