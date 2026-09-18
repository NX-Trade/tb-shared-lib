# pylint: disable=R0902  # CallRecord is a flat data carrier, not behaviour
"""Persist compressed, redacted request/response telemetry.

``RequestMaker`` wrote ``str(headers)`` (leaking live bearer tokens) and
``response.text[:2000]`` — the truncation discarded exactly the part of a broker
error needed to diagnose a rejection. Bodies are now compressed in full, with a
short plain-text preview kept for ``LIKE`` searching.

zlib is used rather than zstd to avoid adding a C-extension dependency to the
library every service imports; the codec name is stored per row, so switching
later needs no migration and old rows stay readable.

Writing telemetry must never break the caller: a failure here is logged and the
session rolled back, and the HTTP result is returned regardless.
"""

import datetime as dt
import logging
import zlib
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from tb_utils.http.redaction import redact_headers, redact_payload, redact_text, to_json_text
from tb_utils.models.broker import ExternalApiRequest

logger = logging.getLogger(__name__)

CODEC = "zlib"
COMPRESSION_LEVEL = 6
PREVIEW_CHARS = 500

# Bodies below this size compress to more bytes than they save.
MIN_COMPRESS_BYTES = 200


@dataclass
class CallRecord:
    """Everything worth keeping about one outbound call."""

    provider: int
    url: str
    method: str
    correlation_id: str
    request_headers: Any = None
    request_payload: Any = None
    status_code: Optional[int] = None
    response_headers: Any = None
    response_text: str = ""
    duration_ms: int = 0
    success: bool = False
    error_code: str = ""
    error_message: str = ""
    retry_count: int = 0
    breaker_state: int = 1


def compress_text(text: str) -> tuple[Optional[bytes], Optional[str]]:
    """Compress ``text``; returns ``(blob, codec)`` or ``(None, None)`` if not worth it."""
    if not text:
        return None, None
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) < MIN_COMPRESS_BYTES:
        return encoded, "raw"
    return zlib.compress(encoded, COMPRESSION_LEVEL), CODEC


def decompress(blob: Optional[bytes], codec: Optional[str]) -> str:
    """Inverse of :func:`compress_text`, tolerant of legacy/absent values."""
    if not blob:
        return ""
    if codec == "raw" or codec is None:
        return bytes(blob).decode("utf-8", errors="replace")
    if codec == CODEC:
        try:
            return zlib.decompress(bytes(blob)).decode("utf-8", errors="replace")
        except zlib.error:
            logger.exception("Corrupt zlib telemetry payload")
            return ""
    logger.warning("Unknown telemetry codec %r", codec)
    return ""


def build_row(record: CallRecord) -> ExternalApiRequest:
    """Turn a :class:`CallRecord` into a redacted, compressed ORM row."""
    request_text = to_json_text(redact_payload(record.request_payload))
    response_text = redact_text(record.response_text)

    request_blob, request_codec = compress_text(request_text)
    response_blob, response_codec = compress_text(response_text)

    return ExternalApiRequest(
        api_provider=record.provider,
        api_endpoint=record.url[:500],
        http_method=record.method.upper(),
        request_headers=to_json_text(redact_headers(record.request_headers)) or None,
        response_headers=to_json_text(redact_headers(record.response_headers)) or None,
        request_payload_z=request_blob,
        response_payload_z=response_blob,
        response_preview=response_text[:PREVIEW_CHARS] or None,
        compression=response_codec or request_codec,
        http_status_code=record.status_code,
        request_timestamp=dt.datetime.now(dt.UTC),
        response_timestamp=dt.datetime.now(dt.UTC),
        duration_ms=record.duration_ms,
        is_success=1 if record.success else 0,
        error_code=record.error_code[:50] or None,
        error_message=record.error_message or None,
        retry_count=record.retry_count,
        circuit_breaker_state=record.breaker_state,
        correlation_id=record.correlation_id[:36],
    )


def save(db: Optional[Session], record: CallRecord) -> Optional[ExternalApiRequest]:
    """Persist one call record. Returns the row, or None when it could not be saved."""
    if db is None:
        return None
    row = build_row(record)
    try:
        db.add(row)
        db.commit()
        return row
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to persist API telemetry for %s %s (correlation_id=%s)",
            record.method,
            record.url,
            record.correlation_id,
        )
        return None
