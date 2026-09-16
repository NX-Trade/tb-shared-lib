"""Unit tests for TelegramNotifier and multi-channel routing."""

import os
from unittest.mock import MagicMock, patch

import requests

from tb_utils import TelegramChannel, TelegramNotifier, send_telegram_alert


def test_telegram_channel_enum_values():
    """Verify channel enum values."""
    assert TelegramChannel.DEFAULT.value == "DEFAULT"
    assert TelegramChannel.ALPHA.value == "ALPHA"
    assert TelegramChannel.ERRORS.value == "ERRORS"
    assert TelegramChannel.SYNC.value == "SYNC"


def test_telegram_notifier_explicit_credentials():
    """Explicit credentials override env vars."""
    notifier = TelegramNotifier(token="custom_token", chat_id="custom_chat_123")
    assert notifier.token == "custom_token"
    assert notifier.chat_id == "custom_chat_123"
    assert notifier.channel == TelegramChannel.DEFAULT.value
    assert notifier.api_url == "https://api.telegram.org/botcustom_token/sendMessage"


def test_telegram_notifier_default_channel_fallback():
    """Default channel resolves from TG_TOKEN and TG_CHAT_ID."""
    with patch.dict(
        os.environ, {"TG_TOKEN": "default_tok", "TG_CHAT_ID": "default_chat"}, clear=True
    ):
        notifier = TelegramNotifier()
        assert notifier.token == "default_tok"
        assert notifier.chat_id == "default_chat"
        assert notifier.channel == "DEFAULT"


def test_telegram_notifier_alpha_channel_specific_env():
    """ALPHA channel resolves from TG_ALPHA_TOKEN and TG_ALPHA_CHAT_ID."""
    env = {
        "TG_TOKEN": "fallback_tok",
        "TG_CHAT_ID": "fallback_chat",
        "TG_ALPHA_TOKEN": "alpha_tok",
        "TG_ALPHA_CHAT_ID": "-100123456789",
    }
    with patch.dict(os.environ, env, clear=True):
        notifier = TelegramNotifier(channel=TelegramChannel.ALPHA)
        assert notifier.token == "alpha_tok"
        assert notifier.chat_id == "-100123456789"
        assert notifier.channel == "ALPHA"


def test_telegram_notifier_channel_fallback_to_default():
    """Channel with no specific env falls back to TG_TOKEN and TG_CHAT_ID."""
    env = {
        "TG_TOKEN": "fallback_tok",
        "TG_CHAT_ID": "fallback_chat",
    }
    with patch.dict(os.environ, env, clear=True):
        notifier = TelegramNotifier(channel=TelegramChannel.ERRORS)
        assert notifier.token == "fallback_tok"
        assert notifier.chat_id == "fallback_chat"
        assert notifier.channel == "ERRORS"


def test_telegram_notifier_string_channel_normalized():
    """String channel names are normalized to uppercase."""
    env = {
        "TG_SYNC_TOKEN": "sync_tok",
        "TG_SYNC_CHAT_ID": "sync_chat",
    }
    with patch.dict(os.environ, env, clear=True):
        notifier = TelegramNotifier(channel="sync")
        assert notifier.channel == "SYNC"
        assert notifier.token == "sync_tok"
        assert notifier.chat_id == "sync_chat"


def test_telegram_notifier_missing_credentials():
    """Missing token or chat_id returns False without raising."""
    with patch.dict(os.environ, {}, clear=True):
        notifier = TelegramNotifier()
        assert notifier.send("Test message") is False


@patch("requests.post")
def test_telegram_notifier_send_success(mock_post):
    """Successful send returns True and posts payload with HTML parse_mode."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_post.return_value = mock_resp

    notifier = TelegramNotifier(token="tok123", chat_id="chat456")
    res = notifier.send("<b>Hello World</b>")

    assert res is True
    mock_post.assert_called_once_with(
        "https://api.telegram.org/bottok123/sendMessage",
        json={"chat_id": "chat456", "text": "<b>Hello World</b>", "parse_mode": "HTML"},
        timeout=10,
    )


@patch("requests.post")
def test_telegram_notifier_send_failure(mock_post):
    """Request exception returns False without crashing."""
    mock_post.side_effect = requests.exceptions.RequestException("Connection error")

    notifier = TelegramNotifier(token="tok123", chat_id="chat456")
    res = notifier.send("Test alert")

    assert res is False


@patch("requests.post")
def test_telegram_notifier_send_with_channel_override(mock_post):
    """Calling send(channel=...) dispatches to the specified channel."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_post.return_value = mock_resp

    env = {
        "TG_TOKEN": "tok_default",
        "TG_CHAT_ID": "chat_default",
        "TG_ERRORS_CHAT_ID": "chat_errors",
    }
    with patch.dict(os.environ, env, clear=True):
        notifier = TelegramNotifier()
        res = notifier.send("Error occurred!", channel=TelegramChannel.ERRORS)
        assert res is True
        mock_post.assert_called_once_with(
            "https://api.telegram.org/bottok_default/sendMessage",
            json={"chat_id": "chat_errors", "text": "Error occurred!", "parse_mode": "HTML"},
            timeout=10,
        )


@patch("requests.post")
def test_send_telegram_alert_convenience(mock_post):
    """send_telegram_alert dispatches to the specified channel."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_post.return_value = mock_resp

    env = {
        "TG_ALPHA_TOKEN": "tok_alpha",
        "TG_ALPHA_CHAT_ID": "chat_alpha",
    }
    with patch.dict(os.environ, env, clear=True):
        res = send_telegram_alert("New STC Signal!", channel=TelegramChannel.ALPHA)
        assert res is True
        mock_post.assert_called_once_with(
            "https://api.telegram.org/bottok_alpha/sendMessage",
            json={"chat_id": "chat_alpha", "text": "New STC Signal!", "parse_mode": "HTML"},
            timeout=10,
        )


def test_escape_html():
    """Verify HTML special characters are properly escaped."""
    from tb_utils import escape_html

    assert escape_html("x < 10 & y > 5") == "x &lt; 10 &amp; y &gt; 5"
    assert escape_html(123) == "123"


@patch("requests.post")
def test_telegram_notifier_chunks_long_message(mock_post):
    """Messages longer than 4000 chars are split into multiple requests."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_post.return_value = mock_resp

    long_message = "\n".join([f"Line {i}: " + "A" * 100 for i in range(50)])  # ~5000 chars
    assert len(long_message) > 4000

    notifier = TelegramNotifier(token="tok", chat_id="chat")
    res = notifier.send(long_message)

    assert res is True
    assert mock_post.call_count >= 2


@patch("requests.post")
def test_send_channel_helpers(mock_post):
    """Test send_alpha_alert, send_error_alert, send_sync_alert."""
    from tb_utils import send_alpha_alert, send_error_alert, send_sync_alert

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_post.return_value = mock_resp

    env = {
        "TG_TOKEN": "base_tok",
        "TG_CHAT_ID": "base_chat",
        "TG_ALPHA_TOKEN": "alpha_tok",
        "TG_ERRORS_TOKEN": "errors_tok",
        "TG_SYNC_TOKEN": "sync_tok",
    }
    with patch.dict(os.environ, env, clear=True):
        assert send_alpha_alert("Alpha trade fill") is True
        assert send_sync_alert("Bhavcopy synced") is True
        assert (
            send_error_alert("Task crashed", error=ValueError("Bad <value>"), details="In pipeline")
            is True
        )

    assert mock_post.call_count == 3
    # Verify error alert auto-escaped bad characters
    error_call = mock_post.call_args_list[2]
    assert "&lt;value&gt;" in error_call[1]["json"]["text"]
