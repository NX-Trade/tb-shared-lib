"""System-generated option basket ideas: up to three per underlying, from a directional view.

A *selector* over analysed candidates, not a new source of maths: every number comes from
:mod:`payoff`, :mod:`probability`, :mod:`margin` and the :mod:`templates` registry. Pure — no DB,
no Redis, no HTTP; callers pass plain dataclasses in and persist the result.
Design: tb-ai-brain/upcoming/OPTION_STRATEGY_BUILDER_AND_MARGIN_DESIGN.md §8B.

Principles (§8B.1)
------------------
* **No view, no idea.** A neutral or missing view, a target on the wrong side of spot, or a stale
  chain produces *zero* baskets and a named reason. An empty result is honest.
* **Defined risk only.** Only ``generator_eligible`` templates are tried (covered shorts,
  2–4 legs), and a candidate whose expiry loss is not finite is dropped regardless.
* **Analysis, not orders.** Nothing here can place anything.
* **Entry is priced where it would trade:** BUY at the ask, SELL at the bid. A leg without a
  two-sided quote, with no IV, or with thin open interest is rejected, never guessed.

Pipeline
--------
expiry (nearest with enough days) → candidates (template × width) → hard filters (liquidity,
slippage, reachability, negative edge at the view) → score → greedy diversity → roles.

Ranking uses the **expected value at the view** (``probability.view_tilt``), not at the market:
under the market's own distribution every fairly priced basket is worth about minus its costs
and they cannot be told apart (design open item M-2).
"""
# pylint: disable=too-many-instance-attributes,too-many-return-statements

# stdlib
import datetime as dt
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Optional

# internal
from tb_utils.greeks import DEFAULT_RISK_FREE_RATE
from tb_utils.options.margin import INDEX, STOCK, Sigma, estimate_margin, sigma_from_iv
from tb_utils.options.payoff import (
    Leg,
    breakevens,
    default_spot_range,
    max_profit_loss,
    net_greeks,
    net_premium,
    payoff_curve,
)
from tb_utils.options.probability import analyze_probability, view_tilt
from tb_utils.options.templates import (
    BEARISH,
    BULLISH,
    CREDIT,
    DEBIT,
    ResolvedLeg,
    Template,
    TemplateError,
    list_templates,
    resolve_template,
    shape_of,
)
from tb_utils.time import IST

BUY = "BUY"
SELL = "SELL"

ROLE_CONSERVATIVE = "CONSERVATIVE"  # highest probability of profit
ROLE_BALANCED = "BALANCED"  # best expected value per rupee at risk
ROLE_TARGETED = "TARGETED"  # pays the most for the least if the target is hit

EXPIRY_CLOSE = dt.time(15, 30)
CURVE_POINTS = 41


# ── Inputs ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DirectionalView:
    """A view the generator consumes; it never decides one."""

    underlying: str
    bias: str  # BULLISH | BEARISH
    conviction: float  # 0..1
    horizon_days: int
    entry: float
    target: Optional[float]
    stop: Optional[float]
    source: str  # e.g. RESEARCH_CONFLUENCE
    as_of: dt.datetime


@dataclass(frozen=True)
class Quote:
    """One contract of a chain snapshot."""

    expiry: dt.date
    strike: float
    option_type: str  # CE | PE
    bid: Optional[float]
    ask: Optional[float]
    ltp: Optional[float]
    open_interest: int
    volume: int
    iv: Optional[float]  # percent


@dataclass(frozen=True)
class ChainData:
    """One coherent snapshot of an underlying's chain."""

    symbol: str
    ts: dt.datetime
    spot: float
    lot_size: int
    is_index: bool
    quotes: Sequence[Quote]
    sigma: Optional[Sigma] = None  # EWMA volatility of the underlying; IV is used when None


@dataclass(frozen=True)
class IdeaConfig:
    """Tunables: starting values to calibrate against outcome tracking, not hand-tune (I-2)."""

    min_dte: int = 7  # never expiry week
    min_conviction: float = 0.4
    widths: tuple[int, ...] = (1, 2)  # in listed-strike steps
    min_open_interest: int = 300
    max_slippage_pct: float = 0.15  # round-trip exit cost over max profit
    max_move_sigmas: float = 1.5  # max profit may not sit further than this from spot
    max_chain_age: dt.timedelta = dt.timedelta(hours=30)
    iv_rank_low: float = 30.0  # below: debit structures preferred
    iv_rank_high: float = 60.0  # above: credit structures preferred
    family_bonus: float = 0.05
    max_ideas: int = 3
    # score weights: return on risk, POP, view alignment, slippage, theta drag
    w_return: float = 1.0
    w_pop: float = 0.5
    w_alignment: float = 0.3
    w_slippage: float = 1.0
    w_theta: float = 0.3


# ── Outputs ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IdeaLeg:
    action: str
    option_type: str
    strike: float
    lots: int
    premium: float
    premium_basis: str  # ask | bid | ltp
    iv: float
    bid: Optional[float]
    ask: Optional[float]
    open_interest: int
    volume: int


@dataclass(frozen=True)
class Idea:
    underlying: str
    template: str
    template_label: str
    shape: str
    family: str
    expiry: dt.date
    dte: int
    lot_size: int
    legs: tuple[IdeaLeg, ...]
    net_premium: float  # rupees, whole position; negative is a debit
    max_profit: float
    max_loss: float  # positive magnitude
    breakevens: tuple[float, ...]
    pop_market: float
    ev_market: float
    pop_view: float
    ev_view: float
    return_on_risk: float  # ev_view / max_loss
    slippage: float  # rupees to cross the spread again on exit
    net_delta: float
    margin_estimate: Optional[float]
    sigma_pct: float
    sigma_source: str
    score: float
    rationale: str
    curve: tuple[tuple[float, float], ...]  # expiry payoff, for a sparkline
    role: str = ""


@dataclass(frozen=True)
class Rejection:
    template: str
    width: int
    reason: str


@dataclass(frozen=True)
class Skip:
    """Why an underlying produced no ideas — shown to the user, never silently dropped."""

    code: str
    message: str


@dataclass(frozen=True)
class IdeaSet:
    underlying: str
    ideas: list[Idea] = field(default_factory=list)
    skip: Optional[Skip] = None
    rejections: list[Rejection] = field(default_factory=list)


# ── Context shared by every candidate of one underlying ──────────────────────


@dataclass(frozen=True)
class _Context:
    view: DirectionalView
    chain: ChainData
    config: IdeaConfig
    now: dt.datetime
    expiry: dt.date
    dte: int
    days: float  # fractional days to the expiry close
    atm_iv: float
    sigma_move: float
    strikes: list[float]
    quotes: dict[tuple[float, str], Quote]
    tilt: float
    iv_rank: Optional[float]


def _close(expiry: dt.date) -> dt.datetime:
    return dt.datetime.combine(expiry, EXPIRY_CLOSE, tzinfo=IST)


def _atm_iv(quotes: Sequence[Quote], spot: float) -> Optional[float]:
    quoted = [(abs(q.strike - spot), q.iv) for q in quotes if q.iv and q.iv > 0]
    if not quoted:
        return None
    nearest = min(distance for distance, _ in quoted)
    at_the_money = [iv for distance, iv in quoted if distance == nearest]
    return sum(at_the_money) / len(at_the_money)


def _choose_expiry(chain: ChainData, config: IdeaConfig, view: DirectionalView, today: dt.date):
    """Nearest expiry at least ``max(min_dte, horizon)`` days away, else None."""
    needed = max(config.min_dte, view.horizon_days)
    for expiry in sorted({q.expiry for q in chain.quotes}):
        if (expiry - today).days >= needed:
            return expiry
    return None


def _preconditions(
    view: DirectionalView, chain: ChainData, config: IdeaConfig, now: dt.datetime
) -> Optional[Skip]:
    if view.bias not in (BULLISH, BEARISH):
        return Skip("NO_VIEW", "No directional view for this underlying.")
    if view.conviction < config.min_conviction:
        return Skip(
            "LOW_CONVICTION",
            f"Conviction {view.conviction:.0%} is below the {config.min_conviction:.0%} minimum.",
        )
    if view.target is None or view.target <= 0:
        return Skip("NO_TARGET", "The view carries no target, so a payoff cannot be placed.")
    wrong_side = (view.bias == BULLISH and view.target <= chain.spot) or (
        view.bias == BEARISH and view.target >= chain.spot
    )
    if wrong_side:
        return Skip(
            "TARGET_WRONG_SIDE",
            f"Target {view.target:g} is not {'above' if view.bias == BULLISH else 'below'} "
            f"spot {chain.spot:g}.",
        )
    if chain.spot <= 0 or not chain.quotes:
        return Skip("NO_CHAIN", "No option chain is stored for this underlying.")
    age = now - chain.ts
    if age > config.max_chain_age:
        return Skip("STALE_CHAIN", f"The chain is {age.total_seconds() / 3600:.1f} h old.")
    return None


def _build_context(
    view: DirectionalView,
    chain: ChainData,
    config: IdeaConfig,
    now: dt.datetime,
    iv_rank: Optional[float],
) -> tuple[Optional[_Context], Optional[Skip]]:
    today = now.astimezone(IST).date()
    expiry = _choose_expiry(chain, config, view, today)
    if expiry is None:
        needed = max(config.min_dte, view.horizon_days)
        return None, Skip("NO_EXPIRY", f"No stored expiry is at least {needed} days away.")
    quotes = [q for q in chain.quotes if q.expiry == expiry]
    atm_iv = _atm_iv(quotes, chain.spot)
    if atm_iv is None:
        return None, Skip("NO_IV", "The chosen expiry has no implied volatility.")
    days = max((_close(expiry) - now).total_seconds() / 86400.0, 0.0)
    sigma_move = chain.spot * (atm_iv / 100.0) * math.sqrt(days / 365.0)
    by_key = {(q.strike, q.option_type): q for q in quotes}
    strikes = sorted({q.strike for q in quotes})
    tilt = view_tilt(chain.spot, view.target, view.conviction)
    context = _Context(
        view, chain, config, now, expiry, (expiry - today).days, days, atm_iv,
        sigma_move, strikes, by_key, tilt, iv_rank,
    )  # fmt: skip
    return context, None


# ── One candidate ────────────────────────────────────────────────────────────


def _price_leg(
    resolved: ResolvedLeg, quote: Optional[Quote], config: IdeaConfig
) -> tuple[Optional[IdeaLeg], Optional[str]]:
    if quote is None:
        return None, f"no quote for {resolved.strike:g} {resolved.option_type}"
    if not quote.iv or quote.iv <= 0:
        return None, f"no IV for {resolved.strike:g} {resolved.option_type}"
    if not (quote.bid and quote.ask and quote.bid > 0 and quote.ask > 0):
        return None, f"no two-sided quote for {resolved.strike:g} {resolved.option_type}"
    if quote.open_interest < config.min_open_interest or quote.volume <= 0:
        return (
            None,
            f"illiquid: {resolved.strike:g} {resolved.option_type} (OI {quote.open_interest})",
        )
    buying = resolved.action == BUY
    premium, basis = (quote.ask, "ask") if buying else (quote.bid, "bid")
    return (
        IdeaLeg(
            resolved.action, resolved.option_type, resolved.strike, resolved.lots, premium, basis,
            quote.iv, quote.bid, quote.ask, quote.open_interest, quote.volume,
        ),
        None,
    )  # fmt: skip


def _payoff_legs(ctx: _Context, legs: Sequence[IdeaLeg]) -> list[Leg]:
    return [
        Leg(
            l.action,
            l.option_type,
            l.strike,
            l.premium,
            l.lots,
            ctx.chain.lot_size,
            ctx.expiry,
            l.iv,
        )
        for l in legs  # noqa: E741 - short alias for a one-line comprehension
    ]


def _alignment(ctx: _Context, delta: float) -> float:
    """Net delta agrees with the bias (+) or fights it (-), saturating at about one lot."""
    sign = 1.0 if ctx.view.bias == BULLISH else -1.0
    return math.tanh(sign * delta / ctx.chain.lot_size)


def _theta_drag(ctx: _Context, theta: float, net: float) -> float:
    """Share of a debit that time decay eats over the view's horizon (0 for credits)."""
    if net >= 0:
        return 0.0
    return min(max(-theta, 0.0) * ctx.view.horizon_days / abs(net), 1.0)


def _family_bonus(ctx: _Context, template: Template) -> float:
    rank, config = ctx.iv_rank, ctx.config
    if rank is None:
        return 0.0
    if rank < config.iv_rank_low and template.family == DEBIT:
        return config.family_bonus
    if rank > config.iv_rank_high and template.family == CREDIT:
        return config.family_bonus
    return 0.0


def _rationale(template: Template, idea_view: DirectionalView, m: dict) -> str:
    cost = f"costs ₹{abs(m['net']):,.0f}" if m["net"] < 0 else f"collects ₹{m['net']:,.0f}"
    return (
        f"{template.label}: {cost}, risks ₹{m['max_loss']:,.0f} "
        f"to make up to ₹{m['max_profit']:,.0f}. "
        f"Wins {m['pop_view']:.0%} of the time if the {idea_view.bias.lower()} view to "
        f"{idea_view.target:g} plays out ({m['pop_market']:.0%} on market odds); "
        f"expected value at the view ₹{m['ev_view']:,.0f}."
    )


def _evaluate(  # pylint: disable=too-many-locals
    ctx: _Context, template: Template, width: int
) -> tuple[Optional[Idea], Optional[str]]:
    """Resolve, price and judge one template at one width: (idea, None) or (None, reason)."""
    chain, config, view = ctx.chain, ctx.config, ctx.view
    both = {leg.option_type for leg in template.legs}
    strikes = sorted({s for s in ctx.strikes if all((s, t) in ctx.quotes for t in both)})
    try:
        resolved = resolve_template(template, strikes, chain.spot, width, view.target)
    except TemplateError as exc:
        return None, str(exc)

    legs: list[IdeaLeg] = []
    for r in resolved:
        priced, why = _price_leg(r, ctx.quotes.get((r.strike, r.option_type)), config)
        if priced is None:
            return None, why
        legs.append(priced)
    payoff_legs = _payoff_legs(ctx, legs)

    extremes = max_profit_loss(payoff_legs)
    if not (math.isfinite(extremes.max_loss.value) and math.isfinite(extremes.max_profit.value)):
        return None, "risk is not defined"
    max_profit, max_loss = extremes.max_profit.value, -extremes.max_loss.value
    if max_profit <= 0 or max_loss <= 0:
        return None, "no profit is possible" if max_profit <= 0 else "no risk to measure"

    slippage = sum(l.lots * chain.lot_size * (l.ask - l.bid) for l in legs)  # noqa: E741
    slippage_pct = slippage / max_profit
    if slippage_pct > config.max_slippage_pct:
        return None, f"slippage is {slippage_pct:.0%} of max profit"
    peak = extremes.max_profit.at_spot
    if peak is not None and abs(peak - chain.spot) > config.max_move_sigmas * ctx.sigma_move:
        return None, f"max profit needs a move beyond {config.max_move_sigmas:g}σ"

    market = analyze_probability(payoff_legs, chain.spot, ctx.atm_iv, ctx.days)
    at_view = analyze_probability(payoff_legs, chain.spot, ctx.atm_iv, ctx.days, tilt=ctx.tilt)
    if at_view.expected_value <= 0:
        return None, "negative expected value at the view"

    greeks = net_greeks(payoff_legs, chain.spot, ctx.now.astimezone(IST).date())
    net = net_premium(payoff_legs)
    ror = at_view.expected_value / max_loss
    score = (
        view.conviction
        * (config.w_return * ror + config.w_alignment * _alignment(ctx, greeks["delta"]))
        + config.w_pop * at_view.pop
        - config.w_slippage * slippage_pct
        - config.w_theta * _theta_drag(ctx, greeks["theta"], net)
        + _family_bonus(ctx, template)
    )  # fmt: skip

    lo, hi = default_spot_range(payoff_legs, chain.spot)
    curve = tuple(
        (round(s, 2), round(p, 2)) for s, p in payoff_curve(payoff_legs, lo, hi, CURVE_POINTS)
    )
    numbers = {
        "net": net, "max_loss": max_loss, "max_profit": max_profit,
        "pop_view": at_view.pop, "pop_market": market.pop, "ev_view": at_view.expected_value,
    }  # fmt: skip
    return (
        Idea(
            underlying=view.underlying, template=template.key, template_label=template.label,
            shape=shape_of(template), family=template.family, expiry=ctx.expiry, dte=ctx.dte,
            lot_size=chain.lot_size, legs=tuple(legs), net_premium=round(net, 2),
            max_profit=round(max_profit, 2), max_loss=round(max_loss, 2),
            breakevens=tuple(round(b, 2) for b in breakevens(payoff_legs)),
            pop_market=round(market.pop, 4), ev_market=round(market.expected_value, 2),
            pop_view=round(at_view.pop, 4), ev_view=round(at_view.expected_value, 2),
            return_on_risk=round(ror, 4), slippage=round(slippage, 2),
            net_delta=round(greeks["delta"], 2),
            margin_estimate=_margin(ctx, payoff_legs),
            sigma_pct=round(ctx.atm_iv, 2), sigma_source="ATM_IV", score=round(score, 4),
            rationale=_rationale(template, view, numbers), curve=curve,
        ),
        None,
    )  # fmt: skip


def _margin(ctx: _Context, legs: list[Leg]) -> Optional[float]:
    """The SPAN-based estimate for opening the basket, or None if it cannot be produced."""
    sigma = ctx.chain.sigma or sigma_from_iv(ctx.atm_iv)
    try:
        result = estimate_margin(
            legs, ctx.chain.spot, sigma, INDEX if ctx.chain.is_index else STOCK,
            ctx.now.astimezone(IST).date(), DEFAULT_RISK_FREE_RATE,
        )  # fmt: skip
    except ValueError:
        return None
    return round(result.total, 2)


# ── Selection ────────────────────────────────────────────────────────────────


def _select(candidates: list[Idea], limit: int) -> list[Idea]:
    """Best score first; each further pick must be a different shape (risk profile)."""
    chosen: list[Idea] = []
    for idea in sorted(candidates, key=lambda i: i.score, reverse=True):
        if len(chosen) == limit:
            break
        if any(idea.shape == c.shape for c in chosen):
            continue
        chosen.append(idea)
    return chosen


def _assign_roles(ideas: list[Idea]) -> list[Idea]:
    """Conservative = highest POP, Balanced = best return on risk, Targeted = the rest."""
    remaining = list(ideas)
    roles: dict[int, str] = {}
    for role, key in (
        (ROLE_CONSERVATIVE, lambda i: i.pop_view),
        (ROLE_BALANCED, lambda i: i.return_on_risk),
        (ROLE_TARGETED, lambda i: i.max_profit / max(abs(i.net_premium), 1.0)),
    ):
        if not remaining:
            break
        best = max(remaining, key=key)
        roles[id(best)] = role
        remaining.remove(best)
    ordered = [replace(i, role=roles[id(i)]) for i in ideas]
    order = [ROLE_CONSERVATIVE, ROLE_BALANCED, ROLE_TARGETED]
    return sorted(ordered, key=lambda i: order.index(i.role))


def _no_survivors(rejections: list[Rejection]) -> Skip:
    counts = Counter(r.reason.split(":")[0].split(" for ")[0] for r in rejections)
    top = ", ".join(f"{reason} ({n})" for reason, n in counts.most_common(3))
    return Skip("ALL_REJECTED", f"Every candidate failed a filter: {top}.")


def generate_ideas(
    view: DirectionalView,
    chain: ChainData,
    now: dt.datetime,
    *,
    iv_rank: Optional[float] = None,
    config: Optional[IdeaConfig] = None,
) -> IdeaSet:
    """Up to ``config.max_ideas`` defined-risk baskets for ``view``, or the reason for none."""
    config = config or IdeaConfig()
    skip = _preconditions(view, chain, config, now)
    if skip:
        return IdeaSet(view.underlying, skip=skip)
    ctx, skip = _build_context(view, chain, config, now, iv_rank)
    if skip or ctx is None:
        return IdeaSet(view.underlying, skip=skip)

    candidates: list[Idea] = []
    rejections: list[Rejection] = []
    for template in list_templates(view.bias, generator_only=True):
        for width in config.widths:
            idea, reason = _evaluate(ctx, template, width)
            if idea is not None:
                candidates.append(idea)
            else:
                rejections.append(Rejection(template.key, width, reason or "rejected"))
    if not candidates:
        return IdeaSet(view.underlying, skip=_no_survivors(rejections), rejections=rejections)
    return IdeaSet(
        view.underlying,
        ideas=_assign_roles(_select(candidates, config.max_ideas)),
        rejections=rejections,
    )
