# liquidvision (Python)

Client for [LiquidVision.app](https://liquidvision.app): exchange-exact crypto derivatives
data for bots and AI agents. Standard library only, Python 3.9+. Pay-per-call needs one
optional extra.

```bash
pip install liquidvision            # live data, history with a key
pip install "liquidvision[x402]"    # + pay per call in USDC without an account (eth-account)
```

## Start here

```python
from liquidvision import LiquidVision

lv = LiquidVision()                       # no key: the conclusions (brief, regime, cascades, map summaries, carry...), 60/min per IP
# lv = LiquidVision(api_key="lv_...")     # free key: 120/min plus 100 units a day of history and positions; Pro/Bot: 10,000 / 100,000 a day, exports, alerts

lv.brief("BTCUSDT")          # one coin, one JSON: liquidations by window, funding extremes, OI by venue, risk zones
lv.liqlevels("BTCUSDT")      # liquidation-map summary: USD on each side of the price, the largest level each side
lv.regime(240)               # who is driving the move: new_longs / short_covering / new_shorts / long_flush per coin
lv.cascades(hours=24)        # liquidation cascades as events, with what price did in the hour after
lv.funding_dispersion()      # where the same coin pays very different funding (each leg on its own cycle)
lv.funding_arbitrage()       # what the carry pair actually earned over 7 and 30 days
lv.microstructure()          # spread, executable depth, cross-venue gap on Binance, Bybit, OKX, Aster
lv.tokenized_stocks()        # stocks / indices / commodities / FX as perps on DEXs, one row per underlying
```

Measured, not modeled:

```python
lv.liqlevels("BTCUSDT", venue="hyperliquid")   # free summary from real Hyperliquid positions (venue="lighter" too)
lv.hl_liqmap("BTCUSDT")                        # every price level: metered, $0.005 a call (key or payer)
lv.lighter_liqmap("BTCUSDT")                   # the same for Lighter, metered
lv.hl_whales(coin="BTC", max_dist_pct=5)       # positions within 5% of liquidation, metered
```

Modeled, and scored: `lv.liqmap("BTCUSDT")` is the CEX liquidation map (a model, metered since
2026-11-13); `lv.accuracy()["liqmap_validation"]` is how it did against realized liquidations.

One priced answer before a trade: `lv.pretrade("BTC", "long", 20, notional_usd=50_000)` returns the
liquidation price on 12 venues, the levels before it, whale positioning, funding cost and `flags`
for what goes against the trade ($0.05; key or payer).

Every dict answer carries `age_s` (seconds since the data was read from the exchange); rows
of `oi()`, `funding()`, `long_short()` carry `age_s` each and `stale=True` when a venue feed is
behind. Check it before acting on a number.

## History

```python
# free: last 24 h; Pro key: any 31-day window; Bot key: everything
rows = lv.export("liquidations", symbol="BTCUSDT", start="2026-09-01", end="2026-09-08")
lv.packages()                                   # monthly Parquet files: rows, bytes, sha256
lv.package("liquidations", "2026-08", "liq_2026-08.parquet")   # Pro: this and last month; Bot: all
```

## Pay per call without an account (x402)

An agent with a wallet can buy one file for one signed USDC payment on Base or Arbitrum (same price; the client picks a network it can sign). The key
never leaves your process: the server receives a signed `transferWithAuthorization` for exactly
the asked amount, to the server's address, valid for a short window; a public facilitator
submits it on-chain.

```python
from liquidvision import LiquidVision, X402Payer

lv = LiquidVision(payer=X402Payer(private_key="0x...", max_usd_per_call=2))
lv.package("liquidations", "2026-08", "liq_2026-08.parquet")             # $1.00
rows = lv.export("funding_hourly", start="2026-09-01", end="2026-09-30", pay=True)   # $0.10, Pro terms
print(lv.last_payment)        # {"success": true, "transaction": "0x...", "network": "arbitrum", "payer": "0x..."}
```

Without a payer the same calls raise `PaymentRequired` with `.requirements` (price, network,
address) so you can decide. Terms: `lv.x402_info()`.

## Webhook alerts (Pro and Bot keys)

```python
sub = lv.create_alert("cascade", "https://your.host/hook", symbol="BTCUSDT", min_usd=2_000_000)
secret = sub["secret"]    # shown once

# in your handler
from liquidvision import verify_signature
ok = verify_signature(secret, raw_body, request.headers["X-LiquidVision-Signature"])
```

Alert types: `cascade` (a liquidation cascade just ended), `hl_near_liq` (a Hyperliquid whale
near its liquidation price), `cluster_sweep` (price reached a large modeled cluster).

## What to know about the data

- Open interest is counted on one side on every venue; an aggregator showing Bybit, Gate or
  HTX at twice the figure is showing both sides.
- Liquidation events from Binance and Bitget are throttled by the exchanges to one order per
  contract per second, so totals are a floor.
- Funding is annualized with each contract's own settlement cycle (1h / 4h / 8h).
- Errors raise `LiquidVisionError` with `.status` and `.detail`; `PaymentRequired` for 402.

For agents: MCP at `https://liquidvision.app/mcp/lite` (19 tools) and `/mcp` (69).
Endpoint list: https://liquidvision.app/llms.txt · plans: https://liquidvision.app/pricing
