"""CLOB API client — price history with caching, rate limiting, and fidelity logic."""

import json
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (CLOB_BASE, RATE_LIMIT_CLOB, CACHE_DIR,
                    RESOLVED_FIDELITY_MIN, RESOLVED_FIDELITY_DAILY,
                    MIN_PRICE_BARS)


_SLEEP = 0.15   # 6-7 req/s, well under the 100/min limit
_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def _cache_path(token_id, fidelity):
    p = Path(CACHE_DIR) / "clob"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{token_id}_f{fidelity}.json"


def get_price_history(token_id, fidelity=RESOLVED_FIDELITY_MIN, force=False):
    """
    Fetch /prices-history for token_id at given fidelity (minutes).
    Returns list of {"t": unix_ts, "p": float} dicts, newest-last.

    For RESOLVED markets use fidelity >= 720 (12h).
    Returns [] if the API returns empty or an error occurs.
    """
    cp = _cache_path(token_id, fidelity)
    if not force and cp.exists():
        return json.loads(cp.read_text(encoding="utf-8"))

    params = {
        "market":   token_id,
        "interval": "max",
        "fidelity": fidelity,
    }
    url = f"{CLOB_BASE}/prices-history?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        time.sleep(_SLEEP)
    except Exception as e:
        print(f"  [clob] ERROR fetching {token_id}: {e}")
        return []

    bars = data.get("history", [])
    cp.write_text(json.dumps(bars), encoding="utf-8")
    return bars


def price_at_ttr(bars, resolution_ts, ttr_seconds):
    """
    Return the last price bar at or before (resolution_ts - ttr_seconds).
    Returns None if no bar exists that far before resolution.

    bars: list of {"t": int, "p": float}, assumed sorted ascending by t.
    """
    if resolution_ts is None:
        return None
    target = resolution_ts - ttr_seconds
    chosen = None
    for bar in bars:
        if bar["t"] <= target:
            chosen = bar["p"]
        else:
            break
    return chosen


def fetch_with_fallback(token_id, is_resolved=True):
    """
    Fetch price history, trying fidelity=720 first, then 1440 if too few bars.
    Returns (bars, fidelity_used) tuple.
    """
    bars = get_price_history(token_id, fidelity=RESOLVED_FIDELITY_MIN)
    if len(bars) >= MIN_PRICE_BARS:
        return bars, RESOLVED_FIDELITY_MIN

    # Try coarser if not enough bars at 12h
    bars = get_price_history(token_id, fidelity=RESOLVED_FIDELITY_DAILY)
    return bars, RESOLVED_FIDELITY_DAILY


def get_live_book(token_id):
    """Fetch current order book snapshot for a token."""
    url = f"{CLOB_BASE}/book?token_id={token_id}"
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        time.sleep(_SLEEP)
        return data
    except Exception as e:
        print(f"  [clob] ERROR fetching book for {token_id}: {e}")
        return None


def get_live_price(token_id):
    """Fetch current mid-price."""
    url = f"{CLOB_BASE}/midpoint?token_id={token_id}"
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        time.sleep(_SLEEP)
        return float(data.get("mid") or 0)
    except Exception as e:
        print(f"  [clob] ERROR fetching midpoint for {token_id}: {e}")
        return None
