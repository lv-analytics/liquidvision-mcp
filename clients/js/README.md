# liquidvision (JavaScript)

Client for [LiquidVision.app](https://liquidvision.app): exchange-exact crypto derivatives
data for bots and AI agents. No dependencies. Node 18+, Deno, Bun and browsers.

```bash
npm install liquidvision
```

## Start here

```js
import { LiquidVision } from "liquidvision";

const lv = new LiquidVision();                       // no key: live data, shared anonymous limits
// const lv = new LiquidVision({ apiKey: "lv_..." }); // free key: 300/min; Pro/Bot: history, alerts

await lv.brief("BTCUSDT");        // one coin, one JSON
await lv.regime(240);             // new_longs / short_covering / new_shorts / long_flush per coin
await lv.cascades({ hours: 24 }); // liquidation cascades as events
await lv.fundingDispersion();     // where the same coin pays very different funding
await lv.fundingArbitrage();      // what the carry pair actually earned, 7 and 30 days
await lv.microstructure();        // spread, executable depth, cross-venue gap
await lv.tokenizedStocks();       // stocks / indices / commodities / FX as perps on DEXs
```

Measured, not modeled: `hlLiqmap`, `lighterLiqmap`, `hlWhales`, `lighterWhales`, `hlAccount`.
Modeled, and scored: `liqmap`, `liqheat`; the score is in `(await lv.accuracy()).liqmap_validation`.

Every object answer carries `age_s`; rows of `oi()`, `funding()`, `longShort()` carry `age_s`
each and `stale: true` when a venue feed is behind.

## History

```js
// free: last 24 h; Pro key: any 31-day window; Bot key: everything
const rows = await lv.export("liquidations", { symbol: "BTCUSDT", start: "2026-09-01", end: "2026-09-08" });
await lv.packages();                                   // monthly Parquet files: rows, bytes, sha256
const buf = await lv.package("liquidations", "2026-08"); // ArrayBuffer; Pro: this and last month, Bot: all
```

## Pay per call without an account (x402)

Bring any wallet that signs EIP-712 typed data (viem, ethers, a browser wallet). The client
signs a USDC `transferWithAuthorization` on Arbitrum One for exactly the asked amount; a public
facilitator submits it on-chain. Your key never leaves your code.

```js
import { privateKeyToAccount } from "viem/accounts";   // or ethers.Wallet, or window.ethereum
const account = privateKeyToAccount("0x...");
const lv = new LiquidVision({
  payer: { address: account.address, signTypedData: (td) => account.signTypedData(td), maxUsdPerCall: 2 },
});
const parquet = await lv.package("liquidations", "2026-08");                          // $1.00
const rows = await lv.export("funding_hourly", { start: "2026-09-01", end: "2026-09-30", pay: true }); // $0.10
console.log(lv.lastPayment);   // { success: true, transaction: "0x...", network: "arbitrum", payer: "0x..." }
```

Without a payer the same calls throw `PaymentRequired` with `.requirements`. Terms: `await lv.x402Info()`.

## Webhook alerts (Pro and Bot keys)

```js
const sub = await lv.createAlert("cascade", "https://your.host/hook", { symbol: "BTCUSDT", minUsd: 2_000_000 });
const secret = sub.secret; // shown once

import { verifySignature } from "liquidvision";
const ok = await verifySignature(secret, rawBody, req.headers["x-liquidvision-signature"]);
```

## What to know about the data

- Open interest is one side on every venue; Bybit, Gate and HTX at twice the figure elsewhere is both sides.
- Binance and Bitget liquidation feeds are throttled to one order per contract per second: totals are a floor.
- Funding is annualized with each contract's own settlement cycle.
- Errors throw `LiquidVisionError` (`.status`, `.detail`); `PaymentRequired` for 402.
- Node inside some containers prefers IPv6 lookups; if `fetch` fails on TLS, run with `--dns-result-order=ipv4first`.

For agents: MCP at `https://liquidvision.app/mcp/lite` (13 tools) and `/mcp` (42).
Endpoint list: https://liquidvision.app/llms.txt · plans: https://liquidvision.app/pricing
