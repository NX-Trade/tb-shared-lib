"""Unit tests for tb_utils.calendar and trading holiday detection."""

import json
from datetime import date
from unittest.mock import MagicMock, patch

from tb_utils.calendar import (
    get_trading_holidays_for_year,
    is_trading_holiday,
)


def test_is_trading_holiday_weekends():
    """Saturday and Sunday should always be identified as trading holidays."""
    saturday = date(2026, 9, 12)
    sunday = date(2026, 9, 13)
    assert is_trading_holiday(saturday) is True
    assert is_trading_holiday(sunday) is True


def test_is_trading_holiday_cached_in_redis():
    """Holiday found in Redis cache returns True without DB hit."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(["2026-09-14"])

    target = date(2026, 9, 14)  # Monday Ganesh Chaturthi
    with patch("tb_utils.calendar._get_redis_client", return_value=mock_redis):
        with patch("tb_utils.calendar.get_session_factory") as mock_db:
            assert is_trading_holiday(target) is True
            mock_db.assert_not_called()


def test_is_trading_holiday_normal_trading_day():
    """Regular weekday not in holiday set returns False."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(["2026-09-14"])

    tuesday = date(2026, 9, 15)
    with patch("tb_utils.calendar._get_redis_client", return_value=mock_redis):
        assert is_trading_holiday(tuesday) is False


def test_get_trading_holidays_from_db_fallback():
    """When Redis empty, fetch from database and cache in Redis."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = None

    mock_db = MagicMock()
    mock_row = MagicMock()
    mock_row.holiday_date = date(2026, 9, 14)
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_row]

    mock_factory = MagicMock(return_value=mock_db)

    with patch("tb_utils.calendar._get_redis_client", return_value=mock_redis):
        with patch("tb_utils.calendar.get_session_factory", return_value=mock_factory):
            holidays = get_trading_holidays_for_year(2026)
            assert date(2026, 9, 14) in holidays
            mock_redis.setex.assert_called_once()
