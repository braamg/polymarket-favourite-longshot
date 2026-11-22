"""
Step 3 — Per-decile one-way cost floor (correct for hold-to-resolution strategy).

Key corrections vs. the Phase 0 viability gate:
1. ONE-WAY cost only (entry taker fee + half-spread + gas). No exit trade.
2. Per-DECILE cost (fee = rate * p * (1-p) collapses at extremes, NOT at p=0.50).
3. Favourite leg and longshot leg treated separately.

Net edge per cell = calibration_residual - one_way_cost_floor(p, category, date)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (FEE_RATES, FEE_LAUNCH_DATES, GIBBS_SPREAD_MEDIAN,
                    LONGSHOT_SPREAD_PREMIUM_P_THRESHOLD, GAS_COST_USD,
                    FLOOR_MULTIPLIER, PRICE_BINS)


def fee_rate_for(category, resolution_ts):
    """Return applicable taker fee rate (0.0 if before fee launch for this category)."""
    launch = FEE_LAUNCH_DATES.get(category, FEE_LAUNCH_DATES["default"])
    if (resolution_ts or 0) < launch:
        return 0.0
    return FEE_RATES.get(category, FEE_RATES["default"])


def one_way_taker_fee(p, category, resolution_ts):
    """Taker fee as a fraction of notional (= shares × price) for a one-way entry."""
    rate = fee_rate_for(category, resolution_ts)
    return rate * p * (1 - p)


def entry_half_spread(p, category):
    """
    Estimated entry half-spread.
    For longshots (p < LONGSHOT_SPREAD_PREMIUM_P_THRESHOLD), apply a premium
    to account for the documented longshot spread premium.
    Returns fraction of notional.
    [MODELLED — sourced from Gibbs spread medians in arXiv 2604.24366]
    """
    base = GIBBS_SPREAD_MEDIAN.get(category, GIBBS_SPREAD_MEDIAN["default"])
    if p < LONGSHOT_SPREAD_PREMIUM_P_THRESHOLD:
        base = base * 2.5   # longshot spread premium (literature-observed)
    return base / 2         # half-spread for entry leg only


def one_way_floor(p, category, resolution_ts):
    """
    Total one-way cost floor for a position entered at price p, held to resolution.
    = taker_fee + half_spread + gas_per_dollar_of_notional
    """
    fee     = one_way_taker_fee(p, category, resolution_ts)
    spread  = entry_half_spread(p, category)
    gas_frac = GAS_COST_USD / max(p, 0.001)   # gas as fraction of notional at price p
    return fee + spread + gas_frac


def net_edge(residual, p, category, resolution_ts):
    """
    Net edge after one-way cost floor.
    Positive → potentially profitable. Negative → killed.
    """
    floor = one_way_floor(p, category, resolution_ts)
    return residual - floor


def apply_cost_floors(calibration_results):
    """
    Augment calibration_results dict (from signals/calibration.py) with cost-floor fields.

    Adds to each cell:
      floor           one-way cost floor (at bin midpoint)
      net_edge        residual - floor
      leg             'favourite' (p >= 0.5) or 'longshot' (p < 0.5)
      passes_floor    True if net_edge > 0
      passes_go_criteria  True if net_edge >= floor * FLOOR_MULTIPLIER AND CI above zero
    """
    for key, cell in calibration_results.items():
        bin_str = cell["bin"]
        lo, hi = [float(x) for x in bin_str.split("–")]
        mid = (lo + hi) / 2

        cat = cell["category"]
        # Use a representative resolution_ts: 2026-06-01 (post full fee rollout)
        rep_ts = 1748736000  # 2026-06-01

        floor  = one_way_floor(mid, cat, rep_ts)
        ne     = net_edge(cell["residual"], mid, cat, rep_ts)

        cell["bin_mid"]          = round(mid, 3)
        cell["floor"]            = round(floor, 4)
        cell["net_edge"]         = round(ne, 4)
        cell["leg"]              = "favourite" if mid >= 0.5 else "longshot"
        cell["passes_floor"]     = ne > 0
        cell["passes_go_criteria"] = (
            ne >= floor * FLOOR_MULTIPLIER
            and cell.get("ci_lo", -1) > 0
            and cell.get("significant", False)
        )

    return calibration_results


def print_floor_table(calibration_results):
    """Print a per-decile cost breakdown table for the two legs."""
    print("\n── Cost floor by bin (one-way, hold-to-resolution) ──")
    print(f"{'Bin':<15} {'Leg':<10} {'Fee (Spt)':<11} {'Fee (Cry)':<11} "
          f"{'½-Spread':<10} {'Floor (Spt)':<12} {'Floor (Cry)':<12}")
    print("─" * 85)

    # Print representative floors at each bin midpoint
    sample_cats = [("Sports", 1748736000), ("Crypto", 1748736000)]
    for i in range(len(PRICE_BINS) - 1):
        lo, hi = PRICE_BINS[i], PRICE_BINS[i + 1]
        mid = (lo + hi) / 2
        leg = "favourite" if mid >= 0.5 else "longshot"
        row = f"{lo:.2f}–{hi:.2f}       {leg:<10}"
        for cat, ts in sample_cats:
            fee  = one_way_taker_fee(mid, cat, ts)
            row += f"  {fee*100:5.2f}%    "
        sp   = entry_half_spread(mid, "Sports")
        row += f" {sp*100:5.3f}%   "
        for cat, ts in sample_cats:
            fl = one_way_floor(mid, cat, ts)
            row += f"  {fl*100:5.2f}%    "
        print(row)
