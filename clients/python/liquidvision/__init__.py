"""LiquidVision API client. Standard library only.

    from liquidvision import LiquidVision
    lv = LiquidVision()                      # no key: live data, shared anonymous limits
    lv = LiquidVision(api_key="lv_...")      # free key: 300 req/min; Pro/Bot: history, alerts

    lv.liqmap("BTCUSDT")                     # modeled liquidation map
    lv.hl_whales(coin="BTC", max_dist_pct=5) # measured Hyperliquid positions near liquidation
    rows = lv.export("liquidations", symbol="BTCUSDT", start="2026-09-01", end="2026-09-08")

Every dict answer carries age_s (seconds since the data was read from the
exchange); rows of oi(), funding() and long_short() carry age_s each and
stale=True when a venue feed is behind. Docs: https://liquidvision.app/llms.txt
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import urllib.error
import urllib.parse
import urllib.request

__version__ = "0.1.0"
__all__ = ["LiquidVision", "LiquidVisionError", "verify_signature"]


class LiquidVisionError(Exception):
    def __init__(self, status: int, detail):
        super().__init__(f"HTTP {status}: {detail}")
        self.status, self.detail = status, detail


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """Check a webhook delivery: header X-LiquidVision-Signature against the raw request body."""
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


class LiquidVision:
    def __init__(self, api_key: str | None = None, base_url: str = "https://liquidvision.app/api/v1",
                 timeout: float = 30):
        self.api_key, self.base_url, self.timeout = api_key, base_url.rstrip("/"), timeout

    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> bytes:
        url = self.base_url + path
        if params:
            q = {k: v for k, v in params.items() if v is not None}
            if q:
                url += "?" + urllib.parse.urlencode(q)
        headers = {"User-Agent": f"liquidvision-python/{__version__}", "Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        data = None
        if body is not None:
            data = json.dumps({k: v for k, v in body.items() if v is not None}).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                detail = json.loads(raw)
                detail = detail.get("detail", detail.get("error", detail)) if isinstance(detail, dict) else detail
            except ValueError:
                detail = raw[:300].decode(errors="replace")
            raise LiquidVisionError(e.code, detail) from None

    def _get(self, path: str, **params):
        return json.loads(self._request("GET", path, params))

    # ---- live market data -------------------------------------------------
    def oi(self) -> list[dict]:
        """Open interest per venue and contract, as each exchange publishes it."""
        return self._get("/oi")

    def funding(self) -> list[dict]:
        """Funding rate and mark price per venue and contract."""
        return self._get("/funding")

    def long_short(self) -> list[dict]:
        return self._get("/longshort")

    def oi_board(self, symbol: str) -> dict:
        """One contract across every venue: OI, funding, share."""
        return self._get(f"/oiboard/{symbol}")

    def brief(self, symbol: str) -> dict:
        """One deterministic risk brief for a coin."""
        return self._get(f"/brief/{symbol}")

    def regime(self, minutes: int = 60) -> dict:
        """Positioning regime per coin: price change x OI change."""
        return self._get("/oi/regime", minutes=minutes)

    def funding_dispersion(self) -> dict:
        """Cross-venue funding spread per coin."""
        return self._get("/funding/dispersion")

    # ---- liquidations -----------------------------------------------------
    def liquidations(self, minutes: int = 60) -> list[dict]:
        """Raw liquidation events. Binance and Bitget are exchange-throttled: a floor."""
        return self._get("/liquidations", minutes=minutes)

    def liquidations_summary(self, minutes: int = 60) -> dict:
        return self._get("/liquidations/summary", minutes=minutes)

    def cascades(self, hours: int = 24, limit: int = 50) -> dict:
        """Liquidation cascades detected as events."""
        return self._get("/liquidations/cascades", hours=hours, limit=limit)

    def liqmap(self, symbol: str, exchange: str = "all", range: str = "1d") -> dict:
        """MODELED liquidation clusters per price bin. How it scores: accuracy()."""
        return self._get(f"/liqmap/{symbol}", exchange=exchange, range=range)

    def liqheat(self, symbol: str, exchange: str = "all", range: str = "1d") -> dict:
        """MODELED liquidation heatmap: grid[time][price bin] with the price path."""
        return self._get(f"/liqheat/{symbol}", exchange=exchange, range=range)

    # ---- Hyperliquid, measured --------------------------------------------
    def hl_liqmap(self, symbol: str, range: str = "1d") -> dict:
        """MEASURED liquidation map from the largest Hyperliquid accounts."""
        return self._get(f"/liqmap/hl/{symbol}", range=range)

    def hl_whales(self, coin: str | None = None, side: str | None = None, min_usd: float = 100_000,
                  max_dist_pct: float | None = None, sort: str = "distance", limit: int = 100) -> dict:
        """Whale positions with exchange-reported liquidation prices, closest to liquidation first."""
        return self._get("/hl/whales", coin=coin, side=side, min_usd=min_usd,
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

    # ---- history (free: last 24 h; Pro: 31-day window; Bot: everything) ---
    def datasets(self) -> dict:
        return self._get("/export")

    def export_csv(self, dataset: str, start: str | None = None, end: str | None = None,
                   symbol: str | None = None, exchange: str | None = None, limit: int | None = None) -> str:
        """Raw CSV text. dataset: liquidations | funding_settlements | funding_hourly |
        open_interest_hourly | hl_positions. start/end: ISO dates, UTC."""
        return self._request("GET", f"/export/{dataset}", {"start": start, "end": end, "symbol": symbol,
                                                            "exchange": exchange, "limit": limit}).decode()

    def export(self, dataset: str, **kw) -> list[dict]:
        """The same export parsed into a list of dicts (all values are strings, as in the CSV)."""
        return list(csv.DictReader(io.StringIO(self.export_csv(dataset, **kw))))

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
