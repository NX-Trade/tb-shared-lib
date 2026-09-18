# pylint: disable=redefined-outer-name  # pytest fixtures are injected by name
# pylint: disable=protected-access       # patching the maker's requests.Session is the seam
"""RequestMaker stores telemetry compressed and redacted, like ExternalClient.

It used to write `str(headers)` — putting live bearer tokens in
`external_api_request` — and truncate bodies to `response.text[:2000]`, throwing
away exactly the part needed to diagnose a broker error. Both paths now share
`tb_utils.http.telemetry`, so there is one implementation of redaction and
compression rather than two behaviours.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from tb_utils.http.redaction import REDACTED
from tb_utils.http.telemetry import decompress
from tb_utils.request_maker import RequestMaker

MAKER = "tb_utils.request_maker"


@pytest.fixture
def session():
    return MagicMock()


def _response(status=200, body='{"ok":true}'):
    response = MagicMock(spec=requests.Response)
    response.status_code = status
    response.ok = 200 <= status < 300
    response.text = body
    response.reason = "OK"
    response.headers = {"Content-Type": "application/json"}
    return response


def _saved_row(session):
    assert session.add.call_count == 1
    return session.add.call_args[0][0]


def test_large_response_is_compressed_not_truncated(session):
    """A 2,000-char cut used to discard the useful part of an error body."""
    body = json.dumps({"candles": [[i, 1, 2, 3, 4] for i in range(600)]})
    assert len(body) > 2000

    maker = RequestMaker(api_provider_id=1, session=session)
    with patch.object(maker._session, "request", return_value=_response(body=body)):
        maker.request("GET", "https://example.com/v2/historical-candle")

    row = _saved_row(session)
    assert row.compression == "zlib"
    assert len(row.response_payload_z) < len(body.encode())
    assert decompress(row.response_payload_z, row.compression) == body  # complete
    assert row.response_payload is None  # no plain copy
    assert row.response_preview.startswith('{"candles"')  # still searchable


def test_credentials_are_never_stored(session):
    maker = RequestMaker(api_provider_id=2, session=session)
    with patch.object(maker._session, "request", return_value=_response()):
        maker.request(
            "POST",
            "https://api.upstox.com/v2/order/place",
            headers={"Authorization": "Bearer super-secret-token", "Accept": "application/json"},
            json_data={"access_token": "super-secret-token", "quantity": 5},
        )

    row = _saved_row(session)
    assert "super-secret-token" not in row.request_headers
    assert REDACTED in row.request_headers
    payload = decompress(row.request_payload_z, row.compression)
    assert "super-secret-token" not in payload
    assert REDACTED in payload
    assert '"quantity":5' in payload  # non-secret fields survive


def test_failure_status_is_recorded_with_the_body(session):
    maker = RequestMaker(api_provider_id=2, session=session)
    body = '{"errors":[{"message":"RMS: Circuit breach, Order Price :1509.00"}]}'
    with patch.object(maker._session, "request", return_value=_response(status=400, body=body)):
        maker.request("POST", "https://api.upstox.com/v2/order/place")

    row = _saved_row(session)
    assert row.is_success == 0
    assert row.error_code == "400"
    assert "Circuit breach" in decompress(row.response_payload_z, row.compression)


def test_transport_error_is_recorded_then_reraised(session):
    maker = RequestMaker(api_provider_id=1, session=session)
    with patch.object(maker._session, "request", side_effect=requests.Timeout("timed out")):
        with pytest.raises(requests.Timeout):
            maker.request("GET", "https://example.com/slow")

    row = _saved_row(session)
    assert row.is_success == 0
    assert row.error_code == "Timeout"
    assert "timed out" in row.error_message


def test_breaker_state_is_recorded_as_an_integer(session):
    maker = RequestMaker(api_provider_id=1, session=session)
    with patch.object(maker._session, "request", return_value=_response()):
        maker.request("GET", "https://example.com/ok")

    assert _saved_row(session).circuit_breaker_state == 1  # CLOSED


def test_correlation_id_is_always_present(session):
    maker = RequestMaker(api_provider_id=1, session=session)
    with patch.object(maker._session, "request", return_value=_response()):
        maker.request("GET", "https://example.com/ok")

    assert _saved_row(session).correlation_id


def test_clean_response_is_stored_byte_for_byte(session):
    """Audit fidelity: a body with no secrets must not be rewritten.

    Re-serialising JSON compacts whitespace and rewrites numbers — a broker's
    "price": 1509.00 would become 1509.0 in a row retained for years.
    """
    body = '{"status": "success", "data": {"price": 1509.00, "qty": 1}}'
    maker = RequestMaker(api_provider_id=2, session=session)
    with patch.object(maker._session, "request", return_value=_response(body=body)):
        maker.request("GET", "https://api.upstox.com/v2/order/details")

    row = _saved_row(session)
    assert decompress(row.response_payload_z, row.compression) == body
    assert "1509.00" in decompress(row.response_payload_z, row.compression)


def test_body_containing_a_secret_is_rewritten_compactly(session):
    body = '{"access_token": "leaked-abc123", "user": "x"}'
    maker = RequestMaker(api_provider_id=2, session=session)
    with patch.object(maker._session, "request", return_value=_response(body=body)):
        maker.request("GET", "https://api.upstox.com/v2/user/profile")

    stored = decompress(_saved_row(session).response_payload_z, _saved_row(session).compression)
    assert "leaked-abc123" not in stored
    assert REDACTED in stored
