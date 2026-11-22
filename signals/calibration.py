"""
Step 2 — Calibration residual measurement (honest, independence-correct).

PRIMARY: one observation per market at each fixed TTR horizon.
CI: block-bootstrap clustered by market_id.
Multiple testing: Benjamini-Hochberg at FDR=0.10.

Residual = realised_outcome_freq − mean_price  (per bin × category × horizon cell)
Favourite-longshot signature: residual > 0 for high-price bins, < 0 for low-price bins.
"""

import json
import math
import random
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (PRICE_BINS, VALID_CATEGORIES, TTR_HORIZONS_SECONDS,
                    BOOTSTRAP_SAMPLES, BOOTSTRAP_CI, RANDOM_SEED,
                    MIN_WALK_FORWARD_WINDOWS)


def assign_bin(price, bins=PRICE_BINS):
    for i in range(len(bins) - 1):
        if bins[i] <= price < bins[i + 1]:
            return f"{bins[i]:.2f}–{bins[i+1]:.2f}"
    return None


def compute_residuals(observations, categories=None, horizons=None):
    """
    Compute per-cell calibration residuals with clustered bootstrap CIs.

    Returns dict keyed by (horizon, category, price_bin) →
      {residual, ci_lo, ci_hi, n_markets, mean_price, outcome_freq, significant}
    """
    random.seed(RANDOM_SEED)

    if categories is None:
        categories = list(VALID_CATEGORIES)
    if horizons is None:
        horizons = list(TTR_HORIZONS_SECONDS.keys())

    # Group observations: market_id → list of obs (one per horizon)
    # For independence: one obs per (market × horizon)
    market_obs = defaultdict(list)
    for o in observations:
        if (o["horizon"] in horizons
                and o["category"] in categories
                and o.get("price_at_ttr") is not None):
            market_obs[o["market_id"]].append(o)

    # Build cells: (horizon, category, bin) → list of (price, outcome)
    cells = defaultdict(list)
    for mkt_id, obs_list in market_obs.items():
        for o in obs_list:
            price = o["price_at_ttr"]
            b = assign_bin(price)
            if b is None:
                continue
            key = (o["horizon"], o["category"], b)
            cells[key].append((price, float(o["resolution"]), mkt_id))

    results = {}
    p_values = []

    for key, triples in cells.items():
        if len(triples) < 5:
            continue
        prices    = [t[0] for t in triples]
        outcomes  = [t[1] for t in triples]
        mkt_ids   = [t[2] for t in triples]

        mean_price    = sum(prices) / len(prices)
        outcome_freq  = sum(outcomes) / len(outcomes)
        residual      = outcome_freq - mean_price

        # Clustered block-bootstrap CI
        ci_lo, ci_hi, pval = _clustered_bootstrap(
            prices, outcomes, mkt_ids,
            n_boot=BOOTSTRAP_SAMPLES, ci=BOOTSTRAP_CI
        )

        results[key] = {
            "horizon":      key[0],
            "category":     key[1],
            "bin":          key[2],
            "n":            len(triples),
            "mean_price":   round(mean_price, 4),
            "outcome_freq": round(outcome_freq, 4),
            "residual":     round(residual, 4),
            "ci_lo":        round(ci_lo, 4),
            "ci_hi":        round(ci_hi, 4),
            "p_value":      round(pval, 4),
            "significant":  False,  # filled in after BH
        }
        p_values.append((key, pval))

    # Benjamini-Hochberg correction at FDR=0.10
    _apply_bh(results, p_values, fdr=0.10)

    return results


def _clustered_bootstrap(prices, outcomes, cluster_ids, n_boot, ci):
    """
    Resample entire markets (clusters) with replacement.
    Computes distribution of (outcome_freq - mean_price) under resampling.
    Returns (ci_lo, ci_hi, two-sided p-value for residual != 0).
    """
    # Build per-cluster lists
    clusters = defaultdict(list)
    for p, o, cid in zip(prices, outcomes, cluster_ids):
        clusters[cid].append((p, o))
    cluster_list = list(clusters.values())
    n_clusters = len(cluster_list)

    observed_residual = sum(outcomes) / len(outcomes) - sum(prices) / len(prices)
    boot_residuals = []

    for _ in range(n_boot):
        # Resample clusters with replacement
        sample = []
        for _ in range(n_clusters):
            sample.extend(random.choice(cluster_list))
        s_prices  = [x[0] for x in sample]
        s_outcomes = [x[1] for x in sample]
        r = sum(s_outcomes) / len(s_outcomes) - sum(s_prices) / len(s_prices)
        boot_residuals.append(r)

    boot_residuals.sort()
    lo_idx = int((1 - ci) / 2 * n_boot)
    hi_idx = int((1 + ci) / 2 * n_boot)
    ci_lo = boot_residuals[max(0, lo_idx)]
    ci_hi = boot_residuals[min(n_boot - 1, hi_idx)]

    # Two-sided p-value: fraction of bootstrap samples on the null (residual=0 side)
    null_residuals = [r - observed_residual for r in boot_residuals]
    pval = 2 * min(
        sum(1 for r in null_residuals if r >= abs(observed_residual)) / n_boot,
        sum(1 for r in null_residuals if r <= -abs(observed_residual)) / n_boot,
    )
    pval = max(pval, 1 / n_boot)

    return ci_lo, ci_hi, pval


def _apply_bh(results, p_values, fdr=0.10):
    """Benjamini-Hochberg: mark surviving cells as significant."""
    m = len(p_values)
    if m == 0:
        return
    sorted_pv = sorted(p_values, key=lambda x: x[1])
    for rank, (key, pval) in enumerate(sorted_pv, start=1):
        threshold = (rank / m) * fdr
        if pval <= threshold:
            results[key]["significant"] = True


def walk_forward_stability(observations, n_windows=MIN_WALK_FORWARD_WINDOWS,
                           category=None, horizon="24h"):
    """
    Split observations chronologically by resolution_ts into n_windows equal parts.
    Compute residual per (price-bin category) in each window.
    Returns dict: bin → list of per-window residuals (for sign-stability check).
    """
    filtered = [o for o in observations
                if o["horizon"] == horizon
                and o.get("price_at_ttr") is not None
                and o.get("resolution_ts") is not None]
    if category:
        filtered = [o for o in filtered if o["category"] == category]

    filtered.sort(key=lambda o: o["resolution_ts"])
    n = len(filtered)
    if n < n_windows * 5:
        print(f"  [walk-forward] Not enough observations ({n}) for {n_windows} windows.")
        return {}

    window_size = n // n_windows
    stability = defaultdict(list)

    for w in range(n_windows):
        window = filtered[w * window_size:(w + 1) * window_size]
        by_bin = defaultdict(list)
        for o in window:
            b = assign_bin(o["price_at_ttr"])
            if b:
                by_bin[b].append((o["price_at_ttr"], float(o["resolution"])))

        for b, pairs in by_bin.items():
            if len(pairs) < 3:
                continue
            residual = (sum(o for _, o in pairs) / len(pairs)
                        - sum(p for p, _ in pairs) / len(pairs))
            stability[b].append(residual)

    return dict(stability)


def sign_stable(window_residuals, min_windows=MIN_WALK_FORWARD_WINDOWS):
    """Return True if residuals have consistent sign across >= min_windows windows."""
    if len(window_residuals) < min_windows:
        return False
    signs = [r > 0 for r in window_residuals]
    return all(signs) or not any(signs)
