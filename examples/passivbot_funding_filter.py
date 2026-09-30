#!/usr/bin/env python3
"""Keep Passivbot out of coins where holding the position is expensive or where
a liquidation cascade is running. Standard library only, no API key.

Passivbot reads `live.ignored_coins` from an external file continuously, split
by side. This script rewrites that file every few minutes from live data:

  funding   A long that sits in a grid for days pays funding the whole time.
            Coins where longs pay more than --max-long-apr a year go on the
            long ignore list; coins where shorts pay more than --max-short-apr
            go on the short one. The rate is annualized with the contract's
            real settlement interval (about half of the Binance and Bybit alts
            settle every 4 hours, not 8), and hourly venues use their 8-hour
            average instead of one noisy print.
  cascades  A coin whose longs were liquidated for more than --cascade-usd in
            the last --cooldown minutes goes on the long ignore list (the same
            for shorts). With Passivbot's default auto_gs a position that is
            already open keeps being managed; only new ones are held back.

Usage
    python passivbot_funding_filter.py --exchange bybit --out ignored_coins.json
    # then in the Passivbot config:  "ignored_coins": "ignored_coins.json"

    python passivbot_funding_filter.py --exchange hyperliquid --once   # print and exit

Coverage: about 90 contracts per exchange (the top-100 coins by market cap that
have a perpetual). A coin outside that set is never added to the list.

Data: https://liquidvision.app (free, 240 requests a minute without a key; this
script makes 2 per run). It is a filter built on public data, not advice and
not a signal with a track record: check the thresholds against your own config.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

API = "https://liquidvision.app/api/v1"


def get(path: str):
    req = urllib.request.Request(API + path, headers={"User-Agent": "passivbot-funding-filter/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def coin(symbol: str) -> str:
    """BTCUSDT -> BTC, the way Passivbot names coins."""
    return symbol[:-4] if symbol.endswith("USDT") else symbol


def funding_apr(exchange: str) -> dict[str, float]:
    """coin -> annualized funding in % on one exchange (positive = longs pay)."""
    out = {}
    for r in get("/funding"):
        if r.get("exchange") != exchange or r.get("stale") or r.get("funding_rate") is None:
            continue
        hours = float(r.get("funding_hours") or 8)
        # contracts that settle faster than 8 h carry an 8-hour average of their rate
        rate = r.get("funding_rate_8h_avg", r["funding_rate"])
        out[coin(r["symbol"])] = rate * 8760 / hours * 100
    return out


def recent_cascades(min_usd: float, cooldown_min: int) -> dict[str, set[str]]:
    """side -> coins with a liquidation cascade of that side in the cooldown window."""
    now = time.time() * 1000
    hit = {"long": set(), "short": set()}
    for e in get("/liquidations/cascades?hours=24&limit=200").get("events", []):
        if e.get("usd", 0) >= min_usd and now - e.get("end", 0) <= cooldown_min * 60_000:
            hit.setdefault(e.get("side"), set()).add(coin(e["symbol"]))
    return hit


def build(args) -> tuple[dict, list[str]]:
    apr = funding_apr(args.exchange)
    if not apr:
        raise RuntimeError(f"no fresh funding rows for exchange '{args.exchange}'")
    casc = recent_cascades(args.cascade_usd, args.cooldown)
    long_pay = {c for c, a in apr.items() if a > args.max_long_apr}
    short_pay = {c for c, a in apr.items() if a < -args.max_short_apr}
    keep = set()
    if args.also and os.path.exists(args.also):
        with open(args.also) as f:
            extra = json.load(f)
        keep = set(extra if isinstance(extra, list) else extra.get("long", []) + extra.get("short", []))
    ignored = {
        "long": sorted(long_pay | (casc["long"] & apr.keys()) | keep),
        "short": sorted(short_pay | (casc["short"] & apr.keys()) | keep),
    }
    lines = [f"{args.exchange}: {len(apr)} contracts with fresh funding"]
    for c in sorted(long_pay, key=lambda c: -apr[c])[:10]:
        lines.append(f"  no new LONG  {c:<10} longs pay {apr[c]:+.1f}% a year")
    for c in sorted(short_pay, key=lambda c: apr[c])[:10]:
        lines.append(f"  no new SHORT {c:<10} shorts pay {-apr[c]:+.1f}% a year")
    for side in ("long", "short"):
        for c in sorted(casc[side] & apr.keys()):
            lines.append(f"  no new {side.upper():<5} {c:<10} {side}s liquidated in a cascade in the last {args.cooldown} min")
    lines.append(f"  ignored: {len(ignored['long'])} long, {len(ignored['short'])} short")
    return ignored, lines


def write_atomic(path: str, data: dict) -> None:
    """Passivbot may read the file at any moment: never leave it half-written."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--exchange", required=True,
                   help="binance, bybit, okx, bitget, gate, kucoin, hyperliquid, mexc, bingx, htx, aster, kraken, gmx")
    p.add_argument("--max-long-apr", type=float, default=30.0, help="ignore longs above this funding, %% a year (default 30)")
    p.add_argument("--max-short-apr", type=float, default=30.0, help="ignore shorts when they pay more than this, %% a year (default 30)")
    p.add_argument("--cascade-usd", type=float, default=2_000_000, help="a cascade this large blocks that side (default 2,000,000)")
    p.add_argument("--cooldown", type=int, default=60, help="minutes a cascade keeps the side blocked (default 60)")
    p.add_argument("--also", help="your own ignore file (a list, or {long, short}); always kept ignored")
    p.add_argument("--out", default="ignored_coins.json", help="file Passivbot reads (default ignored_coins.json)")
    p.add_argument("--every", type=int, default=300, help="seconds between updates (default 300)")
    p.add_argument("--once", action="store_true", help="print the result and exit without writing")
    args = p.parse_args()

    while True:
        try:
            ignored, lines = build(args)
            print(time.strftime("%H:%M:%S"), *lines, sep="\n", flush=True)
            if args.once:
                print(json.dumps(ignored))
                return 0
            write_atomic(args.out, ignored)
        except Exception as e:   # keep the last good file: an API hiccup must not un-ignore everything
            print(time.strftime("%H:%M:%S"), f"update failed, previous file kept: {e}", file=sys.stderr, flush=True)
            if args.once:
                return 1
        time.sleep(args.every)


if __name__ == "__main__":
    sys.exit(main())
