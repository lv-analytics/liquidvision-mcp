"""
liquidvision_cascade_guard — a Hummingbot script that market-makes one perp
and pulls its quotes while a liquidation cascade is running on that coin.

Market makers get run over in cascades: forced orders sweep the book in one
direction and every resting quote on the wrong side fills at a loss. The
LiquidVision.app cascade feed marks those minutes relative to the coin's own
normal minute; this script cancels its orders and stays out for
`pause_minutes` after the last cascade, then resumes.

Copy into hummingbot/scripts/ and run:  start --script liquidvision_cascade_guard.py
Free endpoint, no key (60 req/min per IP; the script polls once a minute).
Docs: https://liquidvision.app/llms.txt
"""
import json
import logging
import time
import urllib.request
from decimal import Decimal
from typing import Dict, List

from hummingbot.core.data_type.common import OrderType, PriceType, TradeType
from hummingbot.core.data_type.order_candidate import PerpetualOrderCandidate
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase

API = "https://liquidvision.app/api/v1"


class LiquidvisionCascadeGuard(ScriptStrategyBase):
    exchange = "binance_perpetual"
    trading_pair = "ETH-USDT"
    order_amount = Decimal("0.01")
    bid_spread = Decimal("0.0010")
    ask_spread = Decimal("0.0010")
    order_refresh_s = 15
    pause_minutes = 20
    poll_s = 60

    markets = {exchange: {trading_pair}}

    _next_order = 0.0
    _next_poll = 0.0
    _paused_until = 0.0

    @property
    def lv_symbol(self) -> str:
        base, quote = self.trading_pair.split("-")
        return f"{base}USDT"

    def _poll_cascades(self) -> None:
        if time.time() < self._next_poll:
            return
        self._next_poll = time.time() + self.poll_s
        try:
            req = urllib.request.Request(f"{API}/liquidations/cascades?hours=2&limit=200",
                                         headers={"User-Agent": "liquidvision-hummingbot/0.1"})
            with urllib.request.urlopen(req, timeout=8) as r:
                events = json.loads(r.read()).get("events", [])
        except Exception as e:   # fail open: never stop quoting because the feed is down
            self.logger().warning(f"LiquidVision unavailable: {e}")
            return
        mine = [e for e in events if e.get("symbol") == self.lv_symbol]
        if mine:
            last_end = max(int(e.get("end") or e.get("start") or 0) for e in mine) / 1000
            until = last_end + self.pause_minutes * 60
            if until > time.time() and until > self._paused_until:
                worst = max(mine, key=lambda e: e.get("usd", 0))
                self.logger().info(
                    f"LiquidVision: {self.lv_symbol} cascade {worst.get('side')} ${worst.get('usd', 0):,.0f} "
                    f"({worst.get('x_normal', 0):.0f}x normal) — pausing quotes for {self.pause_minutes} min")
                self._paused_until = until

    def on_tick(self):
        self._poll_cascades()
        if time.time() < self._paused_until:
            self._cancel_all()
            return
        if time.time() < self._next_order:
            return
        self._cancel_all()
        mid = self.connectors[self.exchange].get_price_by_type(self.trading_pair, PriceType.MidPrice)
        orders: List[PerpetualOrderCandidate] = [
            PerpetualOrderCandidate(self.trading_pair, True, OrderType.LIMIT, TradeType.BUY,
                                    self.order_amount, mid * (Decimal(1) - self.bid_spread)),
            PerpetualOrderCandidate(self.trading_pair, True, OrderType.LIMIT, TradeType.SELL,
                                    self.order_amount, mid * (Decimal(1) + self.ask_spread)),
        ]
        for o in self.connectors[self.exchange].budget_checker.adjust_candidates(orders, all_or_none=False):
            if o.amount > 0:
                place = self.buy if o.order_side == TradeType.BUY else self.sell
                place(self.exchange, o.trading_pair, o.amount, o.order_type, o.price)
        self._next_order = time.time() + self.order_refresh_s

    def _cancel_all(self):
        for o in self.get_active_orders(connector_name=self.exchange):
            self.cancel(self.exchange, o.trading_pair, o.client_order_id)

    def format_status(self) -> str:
        state = "PAUSED (cascade)" if time.time() < self._paused_until else "quoting"
        left = max(0, int(self._paused_until - time.time()))
        return f"LiquidVision cascade guard on {self.trading_pair}: {state}" + (f", {left}s left" if left else "")
