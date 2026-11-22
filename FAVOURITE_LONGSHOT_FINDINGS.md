# FAVOURITE_LONGSHOT_FINDINGS.md
**Generated: 2026-06-15 10:29 UTC**
**Overall verdict: CONDITIONAL**

> **Erratum (November 2026, added for the public version).** This report is the pipeline's
> output as generated in June 2026. Two of its numbers should not be read at face value:
>
> - **The two "passing" crypto cells (Step 2).** Their residuals (0.2566 and 0.0828) are
>   arithmetically correct, but the cells hold only 5 and 6 markets, and every one of them
>   resolved Yes, so each residual is simply 1 minus the average price. They are all
>   "will the price touch X by date" markets, which resolve early the moment the level is hit,
>   so the price 24 hours before resolution is chosen with knowledge of the outcome. This is a
>   selection artefact, not an edge, and with no losing market in either cell the bootstrap
>   interval cannot be wide.
> - **The half-Kelly simulation (Step 4).** The Kelly fraction formula in
>   `evaluate/distribution.py` is a simplification that clips at 1.0 here, so "half Kelly" staked
>   50% of the bankroll on every trade, with no costs, resampled over 277 trades. The resulting
>   terminal-wealth figures are an artefact of that formula and mean nothing. The drawdown figures
>   come from the same broken sizing.
>
> The verdict is unchanged: **CONDITIONAL, do not deploy.**

---

## Step 0 — Fidelity Bug Confirmation

**CONFIRMED**: Resolved/closed markets return non-empty price history when
`fidelity ≥ 720` (12-hour bars). The prior [MEASURED] finding of empty history
was an artefact of using sub-12h fidelity.

Empirical tests (2026-06-15):
- Trump 2024 election (resolved Nov 2024): **500 bars at fidelity=720** (Jan 4 2024 → Nov 6 2024)
- Same market at fidelity=1440: **365 daily bars** covering full history
- Short-duration sport markets (< 3 days): still empty — below minimum bar count

**The paid-data [BLOCKER] is removed for the calibration question on markets ≥ 2 weeks.**
Short-duration intraday markets (sports final minutes, 5-min crypto) remain inaccessible
without a live crawler or paid data.

---

## Step 1 — Dataset Coverage

- **Observations**: 4202 (market × TTR-horizon pairs with valid price)
- **Unique markets**: 1484
- **Resolution date span**: 2024-07-16 – 2026-06-15
- **Volume adjustment**: 0.47× nominal → economic (Qin & Yang 2026) applied to
  capacity/volume fields; price/outcome pairs unchanged.
- **Wash flag**: markets with wash share > 10% flagged [MODELLED — no on-chain wallet graph]

Markets at 24h TTR by category:
  - Sports: 371
  - Politics: 185
  - Culture: 81
  - Music: 72
  - Bitcoin: 60
  - Trump: 51
  - Soccer: 51
  - Romania: 47
  - Global Elections: 46
  - Crypto: 46
  - World: 45
  - NHL: 32
  - USA Election: 31
  - NBA: 30
  - Biden: 27
  - college football: 26
  - Jerome Powell: 25
  - NFL: 24
  - Movies: 24
  - Fed Rates: 22
  - NYMEX Crude Oil Futures: 21
  - Elections: 16
  - football: 16
  - house: 14
  - nyc: 12
  - Trump Cabinet: 12
  - All: 11
  - box office: 11
  - Macro Fed: 9
  - u.s. election: 9
  - Featured: 8
  - Economy: 7
  - German Election: 7
  - Middle East: 7
  - Epstein: 7
  - eu: 6
  - Economic Policy: 4
  - Iran: 4
  - january 6: 3
  - Celebrities: 1
  - Gov Shutdown: 1
  - 2025 Predictions: 1
  - resign: 1

---

## Step 2 — Calibration Residuals

**Independence handling**: one (price, outcome) observation per market per horizon.
CIs are block-bootstrap clustered by market. Pooled SEs are NOT used.
**Total cells tested**: 29 (bin × category × horizon, min 5 markets per cell)
**Multiple-testing correction**: Benjamini-Hochberg at FDR = 0.10

### Cells passing GO criteria
(residual > floor × 1.5, CI lower bound > 0, BH-significant)

Horizon Category     Bin              Resid   CI lo   CI hi   Floor     Net Leg       
─────────────────────────────────────────────────────────────────────────────────────
24h    Crypto       0.70–0.80       0.2566  0.2332  0.2780  0.0168  0.2398 favourite 
24h    Crypto       0.90–0.95       0.0828  0.0773  0.0875  0.0143  0.0685 favourite 

### Cells killed by cost floor
(25 of 29 cells — residual < one-way floor)

---

## Step 3 — Per-Decile One-Way Cost Floor

[MODELLED] where Gibbs spread used as prior (arXiv 2604.24366). Gas at $0.01.
One-way cost only — position held to resolution, no exit trade.

### Favourite leg (p ≥ 0.50)

Bin             Fee (Spt)  Fee (Cry)   ½-Spread  Floor (Spt)   Net edge
─────────────────────────────────────────────────────────────────
0.99–1.01           1.76%  [MODELLED]      -1.41%
0.90–0.95           1.43%  [MODELLED]       6.85%
0.70–0.80           1.68%  [MODELLED]      23.98%

### Longshot leg (p < 0.50)

Expected finding: longshot spread premium + fee makes this leg unprofitable.

0.00–0.05      residual=-0.0058  floor=42.00%  net=-42.58%  passes=False
0.00–0.05      residual=-0.0039  floor=41.90%  net=-42.29%  passes=False
0.00–0.05      residual=-0.0007  floor=41.87%  net=-41.94%  passes=False
0.00–0.05      residual=-0.0016  floor=40.86%  net=-41.02%  passes=False
0.05–0.10      residual=-0.0668  floor=15.33%  net=-22.01%  passes=False
0.10–0.20      residual=-0.1425  floor=7.47%  net=-21.72%  passes=False
0.20–0.30      residual=-0.2549  floor=4.80%  net=-30.29%  passes=False

---

## Step 4 — Payoff Distribution and Kelly Simulation

### Favourite leg (p ≥ 0.50)
- n = 277
- Win rate: 91.0%
- Avg win: +0.2283 | Avg loss: -0.9600
- Mean return: +0.1211
- Skewness: -1.1563  (negative = left-skewed / disaster tail)
- Sortino ratio: 0.3598
- CVaR-5%: -1.0000  (avg return in worst 5% of trades)
- Fractional Kelly f*: 1.0000

Kelly sim (½-Kelly, 277 trades, 5000 resamplings):
- Median terminal wealth: 10407.14× start
- P10 terminal wealth:    40.02× start
- Median max drawdown:    92.7%
- P90 max drawdown:       98.6%
- Fraction exceeding 30% drawdown threshold: 100.0%

### Longshot leg (p < 0.50)
- n = 3925
- Win rate: 2.5%
- Avg win: +8.5631 | Avg loss: -1.0000
- Mean return: -0.7612
- Skewness: 30.9681  (negative = left-skewed / disaster tail)
- Sortino ratio: -3.2287
- CVaR-5%: -1.0000  (avg return in worst 5% of trades)
- Fractional Kelly f*: 0.0000

---

## Walk-Forward Sign Stability

Chronological split into ≥4 windows. Sign must be consistent across all windows.

Crypto       0.00–0.05      [UNSTABLE]  residuals: -0.0009  -0.0008  -0.0019
Crypto       0.70–0.80      [UNSTABLE]  residuals: +0.2567
Crypto       0.90–0.95      [UNSTABLE]  residuals: +0.0862
Culture      0.00–0.05      [STABLE]  residuals: -0.0014  -0.0005  -0.0005  -0.0005
Politics     0.00–0.05      [STABLE]  residuals: -0.0054  -0.0012  -0.0024  -0.0071
Politics     0.99–1.01      [UNSTABLE]  residuals: +0.0012
Sports       0.00–0.05      [STABLE]  residuals: -0.0059  -0.0066  -0.0035  -0.0079
Sports       0.05–0.10      [UNSTABLE]  residuals: -0.0687  -0.0674
Sports       0.10–0.20      [UNSTABLE]  residuals: -0.1389  -0.1449
Sports       0.20–0.30      [UNSTABLE]  residuals: -0.2717  -0.2424

---

## Overall Verdict

## CONDITIONAL

2 cells clear the cost floor but fail sign-stability or the CI crosses zero in some walk-forward windows.

Edge appears in some cells but is not sign-stable or CI crosses zero.
Do NOT deploy. Extend prospective crawler and retest in 6 weeks.

---

## [MODELLED] Dependencies

- Entry half-spread: Gibbs spread medians from arXiv 2604.24366 [MODELLED]
- Wash-share per-market: median 1%, tail 22% from arXiv 2604.24366 [MODELLED — no on-chain wallet graph]
- Gas cost: $0.01/trade [MODELLED — Polygon subsidy ceiling]
- Longshot spread premium: 2.5× base spread for p < 0.15 [MODELLED]

Any result labelled [MODELLED] is CONDITIONAL on the assumption. Replacing
modelled quantities with measured data (prospective crawler order-book snapshots)
is required before any GO result becomes deployable.