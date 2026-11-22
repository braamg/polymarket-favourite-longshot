"""
Step 1 pipeline — enumerate resolved binary markets and build the observation dataset.

Each row in the output represents one (market, horizon) pair:
  market_id, category, resolution (0/1), price_at_ttr, horizon, volume, ...

Survivorship bias: we enumerate ALL resolved markets above the volume floor,
not just "interesting" ones. Confirmed closed = confirmed sample.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (TTR_HORIZONS_SECONDS, VALID_CATEGORIES, EXCLUDED_CATEGORIES,
                    MIN_VOLUME_USDC, ECO_VOLUME_FACTOR, CACHE_DIR,
                    RESOLVED_FIDELITY_MIN)
from fetch.gamma import get_resolved_markets
from fetch.clob import fetch_with_fallback, price_at_ttr


def build_dataset(min_volume=MIN_VOLUME_USDC, verbose=True):
    """
    Returns a list of observation dicts, one per (market × TTR-horizon) with a valid price.
    Skips markets with < MIN_PRICE_BARS or no price at the requested TTR.
    """
    markets = get_resolved_markets(min_volume=min_volume)

    # Filter excluded categories
    markets = [m for m in markets
               if m["category"] not in EXCLUDED_CATEGORIES]

    if verbose:
        print(f"\n[Step 1] {len(markets)} resolved binary markets after category filter")
        _log_coverage(markets)

    observations = []
    no_bars = 0
    no_price = 0

    for i, m in enumerate(markets):
        if verbose and i % 100 == 0:
            print(f"  [{i}/{len(markets)}] fetching price history...")

        # Pull price history for YES token (token index 0)
        bars, fidelity_used = fetch_with_fallback(m["clobTokenYes"], is_resolved=True)

        if not bars:
            no_bars += 1
            continue

        for horizon_label, ttr_sec in TTR_HORIZONS_SECONDS.items():
            price = price_at_ttr(bars, m["resolutionTimestamp"], ttr_sec)
            if price is None:
                no_price += 1
                continue

            # Determine fee regime: zero before fee launch
            from config import FEE_LAUNCH_DATES
            cat = m["category"]
            launch_ts = FEE_LAUNCH_DATES.get(cat, FEE_LAUNCH_DATES["default"])
            fee_applicable = (m["resolutionTimestamp"] or 0) >= launch_ts

            observations.append({
                "market_id":        m["id"],
                "condition_id":     m["conditionId"],
                "question":         m["question"],
                "category":         m["category"],
                "volume_nominal":   m["volume"],
                "volume_economic":  m["volume"] * ECO_VOLUME_FACTOR,
                "resolution":       m["resolution"],      # 1=YES, 0=NO
                "price_at_ttr":     float(price),
                "horizon":          horizon_label,
                "ttr_seconds":      ttr_sec,
                "resolution_ts":    m["resolutionTimestamp"],
                "start_ts":         m["startDate"],
                "fidelity_used":    fidelity_used,
                "fee_applicable":   fee_applicable,
            })

    if verbose:
        print(f"\n[Step 1] Dataset built: {len(observations)} observations")
        print(f"  Markets with no price bars: {no_bars}")
        print(f"  (market, horizon) pairs with no valid TTR price: {no_price}")
        _log_horizon_counts(observations)
        _log_category_counts(observations)

    return observations


def _log_coverage(markets):
    import datetime
    tss = [m["resolutionTimestamp"] for m in markets if m.get("resolutionTimestamp")]
    if not tss:
        print("  No resolution timestamps found")
        return
    earliest = min(tss)
    latest   = max(tss)
    print(f"  Resolution date range: "
          f"{datetime.datetime.utcfromtimestamp(earliest).date()} "
          f"– {datetime.datetime.utcfromtimestamp(latest).date()}")
    cats = {}
    for m in markets:
        cats[m["category"]] = cats.get(m["category"], 0) + 1
    print("  By category:", dict(sorted(cats.items(), key=lambda x: -x[1])))


def _log_horizon_counts(obs):
    counts = {}
    for o in obs:
        counts[o["horizon"]] = counts.get(o["horizon"], 0) + 1
    print("  Observations by horizon:", counts)


def _log_category_counts(obs):
    counts = {}
    for o in obs:
        counts[o["category"]] = counts.get(o["category"], 0) + 1
    print("  Observations by category:", dict(sorted(counts.items(), key=lambda x: -x[1])))


def save_dataset(observations, path="data/processed/observations.json"):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(observations, indent=2), encoding="utf-8")
    print(f"[Step 1] Saved {len(observations)} observations -> {path}")


def load_dataset(path="data/processed/observations.json"):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Run fetch/resolved.py first to build dataset: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    obs = build_dataset(verbose=True)
    save_dataset(obs)
