import datetime as dt

from tb_utils import (
    InstrumentTypeEnum,
    SignalActionEnum,
    SignalOutcomeStatusEnum,
    StrategyClusterEnum,
    TimeframeEnum,
    format_fno_summary,
    format_research_signal_card,
)


def test_enums_exported_correctly():
    assert SignalActionEnum.BUY == "BUY"
    assert SignalActionEnum.SELL == "SELL"
    assert SignalActionEnum.EXIT == "EXIT"
    assert SignalActionEnum.WATCH == "WATCH"

    assert TimeframeEnum.SCALPING == "SCALPING"
    assert TimeframeEnum.INTRADAY == "INTRADAY"
    assert TimeframeEnum.SWING == "SWING"
    assert TimeframeEnum.POSITIONAL == "POSITIONAL"

    assert InstrumentTypeEnum.EQUITY == "EQUITY"
    assert InstrumentTypeEnum.STK == "STK"
    assert InstrumentTypeEnum.OPT == "OPT"

    assert StrategyClusterEnum.RESEARCH_CONFLUENCE == "RESEARCH_CONFLUENCE"
    assert StrategyClusterEnum.INTRADAY_FNO_CLUSTER == "INTRADAY_FNO_CLUSTER"

    assert SignalOutcomeStatusEnum.ACTIVE == "ACTIVE"


def test_format_fno_summary():
    signals = [
        {
            "symbol": "RELIANCE",
            "action": "BUY",
            "entry_price": 2500.0,
            "target_price": 2550.0,
            "stop_loss": 2480.0,
            "confidence": 0.85,
            "indicators": {"fno_buildup": "LONG_BUILDUP", "pcr": 1.2},
            "option_contract": {
                "strike_price": 2520.0,
                "option_type": "CE",
                "expiry_date": "2026-10-29",
                "recommended_action": "BUY_CALL",
            },
        }
    ]
    summary = format_fno_summary(signals, as_of="2026-09-28", mode="INTRADAY")
    assert "<b>F&O Signals (Intraday Update) — 2026-09-28</b>" in summary
    assert "RELIANCE" in summary
    assert "BUY" in summary


def test_format_research_signal_card():
    candidate = {
        "symbol": "TCS",
        "action": "BUY",
        "strategy_type": "RESEARCH_CONFLUENCE",
        "timeframe": "SWING",
        "entry_price": 3500.0,
        "target_price": 3650.0,
        "stop_loss": 3420.0,
        "confidence": 0.82,
        "metadata": {
            "composite_score": 0.74,
            "tech_score": 0.80,
            "delivery_score": 0.65,
            "fno_score": 0.70,
            "ltc_pattern": "LTC_POWER_TREND_BUY",
            "delivery_pattern": "DELIVERY_CROSSOVER",
            "fno_pattern": "LONG_BUILDUP",
        },
    }
    card = format_research_signal_card(candidate, as_of=dt.date(2026, 9, 28))
    assert "RESEARCH BUY: TCS" in card
    assert "SWING" in card
    assert "0.74" in card
    assert "LTC_POWER_TREND_BUY" in card
