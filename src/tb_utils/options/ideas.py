"""Option strategies built straight from a chain snapshot, bullish and bearish.

A *selector* over analysed candidates, not a new source of maths: every number comes from
:mod:`payoff`, :mod:`probability`, :mod:`margin` and the :mod:`templates` registry. Pure — no DB,
no Redis, no HTTP — so it runs inside a request as readily as in a job.
Design: tb-ai-brain/upcoming/OPTION_STRATEGY_BUILDER_AND_MARGIN_DESIGN.md §8B.

Entry point
-----------
:func:`suggest_strategies` — **on demand, no signal and no target needed.** Legs come from the
listed strikes and the templates; both a bullish and a bearish lean are returned, each with its
payoff, breakevens, reward:risk, margin estimate and probability of profit at the market's own
odds. An optional view adds probability and expected value at that view.

Rules
-----
* **Defined risk only.** Only ``generator_eligible`` templates are tried (covered shorts, 2–4
  legs), and a candidate whose expiry loss is not finite is dropped regardless.
* **Analysis, not orders.** Nothing here can place anything.
* **Entry is priced where it would trade:** BUY at the ask, SELL at the bid. A leg without a
  two-sided quote, with no IV, or with thin open interest is rejected, never guessed.
* **Expected value at the market's odds is a cost check**, about minus the bid-ask paid, so it is
  shown but never used to reject or rank (open item M-2). Only an expected value at a *view*
  can do that, and only a view the caller supplies.

Pipeline
--------
expiry (nearest with enough days) → candidates (template × width) → hard filters (liquidity,
slippage, reachability, and negative EV at the view when there is one) → score → order.
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
    VERTICAL,
    ResolvedLeg,
    Template,
    TemplateError,
    get_template,
    list_templates,
    resolve_template,
    shape_of,
)
from tb_utils.time import IST

BUY = "BUY"
SELL = "SELL"

EXPIRY_CLOSE = dt.time(15, 30)
CURVE_POINTS = 41
BODY_MOVES = 0.5  # expected moves from spot at which a view-less butterfly body is centred


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
    tick: float = 0.05  # the contract's own price tick; most stock options are 0.05, some 0.01


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
    min_reward_risk: float = (
        0.0  # drop strategies whose max profit is under this many times max loss
    )
    max_chain_age: dt.timedelta = dt.timedelta(hours=30)
    iv_rank_low: float = 30.0  # below: debit structures preferred
    iv_rank_high: float = 60.0  # above: credit structures preferred
    family_bonus: float = 0.05
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
    pop_view: Optional[float]  # None unless a view was supplied
    ev_view: Optional[float]
    return_on_risk: Optional[float]  # ev_view / max_loss, with a view
    slippage: float  # rupees to cross the spread again on exit
    net_delta: float
    margin_estimate: Optional[float]
    sigma_pct: float
    sigma_source: str
    score: float
    rationale: str
    curve: tuple[tuple[float, float], ...]  # expiry payoff, for a sparkline
    reward_risk: float = 0.0  # max profit over max loss; read with POP, never alone
    bias: str = ""  # BULLISH | BEARISH: which way the structure leans
    width: int = 1  # spread width in listed-strike steps


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


# ── Context shared by every candidate of one underlying ──────────────────────


@dataclass(frozen=True)
class _Context:
    view: Optional[DirectionalView]
    horizon_days: int
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
    tilt: Optional[float]
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


def _choose_expiry(
    chain: ChainData,
    config: IdeaConfig,
    horizon_days: int,
    today: dt.date,
    requested: Optional[dt.date] = None,
):
    """The expiry to build on: the one asked for if it is stored and not expiring today,
    else the nearest at least ``max(min_dte, horizon)`` days away, else None."""
    if requested is not None:
        stored = {q.expiry for q in chain.quotes}
        return requested if requested in stored and (requested - today).days >= 1 else None
    needed = max(config.min_dte, horizon_days)
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
    view: Optional[DirectionalView],
    chain: ChainData,
    config: IdeaConfig,
    now: dt.datetime,
    iv_rank: Optional[float],
    horizon_days: int,
    requested_expiry: Optional[dt.date] = None,
) -> tuple[Optional[_Context], Optional[Skip]]:
    today = now.astimezone(IST).date()
    expiry = _choose_expiry(chain, config, horizon_days, today, requested_expiry)
    if expiry is None and requested_expiry is not None:
        return None, Skip(
            "NO_EXPIRY", f"No chain is stored for the {requested_expiry:%d %b %Y} expiry."
        )
    if expiry is None:
        needed = max(config.min_dte, horizon_days)
        return None, Skip("NO_EXPIRY", f"No stored expiry is at least {needed} days away.")
    quotes = [q for q in chain.quotes if q.expiry == expiry]
    atm_iv = _atm_iv(quotes, chain.spot)
    if atm_iv is None:
        return None, Skip("NO_IV", "The chosen expiry has no implied volatility.")
    days = max((_close(expiry) - now).total_seconds() / 86400.0, 0.0)
    sigma_move = chain.spot * (atm_iv / 100.0) * math.sqrt(days / 365.0)
    by_key = {(q.strike, q.option_type): q for q in quotes}
    strikes = sorted({q.strike for q in quotes})
    tilt = view_tilt(chain.spot, view.target, view.conviction) if view else None
    context = _Context(
        view, horizon_days, chain, config, now, expiry, (expiry - today).days, days, atm_iv,
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


def _alignment(ctx: _Context, delta: float, bias: str) -> float:
    """Net delta agrees with the bias (+) or fights it (-), saturating at about one lot."""
    sign = 1.0 if bias == BULLISH else -1.0
    return math.tanh(sign * delta / ctx.chain.lot_size)


def _theta_drag(ctx: _Context, theta: float, net: float) -> float:
    """Share of a debit that time decay eats over the view's horizon (0 for credits)."""
    if net >= 0:
        return 0.0
    return min(max(-theta, 0.0) * ctx.horizon_days / abs(net), 1.0)


def _family_bonus(ctx: _Context, template: Template) -> float:
    rank, config = ctx.iv_rank, ctx.config
    if rank is None:
        return 0.0
    if rank < config.iv_rank_low and template.family == DEBIT:
        return config.family_bonus
    if rank > config.iv_rank_high and template.family == CREDIT:
        return config.family_bonus
    return 0.0


def _rationale(template: Template, bias: str, view: Optional[DirectionalView], m: dict) -> str:
    cost = f"costs ₹{abs(m['net']):,.0f}" if m["net"] < 0 else f"collects ₹{m['net']:,.0f}"
    base = (
        f"{template.label}: {cost}, risks ₹{m['max_loss']:,.0f} "
        f"to make up to ₹{m['max_profit']:,.0f}. "
    )
    if view is None:
        return (
            base
            + f"On the market's own odds it finishes profitable {m['pop_market']:.0%} of the time; "
            f"a {bias.lower()} lean pays off if the underlying moves that way."
        )
    return (
        base + f"Wins {m['pop_view']:.0%} of the time if the {view.bias.lower()} view to "
        f"{view.target:g} plays out ({m['pop_market']:.0%} on market odds); "
        f"expected value at the view ₹{m['ev_view']:,.0f}."
    )


def _steps_between(ctx: _Context, legs: list[IdeaLeg]) -> int:
    """A vertical's strike distance in listed-strike steps, the way the templates count width."""
    listed = sorted(ctx.strikes)
    low, high = min(leg.strike for leg in legs), max(leg.strike for leg in legs)
    return listed.index(high) - listed.index(low) if low in listed and high in listed else 0


def _vertical_ideas(  # pylint: disable=too-many-locals
    ctx: _Context, bias: str
) -> tuple[list[Idea], list[Rejection]]:
    """A debit and a credit vertical for ``bias``, chosen by the spread engine's delta bands.

    The templates place a vertical by strike offset: buy the at-the-money strike, sell one or two
    strikes away. That costs about half the width, so reward:risk sits near 1:1 whatever the chain,
    and the spec's rules (long delta 0.35 to 0.45, short 0.15 to 0.20, reward:risk of at least 2.5,
    a minimum credit, a minimum probability of profit, per-leg liquidity) can never be met. The
    same engine that builds the STC spreads now builds these, so the Option Builder and the
    auto-trader follow one rule set. A vertical the rules refuse is reported as a rejection with
    the reason, never drawn at 1:1 to fill the list. The generic ``min_reward_risk`` floor does
    not apply to it, because the engine's own floor is the rule.
    """
    # Imported here: the engine imports this module for Quote and Skip.
    from tb_utils.options.spread_engine import (  # pylint: disable=import-outside-toplevel
        FreshChain,
        build_spread,
    )
    from tb_utils.options.spread_policy import (  # pylint: disable=import-outside-toplevel
        HIGH_VOL,
        LOW_VOL,
        SpreadPolicy,
    )
    from tb_utils.options.spread_structures import (  # pylint: disable=import-outside-toplevel
        choose_vertical,
    )

    action = "BUY" if bias == BULLISH else "SELL"
    chain = ctx.chain
    # The engine reads one expiry from what it is given; hand it the one this request is built on.
    scoped = replace(chain, quotes=tuple(q for q in chain.quotes if q.expiry == ctx.expiry))
    fresh = FreshChain(scoped, requested_at=chain.ts)  # the builder uses the stored snapshot as-is
    policy = SpreadPolicy()

    ideas: list[Idea] = []
    rejections: list[Rejection] = []
    for regime in (LOW_VOL, HIGH_VOL):  # debit and credit, whatever the volatility regime
        key = choose_vertical(action, regime, policy).key
        result = build_spread(
            fresh,
            action,
            ctx.now,
            policy,
            lambda a, _r, p, regime=regime: choose_vertical(a, regime, p),
        )
        spread = result.spread
        if spread is None:
            reason = result.skip.message if result.skip else "no strike pair met the rules"
            if result.rejections:  # the closest miss, so the reason is a number the user can read
                reason = f"{reason}: {result.rejections[0].detail}"
            rejections.append(Rejection(key, 0, reason))
            continue
        legs = [
            IdeaLeg(
                l.action,
                l.option_type,
                l.strike,
                l.lots,
                l.premium,
                l.premium_basis,
                l.iv,
                l.bid,
                l.ask,
                l.open_interest,
                l.volume,
            )  # fmt: skip
            for l in spread.legs  # noqa: E741  # pylint: disable=invalid-name
        ]
        idea, reason = _judge(
            ctx, get_template(spread.structure), legs, 0.0, _steps_between(ctx, legs)
        )
        if idea is not None:
            ideas.append(idea)
        else:
            rejections.append(Rejection(key, 0, reason or "rejected"))
    return ideas, rejections


def _evaluate(  # pylint: disable=too-many-locals
    ctx: _Context, template: Template, width: int
) -> tuple[Optional[Idea], Optional[str]]:
    """Resolve, price and judge one template at one width: (idea, None) or (None, reason)."""
    chain, config, view = ctx.chain, ctx.config, ctx.view
    bias = view.bias if view else template.bias
    both = {leg.option_type for leg in template.legs}
    strikes = sorted({s for s in ctx.strikes if all((s, t) in ctx.quotes for t in both)})
    # Without a view a body-at-target structure is centred half an expected move from spot, in
    # the direction the structure leans: a placement rule, not a forecast.
    lean = 1.0 if bias == BULLISH else -1.0
    target = view.target if view else chain.spot + lean * BODY_MOVES * ctx.sigma_move
    try:
        resolved = resolve_template(template, strikes, chain.spot, width, target)
    except TemplateError as exc:
        return None, str(exc)

    legs: list[IdeaLeg] = []
    for r in resolved:
        priced, why = _price_leg(r, ctx.quotes.get((r.strike, r.option_type)), config)
        if priced is None:
            return None, why
        legs.append(priced)
    return _judge(ctx, template, legs, config.min_reward_risk, width)


def _judge(  # pylint: disable=too-many-locals
    ctx: _Context, template: Template, legs: list[IdeaLeg], min_reward_risk: float, width: int
) -> tuple[Optional[Idea], Optional[str]]:
    """Judge priced legs: risk defined, reward:risk, slippage, reach, odds and score."""
    chain, config, view = ctx.chain, ctx.config, ctx.view
    bias = view.bias if view else template.bias
    payoff_legs = _payoff_legs(ctx, legs)

    extremes = max_profit_loss(payoff_legs)
    if not (math.isfinite(extremes.max_loss.value) and math.isfinite(extremes.max_profit.value)):
        return None, "risk is not defined"
    max_profit, max_loss = extremes.max_profit.value, -extremes.max_loss.value
    if max_profit <= 0 or max_loss <= 0:
        return None, "no profit is possible" if max_profit <= 0 else "no risk to measure"
    if max_profit / max_loss < min_reward_risk:
        return None, "reward-to-risk is below the minimum"

    slippage = sum(l.lots * chain.lot_size * (l.ask - l.bid) for l in legs)  # noqa: E741
    slippage_pct = slippage / max_profit
    if slippage_pct > config.max_slippage_pct:
        return None, f"slippage is {slippage_pct:.0%} of max profit"
    peak = extremes.max_profit.at_spot
    if peak is not None and abs(peak - chain.spot) > config.max_move_sigmas * ctx.sigma_move:
        return None, f"max profit needs a move beyond {config.max_move_sigmas:g}σ"

    market = analyze_probability(payoff_legs, chain.spot, ctx.atm_iv, ctx.days)
    at_view = (
        analyze_probability(payoff_legs, chain.spot, ctx.atm_iv, ctx.days, tilt=ctx.tilt or 0.0)
        if view
        else None
    )
    # Only a view can gate on expected value: at the market's own odds every fairly priced basket
    # is worth about minus its cost, so that figure is shown, never used to reject.
    if at_view is not None and at_view.expected_value <= 0:
        return None, "negative expected value at the view"

    greeks = net_greeks(payoff_legs, chain.spot, ctx.now.astimezone(IST).date())
    net = net_premium(payoff_legs)
    drag = config.w_theta * _theta_drag(ctx, greeks["theta"], net)
    ror = at_view.expected_value / max_loss if at_view else None
    if view and at_view and ror is not None:
        score = (
            view.conviction
            * (config.w_return * ror + config.w_alignment * _alignment(ctx, greeks["delta"], bias))
            + config.w_pop * at_view.pop
            - config.w_slippage * slippage_pct
            - drag
            + _family_bonus(ctx, template)
        )  # fmt: skip
    else:
        score = market.pop - config.w_slippage * slippage_pct - drag + _family_bonus(ctx, template)

    lo, hi = default_spot_range(payoff_legs, chain.spot)
    curve = tuple(
        (round(s, 2), round(p, 2)) for s, p in payoff_curve(payoff_legs, lo, hi, CURVE_POINTS)
    )
    numbers = {
        "net": net, "max_loss": max_loss, "max_profit": max_profit,
        "pop_view": at_view.pop if at_view else None, "pop_market": market.pop,
        "ev_view": at_view.expected_value if at_view else None,
    }  # fmt: skip
    return (
        Idea(
            underlying=view.underlying if view else chain.symbol,
            template=template.key, template_label=template.label,
            shape=shape_of(template), family=template.family, expiry=ctx.expiry, dte=ctx.dte,
            lot_size=chain.lot_size, legs=tuple(legs), net_premium=round(net, 2),
            max_profit=round(max_profit, 2), max_loss=round(max_loss, 2),
            breakevens=tuple(round(b, 2) for b in breakevens(payoff_legs)),
            pop_market=round(market.pop, 4), ev_market=round(market.expected_value, 2),
            pop_view=round(at_view.pop, 4) if at_view else None,
            ev_view=round(at_view.expected_value, 2) if at_view else None,
            return_on_risk=round(ror, 4) if ror is not None else None, slippage=round(slippage, 2),
            net_delta=round(greeks["delta"], 2),
            margin_estimate=_margin(ctx, payoff_legs),
            sigma_pct=round(ctx.atm_iv, 2), sigma_source="ATM_IV", score=round(score, 4),
            rationale=_rationale(template, bias, view, numbers), curve=curve,
            reward_risk=round(max_profit / max_loss, 2), bias=bias, width=width,
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


def _no_survivors(rejections: list[Rejection]) -> Skip:
    counts = Counter(r.reason.split(":")[0].split(" for ")[0] for r in rejections)
    top = ", ".join(f"{reason} ({n})" for reason, n in counts.most_common(3))
    return Skip("ALL_REJECTED", f"Every candidate failed a filter: {top}.")


@dataclass(frozen=True)
class Suggestions:
    """Every defined-risk strategy the chain supports for an underlying, both ways of leaning."""

    underlying: str
    ideas: list[Idea] = field(default_factory=list)
    skip: Optional[Skip] = None
    rejections: list[Rejection] = field(default_factory=list)
    expiry: Optional[dt.date] = None
    dte: Optional[int] = None
    atm_iv: Optional[float] = None
    expected_move: Optional[float] = None  # one σ to expiry, in the underlying's price units
    iv_rank: Optional[float] = None


DEFAULT_HORIZON_DAYS = 10
SUGGEST_BIASES = (BULLISH, BEARISH)


def suggest_strategies(  # pylint: disable=too-many-locals
    chain: ChainData,
    now: dt.datetime,
    *,
    view: Optional[DirectionalView] = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    iv_rank: Optional[float] = None,
    config: Optional[IdeaConfig] = None,
    expiry: Optional[dt.date] = None,
) -> Suggestions:
    """Bullish and bearish defined-risk strategies for ``chain``, straight from its quotes.

    No research signal and no target are needed: legs come from the listed strikes and the
    templates, on the nearest expiry at least ``max(min_dte, horizon_days)`` days out. Each one
    carries its payoff, breakevens, reward:risk, margin estimate and its probability of profit
    and expected value **at the market's own odds**. Those are honest but not a forecast: the
    expected value is about minus the cost of trading, so it is never used to reject or to rank.

    An optional ``view`` adds probability and expected value *at that view*, rejects structures
    that are worth nothing even if it plays out, and ranks by them. Strategies come back with
    the best score first within each lean (POP-led without a view).

    ``expiry`` builds on that stored expiry instead of the nearest one with enough days.
    """
    config = config or IdeaConfig()
    name = view.underlying if view else chain.symbol
    if view is not None:
        skip = _preconditions(view, chain, config, now)
        if skip:
            return Suggestions(name, skip=skip)
    elif chain.spot <= 0 or not chain.quotes:
        return Suggestions(
            name, skip=Skip("NO_CHAIN", "No option chain is stored for this underlying.")
        )
    elif now - chain.ts > config.max_chain_age:
        age = (now - chain.ts).total_seconds() / 3600
        return Suggestions(name, skip=Skip("STALE_CHAIN", f"The chain is {age:.1f} h old."))

    horizon = view.horizon_days if view else horizon_days
    ctx, skip = _build_context(view, chain, config, now, iv_rank, horizon, expiry)
    if skip or ctx is None:
        return Suggestions(name, skip=skip)

    survivors: list[Idea] = []
    rejections: list[Rejection] = []
    for bias in SUGGEST_BIASES if view is None else (view.bias,):
        for template in list_templates(bias, generator_only=True):
            if shape_of(template) == VERTICAL:
                continue  # verticals are built below by strike delta, not by strike offset
            for width in config.widths:
                idea, reason = _evaluate(ctx, template, width)
                if idea is not None:
                    survivors.append(idea)
                else:
                    rejections.append(Rejection(template.key, width, reason or "rejected"))
        built, refused = _vertical_ideas(ctx, bias)
        survivors += built
        rejections += refused
    survivors.sort(key=lambda i: (SUGGEST_BIASES.index(i.bias), -i.score))
    return Suggestions(
        name,
        ideas=survivors,
        skip=None if survivors else _no_survivors(rejections),
        rejections=rejections,
        expiry=ctx.expiry,
        dte=ctx.dte,
        atm_iv=round(ctx.atm_iv, 2),
        expected_move=round(ctx.sigma_move, 2),
        iv_rank=iv_rank,
    )
