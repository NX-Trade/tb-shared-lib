"""F&O Buildup Scanner utilities."""

FNO_BUILDUP_QUERY = """
WITH LatestDates AS (
    SELECT
        MAX(timestamp) AS t_today,
        (SELECT MAX(timestamp) FROM futures_oi WHERE timestamp < (SELECT MAX(timestamp) FROM futures_oi)) AS t_yesterday
    FROM futures_oi
),
NearMonthExpiry AS (
    SELECT
        fo.symbol,
        MIN(fo.expiry_date) AS expiry_date
    FROM futures_oi fo
    CROSS JOIN LatestDates ld
    WHERE fo.timestamp = ld.t_today
    GROUP BY fo.symbol
),
TodayMetrics AS (
    SELECT
        fo.symbol,
        fo.timestamp,
        SUM(fo.open_interest) AS total_oi,
        MAX(CASE WHEN fo.expiry_date = nme.expiry_date THEN fo.close END) AS near_close
    FROM futures_oi fo
    JOIN NearMonthExpiry nme ON fo.symbol = nme.symbol
    CROSS JOIN LatestDates ld
    WHERE fo.timestamp = ld.t_today
    GROUP BY fo.symbol, fo.timestamp
),
YesterdayMetrics AS (
    SELECT
        fo.symbol,
        SUM(fo.open_interest) AS total_oi,
        MAX(CASE WHEN fo.expiry_date = nme.expiry_date THEN fo.close END) AS near_close
    FROM futures_oi fo
    JOIN NearMonthExpiry nme ON fo.symbol = nme.symbol
    CROSS JOIN LatestDates ld
    WHERE fo.timestamp = ld.t_yesterday
    GROUP BY fo.symbol
)
SELECT
    tm.timestamp,
    tm.symbol,
    tm.near_close AS close,
    ym.near_close AS prev_close,
    CASE
        WHEN ym.near_close > 0 THEN ((tm.near_close - ym.near_close) / ym.near_close) * 100
        ELSE 0
    END AS p_change,
    tm.total_oi AS open_interest,
    ym.total_oi AS prev_open_interest,
    CASE
        WHEN ym.total_oi > 0 THEN ((tm.total_oi - ym.total_oi) / ym.total_oi) * 100
        ELSE 0
    END AS oi_change
FROM TodayMetrics tm
LEFT JOIN YesterdayMetrics ym ON tm.symbol = ym.symbol
JOIN instrument i ON tm.symbol = i.symbol
WHERE i.is_fno = 1 AND i.is_index = 0
ORDER BY ABS(CASE WHEN ym.total_oi > 0 THEN ((tm.total_oi - ym.total_oi) / ym.total_oi) * 100 ELSE 0 END) DESC;
"""


def categorize_fno_buildup(rows) -> dict:
    """Group stock rows into buildup categories and sort them by significance."""
    long_buildup = []
    short_buildup = []
    long_unwinding = []
    short_covering = []

    for row in rows:
        symbol = str(row.symbol)
        close = float(row.close) if row.close is not None else 0.0
        p_change = float(row.p_change) if row.p_change is not None else 0.0
        open_interest = int(row.open_interest) if row.open_interest is not None else 0
        oi_change = float(row.oi_change) if row.oi_change is not None else 0.0

        stock_data = {
            "symbol": symbol,
            "close": close,
            "p_change": p_change,
            "open_interest": open_interest,
            "oi_change": oi_change,
        }

        if p_change > 0 and oi_change > 0:
            stock_data["buildup_type"] = "Long Buildup"
            long_buildup.append(stock_data)
        elif p_change < 0 and oi_change > 0:
            stock_data["buildup_type"] = "Short Buildup"
            short_buildup.append(stock_data)
        elif p_change < 0 and oi_change < 0:
            stock_data["buildup_type"] = "Long Unwinding"
            long_unwinding.append(stock_data)
        elif p_change > 0 and oi_change < 0:
            stock_data["buildup_type"] = "Short Covering"
            short_covering.append(stock_data)

    # Sort candidates
    long_buildup.sort(key=lambda x: x["oi_change"], reverse=True)
    short_buildup.sort(key=lambda x: x["oi_change"], reverse=True)
    long_unwinding.sort(key=lambda x: x["oi_change"])  # most negative first
    short_covering.sort(key=lambda x: x["oi_change"])  # most negative first

    return {
        "long_buildup": long_buildup,
        "short_buildup": short_buildup,
        "long_unwinding": long_unwinding,
        "short_covering": short_covering,
    }
