"""Telegram Notification Utility with multi-channel routing."""

import logging
import os
from enum import StrEnum
from typing import Optional

import requests

logger = logging.getLogger("tb_utils.telegram")


class TelegramChannel(StrEnum):
    """Telegram routing channels."""

    DEFAULT = "DEFAULT"
    ALPHA = "ALPHA"  # Signals, trade fills, position exits, orders
    ERRORS = "ERRORS"  # Circuit breakers, fatal task failures, unhandled worker exceptions
    SYNC = "SYNC"  # EOD data sync, bhavcopy ingest, participant OI updates


class TelegramNotifier:
    """Telegram Notifier using standard Bot API with multi-channel support."""

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        channel: str | TelegramChannel = TelegramChannel.DEFAULT,
    ) -> None:
        if isinstance(channel, TelegramChannel):
            self.channel = channel.value
        elif isinstance(channel, str) and channel.strip():
            self.channel = channel.strip().upper()
        else:
            self.channel = TelegramChannel.DEFAULT.value

        # Resolve Token: explicit -> TG_{CHANNEL}_TOKEN -> TG_TOKEN
        if token:
            self.token = token
        elif self.channel != TelegramChannel.DEFAULT.value and os.getenv(
            f"TG_{self.channel}_TOKEN"
        ):
            self.token = os.getenv(f"TG_{self.channel}_TOKEN")
        else:
            self.token = os.getenv("TG_TOKEN")

        # Resolve Chat ID: explicit -> TG_{CHANNEL}_CHAT_ID -> TG_CHAT_ID
        if chat_id:
            self.chat_id = chat_id
        elif self.channel != TelegramChannel.DEFAULT.value and os.getenv(
            f"TG_{self.channel}_CHAT_ID"
        ):
            self.chat_id = os.getenv(f"TG_{self.channel}_CHAT_ID")
        else:
            self.chat_id = os.getenv("TG_CHAT_ID")

        self.api_url = (
            f"https://api.telegram.org/bot{self.token}/sendMessage" if self.token else None
        )

    def send(
        self,
        message: str,
        channel: Optional[str | TelegramChannel] = None,
    ) -> bool:
        """Send a message to the configured Telegram chat."""
        if channel is not None:
            target_ch = (
                channel.value
                if isinstance(channel, TelegramChannel)
                else str(channel).strip().upper()
            )
            if target_ch != self.channel:
                return TelegramNotifier(channel=target_ch).send(message)

        if not self.token or not self.chat_id:
            logger.warning(
                "Telegram Notifier: Missing TG_TOKEN or TG_CHAT_ID for channel %s. "
                "Notification skipped.",
                self.channel,
            )
            return False

        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}

        try:
            response = requests.post(self.api_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Telegram notification sent successfully to %s.", self.channel)
            return True
        except requests.exceptions.RequestException:
            logger.exception("Failed to send Telegram notification to channel %s.", self.channel)
            return False


def send_telegram_alert(
    message: str,
    channel: str | TelegramChannel = TelegramChannel.DEFAULT,
) -> bool:
    """Convenience function to send a quick Telegram notification to a specific channel."""
    notifier = TelegramNotifier(channel=channel)
    return notifier.send(message)
