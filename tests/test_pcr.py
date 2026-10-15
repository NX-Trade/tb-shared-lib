import pytest

from tb_utils.options import (
    PcrZone,
    classify_pcr,
    is_euphoria_risk,
    is_oversold_reversal,
    is_pcr_symbol,
)


@pytest.mark.parametrize(
    "pcr,zone",
    [
        (1.9, PcrZone.HEAVILY_BULLISH),
        (1.6, PcrZone.MODERATELY_BULLISH),  # boundary is exclusive: > 1.6
        (1.3, PcrZone.MODERATELY_BULLISH),
        (1.1, PcrZone.BULLISH),
        (1.0, PcrZone.NEUTRAL),
        (0.9, PcrZone.BEARISH),
        (0.8, PcrZone.BEARISH),
        (0.7, PcrZone.MORE_BEARISH),
        (0.5, PcrZone.MORE_BEARISH),
        (0.4, PcrZone.HEAVILY_BEARISH),
    ],
)
def test_classify_pcr(pcr, zone):
    assert classify_pcr(pcr) is zone


def test_only_indices_are_pcr_symbols():
    assert is_pcr_symbol("NIFTY50")
    assert is_pcr_symbol("banknifty")
    assert not is_pcr_symbol("RELIANCE")


def test_oversold_reversal_only_when_heavily_bearish():
    assert is_oversold_reversal(0.45)
    assert not is_oversold_reversal(0.7)


@pytest.mark.parametrize(
    "pcr,vix,change,expected",
    [
        (1.7, 17.0, 0.5, True),
        (1.7, 17.0, None, True),  # level only when no change is known
        (1.7, 17.0, -0.3, False),  # VIX falling
        (1.7, 15.0, 0.5, False),  # VIX below the warning level
        (1.7, None, 0.5, False),  # no VIX reading
        (1.3, 19.0, 1.0, False),  # PCR not heavily bullish
    ],
)
def test_is_euphoria_risk(pcr, vix, change, expected):
    assert is_euphoria_risk(pcr, vix, change) is expected
