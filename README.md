# LiquidVision MCP server

Crypto derivatives data for AI agents and trading bots: a remote MCP server,
no install, no API key needed.

**Endpoint:** `https://liquidvision.app/mcp` (Streamable HTTP, 39 tools, read-only)

## What it gives an agent

Open interest and funding rates across 13 venues (Binance, MEXC, Bybit, Bitget,
Hyperliquid, HTX, Gate, OKX, KuCoin, BingX, Aster, Kraken, GMX on Arbitrum), as
each exchange reports them. An audit compares our figures with the exchanges'
own endpoints every 10 minutes and publishes the result:
https://liquidvision.app/accuracy (tool: `get_accuracy`).

Start with `list_markets`, then the computed views. They return a conclusion,
not a pile of ticks:

| Tool | Answers |
|---|---|
| `get_liquidation_cascades` | Liquidations grouped into events: start, duration, multiples of normal, what price did |
| `get_positioning_regime` | Price direction x change in positions per coin: new longs, short covering, new shorts, long flush |
| `get_funding_dispersion` | Coins ranked by how far funding disagrees across venues, each leg annualized with its real settlement cycle |
| `get_microstructure` | Cross-venue spread, top-of-book depth, basis |
| `get_market_brief` | One deterministic risk brief for a symbol: feed it to your own model |
| `explain_market` | "Why did BTC drop 4%?": a grounded answer built from the live data |

Measured, not modeled (Hyperliquid, where positions are public):

| Tool | Returns |
|---|---|
| `get_hl_whales` | Leveraged positions of the 10,000 largest accounts with exchange-reported liquidation prices, closest to liquidation first |
| `get_hl_account` | One address: live positions, liquidation prices, archived snapshots |
| `get_hl_liquidation_map` | Those positions binned by liquidation price |
| `get_hl_builder_markets` | Builder-deployed (HIP-3) perp markets on Hyperliquid: equity indices, stocks, commodities, with open interest, volume, funding |
| `get_lighter_liquidation_map` | Measured liquidation map for Lighter: positions binned by the exchange-reported liquidation price, with the share of venue open interest covered |
| `get_lighter_whales` | Lighter positions with exchange-reported liquidation prices, closest to liquidation first (address = account index, l1_address = wallet) |

Raw data: `get_funding_rates`, `get_funding_history`, `get_funding_settlements`,
`get_open_interest`, `get_open_interest_history`, `get_oi_board`,
`get_cash_flows`, `get_long_short_ratio`, `get_liquidations`,
`get_liquidations_summary`, `get_liquidation_map`, `get_liquidation_heatmap`,
`get_orderbook_heatmap`, `get_footprint`, `get_cvd`, `get_spoofing`,
`get_arbitrum_perps`, `get_top_traders`, `get_token_unlocks`, `get_stocks`.

For bots: `get_api_key` (a free key by email, without a browser),
`get_history` (archive rows as CSV for backtests), `create_alert`,
`list_alerts`, `delete_alert` (webhooks: a liquidation cascade ended, a
Hyperliquid whale is near liquidation, price reached a large modeled cluster).

## Connect

**Claude Code**

```bash
claude mcp add --transport http liquidvision https://liquidvision.app/mcp
```

**Claude Desktop / claude.ai**: Settings → Connectors → Add custom connector,
URL `https://liquidvision.app/mcp`.

**Cursor / Windsurf / any client with an `mcp.json`**

```json
{
  "mcpServers": {
    "liquidvision": {
      "url": "https://liquidvision.app/mcp"
    }
  }
}
```

**Raw JSON-RPC**

```bash
curl -X POST https://liquidvision.app/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Without MCP

The same data is a REST API and a WebSocket feed (`https://liquidvision.app/llms.txt`
lists every endpoint). Two small clients live in [`clients/`](clients):
Python (standard library only) and JavaScript (built-in `fetch`).

```python
from liquidvision import LiquidVision
lv = LiquidVision()
lv.hl_whales(coin="BTC", max_dist_pct=5)["positions"]
lv.export("liquidations", symbol="BTCUSDT", start="2026-09-01", end="2026-09-08")
```

## Examples

- [`examples/passivbot_funding_filter.py`](examples/passivbot_funding_filter.py): keeps
  [Passivbot](https://github.com/enarjord/passivbot) out of coins where holding the
  position is expensive (funding annualized with the contract's real interval) or where a
  liquidation cascade is running. Writes the `ignored_coins` file Passivbot reads
  continuously. Standard library only, no key:
  `python examples/passivbot_funding_filter.py --exchange bybit --once`
- [`examples/binance_liq_probe.py`](examples/binance_liq_probe.py): which Binance host
  actually delivers the liquidation stream.
- [`collectors/gmx_v2.py`](collectors/gmx_v2.py): a standalone GMX v2 (Arbitrum) collector.

## Limits and honesty

- Free and anonymous: 240 requests/min per IP. A free key raises it to 300;
  send it as `X-API-Key` or `Authorization: Bearer lv_...`. Paid plans (history
  exports, webhook alerts, higher limits): https://liquidvision.app/pricing
- `explain_market` costs real money to run: 5 answers/day anonymous, 25 with a
  free key.
- Every dict answer carries `age_s` (seconds since the data was read from the
  exchange); rows of `get_open_interest`, `get_funding_rates` and
  `get_long_short_ratio` carry `age_s` each and `stale: true` when a venue feed
  is behind.
- Open interest is counted on one side on every venue. Bybit documents its
  `openInterest` as "the sum of both sides" and we serve its
  `singleOpenInterest`; Gate and HTX report both sides and are halved. An
  aggregator showing those venues at twice our figure is showing both sides.
  Commands to check this yourself: [docs/coinglass-vs-exchanges.md](docs/coinglass-vs-exchanges.md).
- Liquidation events come from Binance, Bitget, OKX, Bybit, HTX, Gate, Kraken,
  GMX (on-chain, complete) and Hyperliquid whale accounts. Binance and Bitget
  throttle their feeds to one order per contract per second, so totals are a
  floor for the whole market.
- The CEX liquidation map and heatmap are **models** built from candles and
  open-interest changes. They show where leveraged positions sit, not where
  price will go. Scored against realized liquidations (367 snapshots, 21 days):
  among the price levels actually traded in the next 24 h, the map's top
  quarter held 32% of the liquidated USD, against 25% by chance. The live
  score is on https://liquidvision.app/accuracy.
- Symbols are `BASEUSDT` (`BTCUSDT`, `ETHUSDT`, ...). Computed views accept a
  fixed set of window sizes; other values snap to the nearest.

More for agents: https://liquidvision.app/llms.txt · REST/OpenAPI:
https://liquidvision.app/api/v1/docs · status and uptime:
https://liquidvision.app/status
