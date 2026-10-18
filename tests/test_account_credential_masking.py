"""Credentials are write-only: settable through the API, never readable back."""

from datetime import UTC, datetime
from types import SimpleNamespace

from tb_utils.schema.account import (
    CREDENTIAL_FIELDS,
    MASK,
    ClientAccountResponse,
    ClientAccountUpdate,
    mask_tail,
)


def row(**over):
    """A client_account row with every credential slot filled."""
    base = {
        "account_id": 1,
        "client_code": "UPSTOX_PRIMARY",
        "client_name": "Primary",
        "broker_type": "UPSTOX",
        "api_key": "560bdeeb-8653-4034-8545-7a7055b5ae12",
        "api_secret": "gipdzxb8pg",
        "redirect_uri": "http://127.0.0.1:8080/callback",
        "token_storage_key": "broker:upstox:access_token:UPSTOX_PRIMARY",
        "broker_client_id": None,
        "phone": "9650063413",
        "pin": "280319",
        "totp_secret": "PFL65K4XWVMIG4NCYUUROKBWXPQOQDO4",
        "extra_credentials": None,
        "allocated_capital": 100000,
        "max_risk_per_trade_pct": 0.01,
        "max_active_trades": 2,
        "daily_max_loss_limit": None,
        "monthly_max_loss_limit": None,
        "is_active": 1,
        "is_paper": True,
        "is_halted": False,
        "orders_disabled": False,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    base.update(over)
    return SimpleNamespace(**base)


def test_no_secret_survives_serialisation():
    out = ClientAccountResponse.model_validate(row()).model_dump()

    leaked = {"gipdzxb8pg", "280319", "PFL65K4XWVMIG4NCYUUROKBWXPQOQDO4"}
    assert not leaked & {str(v) for v in out.values()}
    assert out["api_secret"] == out["pin"] == out["totp_secret"] == MASK


def test_a_key_keeps_its_tail_so_two_keys_can_be_told_apart():
    out = ClientAccountResponse.model_validate(row()).model_dump()

    assert out["api_key"].endswith("ae12") and out["api_key"].startswith(MASK)
    assert "560bdeeb" not in out["api_key"]
    assert out["phone"].endswith("3413") and "965006" not in out["phone"]


def test_the_ui_is_told_which_slots_are_filled():
    out = ClientAccountResponse.model_validate(row(pin=None, broker_client_id="A123")).model_dump()

    assert out["has_api_key"] and out["has_api_secret"] and out["has_totp_secret"]
    assert out["has_pin"] is False and out["pin"] is None
    assert out["has_broker_client_id"] is True


def test_the_legacy_blob_shows_its_keys_but_not_its_values():
    legacy = row(extra_credentials={"MOBILE": "9650063413", "TOTP_SECRET": "SEED"})

    out = ClientAccountResponse.model_validate(legacy).model_dump()

    assert set(out["extra_credentials"]) == {"MOBILE", "TOTP_SECRET"}
    assert set(out["extra_credentials"].values()) == {MASK}


def test_fields_that_are_not_credentials_are_untouched():
    out = ClientAccountResponse.model_validate(row()).model_dump()

    assert out["client_code"] == "UPSTOX_PRIMARY"
    assert out["redirect_uri"] == "http://127.0.0.1:8080/callback"
    assert out["token_storage_key"] == "broker:upstox:access_token:UPSTOX_PRIMARY"


# ── Writing back ─────────────────────────────────────────────────────────


def test_an_echoed_mask_is_not_written_over_the_stored_secret():
    # Exactly what a form round-trips when the operator did not retype it.
    update = ClientAccountUpdate(api_secret=MASK, api_key=f"{MASK}ae12", client_name="Renamed")

    applied = update.model_dump(exclude_unset=True)

    assert applied == {"client_name": "Renamed"}


def test_a_blank_credential_means_keep_the_stored_one():
    update = ClientAccountUpdate(api_secret="", pin=None, totp_secret="   New  ")

    applied = update.model_dump(exclude_unset=True)

    assert "api_secret" not in applied and "pin" not in applied
    assert applied["totp_secret"] == "   New  "


def test_a_real_new_secret_is_written():
    update = ClientAccountUpdate(api_secret="brand_new", pin="999999")

    applied = update.model_dump(exclude_unset=True)

    assert applied == {"api_secret": "brand_new", "pin": "999999"}


def test_non_credential_fields_may_still_be_cleared():
    update = ClientAccountUpdate(daily_max_loss_limit=None, max_active_trades=5)

    applied = update.model_dump(exclude_unset=True)

    assert applied == {"daily_max_loss_limit": None, "max_active_trades": 5}


def test_mask_tail_hides_a_short_value_completely():
    assert mask_tail("abcd") == MASK
    assert mask_tail("") is None and mask_tail(None) is None


def test_every_credential_field_is_masked_flagged_and_settable():
    """A new credential must be masked and reported, not quietly readable."""
    filled = ClientAccountResponse.model_validate(
        row(broker_client_id="ANGEL123", extra_credentials=None)
    )

    for name in CREDENTIAL_FIELDS:
        value = getattr(filled, name)
        assert value is None or MASK in value, f"{name} came back unmasked: {value}"
        assert getattr(filled, f"has_{name}") is bool(value), f"{name} has no usable flag"
        # And it can still be written, otherwise it could never be set at all.
        assert ClientAccountUpdate(**{name: "typed"}).model_dump(exclude_unset=True) == {
            name: "typed"
        }
