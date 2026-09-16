# LiquidVision MCP server

Crypto derivatives data for AI agents — a remote MCP server, no install, no
API key needed.

**Endpoint:** `https://liquidvision.app/mcp` (Streamable HTTP)

## What it gives an agent

Open interest and funding rates across 12 venues (Binance, MEXC, Bybit,
Bitget, Hyperliquid, HTX, Gate, OKX, KuCoin, BingX, Aster, Kraken Futures),
served **exactly as the exchanges publish them** — no haircuts, no doubling
(some aggregators halve Bitget's OI and double Gate's; we don't).

The point, though, is the computed views — they return a conclusion, not a
pile of ticks:

| Tool | Answers |
|---|---|
| `get_liquidation_cascades` | Liquidations grouped into events: start, duration, multiples of normal, what price did |
| `get_positioning_regime` | Price direction × OI direction per coin: new longs, short covering, new shorts, long flush |
| `get_funding_dispersion` | Coins ranked by how far funding disagrees across venues (arbitrage), each leg annualized with its real settlement cycle |
| `get_microstructure` | Cross-venue spread, top-of-book depth, basis |
| `get_market_brief` | One deterministic risk brief for a symbol — feed it to your own model |
| `explain_market` | "Why did BTC drop 4%?" — grounded answer built from the live data |

Plus raw data: `get_funding_rates`, `get_funding_history`, `get_open_interest`,
`get_open_interest_history`, `get_oi_board`, `get_cash_flows`,
`get_long_short_ratio`, `get_liquidations`, `get_liquidations_summary`,
`get_liquidation_map`, `get_liquidation_heatmap`, `get_orderbook_heatmap`,
`get_footprint`, `get_cvd`, `get_spoofing`, `get_top_traders`,
`get_token_unlocks`, `get_stocks`. 24 tools total.

## Connect

**Claude Code**

```bash
claude mcp add --transport http liquidvision https://liquidvision.app/mcp
```

**Claude Desktop / claude.ai** — Settings → Connectors → Add custom connector,
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

## Limits and honesty

- Anonymous: 240 requests/min per IP. A free API key (sign up at
  https://liquidvision.app/data) raises it; send it as
  `Authorization: Bearer lv_...`.
- `explain_market` costs real money to run: 5 answers/day anonymous, 25 with
  a free key.
- Liquidation events cover OKX, Bybit, HTX, Gate, Kraken and Hyperliquid whale
  accounts. Binance and Bitget stopped publishing liquidations; we report none
  for them rather than estimating, so totals understate the whole market.
- Liquidation maps and heatmaps are **modeled** from candles and OI deltas —
  estimates of where leverage would break, not exchange-disclosed orders.
- Symbols are `BASEUSDT` (`BTCUSDT`, `ETHUSDT`, ...). Computed views accept a
  fixed set of window sizes; other values snap to the nearest.

More for agents: https://liquidvision.app/llms.txt · REST/OpenAPI:
https://liquidvision.app/api/v1/docs
