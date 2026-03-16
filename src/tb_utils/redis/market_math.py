"""Pure mathematical calculations for market options data."""

def get_strikes_within_range(
    spot_price: float, strikes: list[float], percentage: float = 0.05
) -> list[float]:
    """Filter a list of strikes to only include those within ± percentage of spot."""
    if not spot_price or not strikes:
        return []

    lower_bound = spot_price * (1.0 - percentage)
    upper_bound = spot_price * (1.0 + percentage)

    return sorted([s for s in strikes if lower_bound <= s <= upper_bound])

def calculate_pcr(ce_oi_total: float, pe_oi_total: float) -> float | None:
    """Put-Call Ratio = Total Put OI / Total Call OI"""
    if ce_oi_total == 0:
        return None
    return round(pe_oi_total / ce_oi_total, 4)

def calculate_max_pain(
    strikes: list[float], option_chain_data: dict[float, dict[str, float]]
) -> float | None:
    """Calculate the strike price where option sellers lose the least money.

    option_chain_data format: { strike_price: {"CE_OI": 1000.0, "PE_OI": 1200.0} }
    """
    if not strikes or not option_chain_data:
        return None

    pain_values = []

    # For each possible expiration price (evaluating at existing strike prices)
    for assumed_expiry_price in strikes:
        total_pain = 0.0

        for strike, data in option_chain_data.items():
            ce_oi = data.get("CE_OI", 0.0)
            pe_oi = data.get("PE_OI", 0.0)

            # Call seller loses if assumed_expiry_price > strike
            if assumed_expiry_price > strike:
                total_pain += (assumed_expiry_price - strike) * ce_oi

            # Put seller loses if assumed_expiry_price < strike
            if assumed_expiry_price < strike:
                total_pain += (strike - assumed_expiry_price) * pe_oi

        pain_values.append((assumed_expiry_price, total_pain))

    if not pain_values:
        return None

    best_strike = min(pain_values, key=lambda x: x[1])[0]
    return best_strike

def calculate_support_resistance(
    option_chain_data: dict[float, dict[str, float]]
) -> tuple[float | None, float | None]:
    """Rudimentary S/R based on highest Open Interest.
    Returns (support_strike, resistance_strike).
    """
    if not option_chain_data:
        return None, None

    max_pe_oi = -1.0
    support_strike = None

    max_ce_oi = -1.0
    res_strike = None

    for strike, data in option_chain_data.items():
        pe_oi = data.get("PE_OI", 0.0)
        ce_oi = data.get("CE_OI", 0.0)

        if pe_oi > max_pe_oi:
            max_pe_oi = pe_oi
            support_strike = strike

        if ce_oi > max_ce_oi:
            max_ce_oi = ce_oi
            res_strike = strike

    return support_strike, res_strike
