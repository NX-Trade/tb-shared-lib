"""option_basket_idea / option_idea_skip: shape, uniqueness, response schemas, migration chain."""

import datetime as dt
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from tb_utils.models import OptionBasketIdea, OptionIdeaSkip
from tb_utils.schema import (
    OptionBasketIdeaResponse,
    OptionIdeasForUnderlying,
    OptionIdeaSkipResponse,
)

ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "alembic"
NOW = dt.datetime(2026, 10, 22, 13, 30, tzinfo=dt.UTC)


def _idea_row(**overrides):
    row = {
        "id": 1,
        "generated_for": dt.date(2026, 10, 22),
        "underlying": "ACME",
        "kind": "STOCK",
        "bias": "BULLISH",
        "conviction": 0.7,
        "template": "bull_call_spread",
        "template_label": "Bull Call Spread",
        "shape": "vertical",
        "family": "DEBIT",
        "slot_role": "CONSERVATIVE",
        "expiry_date": dt.date(2026, 11, 26),
        "dte": 35,
        "lot_size": 100,
        "legs": [
            {
                "action": "BUY",
                "option_type": "CE",
                "strike": 1000.0,
                "expiry": "2026-11-26",
                "lots": 1,
            }
        ],
        "analysis": {"net_premium": -1500.0},
        "score": 0.62,
        "ev_view": 780.0,
        "pop_view": 0.64,
        "max_profit": 3500.0,
        "max_loss": 1500.0,
        "return_on_risk": 0.52,
        "view_source": "RESEARCH_CONFLUENCE",
        "view_as_of": NOW,
        "sigma_source": "ATM_IV",
        "chain_ts": NOW,
        "analytics_version": "ideas/1.32",
        "status": "ACTIVE",
        "created_at": NOW,
    }
    return {**row, **overrides}


class TestTables:
    def test_idea_is_unique_per_day_underlying_template_and_expiry(self):
        unique = {
            tuple(c.name for c in constraint.columns)
            for constraint in OptionBasketIdea.__table__.constraints
            if constraint.name == "uq_option_basket_idea"
        }
        assert unique == {("generated_for", "underlying", "template", "expiry_date")}

    def test_idea_status_defaults_to_active_and_outcome_is_optional(self):
        table = OptionBasketIdea.__table__
        assert str(table.c.status.server_default.arg) == "ACTIVE"
        assert table.c.outcome.nullable and not table.c.legs.nullable

    def test_skip_is_keyed_by_day_and_underlying(self):
        assert [c.name for c in OptionIdeaSkip.__table__.primary_key.columns] == [
            "generated_for",
            "underlying",
        ]


class TestSchemas:
    def test_idea_response_round_trips_the_builder_leg_input(self):
        idea = OptionBasketIdeaResponse(**_idea_row())
        assert idea.legs[0]["lots"] == 1 and idea.max_loss == 1500.0

    def test_group_carries_ideas_or_the_reason_for_none(self):
        skip = OptionIdeaSkipResponse(
            generated_for=dt.date(2026, 10, 22),
            underlying="ACME",
            kind="STOCK",
            code="NO_TARGET",
            message="no target",
        )
        group = OptionIdeasForUnderlying(underlying="ACME", kind="STOCK", skip=skip)
        assert not group.ideas and group.skip.code == "NO_TARGET"

    def test_requires_the_provenance_fields(self):
        row = _idea_row()
        del row["view_source"]
        with pytest.raises(ValueError):
            OptionBasketIdeaResponse(**row)


class TestMigrationChain:
    @staticmethod
    def _scripts() -> ScriptDirectory:
        config = Config()
        config.set_main_option("script_location", str(ALEMBIC_DIR))
        return ScriptDirectory.from_config(config)

    def test_there_is_a_single_head(self):
        """A second head would make `alembic upgrade head` refuse to run on optiplex."""
        assert len(self._scripts().get_heads()) == 1

    def test_the_idea_migration_follows_the_lots_migration(self):
        assert self._scripts().get_revision("p1e2f3a4b5c6").down_revision == "o1c2d3e4f5a6"
