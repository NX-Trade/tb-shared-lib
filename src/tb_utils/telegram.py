"""Telegram Notification Utility."""

import logging
import os

import requests

logger = logging.getLogger("tb_utils.telegram")


class TelegramNotifier:
    """Telegram Notifier using standard Bot API."""

    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.getenv("TG_TOKEN")
        self.chat_id = chat_id or os.getenv("TG_CHAT_ID")
        self.api_url = (
            f"https://api.telegram.org/bot{self.token}/sendMessage" if self.token else None
        )

    def send(self, message: str) -> bool:
        """Send a message to the configured Telegram chat."""
        if not self.token or not self.chat_id:
            logger.warning(
                "Telegram Notifier: Missing TG_TOKEN or TG_CHAT_ID. Notification skipped."
            )
            return False

        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}

        try:
            response = requests.post(self.api_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Telegram notification sent successfully.")
            return True
        except requests.exceptions.RequestException as e:
            logger.error("Failed to send Telegram notification: %s", e)
            return False


def send_telegram_alert(message: str) -> bool:
    """Convenience function to send a quick Telegram notification."""
    notifier = TelegramNotifier()
    return notifier.send(message)
