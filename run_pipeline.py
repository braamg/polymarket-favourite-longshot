"""
Main pipeline runner for the favourite-longshot validation.

Steps:
  0  [done] Fidelity bug confirmed — resolved markets return data at fidelity>=720
  1  Build resolved-market dataset
  2  Compute calibration residuals + BH correction
  3  Apply per-decile one-way cost floors
  4  Compute payoff distribution + Kelly sim
     (Steps 2-4 all called from report/findings.py)
  5  Crawler is started separately: python fetch/crawler.py

Usage:
  python run_pipeline.py [--rebuild]   # --rebuild forces re-fetching all API data
"""

import sys
import argparse
from pathlib import Path

from fetch.resolved import build_dataset, save_dataset, load_dataset
from report.findings import run as generate_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true",
                        help="Re-fetch all data from APIs (ignores cache)")
    args = parser.parse_args()

    obs_path = "data/processed/observations.json"

    if args.rebuild or not Path(obs_path).exists():
        print("=== Step 1: Building resolved-market dataset ===")
        obs = build_dataset(verbose=True)
        save_dataset(obs, obs_path)
    else:
        print(f"=== Step 1: Loading cached dataset from {obs_path} ===")
        obs = load_dataset(obs_path)
        print(f"  {len(obs)} observations loaded")

    print("\n=== Steps 2-4: Calibration -> Cost floor -> Distribution ===")
    verdict = generate_report()

    print(f"\n{'='*60}")
    print(f"  Pipeline complete. Verdict: {verdict}")
    print(f"  See FAVOURITE_LONGSHOT_FINDINGS.md for full report.")
    if verdict == "NO-GO":
        print("  The calibration edge does not survive costs. Stop here.")
    elif verdict == "CONDITIONAL":
        print("  Edge is present but not fully stable. Run crawler for 6 weeks.")
    else:
        print("  GO — review surviving segments before any deployment.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
