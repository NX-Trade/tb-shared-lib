"""F&O (Futures & Options) signal SQL queries.

FUTURES_BUILDUP_QUERY and PCR_SCAN_QUERY both surface a ``trade_date``
column (added alongside the existing few-day SQL freshness windows) so
freshness guards can independently verify, per-row, that the data isn't
older than the pipeline's ``as_of`` run date.
"""

from sqlalchemy import func, select, text

from tb_utils.models import ParticipantOI

FUTURES_BUILDUP_QUERY = text("""
WITH latest_two AS (
    SELECT
        symbol,
        expiry_date,
        open_interest,
        change_in_oi,
        close,
        volume,
        timestamp::date AS trade_date,
        ROW_NUMBER() OVER (PARTITION BY symbol, expiry_date ORDER BY timestamp DESC) AS rn
    FROM futures_oi
    WHERE timestamp::date >= CURRENT_DATE - INTERVAL '3 days'
      AND open_interest > 0
),
today AS (
    SELECT * FROM latest_two WHERE rn = 1
),
prev AS (
    SELECT * FROM latest_two WHERE rn = 2
),
buildup AS (
    SELECT
        t.symbol,
        t.expiry_date,
        t.trade_date,
        t.close          AS price,
        t.open_interest,
        t.change_in_oi,
        CASE WHEN p.open_interest > 0
             THEN (t.change_in_oi::float / p.open_interest * 100)
             ELSE 0 END  AS oi_change_pct,
        CASE WHEN p.close > 0
             THEN ((t.close - p.close) / p.close * 100)
             ELSE 0 END  AS price_change_pct,
        ROW_NUMBER() OVER (PARTITION BY t.symbol ORDER BY t.expiry_date ASC) AS exp_rn
    FROM today t
    LEFT JOIN prev p USING (symbol, expiry_date)
    WHERE ABS(
        CASE WHEN p.open_interest > 0
             THEN (t.change_in_oi::float / p.open_interest * 100)
             ELSE 0 END
    ) >= :oi_min
)
SELECT symbol, expiry_date, trade_date, price, open_interest, change_in_oi, oi_change_pct, price_change_pct
FROM buildup
WHERE exp_rn = 1
ORDER BY ABS(change_in_oi) DESC
""")

PCR_SCAN_QUERY = text("""
SELECT
    symbol,
    MAX(ts::date) AS trade_date,
    SUM(CASE WHEN option_type = 'PE' THEN open_interest ELSE 0 END)::float AS put_oi,
    SUM(CASE WHEN option_type = 'CE' THEN open_interest ELSE 0 END)::float AS call_oi,
    CASE
        WHEN SUM(CASE WHEN option_type = 'CE' THEN open_interest ELSE 0 END) > 0
        THEN SUM(CASE WHEN option_type = 'PE' THEN open_interest ELSE 0 END)::float
             / SUM(CASE WHEN option_type = 'CE' THEN open_interest ELSE 0 END)
        ELSE NULL
    END AS pcr,
    MAX(underlying_value) AS spot_price,
    MAX(expiry_date) FILTER (WHERE expiry_date >= CURRENT_DATE) AS nearest_expiry
FROM option_chain
WHERE ts::date = (SELECT MAX(ts::date) FROM option_chain)
  AND open_interest > 0
  AND underlying_value > 0
GROUP BY symbol
HAVING
    SUM(CASE WHEN option_type = 'CE' THEN open_interest ELSE 0 END) > 0
ORDER BY symbol
""")

PARTICIPANT_OI_QUERY = (
    select(
        ParticipantOI.trade_date,
        ParticipantOI.futures_idx_net.label("fii_idx_net"),
        ParticipantOI.futures_stk_net.label("fii_stk_net"),
    )
    .where(
        ParticipantOI.category == "FII",
        ParticipantOI.trade_date >= func.current_date() - text("INTERVAL '3 days'"),
    )
    .order_by(ParticipantOI.trade_date.desc())
    .limit(2)
)

CLIENT_OI_QUERY = (
    select(
        ParticipantOI.trade_date,
        ParticipantOI.futures_idx_net.label("client_idx_net"),
        ParticipantOI.futures_stk_net.label("client_stk_net"),
    )
    .where(
        ParticipantOI.category == "CLIENT",
        ParticipantOI.trade_date >= func.current_date() - text("INTERVAL '3 days'"),
    )
    .order_by(ParticipantOI.trade_date.desc())
    .limit(2)
)

__all__ = [
    "FUTURES_BUILDUP_QUERY",
    "PCR_SCAN_QUERY",
    "PARTICIPANT_OI_QUERY",
    "CLIENT_OI_QUERY",
]
