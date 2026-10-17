"""
LiquidVisionGuard — a Freqtrade strategy mixin that keeps a strategy out of
coins where a liquidation cascade is running or longs are being flushed.

Why: a long entry signalled from candles alone looks the same whether new
money is buying or the move is forced selling that has not finished. Two free
signals from LiquidVision.app separate them:

  * /liquidations/cascades — cascades as events per coin, measured relative to
    the coin's own normal minute (so a mid-cap's 8x minute counts as much as BTC's).
  * /oi/regime — price change crossed with open-interest change per coin:
    new_longs / short_covering / new_shorts / long_flush.

Entry is refused when the pair had a cascade in the last N minutes, or when its
regime is `long_flush` (for longs) / `short_covering` (for shorts). Data is
refreshed at most every 60 s, failures never block trading (fail open).

Use:
    from LiquidVisionGuard import LiquidVisionGuard

    class MyStrategy(LiquidVisionGuard, IStrategy):
        lv_cascade_minutes = 30        # optional knobs, defaults shown
        lv_block_regimes_long = ("long_flush",)
        lv_block_regimes_short = ("short_covering",)
        ...

The mixin implements confirm_trade_entry(); if your strategy has its own, call
`self.lv_allows(pair, side)` inside it. Free endpoints, no key (60 req/min per
IP); set LIQUIDVISION_API_KEY in the environment to send a Pro/Bot key.
Docs: https://liquidvision.app/llms.txt
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from datetime import datetime

logger = logging.getLogger(__name__)

API = os.environ.get("LIQUIDVISION_BASE_URL", "https://liquidvision.app/api/v1").rstrip("/")


def _get(path: str) -> dict:
    headers = {"User-Agent": "liquidvision-freqtrade/0.1", "Accept": "application/json"}
    key = os.environ.get("LIQUIDVISION_API_KEY")
    if key:
        headers["X-API-Key"] = key
    with urllib.request.urlopen(urllib.request.Request(API + path, headers=headers), timeout=10) as r:
        return json.loads(r.read())


def lv_symbol(pair: str) -> str:
    """'BTC/USDT:USDT' or 'BTC/USDT' -> 'BTCUSDT'; '1000PEPE/USDT:USDT' -> '1000PEPEUSDT'."""
    base = pair.split("/")[0].upper()
    return f"{base}USDT"


class LiquidVisionGuard:
    lv_cascade_minutes: int = 30
    lv_block_regimes_long: tuple = ("long_flush",)
    lv_block_regimes_short: tuple = ("short_covering",)
    lv_refresh_s: int = 60

    _lv_at: float = 0.0
    _lv_cascade_until: dict = {}
    _lv_regime: dict = {}

    def _lv_refresh(self) -> None:
        if time.time() - self._lv_at < self.lv_refresh_s:
            return
        self._lv_at = time.time()
        try:
            c = _get("/liquidations/cascades?hours=6&limit=200")
            until = {}
            for e in c.get("events", []):
                end_ms = int(e.get("end") or e.get("start") or 0)
                t = end_ms / 1000 + self.lv_cascade_minutes * 60
                until[e["symbol"]] = max(until.get(e["symbol"], 0), t)
            self._lv_cascade_until = until
        except Exception as ex:   # fail open
            logger.warning("LiquidVision cascades unavailable: %s", ex)
        try:
            r = _get("/oi/regime?minutes=240")
            self._lv_regime = {row["symbol"]: row["regime"] for row in r.get("rows", [])}
        except Exception as ex:
            logger.warning("LiquidVision regime unavailable: %s", ex)

    def lv_allows(self, pair: str, side: str) -> bool:
        self._lv_refresh()
        sym = lv_symbol(pair)
        if self._lv_cascade_until.get(sym, 0) > time.time():
            logger.info("LiquidVision: skip %s %s, liquidation cascade in the last %d min", side, pair, self.lv_cascade_minutes)
            return False
        regime = self._lv_regime.get(sym)
        blocked = self.lv_block_regimes_long if side == "long" else self.lv_block_regimes_short
        if regime in blocked:
            logger.info("LiquidVision: skip %s %s, regime %s", side, pair, regime)
            return False
        return True

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: str | None,
                            side: str, **kwargs) -> bool:
        return self.lv_allows(pair, side)


if __name__ == "__main__":
    # quick check without Freqtrade: python LiquidVisionGuard.py BTC/USDT:USDT ETH/USDT:USDT
    import sys
    g = LiquidVisionGuard()
    for p in sys.argv[1:] or ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]:
        print(p, "long ok" if g.lv_allows(p, "long") else "long BLOCKED",
              "| regime:", g._lv_regime.get(lv_symbol(p)), "| cascade:", g._lv_cascade_until.get(lv_symbol(p), 0) > time.time())
