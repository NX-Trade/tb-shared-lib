"""Gamma exposure: shape of the by-strike figures, the sign convention and the flip level."""

import math

import pytest

from tb_utils.options.gex import GexContract, bs_gamma, compute_gex, net_gex_at

SPOT = 1000.0
IV = 20.0
DAYS = 7.0


def chain(call_oi=100_000, put_oi=100_000, strikes=range(900, 1101, 20)):
    contracts = []
    for k in strikes:
        contracts.append(GexContract(float(k), "CE", call_oi, IV))
        contracts.append(GexContract(float(k), "PE", put_oi, IV))
    return contracts


class TestBsGamma:
    def test_peaks_at_the_money_and_falls_away(self):
        atm = bs_gamma(SPOT, 1000, DAYS / 365, IV)
        assert atm > bs_gamma(SPOT, 1060, DAYS / 365, IV) > bs_gamma(SPOT, 1150, DAYS / 365, IV)
        assert atm > bs_gamma(SPOT, 940, DAYS / 365, IV)

    def test_grows_as_expiry_nears(self):
        assert bs_gamma(SPOT, 1000, 1 / 365, IV) > bs_gamma(SPOT, 1000, 30 / 365, IV)

    def test_matches_the_closed_form(self):
        years, sigma, rate = 30 / 365, 0.25, 0.0675
        d1 = (math.log(1.0) + (rate + 0.5 * sigma**2) * years) / (sigma * math.sqrt(years))
        expected = (
            math.exp(-0.5 * d1**2) / math.sqrt(2 * math.pi) / (SPOT * sigma * math.sqrt(years))
        )
        assert bs_gamma(SPOT, SPOT, years, 25.0) == pytest.approx(expected)

    @pytest.mark.parametrize(
        "args", [(0, 1000, 0.1, 20), (1000, 0, 0.1, 20), (1000, 1000, 0, 20), (1000, 1000, 0.1, 0)]
    )
    def test_degenerate_inputs_give_zero(self, args):
        assert bs_gamma(*args) == 0.0


class TestComputeGex:
    def test_calls_count_positive_and_puts_negative(self):
        result = compute_gex(chain(), SPOT, DAYS)
        assert all(s.call_gex > 0 for s in result.by_strike)
        assert all(s.put_gex < 0 for s in result.by_strike)

    def test_equal_call_and_put_oi_nets_to_about_zero_at_the_money(self):
        atm = next(s for s in compute_gex(chain(), SPOT, DAYS).by_strike if s.strike == 1000)
        assert atm.net_gex == pytest.approx(0, abs=abs(atm.call_gex) * 0.05)

    def test_more_call_than_put_interest_is_positive_gex(self):
        assert compute_gex(chain(call_oi=300_000, put_oi=100_000), SPOT, DAYS).total > 0
        assert compute_gex(chain(call_oi=100_000, put_oi=300_000), SPOT, DAYS).total < 0

    def test_gex_is_concentrated_near_the_money(self):
        by = {s.strike: s for s in compute_gex(chain(), SPOT, DAYS).by_strike}
        assert by[1000].call_gex > by[1100].call_gex
        assert by[1000].call_gex > by[900].call_gex

    def test_walls_are_the_strikes_with_the_most_call_and_put_gex(self):
        contracts = chain() + [
            GexContract(1040.0, "CE", 2_000_000, IV),
            GexContract(960.0, "PE", 2_000_000, IV),
        ]
        result = compute_gex(contracts, SPOT, DAYS)
        assert result.call_wall == 1040.0
        assert result.put_wall == 960.0

    def test_empty_interest_is_skipped(self):
        assert not compute_gex([GexContract(1000.0, "CE", 0, IV)], SPOT, DAYS).by_strike

    def test_broker_gamma_is_used_only_without_an_iv(self):
        with_gamma = compute_gex(
            [GexContract(1000.0, "CE", 100_000, None, gamma=0.004)], SPOT, DAYS
        )
        assert with_gamma.by_strike[0].call_gex == pytest.approx(
            0.004 * 100_000 * SPOT * SPOT * 0.01, rel=1e-3
        )
        nothing = compute_gex([GexContract(1000.0, "CE", 100_000, None)], SPOT, DAYS)
        assert nothing.by_strike[0].call_gex == 0


class TestFlipLevel:
    def _skewed(self):
        """Put interest below spot, call interest above: net GEX is negative low, positive high."""
        contracts = []
        for k in range(900, 1101, 20):
            contracts.append(GexContract(float(k), "PE", 400_000 if k <= 1000 else 20_000, IV))
            contracts.append(GexContract(float(k), "CE", 20_000 if k <= 1000 else 400_000, IV))
        return contracts

    def test_flip_is_where_the_profile_changes_sign(self):
        result = compute_gex(self._skewed(), SPOT, DAYS)
        assert result.flip is not None
        below = net_gex_at(self._skewed(), result.flip * 0.97, DAYS / 365, SPOT)
        above = net_gex_at(self._skewed(), result.flip * 1.03, DAYS / 365, SPOT)
        assert below < 0 < above

    def test_no_flip_when_gex_keeps_one_sign(self):
        assert compute_gex(chain(call_oi=500_000, put_oi=10_000), SPOT, DAYS).flip is None

    def test_the_flip_nearest_to_spot_is_chosen(self):
        result = compute_gex(self._skewed(), SPOT, DAYS)
        assert abs(result.flip - SPOT) <= SPOT * 0.08

    def test_the_profile_covers_the_span_around_spot(self):
        result = compute_gex(chain(), SPOT, DAYS, span=0.05, steps=11)
        assert len(result.profile) == 11
        assert result.profile[0][0] == pytest.approx(950.0)
        assert result.profile[-1][0] == pytest.approx(1050.0)

    def test_a_zero_spot_gives_an_empty_profile(self):
        assert not compute_gex(chain(), 0.0, DAYS).profile
