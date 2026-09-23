"""GMX v2 (Arbitrum) collector — standalone version of the one LiquidVision runs.

    pip install httpx
    python collectors/gmx_v2.py          # prints OI / funding / liquidation events as JSON lines

Open interest per index (collateral pools summed), hourly funding in the CEX
sign convention (positive = longs pay) and liquidations as indexed events, from
GMX's open Subsquid indexer and price API. No key. MIT.
"""
import asyncio
import json
import logging
import time

import httpx



class _Bus:
    def publish(self, topic, ev):
        print(json.dumps({"topic": topic, **ev}), flush=True)


bus = _Bus()
FUNDING, LIQUIDATION, OPEN_INTEREST = "funding", "liquidation", "open_interest"

log = logging.getLogger(__name__)

GQL = "https://gmx.squids.live/gmx-synthetics-arbitrum/graphql"
API = "https://arbitrum-api.gmxinfra.io"
E30 = 10 ** 30
POLL_SECONDS = 60
LIQ_ORDER_TYPE = 7
SYMBOL_FIX = {"WBTC.b": "BTC", "WBTC": "BTC", "WETH": "ETH", "BTC.b": "BTC"}


class GMXPoller:
    name = "gmx"

    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._tokens: dict[str, dict] = {}     # index token address -> {sym, dec}
        self._tokens_ts = 0.0
        self._liq_since = int(time.time()) - POLL_SECONDS
        self._seen_liq: set[str] = set()

    def stop(self) -> None:
        self._stop.set()

    async def _gql(self, client: httpx.AsyncClient, query: str) -> dict:
        r = await client.post(GQL, json={"query": query})
        r.raise_for_status()
        body = r.json()
        if "errors" in body:
            raise RuntimeError(str(body["errors"])[:200])
        return body["data"]

    async def _load_tokens(self, client: httpx.AsyncClient) -> None:
        if self._tokens and time.time() - self._tokens_ts < 86400:
            return
        r = await client.get(f"{API}/tokens")
        r.raise_for_status()
        out = {}
        for t in r.json()["tokens"]:
            sym = SYMBOL_FIX.get(t["symbol"], t["symbol"])
            out[t["address"]] = {"sym": sym.upper(), "dec": int(t.get("decimals", 18))}
        self._tokens = out
        self._tokens_ts = time.time()

    async def _prices(self, client: httpx.AsyncClient) -> dict[str, float]:
        """index token address -> mark price (mid of min/max)."""
        r = await client.get(f"{API}/prices/tickers")
        r.raise_for_status()
        out = {}
        for t in r.json():
            tok = self._tokens.get(t["tokenAddress"])
            if not tok:
                continue
            scale = 10 ** (30 - tok["dec"])
            out[t["tokenAddress"]] = (int(t["minPrice"]) + int(t["maxPrice"])) / 2 / scale
        return out

    async def _markets(self, client: httpx.AsyncClient, prices: dict) -> None:
        data = await self._gql(client, """
            { marketInfos(limit: 500, where: {isDisabled_eq: false}) {
                indexTokenAddress longOpenInterestUsd shortOpenInterestUsd
                fundingFactorPerSecond longsPayShorts } }""")
        now = int(time.time() * 1000)
        agg: dict[str, dict] = {}
        for m in data["marketInfos"]:
            tok = self._tokens.get(m["indexTokenAddress"])
            if not tok or tok["sym"] in ("USDC", "USDT", "DAI"):
                continue  # swap-only pools have no index
            oi_l = int(m["longOpenInterestUsd"]) / E30
            oi_s = int(m["shortOpenInterestUsd"]) / E30
            rate = int(m["fundingFactorPerSecond"]) / E30 * 3600
            if not m["longsPayShorts"]:
                rate = -rate
            a = agg.setdefault(tok["sym"], {"oi": 0.0, "w": 0.0, "addr": m["indexTokenAddress"]})
            a["oi"] += oi_l + oi_s
            a["w"] += rate * (oi_l + oi_s)  # OI-weighted across collateral pools
        for sym, a in agg.items():
            price = prices.get(a["addr"])
            if not price or a["oi"] <= 0:
                continue
            symbol = f"{sym}USDT"
            bus.publish(OPEN_INTEREST, {
                "exchange": self.name, "symbol": symbol,
                "oi": a["oi"] / price, "oi_usd": a["oi"], "ts": now,
            })
            bus.publish(FUNDING, {
                "exchange": self.name, "symbol": symbol,
                "mark_price": price, "funding_rate": a["w"] / a["oi"],
                "funding_hours": 1.0, "next_funding_ts": 0, "ts": now,
            })

    async def _liquidations(self, client: httpx.AsyncClient) -> int:
        data = await self._gql(client, f"""
            {{ tradeActions(limit: 500, orderBy: timestamp_ASC,
                where: {{orderType_eq: {LIQ_ORDER_TYPE}, eventName_eq: "OrderExecuted",
                         timestamp_gte: {self._liq_since - POLL_SECONDS}}}) {{
                id timestamp marketAddress isLong sizeDeltaUsd executionPrice }} }}""")
        rows = data["tradeActions"]
        if not rows:
            return 0
        # market address -> index token: one lookup for the batch
        mkts = await self._gql(client, """
            { marketInfos(limit: 500) { id indexTokenAddress } }""")
        index_of = {m["id"]: m["indexTokenAddress"] for m in mkts["marketInfos"]}
        n = 0
        for r in rows:
            if r["id"] in self._seen_liq:
                continue
            tok = self._tokens.get(index_of.get(r["marketAddress"], ""))
            if not tok:
                continue
            price = int(r["executionPrice"]) / 10 ** (30 - tok["dec"])
            usd = int(r["sizeDeltaUsd"]) / E30
            if price <= 0 or usd <= 0:
                continue
            self._seen_liq.add(r["id"])
            bus.publish(LIQUIDATION, {
                "exchange": self.name, "symbol": f"{tok['sym']}USDT",
                "side": "long" if r["isLong"] else "short",
                "price": price, "qty": usd / price,
                "ts": int(r["timestamp"]) * 1000,
            })
            n += 1
        self._liq_since = max(int(r["timestamp"]) for r in rows)
        if len(self._seen_liq) > 20_000:
            self._seen_liq = set(list(self._seen_liq)[-5000:])
        return n

    async def run(self) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            while not self._stop.is_set():
                try:
                    await self._load_tokens(client)
                    prices = await self._prices(client)
                    await self._markets(client, prices)
                    n = await self._liquidations(client)
                    if n:
                        log.info("[%s] %d liquidation(s)", self.name, n)
                except Exception as e:
                    log.warning("[%s] cycle failed: %s", self.name, e)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=POLL_SECONDS)
                except asyncio.TimeoutError:
                    pass


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(GMXPoller().run())
