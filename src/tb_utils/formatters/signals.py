"""Signal alert formatters for Telegram notifications."""

from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from tb_utils.utils.enums import SignalActionEnum


def format_fno_summary(
    signals: list[dict[str, Any]],
    trade_date: Optional[dt.date | str] = None,
    mode: str = "INTRADAY",
    market_tide_summary: Optional[str | dict] = None,
    as_of: Optional[dt.date | str] = None,
) -> str:
    """Format Telegram HTML message for F&O signals batch summary.

    Args:
        signals: List of signal dictionaries.
        trade_date: Scan / trade date.
        mode: "INTRADAY" or "EOD".
        market_tide_summary: Optional market tide info.
        as_of: Alias for trade_date.

    Returns:
        str: Telegram HTML-formatted message.
    """
    date_val = trade_date if trade_date is not None else as_of
    if date_val is None:
        date_val = dt.date.today()
    is_intraday = mode.upper() == "INTRADAY"
    emoji = "🕐" if is_intraday else "⚡"
    label = " (Intraday Update)" if is_intraday else ""

    if not signals:
        return f"{emoji} <b>F&O Signals{label} ({date_val})</b>\nNo qualifying F&O signals today."

    lines = [f"{emoji} <b>F&O Signals{label} — {date_val}</b>", f"Total: {len(signals)} signal(s)"]
    if market_tide_summary:
        lines.append(f"<i>{market_tide_summary}</i>")
    lines.append("")

    for s in signals[:10]:
        action_val = s["action"].value if isinstance(s["action"], SignalActionEnum) else s["action"]
        action_emoji = "🟢 BUY" if action_val == SignalActionEnum.BUY.value else "🔴 SELL"
        px_str = f" @ ₹{s['entry_price']:.2f}" if s.get("entry_price", 0) > 0 else ""
        entry_line = (
            f"  • {action_emoji} <b>{s['symbol']}</b> [{s.get('strategy_type', '')}]{px_str}\n"
            f"    Confidence: {s.get('confidence', 0) * 100:.0f}% | {s.get('reason', '')[:70]}"
        )
        opt = s.get("indicators", {}).get("option_contract")
        if opt:
            entry_line += f"\n    💼 <b>OPTION STRATEGY:</b> {opt.get('contract_label', '')} @ ₹{opt.get('entry_premium', 0):.2f}"
        lines.append(entry_line)

    if len(signals) > 10:
        lines.append(f"  ... and {len(signals) - 10} more")

    return "\n".join(lines)


def format_research_signal_card(
    signal: dict[str, Any],
    trade_date: Optional[dt.date | str] = None,
    as_of: Optional[dt.date | str] = None,
) -> str:
    """Format an individual Telegram HTML card for a single research confluence signal.

    One message per signal prevents Telegram message length truncation (4096 char limit).

    Args:
        signal: Dictionary representing a single approved research signal.
        trade_date: Scan / trade date.
        as_of: Alias for trade_date.

    Returns:
        str: Telegram HTML-formatted message.
    """
    date_val = trade_date if trade_date is not None else as_of
    if date_val is None:
        date_val = dt.date.today()
    sym = signal.get("symbol", "")
    action = signal.get("action", SignalActionEnum.BUY.value)
    action_val = action.value if hasattr(action, "value") else str(action)
    ep = float(signal.get("entry_price") or 0.0)
    tp = float(signal.get("target_price") or 0.0)
    sl = float(signal.get("stop_loss") or 0.0)
    conf = float(signal.get("confidence") or 0.0)
    tf = signal.get("timeframe", "SWING")
    strat = str(signal.get("strategy_name", "research_confluence")).upper()

    meta = signal.get("metadata", {})
    score = float(meta.get("composite_score") or 0.0)
    tech = float(meta.get("tech_score") or 0.0)
    deliv = float(meta.get("delivery_score") or 0.0)
    fno = meta.get("fno_score")

    tp_pct = ((tp - ep) / ep * 100) if ep > 0 else 0.0
    sl_pct = ((sl - ep) / ep * 100) if ep > 0 else 0.0

    if action_val == SignalActionEnum.BUY.value:
        badge = f"🟢 <b>RESEARCH BUY: {sym}</b>"
    elif action_val == SignalActionEnum.EXIT.value:
        badge = f"🔴 <b>RESEARCH EXIT / RISK: {sym}</b>"
    else:
        badge = f"🟡 <b>RESEARCH WATCH: {sym}</b>"

    lines = [
        badge,
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>Setup:</b> {strat} [{tf}]",
        f"<b>Score:</b> {score:+.2f} | <b>Confidence:</b> {conf * 100:.0f}%",
        "",
        "📊 <b>Cash Equity Levels:</b>",
        f"• Entry: ₹{ep:.2f}",
        f"• Target: ₹{tp:.2f} ({tp_pct:+.1f}%)",
        f"• Stop Loss: ₹{sl:.2f} ({sl_pct:+.1f}%)",
    ]

    # Confluence factors
    if meta.get("ltc_pattern"):
        lines.append(f"• <b>Tech:</b> {meta['ltc_pattern']} ({tech:+.2f})")
    else:
        lines.append(f"• <b>Tech:</b> {tech:+.2f}")

    if meta.get("delivery_pattern"):
        lines.append(f"• <b>Delivery:</b> {meta['delivery_pattern']} ({deliv:+.2f})")
    else:
        lines.append(f"• <b>Delivery:</b> {deliv:+.2f}")

    if fno is not None:
        fno_val = float(fno)
        if meta.get("fno_pattern"):
            lines.append(f"• <b>F&O:</b> {meta['fno_pattern']} ({fno_val:+.2f})")
        else:
            lines.append(f"• <b>F&O:</b> {fno_val:+.2f}")

    # Derivative / Options overlay
    ind = signal.get("indicators", {})
    opt = meta.get("option_contract") or ind.get("option_contract")
    spread = meta.get("option_spread") or ind.get("spread_strategy")

    if opt:
        lines.append("")
        lines.append("🎯 <b>Recommended Option Trade:</b>")
        contract = opt.get("contract_symbol") or opt.get("contract_label", "")
        lines.append(f"• Contract: <b>{contract}</b>")
        tp_target = opt.get("target_premium")
        sl_stop = opt.get("stop_premium")
        ep_prem = float(opt.get("entry_premium") or 0.0)
        tp_pct_str = (
            f" (+{((float(tp_target) - ep_prem) / ep_prem * 100):.0f}%)"
            if (tp_target and ep_prem > 0)
            else ""
        )
        sl_pct_str = (
            f" ({((float(sl_stop) - ep_prem) / ep_prem * 100):.0f}%)"
            if (sl_stop and ep_prem > 0)
            else ""
        )
        lines.append(
            f"• Entry: ₹{ep_prem:.2f} | Target: ₹{float(tp_target or 0.0):.2f}{tp_pct_str} | SL: ₹{float(sl_stop or 0.0):.2f}{sl_pct_str}"
        )
        if opt.get("delta") is not None or opt.get("dte") is not None or opt.get("iv") is not None:
            delta_val = float(opt.get("delta") or 0.0)
            dte_val = int(opt.get("dte") or 0)
            iv_val = float(opt.get("iv") or 0.0) * 100
            lines.append(f"• Delta: {delta_val:.2f} | DTE: {dte_val}d | IV: {iv_val:.1f}%")
    elif spread:
        lines.append("")
        strat_title = spread.get("strategy_type") or spread.get("strategy_name", "")
        bias_str = f" [{spread.get('bias', '')}]" if spread.get("bias") else ""
        lines.append(f"🎯 <b>Option Spread:</b> {strat_title}{bias_str}")
        lines.append(
            f"• Net Premium: ₹{float(spread.get('net_premium') or 0.0):.2f} | "
            f"Max Profit: ₹{float(spread.get('max_profit') or 0.0):.2f} | "
            f"Max Loss: ₹{float(spread.get('max_loss') or 0.0):.2f} | "
            f"R:R: 1:{float(spread.get('risk_reward_ratio') or 0.0):.1f}"
        )
        for leg in spread.get("legs", []):
            lines.append(
                f"  - {leg.get('action')} Strike {float(leg.get('strike_price') or 0.0):.0f} "
                f"{leg.get('option_type')} @ ₹{float(leg.get('entry_premium') or 0.0):.2f}"
            )

    lines.append("")
    date_str = date_val.strftime("%d-%b-%Y") if hasattr(date_val, "strftime") else str(date_val)
    lines.append(f"📅 <i>As of: {date_str}</i>")

    return "\n".join(lines)
