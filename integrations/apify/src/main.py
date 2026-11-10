"""Apify Actor: one crypto-derivatives answer per run, from the LiquidVision.app API.

The Actor owner's LiquidVision key is read from the LV_API_KEY environment variable (set it
as a SECRET in the Actor's settings; never put it in the input or the code). Users of the
Actor need no key and no crypto wallet: they pay Apify per result (pay-per-event), and the
event is charged only after the answer was fetched.
"""
from __future__ import annotations

import os

import httpx
from apify import Actor

API = "https://liquidvision.app/api/v1"

# event name (configured with its price in the Apify console) per mode
EVENTS = {
    "position_check": "position-check",
    "liquidation_map": "liquidation-map",
    "funding_carry": "funding-carry",
    "rule_test": "rule-test",
    "rule_scan": "rule-scan",
    "market_brief": "market-brief",
}


def _sym(inp: dict) -> str:
    return (inp.get("symbol") or "BTC").strip().upper().removesuffix("USDT")


def request_for(inp: dict) -> tuple[str, dict]:
    mode = inp.get("mode") or "position_check"
    if mode == "position_check":
        if not inp.get("entry"):
            raise ValueError("position_check needs `entry` (the entry price)")
        return "/position/check", {"symbol": _sym(inp), "side": inp.get("side") or "long", "entry": float(inp["entry"]),
                                   "leverage": int(inp.get("leverage") or 10),
                                   "notional_usd": int(inp.get("notionalUsd") or 10_000)}
    if mode == "liquidation_map":
        return f"/liqmap/{_sym(inp)}USDT", {"exchange": "all", "range": inp.get("range") or "1d"}
    if mode == "funding_carry":
        return "/funding/arbitrage", {"limit": 60}
    if mode == "rule_test":
        return "/rules/test", {"rules": inp.get("rules") or "", "symbol": _sym(inp)}
    if mode == "rule_scan":
        return "/rules/scan", {"rules": inp.get("rules") or "", "coins": int(inp.get("coins") or 50)}
    if mode == "market_brief":
        return "/answer", {"q": "liquidations funding open interest levels whales sentiment", "coin": _sym(inp)}
    raise ValueError(f"unknown mode {mode!r}")


def summary(mode: str, d: dict) -> str:
    """One line a person reads in the dataset table; the full answer is in `answer`."""
    try:
        if mode == "position_check":
            if d.get("error"):
                return f"{d['error']}: {d.get('detail', '')}"
            ok = [v for v in d["venues"] if v.get("status") == "ok"]
            near = min(ok, key=lambda v: abs(v["distance_pct"]))
            far = max(ok, key=lambda v: abs(v["distance_pct"]))
            return (f"mark {d['mark']:g}; liquidation nearest on {near['venue']} at {near['liquidation_price']:g} "
                    f"({near['distance_pct']:+.2f}%), farthest on {far['venue']} at {far['liquidation_price']:g} "
                    f"({far['distance_pct']:+.2f}%); {len(ok)} venues")
        if mode == "liquidation_map":
            e = d.get("explains_oi_pct") or {}
            return (f"price {d['current_price']:g}; modeled longs below ${d.get('long_usd_below_price', 0) / 1e6:,.0f}M, "
                    f"shorts above ${d.get('short_usd_above_price', 0) / 1e6:,.0f}M "
                    f"({e.get('long')}% / {e.get('short')}% of open interest)")
        if mode == "funding_carry":
            r = d["rows"][0]
            return (f"{len(d['rows'])} pairs, chosen on the prior week and measured after; top: {r['symbol']} short "
                    f"{r['short_venue']} / long {r['long_venue']} {r['realized_7d_apr']:.1f}% APR realized")
        if mode == "rule_test":
            o = d["outcomes"]["24h"]
            return (f"{d['rule']}: {d['episodes_n']} episodes; next 24h up {o['up_share_pct']}% (base "
                    f"{d['base_rate']['24h']['up_share_pct']}%), median {o['median_pct']}%; true now: {d['true_now']}")
        if mode == "rule_scan":
            o = d["pooled"]["24h"]
            return (f"{d['rule']}: {o['n']} episodes on {d['coins_with_episodes']} coins over "
                    f"{d['distinct_days_with_an_episode']} days; next 24h up {o['up_share_pct']}% (base "
                    f"{d['pooled_base_rate']['24h']['up_share_pct']}%); true now on {', '.join(d['true_now']) or 'none'}")
        if mode == "market_brief":
            return " ".join((d.get("answer") or d.get("lines") or [""])[:2]) if isinstance(d.get("answer") or d.get("lines"), list) \
                else str(d.get("answer", ""))[:300]
    except Exception:   # noqa: BLE001  a summary must never cost the answer
        pass
    return ""


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}
        mode = inp.get("mode") or "position_check"
        try:
            path, params = request_for(inp)
        except ValueError as e:
            await Actor.fail(status_message=str(e))
            return
        headers = {"User-Agent": "liquidvision-apify/0.1"}
        key = os.environ.get("LV_API_KEY")
        if key:
            headers["X-API-Key"] = key
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.get(API + path, params=params, headers=headers)
        if r.status_code != 200:
            detail = r.text[:300]
            # nothing is charged for a refused or failed request
            await Actor.fail(status_message=f"LiquidVision answered HTTP {r.status_code}: {detail}")
            return
        data = r.json()
        await Actor.push_data({
            "mode": mode, "symbol": _sym(inp) if mode not in ("funding_carry", "rule_scan") else None,
            "summary": summary(mode, data), "answer": data,
            "source": "https://liquidvision.app" + "/api/v1" + path,
            "note": "Data and statistics, not financial advice. Frequencies come from LiquidVision's own archive.",
        })
        await Actor.charge(event_name=EVENTS[mode])
        Actor.log.info("done: %s", summary(mode, data))
