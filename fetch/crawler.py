"""
Step 5 — Prospective live crawler (runs in background).

Collects data that the historical API cannot provide:
  - Hourly price bars for top-N markets by economic volume
  - Order-book snapshots every 15 min for top-50 (the only path to measured fill data)
  - Resolution outcome logging on market close

Run with: python fetch/crawler.py
Logs accumulate in data/raw/crawler/. Each session appends; do not overwrite.
"""

import json
import os
import sys
import time
import datetime
import urllib.request
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (GAMMA_BASE, CLOB_BASE, RATE_LIMIT_CLOB, RATE_LIMIT_GAMMA,
                    ECO_VOLUME_FACTOR)


CRAWLER_DIR      = Path("data/raw/crawler")
PRICE_INTERVAL   = 3600          # 1 hour between price bar snapshots
BOOK_INTERVAL    = 900           # 15 min between order-book snapshots
TOP_N_PRICE      = 100           # markets to track for price history
TOP_N_BOOK       = 50            # markets to snapshot order books for
CLOB_SLEEP       = 60 / RATE_LIMIT_CLOB
GAMMA_SLEEP      = 60 / RATE_LIMIT_GAMMA


def _get(url, sleep=CLOB_SLEEP):
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
        time.sleep(sleep)
        return data
    except Exception as e:
        print(f"  [crawler] GET error {url[:80]}: {e}")
        return None


def _append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def fetch_active_markets(limit=200):
    """Return top markets by volume (active only)."""
    params = urllib.parse.urlencode({
        "active": "true", "closed": "false",
        "order": "volume", "ascending": "false", "limit": limit
    })
    data = _get(f"{GAMMA_BASE}/markets?{params}", sleep=GAMMA_SLEEP)
    if not data:
        return []
    markets = []
    for m in data:
        tokens = m.get("clobTokenIds") or []
        if len(tokens) < 1:
            continue
        try:
            vol = float(m.get("volume") or 0) * ECO_VOLUME_FACTOR
        except (TypeError, ValueError):
            vol = 0.0
        markets.append({
            "id":           m.get("id"),
            "question":     m.get("question", "")[:80],
            "volume_eco":   vol,
            "token_yes":    tokens[0],
            "token_no":     tokens[1] if len(tokens) > 1 else None,
            "end_date":     m.get("endDate"),
        })
    markets.sort(key=lambda x: -x["volume_eco"])
    return markets


def fetch_newly_resolved(known_ids):
    """Return markets that have just closed and aren't in known_ids."""
    params = urllib.parse.urlencode({
        "closed": "true", "active": "false",
        "order": "endDate", "ascending": "false", "limit": 100
    })
    data = _get(f"{GAMMA_BASE}/markets?{params}", sleep=GAMMA_SLEEP)
    if not data:
        return []
    new_resolved = []
    for m in data:
        if m.get("id") in known_ids:
            continue
        tokens = m.get("clobTokenIds") or []
        if len(tokens) != 2:
            continue
        op = m.get("outcomePrices")
        if isinstance(op, str):
            try:
                op = json.loads(op)
            except Exception:
                op = None
        resolution = None
        if isinstance(op, list) and len(op) == 2:
            try:
                if float(op[0]) > 0.99:
                    resolution = 1
                elif float(op[1]) > 0.99:
                    resolution = 0
            except (TypeError, ValueError):
                pass
        new_resolved.append({
            "id":          m.get("id"),
            "question":    m.get("question", "")[:80],
            "resolution":  resolution,
            "end_date":    m.get("endDate"),
            "token_yes":   tokens[0],
        })
    return new_resolved


def snapshot_prices(markets):
    """Fetch current price for each market's YES token and log."""
    ts = int(time.time())
    for m in markets:
        url = f"{CLOB_BASE}/midpoint?token_id={m['token_yes']}"
        data = _get(url)
        if data is None:
            continue
        record = {
            "ts":       ts,
            "mkt_id":   m["id"],
            "question": m["question"],
            "mid":      data.get("mid"),
        }
        _append_jsonl(CRAWLER_DIR / "prices.jsonl", record)


def snapshot_books(markets):
    """Fetch order-book depth for top-N markets and log."""
    ts = int(time.time())
    for m in markets[:TOP_N_BOOK]:
        url = f"{CLOB_BASE}/book?token_id={m['token_yes']}"
        data = _get(url)
        if data is None:
            continue
        bids = data.get("bids", [])
        asks = data.get("asks", [])
        record = {
            "ts":       ts,
            "mkt_id":   m["id"],
            "question": m["question"],
            "best_bid": bids[0]["price"] if bids else None,
            "best_ask": asks[0]["price"] if asks else None,
            "n_bids":   len(bids),
            "n_asks":   len(asks),
            # depth USDC within 2 cents of mid
            "depth_2c_bid_usdc": _depth_near_mid(bids, 0.02, side="bid",
                                                   mid=_mid(bids, asks)),
            "depth_2c_ask_usdc": _depth_near_mid(asks, 0.02, side="ask",
                                                   mid=_mid(bids, asks)),
        }
        _append_jsonl(CRAWLER_DIR / "books.jsonl", record)


def _mid(bids, asks):
    try:
        return (float(bids[0]["price"]) + float(asks[0]["price"])) / 2
    except Exception:
        return 0.5


def _depth_near_mid(orders, half_band, side, mid):
    total = 0.0
    for o in orders:
        try:
            p = float(o["price"])
            s = float(o["size"])
        except (TypeError, ValueError, KeyError):
            continue
        if abs(p - mid) <= half_band:
            total += p * s   # USDC value
    return round(total, 2)


def log_resolution(market, ts_now):
    record = {
        "ts":         ts_now,
        "mkt_id":     market["id"],
        "question":   market["question"],
        "resolution": market["resolution"],
        "end_date":   market["end_date"],
    }
    _append_jsonl(CRAWLER_DIR / "resolutions.jsonl", record)
    print(f"  [crawler] RESOLVED: {market['question'][:60]} → {market['resolution']}")


def run():
    print("[crawler] Starting prospective data crawler. Ctrl-C to stop.")
    CRAWLER_DIR.mkdir(parents=True, exist_ok=True)

    last_price_snap = 0
    last_book_snap  = 0
    known_resolved  = set()

    while True:
        now = int(time.time())

        markets = fetch_active_markets(limit=TOP_N_PRICE + 50)
        price_markets = markets[:TOP_N_PRICE]
        book_markets  = markets[:TOP_N_BOOK]

        # Hourly price snapshot
        if now - last_price_snap >= PRICE_INTERVAL:
            print(f"  [crawler] price snapshot ({len(price_markets)} markets)")
            snapshot_prices(price_markets)
            last_price_snap = now

        # 15-min order book snapshot
        if now - last_book_snap >= BOOK_INTERVAL:
            print(f"  [crawler] book snapshot ({len(book_markets)} markets)")
            snapshot_books(book_markets)
            last_book_snap = now

        # Resolution detection
        new_res = fetch_newly_resolved(known_resolved)
        for m in new_res:
            log_resolution(m, now)
            known_resolved.add(m["id"])

        time.sleep(60)  # check every minute


if __name__ == "__main__":
    run()
