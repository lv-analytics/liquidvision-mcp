---
name: liquidvision
description: Read the crypto derivatives market through LiquidVision.app — exchange-exact open interest, funding and liquidations on 13 venues, measured Hyperliquid and Lighter liquidation maps, cascades, positioning regime, funding carry, tokenized stocks on DEXs. Use when a task asks about leverage, liquidations, funding, open interest, perp positioning, or needs derivatives history for a backtest.
---

# LiquidVision.app skill

Use this skill when the user asks anything about crypto perpetual futures: who is long or short,
where leverage sits, what got liquidated, what funding costs, whether a move is new money or
short covering, or wants derivatives history for research. All data is public, read-only and
free to call; no key is needed.

## Three ways in, pick the first that fits

1. **MCP (preferred in an agent).** Add the lite server and call tools:
   ```json
   { "mcpServers": { "liquidvision": { "url": "https://liquidvision.app/mcp/lite" } } }
   ```
   13 tools that return conclusions. Start with `list_markets`, then `get_market_brief(symbol)`.
   The full server with 42 tools (raw rows, history, alerts) is `https://liquidvision.app/mcp`.
2. **REST.** `GET https://liquidvision.app/api/v1/...`, JSON, CORS on. Endpoint list and worked
   examples: `https://liquidvision.app/llms.txt` and `https://liquidvision.app/llms-full.txt`.
3. **Client libraries.** `pip install liquidvision` / `npm install liquidvision` (zero dependencies).

## Which tool answers which question

| Question | Tool / endpoint |
|---|---|
| What does the market say about coin X right now? | `get_market_brief` · `/brief/{symbol}` |
| Why did X move? (grounded answer) | `explain_market` · `POST /ask` |
| Is this rally new longs or short covering? | `get_positioning_regime` · `/oi/regime?minutes=240` |
| What got liquidated, and did the flush mark a low? | `get_liquidation_cascades` · `/liquidations/cascades` |
| Where does leverage sit (price levels)? | `get_hl_liquidation_map`, `get_lighter_liquidation_map` (measured) · `get_liquidation_map` (CEX, modeled) |
| Where is funding cheapest / richest for the same coin? | `get_funding_dispersion` · `/funding/dispersion` |
| What did the carry pair actually earn? | `get_funding_arbitrage` · `/funding/arbitrage` |
| Can the book absorb size? Do venues price it apart? | `get_microstructure` · `/microstructure` |
| Tokenized stocks / indices / commodities as perps | `get_tokenized_stocks` · `/stocks/tokenized` |
| Can I trust these numbers? | `get_accuracy` · `/accuracy` (our OI and funding vs the exchanges every 10 min) |
| History for a backtest | `/export/{dataset}` (CSV) · `/export/packages` (monthly Parquet) |

## Rules that keep answers honest

- Say **measured** or **modeled** the way the data does. CEX liquidation maps are models of where
  leverage would break (the map's top quarter held ~32% of liquidated USD on traded levels vs
  25% by chance). Hyperliquid and Lighter maps are measured from real positions with the
  exchange-reported liquidation price.
- Liquidation totals are a **floor**: Binance and Bitget publish at most one order per contract
  per second. Never present them as the whole market.
- Open interest is **one side** on every venue. An aggregator showing Bybit, Gate or HTX at
  twice the figure is showing both sides.
- Funding is annualized with each contract's **own settlement cycle** (1h / 4h / 8h). Hourly
  venues are ranked on an 8-hour mean, not the live print.
- Check **`age_s`** (seconds since the data was read) before acting on a number; rows carry
  `stale: true` when a venue feed is behind.
- Symbols are `BASEUSDT` (BTCUSDT, ETHUSDT). `list_markets` says what exists.
- Funding dispersion and carry are **gross** numbers: before fees, basis and margin. This is
  market data, not financial advice.

## History and paying for it

Free: the last 24 hours of any dataset. A Pro key: any 31-day CSV window; a Bot key: everything
plus monthly Parquet packages. Without an account an agent can pay per call in USDC on Arbitrum
(x402): `GET /export/package/{dataset}/{YYYY-MM}` answers 402 with the payment requirements
($1.00 per monthly file, $0.10 per CSV window with `?pay=x402`); any x402 client, or the
`X402Payer` in the Python client, completes it. Terms: `GET /api/v1/x402`.

## Example: answer "is BTC leverage building or unwinding?"

1. `get_positioning_regime(minutes=240)` → find BTCUSDT: regime (`new_longs` / `long_flush` / ...),
   `oi_delta_usd`, `venues`.
2. `get_market_brief("BTCUSDT")` → liquidations by window and side, funding extremes, OI by venue.
3. `get_hl_liquidation_map("BTCUSDT")` → where measured positions would liquidate below and above.
4. Report: the regime label, the dollar OI change, the liquidation split, and the nearest dense
   measured level on each side. Name the time window and that CEX totals are a floor.
