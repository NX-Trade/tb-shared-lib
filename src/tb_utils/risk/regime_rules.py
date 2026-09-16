"""Single source of truth for regime-dependent position sizing rules.

Previously duplicated between ``tb-execution/risk/position_sizer.py`` (live
sizing) and ``tb-signal-bot/backtest/walk_forward.py`` (backtest simulation),
which risked silent drift if one copy was tuned without updating the other.
Both now import ``REGIME_RULES`` from here.

Regime index → label:
    0 = CALM        (full allocation)
    1 = TRANSITION  (moderate risk-off)
    2 = TURBULENT   (defensive)
"""

from typing import Any

REGIME_RULES: dict[int, dict[str, Any]] = {
    0: {
        "label": "CALM",
        "multiplier": 1.0,
        "max_positions": 5,
        "capital_pct": 0.19,
        "max_deployed": 0.95,
    },
    1: {
        "label": "TRANSITION",
        "multiplier": 0.7,
        "max_positions": 4,
        "capital_pct": 0.16,
        "max_deployed": 0.65,
    },
    2: {
        "label": "TURBULENT",
        "multiplier": 0.3,
        "max_positions": 2,
        "capital_pct": 0.15,
        "max_deployed": 0.30,
    },
}

# Default ATR stop-distance multiplier used by both the live sizer and the
# backtest simulation when a service-level override isn't configured.
ATR_STOP_MULTIPLIER: float = 2.0
