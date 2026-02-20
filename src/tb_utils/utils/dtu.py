from datetime import datetime, date
from typing import Optional

from .enums import DateFormatEnum

TB_DT_MAPPING = {
    "expiry_date": DateFormatEnum.TB_DATE.value,
    "event_date": DateFormatEnum.TB_DATE.value,
    "on_date": DateFormatEnum.TB_DATE.value,
    "date_30d_ago": DateFormatEnum.TB_DATE.value,
    "timestamp": DateFormatEnum.FULL_TS.value,
    "last_update_time": DateFormatEnum.FULL_TS.value,
}

TODAY: str = datetime.today().strftime(DateFormatEnum.TB_DATE.value)


def parse_timestamp(timestamp: str, fmt: Optional[str] = None) -> datetime:
    """Convert a string timestamp given in format to datetime."""

    return datetime.strptime(timestamp, fmt or DateFormatEnum.FULL_TS.value)


def parse_timestamp_to_str(timestamp: datetime, fmt: Optional[str] = None) -> str:
    """Convert a datetime to string in given format."""

    return datetime.strftime(timestamp, fmt or DateFormatEnum.FULL_TS.value)


def str_to_date(date_str: str, fmt: Optional[str] = None) -> date:
    """Convert a date string given in format to actual date."""

    fmt = fmt or DateFormatEnum.NSE_DATE.value
    try:
        return datetime.strptime(date_str, fmt).date()
    except ValueError:
        return datetime.strptime(date_str, DateFormatEnum.TB_DATE.value).date()


def date_to_str(val: date, fmt: Optional[str] = None) -> str:
    """Convert a date to a string in the given format."""

    fmt = fmt or DateFormatEnum.TB_DATE.value
    return val.strftime(fmt) if isinstance(val, date) else val


def parse_dates_to_str(dates: list[dict]) -> list[dict]:
    """Convert List of datetime values to string date values."""

    data = dates if isinstance(dates, list) else [dates]
    return [
        {
            key: (date_to_str(val, TB_DT_MAPPING[key]) if key in TB_DT_MAPPING else val)
            for key, val in datum.items()
        }
        for datum in data
    ]


def parse_str_to_date_in_dict(query: dict) -> dict:
    """Convert all dates in the dict to an actual date."""

    updated_query: dict = {}
    for key, val in query.items():
        updated_query[key] = val
        if key in TB_DT_MAPPING and isinstance(val, str):
            updated_query[key] = str_to_date(val, TB_DT_MAPPING[key])
    return updated_query


def change_date_format(val: str | date, fmt=DateFormatEnum.TB_DATE.value):
    """Expects a date-string or a date/datetime and converts it to new
    dateformat.
    """

    _date = str_to_date(val, fmt) if isinstance(val, str) else val
    return _date.strftime(fmt)


def is_month_same(_date1: date, _date2: date) -> bool:
    """Compare dates to check if the month is same."""
    _date1 = str_to_date(_date1) if isinstance(_date1, str) else _date1
    _date2 = str_to_date(_date2) if isinstance(_date2, str) else _date2
    return _date1.month == _date2.month


def parse_dates_to_str_old(data, key, fmt=DateFormatEnum.TB_DATE.value):
    if data and key in data[0].keys():
        return [{**item, key: item.get(key).strftime(fmt)} for item in data]
    return data
