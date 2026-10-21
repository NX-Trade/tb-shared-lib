"""What actually happened to a generated idea, and whether its odds were honest.

Pure functions — no DB, no Redis, no HTTP. A generated idea claims a probability of profit and an
expected value; this settles it against the price the underlying really closed at on expiry and
aggregates many of them into a calibration report. Calibration is the only way to learn whether
the generator's score weights are wrong (design §8B.11, open item I-2), so the report is built to
be read by someone who does not want to be flattered: it states the sample size and whether it is
big enough to say anything.
"""

# stdlib
import datetime as dt
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Optional

# internal
from tb_utils.options.payoff import Leg, payoff_at_expiry

BULLISH = "BULLISH"
BEARISH = "BEARISH"

# Below this many settled ideas a win rate is noise; the report says so instead of implying more.
MIN_RELIABLE_SAMPLE = 30
POP_BUCKET_EDGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


@dataclass(frozen=True)
class PricePoint:
    """One trading day's range for the underlying, used for the target-reached check."""

    day: dt.date
    high: float
    low: float


@dataclass(frozen=True)
class IdeaOutcome:
    settle_spot: float
    pnl: float  # rupees, whole position, at expiry
    win: bool
    pnl_vs_max_loss: float  # pnl / max loss; -1 is the whole risk lost
    direction_correct: bool  # settled on the side of the entry the view called
    target_reached: bool  # the underlying touched the target at any point before settling
    best_move_pct: float  # furthest move toward the target, % of entry


def settle_idea(
    legs: Sequence[Leg],
    *,
    settle_spot: float,
    bias: str,
    entry: float,
    target: Optional[float],
    path: Sequence[PricePoint],
    max_loss: float,
) -> IdeaOutcome:
    """Settle ``legs`` at ``settle_spot`` and judge the view against the realised path."""
    if settle_spot <= 0 or entry <= 0:
        raise ValueError("settle_spot and entry must be positive")
    pnl = payoff_at_expiry(legs, settle_spot)
    bullish = bias == BULLISH
    toward = (
        max((p.high for p in path), default=settle_spot)
        if bullish
        else min((p.low for p in path), default=settle_spot)
    )
    reached = False
    if target is not None:
        reached = toward >= target if bullish else toward <= target
    best_move = (toward - entry) / entry * 100.0 * (1.0 if bullish else -1.0)
    return IdeaOutcome(
        settle_spot=settle_spot,
        pnl=pnl,
        win=pnl > 0,
        pnl_vs_max_loss=pnl / max_loss if max_loss > 0 else 0.0,
        direction_correct=settle_spot > entry if bullish else settle_spot < entry,
        target_reached=reached,
        best_move_pct=best_move,
    )


def _mean(values: Sequence[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _round(value: Optional[float], digits: int = 4) -> Optional[float]:
    return None if value is None else round(value, digits)


def _group(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row[key])].append(row)
    return {
        name: {
            "n": len(items),
            "win_rate": _round(_mean([1.0 if r["win"] else 0.0 for r in items])),
            "mean_pop_view": _round(_mean([r["pop_view"] for r in items])),
            "mean_ev_view": _round(_mean([r["ev_view"] for r in items]), 2),
            "mean_pnl": _round(_mean([r["pnl"] for r in items]), 2),
        }
        for name, items in sorted(groups.items())
    }


def _buckets(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    edges = POP_BUCKET_EDGES
    for low, high in zip(edges, edges[1:], strict=False):
        last = high == edges[-1]
        inside = [
            r for r in rows if low <= r["pop_view"] < high or (last and r["pop_view"] == high)
        ]
        out.append(
            {
                "low": low,
                "high": high,
                "n": len(inside),
                "predicted": _round(_mean([r["pop_view"] for r in inside])),
                "realised": _round(_mean([1.0 if r["win"] else 0.0 for r in inside])),
            }
        )
    return out


def calibration_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate settled ideas into a calibration report.

    Each row needs ``pop_view``, ``pop_market``, ``ev_view``, ``pnl``, ``win``,
    ``direction_correct``, ``target_reached`` and the labels ``template``, ``shape``, ``role``
    and ``bias``. ``brier_*`` is the mean squared error of the probability against what happened
    (0 is perfect, 0.25 is a coin flip): the view's POP should beat the market's only if the view
    carries real information.
    """
    n = len(rows)
    if n == 0:
        return {"n": 0, "reliable": False, "min_reliable": MIN_RELIABLE_SAMPLE}
    wins = [1.0 if r["win"] else 0.0 for r in rows]
    mean_ev = _mean([r["ev_view"] for r in rows])
    mean_pnl = _mean([r["pnl"] for r in rows])
    return {
        "n": n,
        "reliable": n >= MIN_RELIABLE_SAMPLE,
        "min_reliable": MIN_RELIABLE_SAMPLE,
        "win_rate": _round(_mean(wins)),
        "mean_pop_view": _round(_mean([r["pop_view"] for r in rows])),
        "mean_pop_market": _round(_mean([r["pop_market"] for r in rows])),
        "brier_view": _round(
            _mean([(r["pop_view"] - w) ** 2 for r, w in zip(rows, wins, strict=True)])
        ),
        "brier_market": _round(
            _mean([(r["pop_market"] - w) ** 2 for r, w in zip(rows, wins, strict=True)])
        ),
        "mean_ev_view": _round(mean_ev, 2),
        "mean_pnl": _round(mean_pnl, 2),
        "total_pnl": round(sum(r["pnl"] for r in rows), 2),
        # Positive: ideas did better than they claimed. Negative: the expected value was flattering.
        "ev_error": _round(mean_pnl - mean_ev, 2) if mean_ev is not None else None,
        "direction_rate": _round(_mean([1.0 if r["direction_correct"] else 0.0 for r in rows])),
        "target_rate": _round(_mean([1.0 if r["target_reached"] else 0.0 for r in rows])),
        "buckets": _buckets(rows),
        "by_template": _group(rows, "template"),
        "by_role": _group(rows, "role"),
        "by_bias": _group(rows, "bias"),
    }
