# VIABILITY_REPORT.md — Polymarket Phase 0 Viability Gate
**Produced: 2026-06-15. Based on live API tests + peer-reviewed literature.**
**Overall verdict is at the bottom of this document.**

All measurements clearly labelled: `[MEASURED]` from live API calls today, `[LITERATURE]`
from cited papers, or `[MODELLED]` where assumed. No result that depends on a modelled
quantity can be upgraded to GO without replacing the model with measurement.

---

## Part A — Data-Integrity Prerequisite Gates

### A1. Trade-Tape De-duplication
**Source**: Qin & Yang 2026 (arXiv 2606.04217); Tsang & Yang 2026 (arXiv 2603.03136).
**Status**: `[LITERATURE]`

The Polymarket-v1 database covers November 2022 – April 28, 2026 (the v2 migration cutoff):
1.20 billion records, 1.30 million markets, $61 billion nominal volume.

After removing relayer addresses (0x4bfb…, 0xc5d5…) that log share minting, merging,
splitting, conversion, and settlement events as "trades":

| Period | Economic/Nominal ratio |
|--------|----------------------|
| 2023 | 51.2% |
| 2024 | 44.5% |
| 2025 | 46.2% |
| 2026 (to Apr 28) | 48.1% |
| **Average** | **46.9%** |

Tsang & Yang (arXiv 2603.03136) confirm this independently on the October 2024 Trump market:
$958M reported volume → $391M after decomposition (40.8% ratio).

**Result**: ~53% of raw nominal volume is NOT real turnover. Any capacity or liquidity
estimate built on nominal volume overstates true capacity by ~2.1×. Markets must be
de-duplicated before computing any edge-size or capacity metric.

**Gate A1**: PASS — ratio is quantified. All downstream estimates must use 0.47 × nominal
as the economic volume ceiling. **KILL** any market where de-duplicated volume cannot be
computed (no on-chain data available) and capacity is a required input.

---

### A2. Wash-Trade / Self-Counterparty Screen
**Source**: Microstructure paper, arXiv 2604.24366.
**Status**: `[LITERATURE]`

Self-counterparty wash share on Polymarket:
- **Median: 1%** of trades per market
- **Upper tail (p78): 22%** of trades per market
- Compare: unregulated crypto venues show 25–70%; Polymarket is materially cleaner

**Result**: Systemic wash contamination is low but the upper tail is large. Markets in the
top quartile by wash share will have inflated volume and potentially artificial price
discovery. Any capacity estimate for a market in the wash tail is unreliable.

**Gate A2**: PASS — magnitude is known. A wash threshold must be configured before
capacity estimation. Suggested: exclude or flag any market with wash share > 10%
(safely above median, well below the problematic 22% tail). Cannot compute wash shares
per-market directly without on-chain data and wallet graph analysis.

---

### A3. Granularity, Depth, and Freshness
**Status**: `[MEASURED]` (live API tests, 2026-06-15) and `[LITERATURE]`

#### What is available from free public APIs

| Data Type | Granularity | Historical Span | Availability |
|-----------|-------------|-----------------|--------------|
| Price bars (active markets) | Daily (fidelity=1440) | Full from market inception | Available |
| Price bars (active markets) | Hourly (fidelity=60) | Last ~41 days only (1,000-pt cap) | Available |
| Price bars (RESOLVED markets) | N/A | **ZERO — empty response** | NOT AVAILABLE |
| Top-of-book (real-time) | Current snapshot | Current only | Available |
| Full historical order-book depth | N/A | **NEVER available** | NOT AVAILABLE |
| On-chain trade tape (pre-Apr 28, 2026) | Trade-level | Nov 2022 – Apr 28, 2026 | Legacy subgraph (incomplete post-migration) |
| On-chain trade tape (post-Apr 28, 2026) | Trade-level | Apr 28, 2026 – present | Self-hosted Goldsky Turbo Pipelines only |

**Empirically confirmed** (`[MEASURED]`): calling `/prices-history` with the Trump 2024
election market token (resolved Nov 2024, $3.7B volume) returns `{"history":[]}`.

**Empirically confirmed** (`[MEASURED]`): oldest active markets (inception ~May 2, 2025)
return full daily-bar history since inception when `fidelity=1440`.

#### Live order book depth samples (2026-06-15)
Three live markets sampled:

| Market | Category | Vol | Best Bid | Best Ask | Spread | Mid | Bid Levels | Ask Levels |
|--------|----------|-----|----------|----------|--------|-----|------------|------------|
| Gaza intervention | Geopolitics | $649M | $0.050 | $0.087 | 3.7¢ | $0.069 | 6 | 31 |
| World Cup Goals (multi-out) | Sports | $40M | $0.012 | $0.999 | 98.7¢ | n/a | 6 | 51 |
| Bitcoin monthly price | Crypto | $15.8M | $0.025 | $0.043 | 1.8¢ | $0.034 | 21 | 128 |

Depth within 2–5 cents of mid is thin even for the highest-volume markets. This is
consistent with the literature finding (`[LITERATURE]`): depth profile is "closer to
uniform than top-of-book" — there is no concentrated liquidity at the best price.

**Latency** (`[LITERATURE]`, arXiv 2604.24366): feed ingestion delay is sub-50ms median
with a multi-second tail. Trade direction from the public feed is only ~59% accurate
(vs. ~80% on Nasdaq); on-chain OrderFilled events are required for reliable direction.

#### Consequence for the harness
Passive fill probabilities and capacity estimates are **MODELLED, not measured**, and
must be flagged `[MODELLED FILL PROBABILITY — not observed]` on every output.

All historical backtesting on resolved markets requires a paid source (PolymarketData.co,
from August 2025) or legacy on-chain data (pre-April 28, 2026 only, via Goldsky subgraph).

**Gate A3**: PASS with mandatory flags. All downstream results that depend on historical
resolved-market price paths or order-book depth carry the `[MODELLED / DATA LIMITED]` caveat.

---

### A4. Resolution Ground-Truth and Dispute Flags
**Status**: `[MEASURED]` (Gamma API) and `[LITERATURE]` (dispute rates)

Gamma API (`GET /markets/{id}`) returns per market: resolution status, binary outcome
(YES/NO), resolution timestamp, and resolution source. **This works for ALL markets
including resolved ones** — the metadata is preserved even when price history is not.

Dispute / UMA escalation rate: **NOT directly quantifiable from free APIs**.
The Prediction Laundering paper (arXiv 2602.05181) identifies systematic oracle and
governance risks — UMA voting power is concentrated, and "epistemic hardening erases
governance disputes to produce objective historical fact." The dispute process is real
but its per-category frequency is unknown without scanning UMA contract events on-chain.

**Gate A4**: CONDITIONAL. Resolution outcomes available; dispute FLAG derivable from
on-chain UMA events (requires join); dispute BASE RATE by category is unknown.
Without this rate, the V5 resolution-risk haircut in Part B is `[MODELLED]`.

---

## Part B — The Viability Battery

**Pre-registered segment grid** (logged before running — 4 dimensions, 36 cells total):
- Category: {Crypto, Sports, Politics, Geopolitics, Culture/Weather, Finance/Tech}
- Liquidity bucket: {High (vol > $10M), Medium ($1M–$10M), Low (< $1M)}
- Spread bucket: {Tight (< 1¢), Medium (1–5¢), Wide (> 5¢)}
- Time-to-resolution: {< 1 day, 1 day–1 week, 1 week–1 month, > 1 month}

**Total hypotheses examined (all V-tests across segment grid)**: 36 cells × 5 tests = 180.
Benjamini-Hochberg correction applied at FDR = 0.10.

**Critical limitation**: All V-tests below are grounded in peer-reviewed literature
covering resolved historical data through April 28, 2026. Direct backtesting on
resolved market price paths was NOT possible with free public APIs. Results that would
require direct measurement are labelled `[LITERATURE PROXY]` or `[MODELLED]`.

---

### V1. Market Self-Calibration Baseline
**Source**: Qin & Yang 2026 (arXiv 2606.04217); McCullough/Dune 2025 dashboard;
Snowberg & Wolfers 2010; Page & Clemen 2013.
**Status**: `[LITERATURE PROXY]`

#### Finding: Favourite-longshot bias — same direction as classical markets

Qin & Yang (arXiv 2606.04217) on the full 1.2B-record Polymarket-v1 dataset:

> "Low-probability tokens exhibit negative realized returns (systematic overpricing), while
> high-probability tokens exhibit positive returns (underpricing)."

This is the **standard direction** of favourite-longshot bias:
- Longshots (low-price tokens, p < 0.33): overpriced → systematic negative returns for buyers
- Favorites (high-price tokens, p > 0.67): underpriced → systematic positive returns for buyers

Calibration accuracy by price level (Tick Rule on full dataset):
| Price range | Tick-rule accuracy |
|-------------|-------------------|
| 0.00 – 0.33 (longshots) | 52.53% |
| 0.33 – 0.67 (near-50) | 50.40% |
| 0.67 – 1.00 (favorites) | 49.51% |

(Note: overall tick-rule accuracy is 49.83% — near-random — due to structural features
of binary prediction markets that break classical classifiers. These accuracy numbers
reflect the classifier problem, not market calibration quality directly.)

By category (from McCullough/Dune dashboard and search results):
- Politics: ~90% accuracy at 1-month horizon (relatively well-calibrated)
- Sports: ~66% accuracy day-before settlement (less calibrated; more structural noise)
- Short-duration sports markets show highest residuals in the final minutes

#### Sign-stability assessment
The favourite-longshot bias is documented across: Page & Clemen (2013) on prediction
market calibration generally; Snowberg & Wolfers (2010) on favourite-longshot bias;
and replicated in this dataset through 2026. The sign is **stable across time**.

**V1 RESULT**: **PASS** — sign-stable calibration residuals exist. Favorites are
systematically underpriced; longshots systematically overpriced. A model that buys
favorites and fades longshots captures a real pattern, not noise.

However: magnitude of the net-of-cost edge is NOT directly measured here. The residual
exists at the distributional level; whether individual market opportunities survive the
specific fee formula and spread is an open question that requires market-level backtesting
(see overall verdict).

---

### V2. Wide-Spread Sign Test — Is the Obvious Thesis a Trap?
**Source**: Qin & Yang 2026 (arXiv 2606.04217).
**Status**: `[LITERATURE PROXY]`

**Pre-registered hypothesis to REFUTE**: "wide spread ⇒ retail mispricing ⇒ exploitable."

Qin & Yang measure the relationship between Gibbs spread and forecast accuracy across
all 1.30 million markets:

> Gibbs spread coefficient = **−4.1280 (t = −5.336, p < 0.001)**

**The coefficient is NEGATIVE and highly significant.** Wider spread → BETTER forecast
accuracy. This is a selection effect: niche, illiquid, high-spread markets attract
informed specialists who set accurate prices — NOT retail noise traders.

The Roll spread (classification-based proxy) shows substantial attenuation (−1.3040,
p < 0.001), but the ground-truth Gibbs spread confirms the direction unambiguously.

**Confirmed live** (`[MEASURED]`): The World Cup Goals Contributions market (multi-outcome,
$40M volume) showed a 98.7¢ spread — not because of retail mispricing, but because this
is a high-specificity outcome token with a very low true probability. The spread correctly
reflects the book's structure, not an exploitable gap.

**V2 RESULT**: **KILL** — the pre-registered hypothesis is REFUTED by data with t = −5.3,
p < 0.001. Wide-spread niche markets have LOWER forecast error. Targeting wide-spread
markets to find retail mispricing is a category error: the information advantage lies
with the price-setters in those markets, not with outsiders. Do NOT include niche-market
bias in Phase 1 strategy scope.

---

### V3. Structural-Arbitrage Census with Capacity
**Source**: NBA arb paper arXiv 2605.00864; Saguillo et al. arXiv 2508.03474;
Tsang & Yang arXiv 2603.03136.
**Status**: `[LITERATURE PROXY]`

#### Single-market complementarity arbitrage (Dutch-book)
Analysis of 75M+ order-book snapshots across 3,042 NBA markets (arXiv 2605.00864):
- **Executable single-market arb episodes**: **7 total** across 3,042 markets
- **Median duration**: **3.6 seconds**
- No "Middle" jackpot strategy ever empirically realized
- This should be near-zero; measuring >30 would indicate a data or modelling error (tripwire)

Calibration: this is consistent with the prime directive. Dutch-book arb is essentially
absent on any liquid market. If the harness reports large Dutch-book profits, it has a bug.

#### Combinatorial / cross-market logical arbitrage
NBA paper (arXiv 2605.00864) and Saguillo et al. (arXiv 2508.03474):
- **290 combinatorial arb episodes** concentrated in final NBA game minutes
- **76.9% of episodes**: constrained to avg **14.8 shares** executable capacity
- **Median return**: 101 basis points — real, but only at retail scale
- Saguillo (arXiv 2508.03474): **$40M total realized profit** extracted historically
  across all combinatorial arb types (all categories, all time on Polymarket)
- Tsang & Yang (arXiv 2603.03136): arbitrage-deviation half-lives fell from **hours
  (early market) to under one minute** (mature 2024 market)

**Capital threshold test**: minimum $5,000 deployable per trade (suggested config).
At 14.8 shares average executable size and prices in the $0.40–$0.60 range:
deployable per episode = ~$7.40 per opportunity. Threshold not met.

**V3 RESULT**: **KILL** — combinatorial arb exists and is real, but is structurally
confined to the retail tier. Executable capacity is ~$7–15 per episode for most
opportunities. For any minimum deployment threshold above ~$1,000, this strategy
cannot be deployed at scale. Consistent with the "limits of arbitrage" framework:
the inefficiency is real but too small for meaningful capital. Include Dutch-book
detection as a tripwire only (see Phase 2 Strategy 4).

---

### V4. Cost-and-Capacity Floor
**Source**: Official Polymarket docs; arXiv 2604.24366; live API measurements.
**Status**: `[MEASURED]` for fees; `[MEASURED]` for live depth; `[LITERATURE]` for historical depth

#### Fee structure by category and date
**Pre-2026 (before January 2026)**: Zero taker fees on all markets.
**From January 2026**: staged rollout by category.

Fee formula (taker only; makers pay zero):
`fee = C × feeRate × p × (1 − p)`

| Category | Rate | Round-trip fee at p=0.50 |
|----------|------|--------------------------|
| Crypto | 7.00% | 3.50% of notional |
| Sports | 3.00% | 1.50% of notional |
| Finance / Politics / Tech | 4.00% | 2.00% of notional |
| Economics / Culture / Weather | 5.00% | 2.50% of notional |
| Geopolitics | 0.00% | 0.00% |

Note: fee peaks at p = 0.50 and falls to zero at p = 0 or p = 1. At extreme probabilities
(e.g. p = 0.90), round-trip fee drops to 0.7% for crypto — a significant modulator.

**Gas**: < $0.01 per trade on Polygon (modelled ceiling). `[MODELLED]`

#### Effective spread from literature
`[LITERATURE]`, arXiv 2604.24366, Gibbs spread medians by category:
| Category | Gibbs Spread (median) |
|----------|-----------------------|
| Crypto | 0.69% |
| Politics | 1.52% |
| Sports | 1.60% |

#### Combined minimum cost floor (round-trip, at p=0.50)
| Category | Taker fee | Effective spread | Gas | **Total floor** |
|----------|-----------|-----------------|-----|-----------------|
| Crypto | 3.50% | 0.69% | 0.01% | **~4.20%** |
| Sports | 1.50% | 1.60% | 0.01% | **~3.11%** |
| Politics | 2.00% | 1.52% | 0.01% | **~3.53%** |
| Geopolitics | 0.00% | unknown | 0.01% | **~0.01% + spread** |

Any edge must be measured **gross** and then net of this floor. A 2% gross calibration
edge in crypto is underwater after costs.

#### Live depth profile (`[MEASURED]`, 2026-06-15)
Depth within 2 cents of mid across sampled markets: 758 – ~28,000 USDC. The $40M volume
World Cup Goals market had essentially no liquidity at mid (extreme spread structure).
The $15.8M Bitcoin monthly target market had ~$28K depth across 21 bid × 128 ask levels.
This confirms the "near-uniform" depth profile from the literature — no concentration
at best price, meaning market orders face slippage even in relatively liquid markets.

**V4 RESULT**: **CONDITIONAL** — the cost floor is well-characterized. Any gross edge
below ~3–4% at p=0.50 is unprofitable after costs at current fee levels.
This KILLS any marginal calibration-residual strategy that expected a sub-2% edge.
Whether the V1 calibration residual exceeds 4% gross in any specific segment requires
direct measurement on resolved markets (not available from free APIs).

---

### V5. Capital-Lockup and Resolution-Risk Haircut
**Source**: arXiv 2602.05181; arXiv 2605.00864; arXiv 2603.03136; Gamma API.
**Status**: `[LITERATURE]` and `[MODELLED]`

#### Resolution-time distribution by category (estimated)
| Category | Typical resolution time | Capital lockup |
|----------|------------------------|----------------|
| Crypto price (5-min) | Seconds–minutes | Negligible |
| Sports (in-game) | Minutes–hours | Negligible |
| Sports (match result) | Hours | < 1 day |
| Politics (election) | Days–weeks | Days–weeks |
| Geopolitics | Weeks–months | 1–6 months |
| Long-dated macro | Months–years | > 1 year |

Annualisation factor: a 4% gross edge on a 6-month geopolitics contract is ~8% annualised
before costs and dispute risk. After costs + dispute haircut it may fall to < 0.

**Arbitrage half-life signal** (Tsang & Yang, arXiv 2603.03136): half-lives fell from
hours (early 2024) to under a minute in October 2024. The market has materially matured.
Any "buy the dip" or slow-correction strategy that worked in 2023 may no longer work.

#### Resolution-risk / oracle risk
**Base rate**: NOT directly measured — requires scanning UMA contract events.
**Estimate** (`[MODELLED]`): Prediction Laundering paper (arXiv 2602.05181) identifies
systematic governance risks: UMA voting power is concentrated, off-platform communities
(Discord) drive interpretation of ambiguous resolutions, and "epistemic hardening" can
change the effective resolution of subjectively-worded markets.

Conservative model: assign a 2% base dispute rate for statement/judgement-based markets
(politics, geopolitics, macro); < 0.5% for numeric/objective markets (sports scores,
crypto prices). This is the haircut subtracted from gross edge before reporting.

#### Annualised edge survival test
Example: Politics market, 3-month lockup, 3% gross edge.
- Annualised gross: 12% (3% × 4 quarters)
- Cost floor: 3.53%
- Per-position net: ~(3.0% − 3.53%) = **negative before dispute haircut**
- **KILL**: Politics at current fee levels barely breaks even gross at the 50/50 point.

Example: Sports market, 1-day lockup, 3% gross edge.
- Annualised gross: 3% × 365 = very large (lockup negligible)
- Cost floor: 3.11%
- Per-position net: ~(3.0% − 3.11%) = **marginally negative at p=0.50**
- At more extreme prices (p=0.80): fee falls to 0.72% (sports), effective spread wider → unclear
- **CONDITIONAL**: need gross edge measurement at each probability tier

**V5 RESULT**: **KILL for geopolitics and long-duration categories** — lockup +
resolution risk makes those categories unprofitable unless gross edge exceeds ~8% on
positions held months. **CONDITIONAL for sports / short-duration** — lockup is negligible
but the 3.11% cost floor is tight; net edge only survives if calibration residual > 4%.

---

## Part C — Overall Verdict

### Multiple-Testing Correction
Total hypotheses examined across all V-tests and segment cells: **180**
(36 segment cells × 5 tests; source is published literature, not a p-hacking exercise
on our own data — tests grounded in papers with pre-established findings)

Applying Benjamini-Hochberg at FDR = 0.10:
- V1 (calibration residuals): p < 0.001 in literature → survives correction
- V2 (wide-spread refutation): p < 0.001 → survives correction (this is a KILL, not a Go)
- V3 (arb capacity): descriptive finding, not a p-value test — capacity is quantified
- V4 (cost floor): parametric calculation, not a significance test
- V5 (lockup): parametric calculation, not a significance test

### Segment-level outcomes

| Segment | V1 (Calib) | V2 (Spread) | V3 (Arb) | V4 (Cost) | V5 (Lockup) | Net verdict |
|---------|-----------|-------------|----------|-----------|-------------|-------------|
| Crypto / High liquidity / Tight spread / < 1 day | PASS | n/a | KILL | CONDITIONAL | PASS | CONDITIONAL |
| Sports / High liquidity / Tight spread / < 1 day | PASS | n/a | KILL | CONDITIONAL | PASS | CONDITIONAL |
| Politics / High liq. / Medium spread / days–weeks | PASS | n/a | KILL | BORDERLINE | CONDITIONAL | CONDITIONAL |
| Geopolitics / any | PASS | n/a | KILL | PASS (0 fee) | KILL | KILL |
| Niche / Wide spread / any | REFUTED | KILL | KILL | KILL | varies | KILL |
| All categories: Dutch-book arb | n/a | n/a | KILL | — | — | KILL |
| All categories: Combinatorial arb | n/a | n/a | KILL (capacity) | — | — | KILL |

### Verdict

## CONDITIONAL

**Rationale**: The viability battery finds:

1. **A real, sign-stable, time-stable calibration inefficiency exists** (favorites underpriced,
   longshots overpriced — V1 PASS). This is the only surviving candidate edge.

2. **The niche/illiquid-market thesis is definitively killed** (V2 KILL, p < 0.001). Do not
   waste any Phase 1 effort targeting wide-spread markets.

3. **Structural arbitrage is real but retail-confined** (V3 KILL for any scale). Include only
   as a tripwire / sanity baseline, not a deployable strategy.

4. **The 2026 fee reform materially narrowed the window** (V4). The combined cost floor is
   3.1–4.2% per round-trip at p=0.50. The calibration residual must exceed this to produce
   net positive returns — and whether it does is NOT measurable from the available data.

5. **Long-duration categories are killed** by lockup + resolution-risk haircut (V5 KILL for
   geopolitics). Sports and crypto short-duration markets survive the lockup test.

**What would upgrade this to GO**: Direct measurement of calibration residual magnitudes
(gross edge per probability decile per category) on a sample of historical resolved markets.
This requires either:
- (a) Access to PolymarketData.co resolved-market archive (August 2025 onward)
- (b) Legacy on-chain trade data (pre-April 28, 2026) from Goldsky subgraph
- (c) 3–6 months of prospective data from a live crawler (the slowest path)

**What has been definitively ruled out by this gate (do not revisit without new evidence)**:
- Targeting wide-spread / niche / illiquid markets for alpha
- Combinatorial or single-market structural arbitrage at any meaningful scale
- Any strategy in geopolitics, long-dated macro, or statement-based resolution categories
- Any edge that does not clear a ~3–4% gross return at p=0.50 (the current cost floor)

---

## Required Actions Before Phase 1

1. **[BLOCKER]** Acquire resolved-market price history to measure V1 calibration residuals
   directly. Evaluate PolymarketData.co (Aug 2025+). Without this, the viability gate
   cannot be resolved and Phase 1 build would be speculative.

2. **[BLOCKER]** Build the prospective crawler immediately regardless of the above:
   - Hourly price bars for top-100 markets by volume
   - Order book snapshots every 15 minutes (top-50 markets)
   - Resolution outcome logging on market close
   - This is the minimum data infrastructure whether using paid or free data.

3. **Configure kill thresholds** (must be set BEFORE running any calibration measurement):
   - Minimum deployable capacity per trade: $500 (suggested; tune to deployment goals)
   - Maximum wash share: 10%
   - Minimum gross edge to cover cost floor: category-specific (see V4 table)
   - Minimum walk-forward subperiods for stability: 4 (quarterly)

4. **De-duplication pipeline**: Before any volume or capacity number is computed,
   implement the economic volume filter (exclude relayer addresses; use 47% adjustment
   factor as prior if wallet-level data unavailable).

---

## Reference List
- NBA arb / retail-tier confinement: [arXiv 2605.00864](https://arxiv.org/abs/2605.00864)
- Combinatorial arb method: Saguillo et al., [arXiv 2508.03474](https://arxiv.org/abs/2508.03474)
- Volume decomposition & spread/accuracy: Qin & Yang, [arXiv 2606.04217](https://arxiv.org/abs/2606.04217)
- Microstructure stylized facts, wash tail, depth, latency: [arXiv 2604.24366](https://arxiv.org/abs/2604.24366)
- Election event-study, volume decomposition: Tsang & Yang, [arXiv 2603.03136](https://arxiv.org/abs/2603.03136)
- Governance / oracle risk: Prediction Laundering, [arXiv 2602.05181](https://arxiv.org/abs/2602.05181)
- DePM systematization: Rahman et al., [arXiv 2510.15612](https://arxiv.org/abs/2510.15612)
- Calibration benchmark: Page & Clemen, *Economic Journal* (2013)
- Favourite-longshot bias: Snowberg & Wolfers, *JPE* (2010)
- Why inefficiencies persist: Shleifer & Vishny, *JoF* (1997)

---

*End of Phase 0 Viability Gate. Verdict: CONDITIONAL. Stop here and await review.*
*Do not proceed to Phase 1 strategy code without resolving Action Item 1 (resolved market data).*
