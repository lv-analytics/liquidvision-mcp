# liquidvision (JavaScript)

Client for the [LiquidVision](https://liquidvision.app) crypto derivatives data API.
No dependencies. Node 18+, Deno, Bun and browsers.

```bash
npm install liquidvision
```

```js
import { LiquidVision } from "liquidvision";

const lv = new LiquidVision();                       // no key: live data, shared anonymous limits
// const lv = new LiquidVision({ apiKey: "lv_..." }); // free key: 300 req/min

// open interest exactly as each exchange publishes it, 13 venues
for (const row of await lv.oi()) {
  if (row.symbol === "BTCUSDT" && !row.stale) console.log(row.exchange, row.oi_usd, row.age_s);
}

// measured: Hyperliquid whale positions within 5% of liquidation
const { positions } = await lv.hlWhales({ coin: "BTC", maxDistPct: 5 });

// modeled liquidation map, and how that model scores against realized liquidations
const map = await lv.liqmap("BTCUSDT");
console.log((await lv.accuracy()).liqmap_validation);

// history for a backtest (free: last 24 h, Pro: any 31-day window, Bot: everything)
const rows = await lv.export("liquidations", { symbol: "BTCUSDT", start: "2026-09-01", end: "2026-09-08" });
```

## Webhook alerts (Pro and Bot keys)

```js
const sub = await lv.createAlert("cascade", "https://your.host/hook", { symbol: "BTCUSDT", minUsd: 2_000_000 });
const secret = sub.secret; // shown once

// in your handler
import { verifySignature } from "liquidvision";
const ok = await verifySignature(secret, rawBody, req.headers["x-liquidvision-signature"]);
```

Alert types: `cascade` (a liquidation cascade just ended), `hl_near_liq` (a Hyperliquid
whale near its liquidation price), `cluster_sweep` (price reached a large modeled
liquidation cluster; payload carries modeled and realized USD).

## What to know about the data

- Every object answer carries `age_s`; rows of `oi()`, `funding()`, `longShort()` carry
  `age_s` each and `stale: true` when a venue feed is behind.
- Liquidation events from Binance and Bitget are throttled by the exchanges to one order
  per contract per second, so totals are a floor.
- `liqmap` and `liqheat` are models. `hlLiqmap`, `hlWhales`, `hlAccount` are measured.
- Errors throw `LiquidVisionError` with `.status` and `.detail` (401 no key, 402 plan needed, 429 rate limit).

Full endpoint list: https://liquidvision.app/llms.txt · plans: https://liquidvision.app/pricing
