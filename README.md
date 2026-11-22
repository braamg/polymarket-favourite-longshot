# Is there a favourite–longshot bias on Polymarket, and can you trade it?

**June 2026.** A viability study: before building any trading system, test whether a known pricing bias exists on Polymarket after realistic costs. **Verdict: conditional. Do not deploy.**

## The question

In betting markets, longshots tend to be overpriced and favourites slightly underpriced: the favourite–longshot bias. If Polymarket shows it, buying favourites might pay. The study asks whether the bias is there, whether it survives fees and spreads, and whether it is stable over time.

## How

Every number in the reports is labelled **[MEASURED]** (from live API calls), **[LITERATURE]** (from a cited paper) or **[MODELLED]** (an assumption). A result that rests on a modelled input can't be called a go.

- **Data-integrity gates first.** About 53% of Polymarket's nominal volume isn't real turnover (share minting, merging and settlement logged as trades) [LITERATURE], so all capacity numbers use about 0.47× nominal. Wash trading was screened per market [MODELLED].
- **A data-access check.** Price history for resolved markets looked empty at fine resolution; at 12-hour bars it's there for any market that ran two weeks or more [MEASURED]. That removed the need for paid data.
- **Dataset:** 4,202 observations (market × time-to-resolution) on 1,484 resolved markets, July 2024 to June 2026, across sports, politics, crypto, culture and more.
- **Calibration residuals:** realised win rate minus price, per price bin × category × horizon, one observation per market per horizon, with block-bootstrap confidence intervals clustered by market.
- **Multiple testing:** 29 cells tested, Benjamini–Hochberg at a 10% false-discovery rate.
- **Costs:** a one-way cost floor per price bin (fee, half-spread, gas), with a larger spread premium for longshots [MODELLED spreads].
- **Stability:** a walk-forward split into at least four windows. The sign must hold in all of them.

## What it found

- **Longshots are overpriced, as the literature says, and the cost floor makes them worse to buy:** a contract under 5¢ carries about a 41% one-way cost floor. Buying longshots lost 76% per trade on average, with a 2.5% win rate.
- **Only 2 of 29 cells passed the go criteria**, both favourites in short-horizon crypto markets, and neither was sign-stable across the walk-forward windows. Rechecking them in November 2026 showed they aren't evidence of anything: each holds only 5 or 6 markets, every one resolved Yes, and all are "will the price touch X by date" markets that resolve the moment the level is hit, so the price a day before resolution is picked with hindsight. The residual is just one minus the price.
- **Favourites win often and lose big:** a 91% win rate, but negative skew, and the worst 5% of trades lose the whole stake. The study's half-Kelly bankroll simulation is not reported here: its Kelly formula clips to full stake, so its results are an artefact (see the erratum at the top of `FAVOURITE_LONGSHOT_FINDINGS.md`).

**Verdict: CONDITIONAL.** No cell shows an edge that is both stable and real, and several inputs are modelled rather than measured. The study recommended against deploying and called for measured order-book data before any retest.

## What I'd take from this

1. **Run a viability gate before building anything.** A day of measurement saved weeks of engineering on a strategy that wouldn't survive costs.
2. **Label every number as measured, from the literature, or modelled.** A result that rests on a modelled input can't be called a go.
3. **With many cells, correct for multiple testing,** and demand sign stability over time, not just significance.
4. **Look inside the cells that pass.** Both survivors here were tiny and selected on the outcome; a significance test can't catch that.
5. **This study fed directly into the World Cup project's caution about buying longshots** (see [worldcup-2026-polymarket](https://github.com/braamg/worldcup-2026-polymarket)).

## The code

```
config.py           pre-registered parameters (bins, horizons, thresholds, fees), fixed before measuring
fetch/              Polymarket Gamma and CLOB API clients, the resolved-market dataset builder, a live crawler
signals/            calibration residuals, clustered bootstrap, Benjamini–Hochberg, walk-forward stability
evaluate/           per-bin one-way cost floors; payoff distribution and the Kelly simulation
report/             writes FAVOURITE_LONGSHOT_FINDINGS.md
run_pipeline.py     runs it end to end
```

Standard library only (tested on Python 3.12). `python run_pipeline.py` downloads the public market data into `data/` (gitignored) on its first run, which takes a while, then regenerates `FAVOURITE_LONGSHOT_FINDINGS.md`. The two reports in this repository are the June 2026 outputs:

- `VIABILITY_REPORT.md`: the phase-0 viability gate (data integrity, fees, costs, literature).
- `FAVOURITE_LONGSHOT_FINDINGS.md`: the calibration study, with a November 2026 erratum at the top.

## Data and licences

Code: MIT (see `LICENSE`). No raw Polymarket data is included; the reports contain aggregate tables only. The data comes from Polymarket's public APIs, under Polymarket's terms. The papers cited in the reports are referenced, not reproduced.
