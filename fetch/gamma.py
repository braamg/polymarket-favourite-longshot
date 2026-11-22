"""Gamma API client — resolved market enumeration via the /events endpoint."""

import json
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import GAMMA_BASE, RATE_LIMIT_GAMMA, CACHE_DIR, MIN_VOLUME_USDC


_SLEEP = 60 / RATE_LIMIT_GAMMA
_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def _cache_path(name):
    p = Path(CACHE_DIR) / "gamma"
    p.mkdir(parents=True, exist_ok=True)
    return p / name


def _get(url, cache_key=None):
    if cache_key:
        cp = _cache_path(cache_key + ".json")
        if cp.exists():
            return json.loads(cp.read_text(encoding="utf-8"))

    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    time.sleep(_SLEEP)

    if cache_key:
        cp = _cache_path(cache_key + ".json")
        cp.write_text(json.dumps(data), encoding="utf-8")
    return data


def _parse_tokens(raw):
    if isinstance(raw, str):
        try: return json.loads(raw)
        except: return []
    return raw or []


def _parse_op(raw):
    if isinstance(raw, str):
        try: return json.loads(raw)
        except: return []
    return raw or []


def _parse_ts(value):
    if value is None: return None
    if isinstance(value, (int, float)): return int(value)
    import datetime, calendar
    v = str(value).strip()
    # Normalise timezone suffix so a single parser covers all variants
    v = v.replace("+00:00", "Z").replace("+00", "Z").replace(" ", "T")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.datetime.strptime(v, fmt)
            return int(calendar.timegm(dt.timetuple()))
        except ValueError:
            continue
    return None


def _extract_binary_outcome(m):
    """Return 1 if YES resolved, 0 if NO resolved, None if unclear."""
    op = _parse_op(m.get("outcomePrices"))
    if len(op) == 2:
        try:
            p0, p1 = float(op[0]), float(op[1])
            if p0 > 0.99: return 1
            if p1 > 0.99: return 0
        except (TypeError, ValueError):
            pass
    return None


def _extract_category(event, market):
    """Best-effort category string from event or market tags."""
    for src in (event, market):
        tags = src.get("tags") or []
        if tags:
            t = tags[0]
            if isinstance(t, dict):
                return t.get("label") or t.get("slug") or "Unknown"
            return str(t)
    return (event.get("category") or market.get("category") or "Unknown")


def _market_from_event(event, m):
    """Extract one market dict from an event's market entry."""
    tokens = _parse_tokens(m.get("clobTokenIds"))
    if len(tokens) != 2:
        return None

    outcome = _extract_binary_outcome(m)
    if outcome is None:
        return None

    try:
        vol = float(m.get("volumeClob") or m.get("volume") or 0)
    except (TypeError, ValueError):
        vol = 0.0

    # closedTime = actual resolution time; endDate = scheduled close (use as fallback)
    end_ts   = _parse_ts(m.get("closedTime") or m.get("endDate"))
    start_ts = _parse_ts(m.get("startDate"))

    # Skip markets that are too short for any TTR horizon
    if end_ts and start_ts:
        duration_h = (end_ts - start_ts) / 3600
        if duration_h < 24:
            return None
    else:
        duration_h = None

    category = _extract_category(event, m)

    return {
        "id":                  m.get("id"),
        "conditionId":         m.get("conditionId"),
        "question":            m.get("question"),
        "category":            category,
        "event_title":         event.get("title"),
        "volume":              vol,
        "resolution":          outcome,        # 1=YES, 0=NO
        "resolutionTimestamp": end_ts,
        "startDate":           start_ts,
        "endDate":             end_ts,
        "duration_h":          duration_h,
        "clobTokenYes":        str(tokens[0]),
        "clobTokenNo":         str(tokens[1]),
    }


def get_resolved_markets(min_volume=MIN_VOLUME_USDC, page_size=100, max_events=50):
    """
    Enumerate resolved binary markets via the /events endpoint.

    Strategy: paginate /events?closed=true ordered by volume descending.
    Each event contains its markets inline. Extract all binary markets.
    """
    markets = []
    event_count = 0
    offset = 0

    while event_count < max_events:
        cache_key = f"events_closed_offset{offset}_size{page_size}_v2"
        url = (f"{GAMMA_BASE}/events"
               f"?closed=true&limit={page_size}&offset={offset}"
               f"&order=volume&ascending=false")
        page = _get(url, cache_key=cache_key)

        if not page:
            break

        for event in page:
            event_count += 1
            mkts = event.get("markets") or []
            for m in mkts:
                rec = _market_from_event(event, m)
                if rec is None:
                    continue
                if rec["volume"] < min_volume:
                    continue
                markets.append(rec)

        print(f"  events fetched: {event_count}, markets kept: {len(markets)}")

        if len(page) < page_size:
            break
        offset += page_size
        if event_count >= max_events:
            break

    print(f"[gamma] total resolved binary markets: {len(markets)} from {event_count} events")
    return markets
