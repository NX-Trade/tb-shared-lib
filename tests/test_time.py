"""Unit tests for tb_utils.time module."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import Column, DateTime
from sqlalchemy.orm import declarative_base

from tb_utils.time import (
    IST,
    UTC,
    ist_day_bounds_utc,
    now_ist,
    sql_ist_day_range,
    to_ist,
    to_utc,
    today_ist,
    trading_day,
)

Base = declarative_base()


class DummyModel(Base):
    __tablename__ = "dummy"
    created_at = Column(DateTime(timezone=True), primary_key=True)


def test_now_ist_and_today_ist():
    now = now_ist()
    assert now.tzinfo is not None
    assert now.tzinfo.utcoffset(now) == timedelta(hours=5, minutes=30)

    today = today_ist()
    assert isinstance(today, date)
    assert today == now.date()


def test_trading_day_none_returns_today_ist():
    assert trading_day(None) == today_ist()


def test_trading_day_date_passthrough():
    d = date(2026, 9, 17)
    assert trading_day(d) == d


def test_trading_day_aware_datetime_conversion():
    # 2026-09-17 04:00:00 UTC is 2026-09-17 09:30:00 IST
    dt_utc = datetime(2026, 9, 17, 4, 0, 0, tzinfo=UTC)
    assert trading_day(dt_utc) == date(2026, 9, 17)

    # 2026-09-16 20:00:00 UTC is 2026-09-17 01:30:00 IST -> belongs to 2026-09-17
    dt_late = datetime(2026, 9, 16, 20, 0, 0, tzinfo=UTC)
    assert trading_day(dt_late) == date(2026, 9, 17)

    # 2026-09-16 18:00:00 UTC is 2026-09-16 23:30:00 IST -> belongs to 2026-09-16
    dt_prev = datetime(2026, 9, 16, 18, 0, 0, tzinfo=UTC)
    assert trading_day(dt_prev) == date(2026, 9, 16)


def test_trading_day_naive_datetime_assumed_utc():
    # Naive datetime in DB is canonical UTC
    dt_naive = datetime(2026, 9, 17, 1, 0, 0)  # 01:00 UTC -> 06:30 IST
    assert trading_day(dt_naive) == date(2026, 9, 17)

    dt_naive_late = datetime(2026, 9, 16, 19, 0, 0)  # 19:00 UTC -> 00:30 IST on 17th
    assert trading_day(dt_naive_late) == date(2026, 9, 17)


def test_trading_day_string_parsing():
    assert trading_day("2026-09-17") == date(2026, 9, 17)
    assert trading_day("17-09-2026") == date(2026, 9, 17)
    assert trading_day("17-Sep-2026") == date(2026, 9, 17)
    assert trading_day("2026-09-17T09:30:00+05:30") == date(2026, 9, 17)
    assert trading_day("2026-09-16T20:00:00Z") == date(2026, 9, 17)


def test_trading_day_invalid_type_raises():
    with pytest.raises(TypeError):
        trading_day(12345)


def test_to_ist_and_to_utc():
    # Naive UTC conversion to IST
    naive_utc = datetime(2026, 9, 17, 10, 0, 0)
    ist_dt = to_ist(naive_utc)
    assert ist_dt.tzinfo == IST
    assert ist_dt.hour == 15
    assert ist_dt.minute == 30

    # Aware conversion
    utc_dt = datetime(2026, 9, 17, 10, 0, 0, tzinfo=UTC)
    ist_dt2 = to_ist(utc_dt)
    assert ist_dt2.hour == 15
    assert ist_dt2.minute == 30

    # to_utc
    back_to_utc = to_utc(ist_dt2)
    assert back_to_utc.tzinfo == UTC
    assert back_to_utc.hour == 10
    assert back_to_utc.minute == 0


def test_ist_day_bounds_utc():
    # For trade date 2026-09-17:
    # 2026-09-17 00:00:00 IST = 2026-09-16 18:30:00 UTC
    # 2026-09-18 00:00:00 IST = 2026-09-17 18:30:00 UTC
    start_utc, end_utc = ist_day_bounds_utc(date(2026, 9, 17))

    assert start_utc == datetime(2026, 9, 16, 18, 30, 0, tzinfo=UTC)
    assert end_utc == datetime(2026, 9, 17, 18, 30, 0, tzinfo=UTC)
    assert (end_utc - start_utc) == timedelta(days=1)


def test_sql_ist_day_range_clause():
    expr = sql_ist_day_range(DummyModel.created_at, date(2026, 9, 17))
    sql_str = str(expr.compile(compile_kwargs={"literal_binds": True}))

    assert "dummy.created_at >=" in sql_str
    assert "dummy.created_at <" in sql_str
    assert "2026-09-16 18:30:00" in sql_str
    assert "2026-09-17 18:30:00" in sql_str
