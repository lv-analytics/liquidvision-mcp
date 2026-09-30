# liquidvision (Python)

Client for the [LiquidVision](https://liquidvision.app) crypto derivatives data API.
Standard library only, Python 3.9+.

```bash
pip install liquidvision
```

```python
from liquidvision import LiquidVision

lv = LiquidVision()                       # no key: live data, shared anonymous limits
lv = LiquidVision(api_key="lv_...")       # free key: 300 req/min

# open interest and funding exactly as each exchange publishes them, 13 venues
for row in lv.oi():
    if row["symbol"] == "BTCUSDT" and not row.get("stale"):
        print(row["exchange"], row["oi_usd"], row["age_s"])

# measured: Hyperliquid whale positions within 5% of liquidation
for p in lv.hl_whales(coin="BTC", max_dist_pct=5)["positions"]:
    print(p["side"], p["value_usd"], p["liq_px"], p["distance_pct"])

# modeled liquidation map, and how that model scores against realized liquidations
m = lv.liqmap("BTCUSDT")
print(lv.accuracy()["liqmap_validation"])

# history for a backtest (free: last 24 h, Pro: any 31-day window, Bot: everything)
rows = lv.export("liquidations", symbol="BTCUSDT", start="2026-09-01", end="2026-09-08")
```

## Webhook alerts (Pro and Bot keys)

```python
sub = lv.create_alert("cascade", "https://your.host/hook", symbol="BTCUSDT", min_usd=2_000_000)
secret = sub["secret"]    # shown once

# in your handler
from liquidvision import verify_signature
ok = verify_signature(secret, raw_body_bytes, request.headers["X-LiquidVision-Signature"])
```

Alert types: `cascade` (a liquidation cascade just ended), `hl_near_liq` (a Hyperliquid
whale near its liquidation price), `cluster_sweep` (price reached a large modeled
liquidation cluster; payload carries modeled and realized USD).

## What to know about the data

- Every dict answer carries `age_s`; rows of `oi()`, `funding()`, `long_short()` carry
  `age_s` each and `stale: True` when a venue feed is behind.
- Liquidation events from Binance and Bitget are throttled by the exchanges to one order
  per contract per second, so totals are a floor.
- `liqmap` and `liqheat` are models. `hl_liqmap`, `hl_whales`, `hl_account` are measured.
- Errors raise `LiquidVisionError` with `.status` and `.detail` (401 no key, 402 plan needed, 429 rate limit).

Full endpoint list: https://liquidvision.app/llms.txt · plans: https://liquidvision.app/pricing
