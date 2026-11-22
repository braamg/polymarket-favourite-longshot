# PRE-REGISTERED PARAMETERS — do not tune after seeing results.
# Written before any measurement per the spec.

# ── Fidelity ──────────────────────────────────────────────────────────────────
# Minimum fidelity (minutes) that returns data for resolved markets.
# Confirmed empirically 2026-06-15: fidelity<720 returns empty for resolved markets.
RESOLVED_FIDELITY_MIN = 720          # 12-hour bars — finest granularity for resolved markets
RESOLVED_FIDELITY_DAILY = 1440       # 24-hour bars — use for full-span coverage on long markets

# ── Price snapshot horizons (Step 2) ──────────────────────────────────────────
# Fixed time-before-resolution windows at which we snapshot the price.
# One independent (price, outcome) observation per market per horizon.
TTR_HORIZONS_SECONDS = {
    "24h":  24 * 3600,
    "7d":   7  * 24 * 3600,
    "30d":  30 * 24 * 3600,
}

# ── Calibration bins (pre-registered before running) ─────────────────────────
# Decile bins plus finer resolution at the extremes where fee advantage lives.
PRICE_BINS = [0.0, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50,
              0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 0.99, 1.01]

# ── Categories to include (geopolitics excluded — killed in Phase 0 V5) ───────
VALID_CATEGORIES = {"Crypto", "Sports", "Politics", "Finance", "Tech", "Culture"}
EXCLUDED_CATEGORIES = {"Geopolitics"}

# ── Data quality filters ──────────────────────────────────────────────────────
MIN_VOLUME_USDC     = 500      # exclude markets below this nominal volume (too thin to de-dup)
WASH_SHARE_MAX      = 0.10     # exclude / flag markets with self-counterparty share > 10%
ECO_VOLUME_FACTOR   = 0.47     # nominal → economic volume adjustment (Qin & Yang 2026)
MIN_PRICE_BARS      = 3        # minimum bars returned before a market is considered usable

# ── Walk-forward windows ──────────────────────────────────────────────────────
MIN_WALK_FORWARD_WINDOWS = 4   # minimum chronological subperiods for sign-stability test

# ── GO / NO-GO thresholds (per the spec) ─────────────────────────────────────
# A decile is GO only if: net_edge > 0 AND net_edge >= one_way_floor * FLOOR_MULTIPLIER
# AND the CI lower bound (clustered bootstrap) is above zero.
FLOOR_MULTIPLIER    = 1.5      # edge must clear its own floor by at least 1.5×
MIN_CAPACITY_USD    = 500      # minimum deployable per trade (economic volume)
MAX_KELLY_DRAWDOWN  = 0.30     # maximum acceptable drawdown in Kelly simulation

# ── Fee structure (by category, effective from dates below) ──────────────────
# taker fee formula: fee = rate * p * (1 - p) per share
# Makers pay 0. One-way cost applies (no exit trade; positions redeemed at settlement).
FEE_RATES = {
    "Crypto":       0.07,
    "Sports":       0.03,
    "Politics":     0.04,
    "Finance":      0.04,
    "Tech":         0.04,
    "Mentions":     0.04,
    "Economics":    0.05,
    "Culture":      0.05,
    "Weather":      0.05,
    "Geopolitics":  0.00,
    "default":      0.05,
}

# Fee launch dates (Unix timestamps) — trades BEFORE these dates have zero taker fees.
# Pre-register so segmentation is done before results are seen.
import datetime, calendar
def _ts(y, m, d):
    return int(calendar.timegm(datetime.date(y, m, d).timetuple()))

FEE_LAUNCH_DATES = {
    "Crypto":    _ts(2026, 1, 1),    # January 2026
    "Sports":    _ts(2026, 2, 18),   # February 18 2026
    "default":   _ts(2026, 3, 1),    # March 2026 (all other categories)
}

# ── Gibbs spread priors (literature, [MODELLED]) ─────────────────────────────
# From arXiv 2604.24366. Applied as entry half-spread prior when live data not available.
GIBBS_SPREAD_MEDIAN = {
    "Crypto":    0.0069,
    "Politics":  0.0152,
    "Sports":    0.0160,
    "default":   0.0150,
}
LONGSHOT_SPREAD_PREMIUM_P_THRESHOLD = 0.15  # apply extra spread premium below this price

# ── Gas cost ─────────────────────────────────────────────────────────────────
GAS_COST_USD = 0.01    # conservative ceiling per trade on Polygon [MODELLED]

# ── Bootstrap ────────────────────────────────────────────────────────────────
BOOTSTRAP_SAMPLES = 5000
BOOTSTRAP_CI      = 0.90    # report 90% CI (5th–95th percentile)
RANDOM_SEED       = 42

# ── API settings ─────────────────────────────────────────────────────────────
GAMMA_BASE   = "https://gamma-api.polymarket.com"
CLOB_BASE    = "https://clob.polymarket.com"
DATA_BASE    = "https://data-api.polymarket.com"
RATE_LIMIT_GAMMA = 60   # requests per minute
RATE_LIMIT_CLOB  = 100  # requests per minute
CACHE_DIR    = "data/raw"
