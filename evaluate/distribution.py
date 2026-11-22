"""
Step 4 — Payoff distribution, skewness, CVaR, and fractional-Kelly bankroll simulation.

Buying favourites is structurally short-vol / negative-skew:
  - Win small often (buy at 0.80, collect 1.00 → +25% per dollar staked)
  - Lose large rarely  (buy at 0.80, get 0.00 → -100% per dollar staked)

Required outputs:
  - Win rate, avg win, avg loss, skewness, Sortino ratio, CVaR-5%
  - Walk-forward fractional-Kelly bankroll sim: terminal-wealth distribution, max drawdown
"""

import math
import random
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import RANDOM_SEED, BOOTSTRAP_SAMPLES, MAX_KELLY_DRAWDOWN


def trade_pnl(price, outcome, net_edge_frac):
    """
    PnL per dollar staked (normalised to stake = price, so PnL is per-share basis).
    If YES wins: you paid `price`, receive 1.00 → gross return = (1 - price)/price per dollar
    If NO  wins: you paid `price`, receive 0.00 → gross return = -1.0 per dollar

    net_edge_frac is the expected edge already accounting for one-way cost.
    We simulate raw outcome PnL (pre-knowing the net_edge) to get the distribution.
    """
    if outcome == 1:  # YES
        return (1.0 - price) / price
    else:             # NO
        return -1.0


def compute_payoff_stats(observations, leg="favourite"):
    """
    Compute payoff distribution statistics for a set of (price, outcome) observations.
    leg = 'favourite' (price >= 0.5) or 'longshot' (price < 0.5)

    Returns dict with: n, win_rate, avg_win, avg_loss, skewness, sortino, cvar5, kelly_f
    """
    data = [o for o in observations if o.get("price_at_ttr") is not None]
    if leg == "favourite":
        data = [o for o in data if o["price_at_ttr"] >= 0.5]
    else:
        data = [o for o in data if o["price_at_ttr"] < 0.5]

    if len(data) < 10:
        return None

    returns = [trade_pnl(o["price_at_ttr"], o["resolution"], 0) for o in data]

    wins  = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    win_rate  = len(wins) / len(returns)
    avg_win   = sum(wins) / len(wins) if wins else 0
    avg_loss  = sum(losses) / len(losses) if losses else 0

    mean_r = sum(returns) / len(returns)
    n = len(returns)

    # Skewness
    variance = sum((r - mean_r) ** 2 for r in returns) / n
    std = math.sqrt(variance) if variance > 0 else 1e-9
    skewness = (sum((r - mean_r) ** 3 for r in returns) / n) / (std ** 3)

    # Sortino (downside std only)
    downside = [min(r - mean_r, 0) ** 2 for r in returns]
    downside_std = math.sqrt(sum(downside) / n) if downside else 1e-9
    sortino = mean_r / downside_std if downside_std > 0 else 0

    # CVaR at 5% (expected return in worst 5% of trades)
    sorted_r = sorted(returns)
    cutoff = max(1, int(0.05 * n))
    cvar5 = sum(sorted_r[:cutoff]) / cutoff

    # Fractional Kelly: f* = edge / odds
    # For YES bets at price p: odds = (1-p)/p, edge = net_edge_per_dollar_staked
    # Use mean_r as edge proxy (raw P&L includes edge and risk premium)
    avg_price = sum(o["price_at_ttr"] for o in data) / len(data)
    odds = (1 - avg_price) / avg_price if avg_price < 1 else 0
    kelly_f = mean_r / (odds * (1 - win_rate) + (1 - win_rate))  # simplified
    kelly_f = max(0, min(kelly_f, 1))  # clip to [0, 1]

    return {
        "n":         n,
        "win_rate":  round(win_rate, 4),
        "avg_win":   round(avg_win, 4),
        "avg_loss":  round(avg_loss, 4),
        "mean_return": round(mean_r, 4),
        "skewness":  round(skewness, 4),
        "sortino":   round(sortino, 4),
        "cvar5":     round(cvar5, 4),
        "kelly_f":   round(kelly_f, 4),
        "leg":       leg,
    }


def kelly_simulation(observations, fraction=0.5, n_sims=BOOTSTRAP_SAMPLES,
                     leg="favourite", max_drawdown_threshold=MAX_KELLY_DRAWDOWN):
    """
    Walk-forward fractional-Kelly bankroll simulation.

    At each trade, stake = fraction * kelly_f * bankroll.
    Returns: {
        terminal_wealth_pct_list,   # distribution of terminal wealth % vs. start
        max_drawdown_list,          # distribution of max drawdown
        median_terminal_wealth,
        p10_terminal_wealth,
        median_max_drawdown,
        p90_max_drawdown,
        pct_below_max_dd_threshold,
    }
    """
    random.seed(RANDOM_SEED)

    data = [o for o in observations if o.get("price_at_ttr") is not None]
    if leg == "favourite":
        data = [o for o in data if o["price_at_ttr"] >= 0.5]
    else:
        data = [o for o in data if o["price_at_ttr"] < 0.5]

    if len(data) < 20:
        return None

    stats = compute_payoff_stats(data, leg=leg)
    if stats is None or stats["kelly_f"] <= 0:
        return None

    f_star = stats["kelly_f"] * fraction   # fractional Kelly

    terminal_wealths = []
    max_drawdowns    = []

    for _ in range(n_sims):
        # Shuffle trades for this simulation run (walk-forward: use chronological order
        # in the actual run; shuffle here for distribution)
        sample = random.choices(data, k=len(data))
        bankroll = 1.0
        peak     = 1.0
        max_dd   = 0.0

        for o in sample:
            price   = o["price_at_ttr"]
            outcome = o["resolution"]
            stake   = f_star * bankroll
            if outcome == 1:
                bankroll += stake * (1 - price) / price
            else:
                bankroll -= stake
            bankroll = max(bankroll, 0)
            if bankroll > peak:
                peak = bankroll
            dd = (peak - bankroll) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        terminal_wealths.append(bankroll)
        max_drawdowns.append(max_dd)

    terminal_wealths.sort()
    max_drawdowns.sort()
    n = len(terminal_wealths)

    median_tw  = terminal_wealths[n // 2]
    p10_tw     = terminal_wealths[n // 10]
    median_dd  = max_drawdowns[n // 2]
    p90_dd     = max_drawdowns[int(n * 0.9)]
    pct_bad_dd = sum(1 for d in max_drawdowns if d > max_drawdown_threshold) / n

    return {
        "fraction_used":             fraction,
        "kelly_f":                   stats["kelly_f"],
        "median_terminal_wealth_x":  round(median_tw, 3),
        "p10_terminal_wealth_x":     round(p10_tw, 3),
        "median_max_drawdown":       round(median_dd, 4),
        "p90_max_drawdown":          round(p90_dd, 4),
        "pct_exceeds_dd_threshold":  round(pct_bad_dd, 4),
        "n_trades":                  len(data),
    }
