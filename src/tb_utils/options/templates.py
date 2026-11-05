"""Named option structures, defined once and shared by the builder picker and the generator.

A template is a list of leg specs expressed as **strike steps from an anchor** — never as fixed
strikes — so one definition fits any underlying and any strike spacing. Resolving it against the
listed strikes of an expiry yields concrete legs; pricing them is the caller's job (the backend
prices from the latest chain, ``payoff.py`` does the maths).

Pure functions only: no DB, no Redis, no HTTP. Design:
tb-ai-brain/upcoming/OPTION_STRATEGY_BUILDER_AND_MARGIN_DESIGN.md §8A.1 and §8B.5.

Anchor and width
----------------
* ``anchor`` is where offset 0 sits: ``ATM`` (listed strike nearest spot) or ``TARGET`` (listed
  strike nearest the view's target price, falling back to a shift from ATM when none is given).
* ``width`` is the spread width in **listed-strike steps**; a leg's strike is the one
  ``offset × width`` steps from the anchor. Steps count listed strikes, so uneven spacing and
  gaps are handled by construction.
* A required strike outside the listed range raises :class:`TemplateError` — a structure is never
  silently truncated.

Every template here has a capped loss: structures with an uncovered short leg (short straddles
and strangles, ratio spreads) are deliberately not offered anywhere, and tests assert both the
payoff and the leg cover so one cannot be added by accident.
"""

# stdlib
from bisect import bisect_left
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Optional

BUY = "BUY"
SELL = "SELL"
CE = "CE"
PE = "PE"

BULLISH = "BULLISH"
BEARISH = "BEARISH"
NEUTRAL = "NEUTRAL"

DEBIT = "DEBIT"
CREDIT = "CREDIT"
MIXED = "MIXED"

ATM = "ATM"
TARGET = "TARGET"


class TemplateError(ValueError):
    """A template cannot be resolved against the listed strikes."""


@dataclass(frozen=True)
class TemplateLeg:
    action: str
    option_type: str
    offset: int  # in widths from the anchor; negative is below
    lots: int = 1


@dataclass(frozen=True)
class Template:  # pylint: disable=too-many-instance-attributes
    key: str
    label: str
    bias: str
    family: str
    legs: tuple[TemplateLeg, ...]
    description: str
    anchor: str = ATM
    needs_target: bool = False  # True: the body is placed at the view's target, so one is required
    anchor_shift: int = 0  # widths from ATM when anchor is TARGET but no target was given
    defined_risk: bool = True
    generator_eligible: bool = True  # the §8B generator only proposes defined-risk directional ones


# What a structure *is*, independent of direction and wing choice. The idea generator picks at
# most one basket per shape so three results are three different risk profiles, not one spread
# shifted a strike.
VERTICAL = "vertical"
BUTTERFLY = "butterfly"
BROKEN_WING = "broken_wing"
CONDOR = "condor"
FLY = "fly"
STRADDLE = "straddle"
STRANGLE = "strangle"

_SHAPE_BY_KEY = {
    "bull_call_spread": VERTICAL,
    "bear_put_spread": VERTICAL,
    "bull_put_spread": VERTICAL,
    "bear_call_spread": VERTICAL,
    "call_butterfly": BUTTERFLY,
    "put_butterfly": BUTTERFLY,
    "bullish_broken_wing_butterfly": BROKEN_WING,
    "bearish_broken_wing_butterfly": BROKEN_WING,
    "bullish_iron_condor": CONDOR,
    "bearish_iron_condor": CONDOR,
    "iron_condor": CONDOR,
    "bullish_iron_fly": FLY,
    "bearish_iron_fly": FLY,
    "iron_fly": FLY,
    "long_straddle": STRADDLE,
    "long_strangle": STRANGLE,
}


def shape_of(template: Template) -> str:
    """The structure's shape (vertical, butterfly, condor, ...), for diversity and display."""
    return _SHAPE_BY_KEY[template.key]


@dataclass(frozen=True)
class ResolvedLeg:
    action: str
    option_type: str
    strike: float
    lots: int


def _leg(action: str, option_type: str, offset: int, lots: int = 1) -> TemplateLeg:
    return TemplateLeg(action, option_type, offset, lots)


_TEMPLATES: tuple[Template, ...] = (
    # ── Verticals ────────────────────────────────────────────────────────────
    Template(
        "bull_call_spread",
        "Bull Call Spread",
        BULLISH,
        DEBIT,
        (_leg(BUY, CE, 0), _leg(SELL, CE, 1)),
        "Buy the ATM call, sell the call one width up. Pays for a rise to the short strike.",
    ),
    Template(
        "bear_put_spread",
        "Bear Put Spread",
        BEARISH,
        DEBIT,
        (_leg(BUY, PE, 0), _leg(SELL, PE, -1)),
        "Buy the ATM put, sell the put one width down. Pays for a fall to the short strike.",
    ),
    Template(
        "bull_put_spread",
        "Bull Put Spread",
        BULLISH,
        CREDIT,
        (_leg(SELL, PE, -1), _leg(BUY, PE, -2)),
        "Sell a put below the market and buy one further down. Keeps the credit if spot holds.",
    ),
    Template(
        "bear_call_spread",
        "Bear Call Spread",
        BEARISH,
        CREDIT,
        (_leg(SELL, CE, 1), _leg(BUY, CE, 2)),
        "Sell a call above the market and buy one further up. Keeps the credit if spot holds.",
    ),
    # ── Butterflies (body at the target) ─────────────────────────────────────
    Template(
        "call_butterfly",
        "Call Butterfly",
        BULLISH,
        DEBIT,
        (_leg(BUY, CE, -1), _leg(SELL, CE, 0, 2), _leg(BUY, CE, 1)),
        "Buy near the money, sell two strikes costing 40-50% as much, buy a wing at 30% or less.",
        anchor=TARGET,
        needs_target=True,
        anchor_shift=1,
    ),
    Template(
        "put_butterfly",
        "Put Butterfly",
        BEARISH,
        DEBIT,
        (_leg(BUY, PE, 1), _leg(SELL, PE, 0, 2), _leg(BUY, PE, -1)),
        "Buy near the money, sell two strikes costing 40-50% as much, buy a wing at 30% or less.",
        anchor=TARGET,
        needs_target=True,
        anchor_shift=-1,
    ),
    Template(
        "bullish_broken_wing_butterfly",
        "Bullish Broken-Wing Butterfly",
        BULLISH,
        MIXED,
        (_leg(BUY, CE, -1), _leg(SELL, CE, 0, 2), _leg(BUY, CE, 2)),
        "Call butterfly with the upper wing twice as far. Near-zero cost; the risk sits above.",
        anchor=TARGET,
        needs_target=True,
        anchor_shift=1,
    ),
    Template(
        "bearish_broken_wing_butterfly",
        "Bearish Broken-Wing Butterfly",
        BEARISH,
        MIXED,
        (_leg(BUY, PE, 1), _leg(SELL, PE, 0, 2), _leg(BUY, PE, -2)),
        "Put butterfly with the lower wing twice as far. Near-zero cost; the risk sits below.",
        anchor=TARGET,
        needs_target=True,
        anchor_shift=-1,
    ),
    # ── Condors and flies (credit) ───────────────────────────────────────────
    Template(
        "bullish_iron_condor",
        "Bullish Skewed Iron Condor",
        BULLISH,
        CREDIT,
        (_leg(SELL, PE, -1), _leg(BUY, PE, -2), _leg(SELL, CE, 2), _leg(BUY, CE, 3)),
        "Put side tight, call side wide: more credit on the side the view says is safe.",
    ),
    Template(
        "bearish_iron_condor",
        "Bearish Skewed Iron Condor",
        BEARISH,
        CREDIT,
        (_leg(SELL, CE, 1), _leg(BUY, CE, 2), _leg(SELL, PE, -2), _leg(BUY, PE, -3)),
        "Call side tight, put side wide: more credit on the side the view says is safe.",
    ),
    Template(
        "bullish_iron_fly",
        "Bullish Iron Fly",
        BULLISH,
        CREDIT,
        (_leg(SELL, CE, 0), _leg(SELL, PE, 0), _leg(BUY, CE, 1), _leg(BUY, PE, -1)),
        "Short straddle with wings, body at the target or one width above spot.",
        anchor=TARGET,
        anchor_shift=1,
    ),
    Template(
        "bearish_iron_fly",
        "Bearish Iron Fly",
        BEARISH,
        CREDIT,
        (_leg(SELL, CE, 0), _leg(SELL, PE, 0), _leg(BUY, CE, 1), _leg(BUY, PE, -1)),
        "Short straddle with wings, body at the target or one width below spot.",
        anchor=TARGET,
        anchor_shift=-1,
    ),
    # ── Non-directional: builder picker only ─────────────────────────────────
    Template(
        "iron_condor",
        "Iron Condor",
        NEUTRAL,
        CREDIT,
        (_leg(SELL, PE, -1), _leg(BUY, PE, -2), _leg(SELL, CE, 1), _leg(BUY, CE, 2)),
        "Short strangle with protective wings. Profits if spot stays between the short strikes.",
        generator_eligible=False,
    ),
    Template(
        "iron_fly",
        "Iron Fly",
        NEUTRAL,
        CREDIT,
        (_leg(SELL, CE, 0), _leg(SELL, PE, 0), _leg(BUY, CE, 1), _leg(BUY, PE, -1)),
        "Short ATM straddle with protective wings.",
        generator_eligible=False,
    ),
    Template(
        "long_straddle",
        "Long Straddle",
        NEUTRAL,
        DEBIT,
        (_leg(BUY, CE, 0), _leg(BUY, PE, 0)),
        "Buy the ATM call and put. Profits from a large move either way.",
        generator_eligible=False,
    ),
    Template(
        "long_strangle",
        "Long Strangle",
        NEUTRAL,
        DEBIT,
        (_leg(BUY, CE, 1), _leg(BUY, PE, -1)),
        "Buy an OTM call and put. Cheaper than a straddle, needs a bigger move.",
        generator_eligible=False,
    ),
)

_BY_KEY = {t.key: t for t in _TEMPLATES}


def get_template(key: str) -> Template:
    try:
        return _BY_KEY[key]
    except KeyError:
        raise TemplateError(f"unknown template {key!r}") from None


def list_templates(bias: Optional[str] = None, generator_only: bool = False) -> list[Template]:
    """Registered templates, optionally filtered to one bias or to generator-eligible ones."""
    return [
        t
        for t in _TEMPLATES
        if (bias is None or t.bias == bias) and (not generator_only or t.generator_eligible)
    ]


def _nearest_index(strikes: Sequence[float], price: float) -> int:
    """Index of the listed strike closest to ``price``; the lower one on an exact tie."""
    pos = bisect_left(strikes, price)
    if pos == 0:
        return 0
    if pos == len(strikes):
        return len(strikes) - 1
    below, above = strikes[pos - 1], strikes[pos]
    return pos - 1 if price - below <= above - price else pos


def resolve_template(
    template: Template,
    strikes: Sequence[float],
    spot: float,
    width: int = 1,
    target: Optional[float] = None,
) -> list[ResolvedLeg]:
    """Concrete legs for ``template`` on the listed ``strikes`` of one expiry.

    ``width`` is in listed-strike steps. A TARGET-anchored template uses ``target`` when given,
    otherwise sits ``anchor_shift × width`` steps from ATM; one with ``needs_target`` requires it.
    Raises :class:`TemplateError` if a required strike is not listed.
    """
    if width < 1:
        raise TemplateError("width must be at least 1 strike step")
    if template.needs_target and target is None:
        raise TemplateError(f"{template.label} places its body at the target; a target is required")
    listed = sorted({float(s) for s in strikes})
    if not listed:
        raise TemplateError("no listed strikes")

    atm = _nearest_index(listed, spot)
    if template.anchor == TARGET and target is not None:
        anchor = _nearest_index(listed, target)
    elif template.anchor == TARGET:
        anchor = atm + template.anchor_shift * width
    else:
        anchor = atm

    resolved = []
    for leg in template.legs:
        idx = anchor + leg.offset * width
        if not 0 <= idx < len(listed):
            raise TemplateError(
                f"{template.label}: strike {leg.offset * width:+d} steps from the anchor "
                f"is outside the listed range {listed[0]:g}-{listed[-1]:g}"
            )
        resolved.append(ResolvedLeg(leg.action, leg.option_type, listed[idx], leg.lots))
    if len({(leg.option_type, leg.strike, leg.action) for leg in resolved}) != len(resolved):
        raise TemplateError(f"{template.label}: width {width} collapses two legs onto one strike")
    return resolved


# A 1:2:1 butterfly is placed by premium, not by equal strike steps. The two sold strikes sit where
# the option costs 40-50% of the first buy, the far wing where it costs at most 30%. Sold legs that
# are nearly as dear as the long (ATM-ish body) gain and lose value as fast as the long does, so in
# a volatility spike they eat the gain; further out they are slower and the structure keeps it.
BUTTERFLY_BODY_RATIO = (0.40, 0.50)
BUTTERFLY_WING_MAX_RATIO = 0.30


def _body_strike(
    beyond: Sequence[float], premiums: Mapping[float, float], first: float
) -> Optional[int]:
    """Index in ``beyond`` of the strike nearest 45% of the first buy, inside the 40-50% band."""
    low, high = BUTTERFLY_BODY_RATIO
    middle = (low + high) / 2
    best, best_gap = None, None
    for i, strike in enumerate(beyond):
        ratio = premiums.get(strike, 0.0) / first
        if low <= ratio <= high and (best_gap is None or abs(ratio - middle) < best_gap):
            best, best_gap = i, abs(ratio - middle)
    return best


def _wing_strike(
    beyond: Sequence[float], premiums: Mapping[float, float], first: float
) -> Optional[int]:
    """Index in ``beyond`` of the dearest strike still at or under 30% of the first buy."""
    best, best_ratio = None, None
    for i, strike in enumerate(beyond):
        ratio = premiums.get(strike, 0.0) / first
        if 0 < ratio <= BUTTERFLY_WING_MAX_RATIO and (best_ratio is None or ratio > best_ratio):
            best, best_ratio = i, ratio
    return best


def resolve_butterfly_by_premium(
    template: Template,
    strikes: Sequence[float],
    premiums: Mapping[float, float],
    spot: float,
    width: int = 1,
    target: Optional[float] = None,
) -> list[ResolvedLeg]:
    """A call or put butterfly whose sold and far strikes are chosen by premium.

    The first buy is where :func:`resolve_template` puts it. The body (sold twice) is the listed
    strike further out whose premium is closest to 45% of the first buy's, inside 40-50%. The far
    wing is the dearest strike beyond the body at or under 30%. ``premiums`` is one price per
    strike for this template's option type (the caller chooses mid or last). The wings need not be
    equally far from the body: the loss stays capped either way (1 + 1 bought, 2 sold). Raises
    :class:`TemplateError` when no strike meets a band, instead of drifting outside it.
    """
    if template.key not in ("call_butterfly", "put_butterfly"):
        raise TemplateError(f"{template.label} is not a 1:2:1 butterfly")
    legs = resolve_template(template, strikes, spot, width, target)
    first = legs[0]
    first_premium = premiums.get(first.strike, 0.0)
    if first_premium <= 0:
        raise TemplateError(f"{template.label}: the first buy at {first.strike:g} has no price")

    listed = sorted({float(s) for s in strikes})
    outward = first.option_type == CE
    beyond = [s for s in listed if (s > first.strike if outward else s < first.strike)]
    if not outward:
        beyond.reverse()  # nearest the first buy first, whichever way the strikes run

    body_i = _body_strike(beyond, premiums, first_premium)
    if body_i is None:
        low, high = BUTTERFLY_BODY_RATIO
        raise TemplateError(
            f"{template.label}: no strike costs {low:.0%}-{high:.0%} of the {first.strike:g} buy"
            f" ({first_premium:g})"
        )
    wing_i = _wing_strike(beyond[body_i + 1 :], premiums, first_premium)
    if wing_i is None:
        raise TemplateError(
            f"{template.label}: no strike beyond {beyond[body_i]:g} costs "
            f"{BUTTERFLY_WING_MAX_RATIO:.0%} or less of the {first.strike:g} buy"
        )
    body, wing = beyond[body_i], beyond[body_i + 1 + wing_i]
    return [
        first,
        ResolvedLeg(SELL, first.option_type, body, 2),
        ResolvedLeg(BUY, first.option_type, wing, 1),
    ]
