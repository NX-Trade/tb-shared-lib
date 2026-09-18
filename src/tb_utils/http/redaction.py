"""Strip secrets before request/response data is written to the database.

``RequestMaker`` stored ``str(headers)`` verbatim, so every telemetry row for a
broker call contained a live ``Authorization: Bearer <token>``. Anyone with read
access to ``external_api_request`` — or a copy of a backup — could place orders
until that token expired.

Redaction happens on the way *into* storage, never on the way out, so a leaked
token cannot be recovered from an old row.
"""

import json
import re
from typing import Any

REDACTED = "***REDACTED***"

# Header names whose values are credentials (compared case-insensitively).
SECRET_HEADERS: frozenset[str] = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "x-api-key",
        "api-key",
        "apikey",
        "x-auth-token",
        "x-access-token",
        "cookie",
        "set-cookie",
    }
)

# Body/query keys that hold credentials or personal identifiers.
SECRET_KEYS: frozenset[str] = frozenset(
    {
        "access_token",
        "refresh_token",
        "api_key",
        "api_secret",
        "apikey",
        "client_secret",
        "password",
        "passwd",
        "pin",
        "totp",
        "session_token",
        "authorization",
        "code",
        "id_token",
    }
)

# Bearer/JWT-shaped values that appear inside free-text bodies.
_TOKEN_PATTERN = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}", re.IGNORECASE)


def redact_headers(headers: Any) -> dict[str, str]:
    """Return headers with credential values replaced."""
    if not headers:
        return {}
    try:
        items = headers.items()
    except AttributeError:
        return {"_unparsed": REDACTED}
    return {
        key: (REDACTED if str(key).lower() in SECRET_HEADERS else str(value))
        for key, value in items
    }


def redact_payload(payload: Any) -> Any:
    """Recursively replace secret-looking values in a JSON-ish structure.

    Strings are scanned for bearer tokens; dicts and lists are walked. Anything
    unrecognised is returned unchanged (it is serialised later, not executed).
    """
    if isinstance(payload, dict):
        return {
            key: (REDACTED if str(key).lower() in SECRET_KEYS else redact_payload(value))
            for key, value in payload.items()
        }
    if isinstance(payload, (list, tuple)):
        return [redact_payload(item) for item in payload]
    if isinstance(payload, str):
        return _TOKEN_PATTERN.sub(rf"\1{REDACTED}", payload)
    return payload


def redact_text(text: str) -> str:
    """Redact secrets in a raw body, parsing it as JSON when possible."""
    if not text:
        return ""
    try:
        return json.dumps(redact_payload(json.loads(text)), separators=(",", ":"))
    except (ValueError, TypeError):
        return _TOKEN_PATTERN.sub(rf"\1{REDACTED}", text)


def to_json_text(value: Any) -> str:
    """Serialise a redacted structure for storage, never raising."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return str(value)
