# plugin-liquidvision (ElizaOS)

Crypto derivatives context for ElizaOS agents from [LiquidVision.app](https://liquidvision.app):
exchange-exact open interest, liquidations, cascades, positioning regime, measured Hyperliquid
liquidation maps, funding dispersion across 13 venues, and tokenized stocks traded as perps on
DEXs. Read-only: nothing here signs, trades or spends. No key needed.

```bash
elizaos plugins add plugin-liquidvision      # or: bun add plugin-liquidvision
```

```json
{ "name": "Trader", "plugins": ["plugin-liquidvision"] }
```

## What the agent can now answer

| Ask | Action |
|---|---|
| "What's the derivatives picture on $BTC?" | `LIQUIDVISION_DERIVATIVES_BRIEF` — price, OI, liquidations by side and window, largest venues |
| "Is this ETH rally new longs or short covering?" | `LIQUIDVISION_POSITIONING_REGIME` — price x open interest per coin |
| "Any big liquidation cascades today?" | `LIQUIDVISION_LIQUIDATION_CASCADES` — events with what price did in the hour after |
| "Where are the BTC liquidation levels?" | `LIQUIDVISION_LIQUIDATION_MAP` — measured Hyperliquid positions, densest levels below and above |
| "Where is funding cheapest for SOL?" | `LIQUIDVISION_FUNDING_DISPERSION` — cheapest long venue vs richest short venue, own settlement cycles |
| "How big is the tokenized stocks perp market?" | `LIQUIDVISION_TOKENIZED_STOCKS` — Lighter, Hyperliquid builder markets, Ostium, gTrade |

A dynamic provider, `LIQUIDVISION_DERIVATIVES`, adds a one-paragraph derivatives context when a
message mentions a coin (`$BTC`, `ethereum`, `SOLUSDT`).

## Settings

| Setting | Default | |
|---|---|---|
| `LIQUIDVISION_API_KEY` | — | Optional. Free endpoints need no key (60 req/min per IP); a Pro/Bot key raises it. |
| `LIQUIDVISION_BASE_URL` | `https://liquidvision.app/api/v1` | |

## Honest data

- Liquidation totals are a floor: Binance and Bitget publish at most one order per contract per second.
- Open interest is one side on every venue.
- The liquidation map is **measured** (real Hyperliquid positions with the exchange's liquidation price), large accounts only.
- Funding spreads are gross: before fees, basis and margin. Market data, not financial advice.

Raw rows, history and alerts are on the REST API and MCP server: https://liquidvision.app/llms.txt.
MCP for agents: `https://liquidvision.app/mcp/lite`.
