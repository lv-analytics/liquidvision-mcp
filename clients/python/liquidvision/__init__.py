"""LiquidVision.app API client. Standard library only; x402 pay-per-call needs `eth-account`.

    from liquidvision import LiquidVision
    lv = LiquidVision()                      # no key: the conclusions only (brief, regime, cascades, maps, carry), 60/min per IP
    lv = LiquidVision(api_key="lv_...")      # free key: 120/min on the conclusions; Pro/Bot: raw rows, history, alerts

    lv.brief("BTCUSDT")                      # one coin, one JSON: the place to start
    lv.regime(240)                           # who is driving the move: new longs / short covering / ...
    lv.cascades(hours=24)                    # liquidation cascades as events
    lv.hl_liqmap("BTCUSDT")                  # MEASURED map from real Hyperliquid positions
    lv.lighter_liqmap("BTCUSDT")             # same for Lighter
    lv.tokenized_stocks()                    # stocks / indices / commodities / FX as perps on DEXs
    rows = lv.export("liquidations", symbol="BTCUSDT", start="2026-09-01", end="2026-09-08")

Pay-per-call without an account (x402, USDC on Arbitrum One):

    from liquidvision import LiquidVision, X402Payer
    lv = LiquidVision(payer=X402Payer(private_key="0x..."))     # pip install liquidvision[x402]
    lv.package("liquidations", "2026-08", "liq_2026-08.parquet")  # $1.00, paid from the wallet
    lv.export("funding_hourly", start="2026-09-01", end="2026-09-30", pay=True)   # $0.10

Every dict answer carries age_s (seconds since the data was read from the
exchange); rows of oi(), funding() and long_short() carry age_s each and
stale=True when a venue feed is behind. Docs: https://liquidvision.app/llms.txt
MCP for agents: https://liquidvision.app/mcp/lite (13 tools) and /mcp (42).
"""
from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

__version__ = "0.2.0"
__all__ = ["LiquidVision", "LiquidVisionError", "PaymentRequired", "X402Payer", "verify_signature"]

USDC_ARBITRUM = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
ARBITRUM_CHAIN_ID = 42161


class LiquidVisionError(Exception):
    def __init__(self, status: int, detail):
        super().__init__(f"HTTP {status}: {detail}")
        self.status, self.detail = status, detail


class PaymentRequired(LiquidVisionError):
    """402: the resource is paid. `requirements` is the x402 PaymentRequirements
    object (v1: network 'arbitrum', maxAmountRequired in USDC atomic units)."""

    def __init__(self, detail, requirements: dict | None):
        super().__init__(402, detail)
        self.requirements = requirements


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """Check a webhook delivery: header X-LiquidVision-Signature against the raw request body."""
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


class X402Payer:
    """Signs USDC transfer authorizations (EIP-3009) for x402 pay-per-call.

    Needs `eth-account` (pip install liquidvision[x402]). The private key never
    leaves the process: the server receives only the signed authorization and
    a public facilitator submits the transfer on-chain. Each authorization is
    for exactly the amount the server asks, to the server's address, valid
    for the server's timeout window, with a random nonce, so it cannot be
    replayed or re-priced. max_usd_per_call is your own ceiling.
    """

    def __init__(self, private_key: str, max_usd_per_call: float = 5.0):
        try:
            from eth_account import Account
        except ImportError as e:   # pragma: no cover
            raise ImportError("x402 payments need eth-account: pip install liquidvision[x402]") from e
        self._acct = Account.from_key(private_key)
        self.address = self._acct.address
        self.max_usd_per_call = max_usd_per_call

    def sign(self, requirements: dict) -> str:
        """Return the base64 X-PAYMENT header for one v1 PaymentRequirements object."""
        from eth_account.messages import encode_typed_data

        value = int(requirements["maxAmountRequired"])
        if value > self.max_usd_per_call * 1_000_000:
            raise PaymentRequired(f"server asks {value / 1e6:.2f} USDC, above max_usd_per_call", requirements)
        if (requirements.get("asset", USDC_ARBITRUM).lower() != USDC_ARBITRUM.lower()
                or requirements.get("network") not in ("arbitrum", "eip155:42161")):
            raise PaymentRequired("this payer only signs USDC on Arbitrum One", requirements)
        now = int(time.time())
        nonce = os.urandom(32)
        auth = {"from": self.address, "to": requirements["payTo"], "value": value,
                "validAfter": now - 60, "validBefore": now + int(requirements.get("maxTimeoutSeconds") or 60),
                "nonce": nonce}
        extra = requirements.get("extra") or {}
        typed = {
            "types": {
                "EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                                 {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}],
                "TransferWithAuthorization": [
                    {"name": "from", "type": "address"}, {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
                    {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"}],
            },
            "primaryType": "TransferWithAuthorization",
            "domain": {"name": extra.get("name", "USD Coin"), "version": extra.get("version", "2"),
                       "chainId": ARBITRUM_CHAIN_ID, "verifyingContract": USDC_ARBITRUM},
            "message": auth,
        }
        sig = self._acct.sign_message(encode_typed_data(full_message=typed)).signature.hex()
        if not sig.startswith("0x"):
            sig = "0x" + sig
        payload = {"x402Version": 1, "scheme": "exact", "network": "arbitrum",
                   "payload": {"signature": sig, "authorization": {
                       "from": auth["from"], "to": auth["to"], "value": str(auth["value"]),
                       "validAfter": str(auth["validAfter"]), "validBefore": str(auth["validBefore"]),
                       "nonce": "0x" + nonce.hex()}}}
        return base64.b64encode(json.dumps(payload).encode()).decode()


class LiquidVision:
    def __init__(self, api_key: str | None = None, base_url: str = "https://liquidvision.app/api/v1",
                 timeout: float = 30, payer: X402Payer | None = None):
        self.api_key, self.base_url, self.timeout, self.payer = api_key, base_url.rstrip("/"), timeout, payer
        self.last_payment: dict | None = None   # settlement of the last paid call (tx hash, payer)

    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None,
                 pay: bool = False, _payment: str | None = None) -> bytes:
        url = self.base_url + path
        if params:
            q = {k: v for k, v in params.items() if v is not None}
            if q:
                url += "?" + urllib.parse.urlencode(q)
        headers = {"User-Agent": f"liquidvision-python/{__version__}", "Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if _payment:
            headers["X-PAYMENT"] = _payment
        data = None
        if body is not None:
            data = json.dumps({k: v for k, v in body.items() if v is not None}).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                settled = r.headers.get("X-PAYMENT-RESPONSE")
                if settled:
                    try:
                        self.last_payment = json.loads(base64.b64decode(settled + "=" * (-len(settled) % 4)))
                    except Exception:
                        self.last_payment = {"raw": settled}
                return r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                detail = json.loads(raw)
            except ValueError:
                detail = raw[:300].decode(errors="replace")
            if e.code == 402:
                reqs = detail["accepts"][0] if isinstance(detail, dict) and detail.get("accepts") else None
                err = detail.get("error", detail) if isinstance(detail, dict) else detail
                # one automatic payment attempt when a payer is configured and the caller asked to pay
                if reqs and pay and self.payer and _payment is None:
                    return self._request(method, path, params, body, pay=False, _payment=self.payer.sign(reqs))
                raise PaymentRequired(err, reqs) from None
            if isinstance(detail, dict):
                detail = detail.get("detail", detail.get("error", detail))
            raise LiquidVisionError(e.code, detail) from None

    def _get(self, path: str, **params):
        return json.loads(self._request("GET", path, params))

    # ---- start here -------------------------------------------------------
    def markets(self) -> dict:
        """What exists: every venue and the contracts it has live open interest for (built from /oi)."""
        out: dict[str, list[str]] = {}
        for r in self.oi():
            out.setdefault(r["exchange"], []).append(r["symbol"])
        return {k: sorted(v) for k, v in sorted(out.items())}

    def brief(self, symbol: str) -> dict:
        """One deterministic risk brief for a coin: liquidations by window, funding extremes,
        OI by venue, flows, modeled risk zones, top-trader positioning."""
        return self._get(f"/brief/{symbol}")

    def regime(self, minutes: int = 240) -> dict:
        """Positioning regime per coin: price change x OI change (new longs, short covering, ...)."""
        return self._get("/oi/regime", minutes=minutes)

    def cascades(self, hours: int = 24, limit: int = 50) -> dict:
        """Liquidation cascades detected as events, with what price did in the hour after."""
        return self._get("/liquidations/cascades", hours=hours, limit=limit)

    def funding_dispersion(self) -> dict:
        """Where the same coin pays very different funding across venues (each leg on its own cycle)."""
        return self._get("/funding/dispersion")

    def funding_arbitrage(self, min_venues: int = 3, limit: int = 40) -> dict:
        """What the carry pair actually earned over 7 and 30 days, from the hourly archive."""
        return self._get("/funding/arbitrage", min_venues=min_venues, limit=limit)

    def microstructure(self, minutes: int = 240) -> dict:
        """Spread, immediately executable depth and cross-venue price gap (Binance, Bybit, OKX, Aster)."""
        return self._get("/microstructure", minutes=minutes)

    def tokenized_stocks(self) -> dict:
        """Stocks, indices, ETFs, commodities, FX and pre-IPO names as perps on Lighter,
        Hyperliquid builder markets, Ostium and gTrade: one row per underlying."""
        return self._get("/stocks/tokenized")

    def onchain(self) -> dict:
        """On-chain perp venues grouped by chain next to the CEX total."""
        return self._get("/onchain")

    # ---- live market data -------------------------------------------------
    def oi(self) -> list[dict]:
        """Open interest per venue and contract, as each exchange publishes it (one side)."""
        return self._get("/oi")

    def funding(self) -> list[dict]:
        """Funding rate and mark price per venue and contract, with the contract's own interval."""
        return self._get("/funding")

    def long_short(self) -> list[dict]:
        return self._get("/longshort")

    def oi_board(self, symbol: str) -> dict:
        """One contract across every venue: OI, share, 1h/4h/24h change in positions."""
        return self._get(f"/oiboard/{symbol}")

    # ---- liquidations -----------------------------------------------------
    def liquidations(self, minutes: int = 60) -> list[dict]:
        """Raw liquidation events. Binance and Bitget are exchange-throttled: a floor."""
        return self._get("/liquidations", minutes=minutes)

    def liquidations_summary(self, minutes: int = 60) -> dict:
        return self._get("/liquidations/summary", minutes=minutes)

    def liqmap(self, symbol: str, exchange: str = "all", range: str = "1d") -> dict:
        """MODELED liquidation clusters per price bin (CEXs). How it scores: accuracy()."""
        return self._get(f"/liqmap/{symbol}", exchange=exchange, range=range)

    def liqheat(self, symbol: str, exchange: str = "all", range: str = "1d") -> dict:
        """MODELED liquidation heatmap: grid[time][price bin] with the price path."""
        return self._get(f"/liqheat/{symbol}", exchange=exchange, range=range)

    # ---- measured positions: Hyperliquid and Lighter ----------------------
    def hl_liqmap(self, symbol: str, range: str = "1d") -> dict:
        """MEASURED liquidation map from the ~10,000 largest Hyperliquid accounts."""
        return self._get(f"/liqmap/hl/{symbol}", range=range)

    def lighter_liqmap(self, symbol: str, range: str = "1d") -> dict:
        """MEASURED liquidation map from every Lighter account."""
        return self._get(f"/liqmap/lighter/{symbol}", range=range)

    def hl_whales(self, coin: str | None = None, side: str | None = None, min_usd: float = 100_000,
                  max_dist_pct: float | None = None, sort: str = "distance", limit: int = 100) -> dict:
        """Hyperliquid positions with exchange-reported liquidation prices, closest to liquidation first."""
        return self._get("/hl/whales", coin=coin, side=side, min_usd=min_usd,
                         max_dist_pct=max_dist_pct, sort=sort, limit=limit)

    def lighter_whales(self, coin: str | None = None, side: str | None = None, min_usd: float = 100_000,
                       max_dist_pct: float | None = None, sort: str = "distance", limit: int = 100) -> dict:
        """Lighter positions with exchange-reported liquidation prices."""
        return self._get("/lighter/whales", coin=coin, side=side, min_usd=min_usd,
                         max_dist_pct=max_dist_pct, sort=sort, limit=limit)

    def hl_account(self, address: str) -> dict:
        """One Hyperliquid account: live positions and archived snapshots."""
        return self._get(f"/hl/account/{address}")

    # ---- service ----------------------------------------------------------
    def accuracy(self) -> dict:
        """The public audit: our OI and funding vs the exchanges, and the map's score."""
        return self._get("/accuracy")

    def status(self) -> dict:
        return self._get("/status")

    def uptime(self) -> dict:
        return self._get("/status/uptime")

    def x402_info(self) -> dict:
        """Pay-per-call terms: prices, network, receiving address, facilitator."""
        return self._get("/x402")

    # ---- history: CSV windows ---------------------------------------------
    def datasets(self) -> dict:
        return self._get("/export")

    def export_csv(self, dataset: str, start: str | None = None, end: str | None = None,
                   symbol: str | None = None, exchange: str | None = None, limit: int | None = None,
                   pay: bool = False) -> str:
        """Raw CSV text. Free: last 24 h; Pro key: any 31-day window; Bot key: everything.
        pay=True with a payer: buy this one window at Pro terms for $0.10 (x402)."""
        params = {"start": start, "end": end, "symbol": symbol, "exchange": exchange, "limit": limit}
        if pay:
            params["pay"] = "x402"
        return self._request("GET", f"/export/{dataset}", params, pay=pay).decode()

    def export(self, dataset: str, pay: bool = False, **kw) -> list[dict]:
        """The same export parsed into a list of dicts (all values are strings, as in the CSV)."""
        return list(csv.DictReader(io.StringIO(self.export_csv(dataset, pay=pay, **kw))))

    # ---- history: monthly Parquet packages --------------------------------
    def packages(self) -> dict:
        """Catalogue of monthly Parquet files (rows, bytes, sha256, which months your tier may take)."""
        return self._get("/export/packages")

    def package(self, dataset: str, month: str, path: str | None = None, pay: bool = True) -> bytes | str:
        """One monthly Parquet file (e.g. "liquidations", "2026-08"). Pro: this and last month,
        Bot: all; otherwise one x402 payment of $1.00 when a payer is configured.
        Returns the bytes, or writes them to `path` and returns the path."""
        body = self._request("GET", f"/export/package/{dataset}/{month}", pay=pay)
        if path:
            with open(path, "wb") as f:
                f.write(body)
            return path
        return body

    # ---- webhook alerts (Pro: 3, Bot: 20) ---------------------------------
    def create_alert(self, type: str, url: str, symbol: str | None = None, min_usd: float | None = None,
                     x_normal: float | None = None, max_dist_pct: float | None = None) -> dict:
        """type: cascade | hl_near_liq | cluster_sweep. Returns the signing secret once."""
        return json.loads(self._request("POST", "/webhooks", body={
            "type": type, "url": url, "symbol": symbol, "min_usd": min_usd,
            "x_normal": x_normal, "max_dist_pct": max_dist_pct}))

    def list_alerts(self) -> list[dict]:
        return self._get("/webhooks")["webhooks"]

    def delete_alert(self, id: int) -> bool:
        return json.loads(self._request("DELETE", f"/webhooks/{id}"))["deleted"]

    def test_alert(self, id: int) -> dict:
        """Send a signed sample payload to the subscription's URL now."""
        return json.loads(self._request("POST", f"/webhooks/{id}/test"))
