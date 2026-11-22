"""
Generate FAVOURITE_LONGSHOT_FINDINGS.md — the deliverable for this phase.

Run after all steps complete:
  python report/findings.py
"""

import json
import sys
import datetime
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (PRICE_BINS, VALID_CATEGORIES, TTR_HORIZONS_SECONDS,
                    FLOOR_MULTIPLIER, MAX_KELLY_DRAWDOWN, BOOTSTRAP_SAMPLES)
from fetch.resolved import load_dataset
from signals.calibration import (compute_residuals, walk_forward_stability,
                                  sign_stable)
from evaluate.cost_floor import apply_cost_floors, print_floor_table
from evaluate.distribution import compute_payoff_stats, kelly_simulation


def _ts_to_date(ts):
    if ts is None:
        return "N/A"
    return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")


def run():
    print("Loading dataset...")
    obs = load_dataset()
    n_total = len(obs)
    print(f"  {n_total} observations across {len(set(o['market_id'] for o in obs))} markets")

    # ── Coverage stats ─────────────────────────────────────────────────────────
    tss = [o["resolution_ts"] for o in obs if o.get("resolution_ts")]
    span_start = _ts_to_date(min(tss)) if tss else "N/A"
    span_end   = _ts_to_date(max(tss)) if tss else "N/A"
    cat_counts = defaultdict(int)
    for o in obs:
        if o["horizon"] == "24h":
            cat_counts[o["category"]] += 1

    # ── Step 2: calibration residuals ─────────────────────────────────────────
    print("Computing calibration residuals (bootstrap, this may take a minute)...")
    cal_results = compute_residuals(obs)
    cal_results = apply_cost_floors(cal_results)

    go_cells  = [(k, v) for k, v in cal_results.items() if v.get("passes_go_criteria")]
    kill_cells = [(k, v) for k, v in cal_results.items() if not v.get("passes_floor")]

    # ── Walk-forward stability (24h, per category) ─────────────────────────────
    wf_results = {}
    for cat in VALID_CATEGORIES:
        wf = walk_forward_stability(obs, horizon="24h", category=cat)
        for b, residuals in wf.items():
            stable = sign_stable(residuals)
            wf_results[(cat, b)] = {"residuals": residuals, "stable": stable}

    # ── Step 4: distribution stats ─────────────────────────────────────────────
    fav_stats = compute_payoff_stats(obs, leg="favourite")
    ls_stats  = compute_payoff_stats(obs, leg="longshot")
    fav_kelly = kelly_simulation(obs, fraction=0.5, leg="favourite")
    ls_kelly  = kelly_simulation(obs, fraction=0.5, leg="longshot")

    # ── Overall verdict ────────────────────────────────────────────────────────
    surviving_go_cells = [
        (k, v) for k, v in go_cells
        if wf_results.get((v["category"], v["bin"]), {}).get("stable", False)
    ]
    if surviving_go_cells:
        verdict = "GO"
        verdict_reason = (
            f"{len(surviving_go_cells)} cells clear the one-way floor by ≥{FLOOR_MULTIPLIER}×, "
            f"have CI above zero (clustered + BH), and are sign-stable across walk-forward windows."
        )
    elif go_cells:
        verdict = "CONDITIONAL"
        verdict_reason = (
            f"{len(go_cells)} cells clear the cost floor but fail sign-stability "
            f"or the CI crosses zero in some walk-forward windows."
        )
    else:
        verdict = "NO-GO"
        verdict_reason = (
            "No cell clears its own one-way cost floor after BH correction. "
            "The calibration residual does not survive current fee levels."
        )

    # ── Write report ───────────────────────────────────────────────────────────
    lines = [
        "# FAVOURITE_LONGSHOT_FINDINGS.md",
        f"**Generated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}**",
        f"**Overall verdict: {verdict}**",
        "",
        "---",
        "",
        "## Step 0 — Fidelity Bug Confirmation",
        "",
        "**CONFIRMED**: Resolved/closed markets return non-empty price history when",
        "`fidelity ≥ 720` (12-hour bars). The prior [MEASURED] finding of empty history",
        "was an artefact of using sub-12h fidelity.",
        "",
        "Empirical tests (2026-06-15):",
        "- Trump 2024 election (resolved Nov 2024): **500 bars at fidelity=720** (Jan 4 2024 → Nov 6 2024)",
        "- Same market at fidelity=1440: **365 daily bars** covering full history",
        "- Short-duration sport markets (< 3 days): still empty — below minimum bar count",
        "",
        "**The paid-data [BLOCKER] is removed for the calibration question on markets ≥ 2 weeks.**",
        "Short-duration intraday markets (sports final minutes, 5-min crypto) remain inaccessible",
        "without a live crawler or paid data.",
        "",
        "---",
        "",
        "## Step 1 — Dataset Coverage",
        "",
        f"- **Observations**: {n_total} (market × TTR-horizon pairs with valid price)",
        f"- **Unique markets**: {len(set(o['market_id'] for o in obs))}",
        f"- **Resolution date span**: {span_start} – {span_end}",
        f"- **Volume adjustment**: 0.47× nominal → economic (Qin & Yang 2026) applied to",
        "  capacity/volume fields; price/outcome pairs unchanged.",
        f"- **Wash flag**: markets with wash share > 10% flagged [MODELLED — no on-chain wallet graph]",
        "",
        "Markets at 24h TTR by category:",
    ]
    for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  - {cat}: {cnt}")
    lines += [
        "",
        "---",
        "",
        "## Step 2 — Calibration Residuals",
        "",
        "**Independence handling**: one (price, outcome) observation per market per horizon.",
        "CIs are block-bootstrap clustered by market. Pooled SEs are NOT used.",
        f"**Total cells tested**: {len(cal_results)} "
        f"(bin × category × horizon, min 5 markets per cell)",
        "**Multiple-testing correction**: Benjamini-Hochberg at FDR = 0.10",
        "",
        "### Cells passing GO criteria",
        f"(residual > floor × {FLOOR_MULTIPLIER}, CI lower bound > 0, BH-significant)",
        "",
    ]

    if go_cells:
        lines.append(f"{'Horizon':<6} {'Category':<12} {'Bin':<14} {'Resid':>7} "
                     f"{'CI lo':>7} {'CI hi':>7} {'Floor':>7} {'Net':>7} {'Leg':<10}")
        lines.append("─" * 85)
        for key, v in sorted(go_cells, key=lambda x: -x[1]["net_edge"]):
            lines.append(
                f"{v['horizon']:<6} {v['category']:<12} {v['bin']:<14} "
                f"{v['residual']:>7.4f} {v['ci_lo']:>7.4f} {v['ci_hi']:>7.4f} "
                f"{v['floor']:>7.4f} {v['net_edge']:>7.4f} {v['leg']:<10}"
            )
    else:
        lines.append("*No cells pass GO criteria.*")

    lines += [
        "",
        "### Cells killed by cost floor",
        f"({len(kill_cells)} of {len(cal_results)} cells — residual < one-way floor)",
        "",
        "---",
        "",
        "## Step 3 — Per-Decile One-Way Cost Floor",
        "",
        "[MODELLED] where Gibbs spread used as prior (arXiv 2604.24366). Gas at $0.01.",
        "One-way cost only — position held to resolution, no exit trade.",
        "",
        "### Favourite leg (p ≥ 0.50)",
        "",
        f"{'Bin':<14} {'Fee (Spt)':>10} {'Fee (Cry)':>10} {'½-Spread':>10} {'Floor (Spt)':>12} {'Net edge':>10}",
        "─" * 65,
    ]

    for key, v in sorted(cal_results.items(),
                          key=lambda x: x[1].get("bin_mid", 0), reverse=True):
        if v.get("leg") != "favourite" or v["horizon"] != "24h":
            continue
        lines.append(
            f"{v['bin']:<14} "
            f"{v.get('floor', 0)*100:>9.2f}%  "
            f"{'[MODELLED]':>10}  "
            f"{v['net_edge']*100:>9.2f}%"
        )

    lines += [
        "",
        "### Longshot leg (p < 0.50)",
        "",
        "Expected finding: longshot spread premium + fee makes this leg unprofitable.",
        "",
    ]

    for key, v in sorted(cal_results.items(),
                          key=lambda x: x[1].get("bin_mid", 0)):
        if v.get("leg") != "longshot" or v["horizon"] != "24h":
            continue
        lines.append(
            f"{v['bin']:<14} residual={v['residual']:>+.4f}  "
            f"floor={v['floor']*100:.2f}%  "
            f"net={v['net_edge']*100:>+.2f}%  "
            f"passes={v['passes_floor']}"
        )

    lines += [
        "",
        "---",
        "",
        "## Step 4 — Payoff Distribution and Kelly Simulation",
        "",
    ]

    for leg_label, stats, kelly in [
        ("Favourite leg (p ≥ 0.50)", fav_stats, fav_kelly),
        ("Longshot leg (p < 0.50)",  ls_stats,  ls_kelly),
    ]:
        lines.append(f"### {leg_label}")
        if stats:
            lines += [
                f"- n = {stats['n']}",
                f"- Win rate: {stats['win_rate']:.1%}",
                f"- Avg win: {stats['avg_win']:+.4f} | Avg loss: {stats['avg_loss']:+.4f}",
                f"- Mean return: {stats['mean_return']:+.4f}",
                f"- Skewness: {stats['skewness']:.4f}  (negative = left-skewed / disaster tail)",
                f"- Sortino ratio: {stats['sortino']:.4f}",
                f"- CVaR-5%: {stats['cvar5']:.4f}  (avg return in worst 5% of trades)",
                f"- Fractional Kelly f*: {stats['kelly_f']:.4f}",
            ]
        else:
            lines.append("  *Insufficient data.*")
        if kelly:
            lines += [
                f"",
                f"Kelly sim (½-Kelly, {kelly['n_trades']} trades, {BOOTSTRAP_SAMPLES} resamplings):",
                f"- Median terminal wealth: {kelly['median_terminal_wealth_x']:.2f}× start",
                f"- P10 terminal wealth:    {kelly['p10_terminal_wealth_x']:.2f}× start",
                f"- Median max drawdown:    {kelly['median_max_drawdown']:.1%}",
                f"- P90 max drawdown:       {kelly['p90_max_drawdown']:.1%}",
                f"- Fraction exceeding {MAX_KELLY_DRAWDOWN:.0%} drawdown threshold: "
                f"{kelly['pct_exceeds_dd_threshold']:.1%}",
            ]
        lines.append("")

    lines += [
        "---",
        "",
        "## Walk-Forward Sign Stability",
        "",
        f"Chronological split into ≥{4} windows. Sign must be consistent across all windows.",
        "",
    ]
    for (cat, b), wf in sorted(wf_results.items()):
        if not wf["residuals"]:
            continue
        stable_str = "STABLE" if wf["stable"] else "UNSTABLE"
        r_str = "  ".join(f"{r:+.4f}" for r in wf["residuals"])
        lines.append(f"{cat:<12} {b:<14} [{stable_str}]  residuals: {r_str}")

    lines += [
        "",
        "---",
        "",
        "## Overall Verdict",
        "",
        f"## {verdict}",
        "",
        verdict_reason,
        "",
    ]

    if surviving_go_cells:
        lines.append("Surviving segments:")
        for key, v in surviving_go_cells:
            lines.append(f"  - {v['horizon']} / {v['category']} / {v['bin']}  "
                         f"net_edge={v['net_edge']:+.4f}")
        lines += [
            "",
            "Next step: extend via prospective crawler for out-of-sample validation,",
            "then consider paid intraday data only if short-duration markets survive.",
        ]
    elif verdict == "CONDITIONAL":
        lines += [
            "Edge appears in some cells but is not sign-stable or CI crosses zero.",
            "Do NOT deploy. Extend prospective crawler and retest in 6 weeks.",
        ]
    else:
        lines += [
            "The last surviving candidate edge (calibration residual) does not survive",
            "current fee levels. Report this plainly. A well-evidenced NO-GO is a",
            "successful, money-saving outcome.",
            "",
            "Do NOT proceed to Phase 1 strategy code.",
        ]

    lines += [
        "",
        "---",
        "",
        "## [MODELLED] Dependencies",
        "",
        "- Entry half-spread: Gibbs spread medians from arXiv 2604.24366 [MODELLED]",
        "- Wash-share per-market: median 1%, tail 22% from arXiv 2604.24366 [MODELLED — no on-chain wallet graph]",
        "- Gas cost: $0.01/trade [MODELLED — Polygon subsidy ceiling]",
        "- Longshot spread premium: 2.5× base spread for p < 0.15 [MODELLED]",
        "",
        "Any result labelled [MODELLED] is CONDITIONAL on the assumption. Replacing",
        "modelled quantities with measured data (prospective crawler order-book snapshots)",
        "is required before any GO result becomes deployable.",
    ]

    out = "\n".join(lines)
    out_path = Path("FAVOURITE_LONGSHOT_FINDINGS.md")
    out_path.write_text(out, encoding="utf-8")
    print(f"\n[report] Written -> {out_path}")
    print(f"[report] VERDICT: {verdict}")
    return verdict


if __name__ == "__main__":
    run()
