"""The target and stop stored for a signal that left them empty (30 Oct 2026)."""

import pytest

from tb_utils.persistence.signal_writer import resolve_levels


class TestDefaults:
    def test_an_ordinary_buy_without_levels_gets_the_old_defaults(self):
        target, stop = resolve_levels("BUY", 100.0, 0.0, 0.0)
        assert (round(target, 2), round(stop, 2)) == (102.0, 98.5)

    def test_an_ordinary_sell_without_levels_gets_the_mirror_image(self):
        target, stop = resolve_levels("SELL", 100.0, 0.0, 0.0)
        assert (round(target, 2), round(stop, 2)) == (98.0, 101.5)

    def test_levels_the_signal_supplied_are_kept(self):
        assert resolve_levels("BUY", 100.0, 108.0, 96.0) == (108.0, 96.0)

    def test_a_watch_signal_references_its_entry(self):
        assert resolve_levels("WATCH", 100.0, 0.0, 0.0) == (100.0, 100.0)


class TestDynamicExit:
    """STC exits on the trend or at 15:00; the +/- 2 % target the writer added was never a plan."""

    @pytest.mark.parametrize("action", ["BUY", "SELL"])
    def test_no_target_is_invented(self, action):
        target, _ = resolve_levels(
            action, 100.0, 0.0, 99.5 if action == "BUY" else 100.5, dynamic_exit=True
        )
        assert target == 0.0

    def test_the_signals_own_stop_is_kept(self):
        assert resolve_levels("SELL", 818.4, 0.0, 822.49, dynamic_exit=True) == (0.0, 822.49)

    def test_a_missing_stop_is_still_filled_because_every_signal_needs_one(self):
        target, stop = resolve_levels("BUY", 100.0, 0.0, 0.0, dynamic_exit=True)
        assert target == 0.0 and round(stop, 2) == 98.5

    def test_a_real_target_on_a_dynamic_signal_is_not_thrown_away(self):
        assert resolve_levels("BUY", 100.0, 105.0, 99.5, dynamic_exit=True) == (105.0, 99.5)
