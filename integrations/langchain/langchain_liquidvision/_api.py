"""
Shared core for the LiquidVision.app agent-framework wrappers.

Nine read-only questions an agent asks about crypto derivatives, each answered
from LiquidVision.app's free "conclusion" endpoints and trimmed to a compact
JSON answer an LLM can read in one pass. No key needed (60 requests a minute
per IP); LIQUIDVISION_API_KEY raises the limit. Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

__version__ = "0.2.0"
DEFAULT_BASE = "https://liquidvision.app/api/v1"


def norm_symbol(symbol: Optional[str]) -> Optional[str]:
    """'btc', 'BTC/USDT', 'BTC-USDT-SWAP', '$BTC' -> 'BTCUSDT'."""
    if not symbol:
        return None
    s = re.sub(r"[^A-Za-z0-9]", "", symbol.upper().replace("SWAP", ""))
    if s.endswith("USDC"):
        s = s[:-4]
    return s if s.endswith("USDT") else s + "USDT"


class LiquidVisionAPI:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 15.0):
        self.api_key = api_key or os.environ.get("LIQUIDVISION_API_KEY")
        self.base = (base_url or os.environ.get("LIQUIDVISION_BASE_URL") or DEFAULT_BASE).rstrip("/")
        self.timeout = timeout

    def get(self, path: str, **params: Any) -> Any:
        q = {k: v for k, v in params.items() if v is not None}
        url = self.base + path + ("?" + urllib.parse.urlencode(q) if q else "")
        headers = {"User-Agent": f"liquidvision-agent-tools/{__version__}", "Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RuntimeError("LiquidVision rate limit reached (60/min without a key); retry in a minute") from None
            raise RuntimeError(f"LiquidVision returned HTTP {e.code} for {path}") from None

    # ------------------------------------------------------------ the six tools

    def brief(self, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        b = self.get(f"/brief/{norm_symbol(symbol) or 'BTCUSDT'}")
        liq = b.get("liquidations") or {}
        return {
            "symbol": b.get("symbol"),
            "asset": b.get("asset"),
            "liquidations_this_symbol_24h": liq.get("this_symbol_24h"),
            "liquidations_market_wide_usd": liq.get("windows_usd"),
            "funding_pct_by_exchange": (b.get("funding") or {}).get("current_pct_by_exchange"),
            "open_interest_by_venue": b.get("open_interest_by_venue"),
            "position_flows_usd": b.get("position_flows_usd"),
            "next_risk_zones": b.get("next_risk_zones"),
            "top_traders_positioning": b.get("top_traders_positioning"),
            "data_age_s": b.get("age_s"),
        }

    def positioning_regime(self, symbol: Optional[str] = None, minutes: int = 240, limit: int = 15) -> Dict[str, Any]:
        r = self.get("/oi/regime", minutes=minutes)
        rows = r.get("rows") or []
        sym = norm_symbol(symbol)
        if sym:
            rows = [x for x in rows if x.get("symbol") == sym]
        else:
            rows = sorted(rows, key=lambda x: abs(x.get("oi_delta_usd") or 0), reverse=True)[:limit]
        return {
            "window_minutes": r.get("minutes"),
            "meaning": "price up + OI up = new longs; price up + OI down = short covering; "
                       "price down + OI up = new shorts; price down + OI down = long flush",
            "market_summary": r.get("summary"),
            "coins": rows,
        }

    def liquidation_cascades(self, symbol: Optional[str] = None, hours: int = 24, limit: int = 10) -> Dict[str, Any]:
        c = self.get("/liquidations/cascades", hours=hours, limit=200)
        ev = c.get("events") or []
        sym = norm_symbol(symbol)
        if sym:
            ev = [e for e in ev if e.get("symbol") == sym]
        ev = sorted(ev, key=lambda e: e.get("usd") or 0, reverse=True)[:limit]
        keep = ("symbol", "side", "start", "minutes", "usd", "peak_usd", "x_normal", "impact_pct", "reversion_pct")
        return {
            "hours": c.get("hours"),
            "events_total": c.get("events_total"),
            "market_wide_minutes": len(c.get("market_wide") or []),
            "largest": [{k: e.get(k) for k in keep} for e in ev],
            "notes": "side = which side was liquidated; x_normal = multiples of the coin's own normal minute; "
                     "start is epoch ms; reversion_pct = how much of the move came back in the next hour. "
                     + ((c.get("detector") or {}).get("caveat") or ""),
        }

    def liquidation_map(self, symbol: str = "BTCUSDT", top: int = 5) -> Dict[str, Any]:
        m = self.get(f"/liqmap/hl/{norm_symbol(symbol) or 'BTCUSDT'}", range="1d")
        px = m.get("current_price") or 0
        bins, lo, sh = m.get("bins") or [], m.get("long") or [], m.get("short") or []
        below = sorted(((b, v) for b, v in zip(bins, lo) if b < px and v > 0), key=lambda t: -t[1])[:top]
        above = sorted(((b, v) for b, v in zip(bins, sh) if b > px and v > 0), key=lambda t: -t[1])[:top]
        fmt = lambda t: {"price": round(t[0], 6), "usd": round(t[1]), "dist_pct": round((t[0] / px - 1) * 100, 2) if px else None}
        return {
            "symbol": m.get("symbol"),
            "source": "measured Hyperliquid positions, binned by the liquidation price the exchange reports (not a model)",
            "current_price": px,
            "long_liquidations_below": [fmt(t) for t in sorted(below, key=lambda t: -t[0])],
            "short_liquidations_above": [fmt(t) for t in sorted(above, key=lambda t: t[0])],
            "total_long_below_usd": m.get("total_long_below"),
            "total_short_above_usd": m.get("total_short_above"),
            "coverage": m.get("coverage"),
            "positions": m.get("positions"),
        }

    def funding_dispersion(self, symbol: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        sym = norm_symbol(symbol)
        d = self.get("/funding/dispersion", limit=200 if sym else None)
        rows = d.get("rows") or []
        if sym:
            rows = [r for r in rows if r.get("symbol") == sym]
        out = []
        for r in rows[:limit]:
            x = {k: r.get(k) for k in ("symbol", "venues", "spread_apr", "long_venue", "long_apr",
                                       "short_venue", "short_apr", "median_apr")}
            if sym:
                x["legs"] = [{k: l.get(k) for k in ("exchange", "apr", "funding_hours")} for l in r.get("legs") or []]
            out.append(x)
        return {
            "window_minutes": d.get("window_minutes"),
            "meaning": "APR in percent, each leg annualized on its own settlement cycle. long_venue is the cheapest "
                       "place to hold a long, short_venue the richest place to hold a short.",
            "coins": out,
        }

    def tokenized_stocks(self, limit: int = 15) -> Dict[str, Any]:
        t = self.get("/stocks/tokenized")
        rows = sorted(t.get("rows") or [], key=lambda r: r.get("oi_usd") or 0, reverse=True)[:limit]
        keep = ("id", "name", "class_label", "venues", "oi_usd", "volume_24h_usd", "change_24h_pct", "mark")
        return {
            "what": "tokenized stocks, indices, commodities and FX traded as perps on DEXs",
            "underlyings": t.get("underlyings"),
            "total_oi_usd": t.get("total_oi_usd"),
            "total_volume_24h_usd": t.get("total_volume_24h_usd"),
            "by_class": t.get("by_class"),
            "largest": [{k: r.get(k) for k in keep} for r in rows],
        }

    # ------------------------------------------------------- added in 0.2.0

    def ask(self, question: str, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        coin = (norm_symbol(symbol) or "BTCUSDT")[:-4]
        a = self.get("/answer", q=question, coin=coin)
        return {
            "symbol": a.get("symbol"),
            "answer": a.get("answer"),
            "facts": a.get("facts"),
            "caveats": a.get("caveats"),
            "sources": [{"path": s.get("path"), "age_s": s.get("age_s")} for s in a.get("sources") or []],
            "note": "facts from the live endpoints, no model involved; figures, not advice",
        }

    def check_position(self, side: str, entry: float, leverage: float, symbol: str = "BTCUSDT",
                       notional_usd: float = 10_000, venue: Optional[str] = None) -> Dict[str, Any]:
        coin = (norm_symbol(symbol) or "BTCUSDT")[:-4]
        p = self.get("/position/check", symbol=coin, side=side, entry=entry, leverage=leverage,
                     notional_usd=notional_usd, venue=venue)
        keep = ("venue", "maintenance_margin_rate", "mmr_source", "liquidation_price", "distance_pct",
                "funding_cost_per_day_usd")
        return {
            "symbol": p.get("symbol"), "side": p.get("side"), "mark": p.get("mark"),
            "unrealized_pnl_pct_of_margin": p.get("unrealized_pnl_pct_of_margin"),
            "venues": [{k: v.get(k) for k in keep} for v in p.get("venues") or []],
            "leverage_between_mark_and_liquidation": p.get("leverage_between_mark_and_liquidation"),
            "archive": p.get("archive"),
            "assumptions": p.get("assumptions"),
        }

    def test_rule(self, rules: str, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        coin = (norm_symbol(symbol) or "BTCUSDT")[:-4]
        r = self.get("/rules/test", rules=rules, symbol=coin)
        out = {k: r.get(k) for k in ("symbol", "rule", "true_now", "now", "archive", "matched_hours", "episodes_n",
                                     "outcomes", "base_rate", "verdict", "note")}
        out["episodes_last"] = (r.get("episodes") or [])[-5:]
        return out


TOOL_SPECS = [
    ("liquidvision_ask", "ask",
     "Ask a plain-words question about one coin's derivatives market (why did it drop, is funding crowded, where "
     "is leverage stacked) and get short statements with the numbers in them, the facts as JSON and the sources' "
     "age. No model involved. Input: question, symbol."),
    ("liquidvision_check_position", "check_position",
     "Check YOUR OWN position: liquidation price on each venue from that venue's maintenance-margin tier, distance "
     "from the mark, how much modeled and measured leverage sits between the mark and your liquidation, funding "
     "cost per day, how often price moved that far against you in the archive. Input: side (long|short), entry, "
     "leverage, symbol, notional_usd, optional venue."),
    ("liquidvision_test_rule", "test_rule",
     "Test a trigger against the hourly archive before acting on it: rules like 'funding_apr_pct>40,oi_chg_24h_pct>5' "
     "(metrics: price_chg_1h_pct, price_chg_24h_pct, oi_chg_1h_pct, oi_chg_24h_pct, funding_apr_pct, long_pct, "
     "liq_1h_usd, liq_24h_usd); returns the episodes, 24h/72h outcomes, base rate and whether it is true now. "
     "Needs LIQUIDVISION_API_KEY (a free key allows 100 such calls a day)."),
    ("liquidvision_derivatives_brief", "brief",
     "One-coin crypto derivatives snapshot: price, open interest by venue, liquidations by side, funding per "
     "exchange, nearest liquidation zones, top-trader positioning. Input: symbol like BTC or ETHUSDT."),
    ("liquidvision_positioning_regime", "positioning_regime",
     "Is a move new money or positions closing? Per coin: price change crossed with open-interest change "
     "(new longs, short covering, new shorts, long flush). Optional symbol; without it, the biggest OI movers."),
    ("liquidvision_liquidation_cascades", "liquidation_cascades",
     "Liquidation cascades as events over the last hours: coin, side liquidated, size, multiple of normal, "
     "price impact and what price did after. Optional symbol."),
    ("liquidvision_liquidation_map", "liquidation_map",
     "Where leverage would break: measured Hyperliquid positions by exchange-reported liquidation price, the "
     "densest long-liquidation levels below price and short-liquidation levels above. Input: symbol."),
    ("liquidvision_funding_dispersion", "funding_dispersion",
     "Where the same coin pays very different funding across 13 exchanges: cheapest venue to be long, richest "
     "to be short, spread in APR. Optional symbol for per-venue legs."),
    ("liquidvision_tokenized_stocks", "tokenized_stocks",
     "Tokenized stocks, indices, commodities and FX traded as perps on DEXs (Hyperliquid, Lighter, Ostium, "
     "gTrade): open interest, volume, 24h change, largest markets."),
]


def run(api: LiquidVisionAPI, method: str, **kwargs: Any) -> str:
    """Call a tool and return JSON text; errors come back as text so the agent can carry on."""
    try:
        return json.dumps(getattr(api, method)(**{k: v for k, v in kwargs.items() if v is not None}),
                          separators=(",", ":"), default=str)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": str(e)})
