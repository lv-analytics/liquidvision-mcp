/**
 * LiquidVision.app API client. No dependencies; needs global fetch (Node 18+, Deno, Bun, browsers).
 *
 *   import { LiquidVision } from "liquidvision";
 *   const lv = new LiquidVision();                     // no key: live data, shared anonymous limits
 *   const lv = new LiquidVision({ apiKey: "lv_..." }); // free key: 300 req/min; Pro/Bot: history, alerts
 *
 *   await lv.brief("BTCUSDT");          // one coin, one JSON: the place to start
 *   await lv.regime(240);               // who is driving the move
 *   await lv.hlLiqmap("BTCUSDT");       // MEASURED map from real Hyperliquid positions
 *   await lv.tokenizedStocks();         // stocks / indices / commodities / FX as perps on DEXs
 *
 * Pay-per-call without an account (x402, USDC on Arbitrum One). Bring any wallet that
 * can sign EIP-712 typed data (viem walletClient, ethers Wallet, a browser wallet):
 *
 *   import { privateKeyToAccount } from "viem/accounts";
 *   const account = privateKeyToAccount("0x...");
 *   const lv = new LiquidVision({ payer: { address: account.address, signTypedData: (td) => account.signTypedData(td) } });
 *   await lv.package("liquidations", "2026-08");                     // $1.00 -> ArrayBuffer of the Parquet file
 *   await lv.export("funding_hourly", { start: "2026-09-01", end: "2026-09-30", pay: true });   // $0.10
 *
 * Every object answer carries age_s (seconds since the data was read from the
 * exchange); rows of oi(), funding() and longShort() carry age_s each and
 * stale: true when a venue feed is behind. Docs: https://liquidvision.app/llms.txt
 * MCP for agents: https://liquidvision.app/mcp/lite (13 tools) and /mcp (42).
 */

export const VERSION = "0.2.0";
export const USDC_ARBITRUM = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831";
export const ARBITRUM_CHAIN_ID = 42161;

export class LiquidVisionError extends Error {
  constructor(status, detail) {
    super(`HTTP ${status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
    this.name = "LiquidVisionError";
    this.status = status;
    this.detail = detail;
  }
}

/** 402: the resource is paid. `requirements` is the x402 PaymentRequirements object (v1). */
export class PaymentRequired extends LiquidVisionError {
  constructor(detail, requirements) {
    super(402, detail);
    this.name = "PaymentRequired";
    this.requirements = requirements;
  }
}

/** Check a webhook delivery: header X-LiquidVision-Signature against the raw request body. */
export async function verifySignature(secret, body, signature) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, typeof body === "string" ? enc.encode(body) : body);
  const hex = [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
  const given = String(signature || "");
  if (hex.length !== given.length) return false;
  let diff = 0;
  for (let i = 0; i < hex.length; i++) diff |= hex.charCodeAt(i) ^ given.charCodeAt(i);
  return diff === 0;
}

const b64 = (obj) => btoa(unescape(encodeURIComponent(JSON.stringify(obj))));
const unb64 = (s) => JSON.parse(decodeURIComponent(escape(atob(s))));

/**
 * Build the X-PAYMENT header for one v1 PaymentRequirements object.
 * payer = { address, signTypedData({domain, types, primaryType, message}) -> Promise<hex>, maxUsdPerCall? }
 */
export async function signX402(payer, requirements) {
  const value = BigInt(requirements.maxAmountRequired);
  const maxUsd = payer.maxUsdPerCall ?? 5;
  if (value > BigInt(Math.round(maxUsd * 1_000_000))) {
    throw new PaymentRequired(`server asks ${Number(value) / 1e6} USDC, above maxUsdPerCall`, requirements);
  }
  if ((requirements.asset ?? USDC_ARBITRUM).toLowerCase() !== USDC_ARBITRUM.toLowerCase() ||
      !["arbitrum", "eip155:42161"].includes(requirements.network)) {
    throw new PaymentRequired("this payer only signs USDC on Arbitrum One", requirements);
  }
  const now = Math.floor(Date.now() / 1000);
  const nonceBytes = crypto.getRandomValues(new Uint8Array(32));
  const nonce = "0x" + [...nonceBytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  const authorization = {
    from: payer.address, to: requirements.payTo, value,
    validAfter: BigInt(now - 60), validBefore: BigInt(now + Number(requirements.maxTimeoutSeconds ?? 60)), nonce,
  };
  const extra = requirements.extra ?? {};
  const signature = await payer.signTypedData({
    domain: { name: extra.name ?? "USD Coin", version: extra.version ?? "2", chainId: ARBITRUM_CHAIN_ID, verifyingContract: USDC_ARBITRUM },
    types: {
      TransferWithAuthorization: [
        { name: "from", type: "address" }, { name: "to", type: "address" }, { name: "value", type: "uint256" },
        { name: "validAfter", type: "uint256" }, { name: "validBefore", type: "uint256" }, { name: "nonce", type: "bytes32" },
      ],
    },
    primaryType: "TransferWithAuthorization",
    message: authorization,
  });
  return b64({
    x402Version: 1, scheme: "exact", network: "arbitrum",
    payload: { signature, authorization: { ...authorization, value: value.toString(),
      validAfter: authorization.validAfter.toString(), validBefore: authorization.validBefore.toString() } },
  });
}

export class LiquidVision {
  /** @param {{apiKey?: string, baseUrl?: string, fetch?: typeof fetch, payer?: {address: string, signTypedData: Function, maxUsdPerCall?: number}}} [opts] */
  constructor({ apiKey, baseUrl = "https://liquidvision.app/api/v1", fetch: f, payer } = {}) {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this._fetch = f ?? globalThis.fetch.bind(globalThis);
    this.payer = payer;
    this.lastPayment = null;   // settlement of the last paid call (tx hash, payer)
  }

  async _request(method, path, params, body, { pay = false, payment } = {}) {
    const url = new URL(this.baseUrl + path);
    for (const [k, v] of Object.entries(params ?? {})) if (v != null) url.searchParams.set(k, v);
    const headers = { Accept: "application/json", "User-Agent": `liquidvision-js/${VERSION}` };
    if (this.apiKey) headers["X-API-Key"] = this.apiKey;
    if (payment) headers["X-PAYMENT"] = payment;
    let payload;
    if (body) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(Object.fromEntries(Object.entries(body).filter(([, v]) => v != null)));
    }
    const r = await this._fetch(url, { method, headers, body: payload });
    if (r.status === 402) {
      let j = null;
      try { j = await r.json(); } catch { /* not JSON */ }
      const reqs = j?.accepts?.[0] ?? null;
      if (reqs && pay && this.payer && !payment) {
        return this._request(method, path, params, body, { payment: await signX402(this.payer, reqs) });
      }
      throw new PaymentRequired(j?.error ?? "payment required", reqs);
    }
    if (!r.ok) {
      const text = await r.text();
      let detail = text.slice(0, 300);
      try { const j = JSON.parse(text); detail = j.detail ?? j.error ?? j; } catch { /* not JSON */ }
      throw new LiquidVisionError(r.status, detail);
    }
    const settled = r.headers.get("x-payment-response");
    if (settled) { try { this.lastPayment = unb64(settled); } catch { this.lastPayment = { raw: settled }; } }
    return r;
  }

  async _get(path, params) { return (await this._request("GET", path, params)).json(); }

  // ---- start here ----
  /** What exists: every venue and its contracts with live open interest. */
  async markets() {
    const out = {};
    for (const r of await this.oi()) (out[r.exchange] ??= []).push(r.symbol);
    for (const k of Object.keys(out)) out[k].sort();
    return out;
  }
  /** One deterministic risk brief for a coin. */
  brief(symbol) { return this._get(`/brief/${symbol}`); }
  /** Positioning regime per coin: price change x OI change. */
  regime(minutes = 240) { return this._get("/oi/regime", { minutes }); }
  /** Liquidation cascades detected as events, with what price did in the hour after. */
  cascades({ hours = 24, limit = 50 } = {}) { return this._get("/liquidations/cascades", { hours, limit }); }
  /** Where the same coin pays very different funding across venues. */
  fundingDispersion() { return this._get("/funding/dispersion"); }
  /** What the carry pair actually earned over 7 and 30 days. */
  fundingArbitrage({ minVenues = 3, limit = 40 } = {}) { return this._get("/funding/arbitrage", { min_venues: minVenues, limit }); }
  /** Spread, immediately executable depth and cross-venue price gap. */
  microstructure(minutes = 240) { return this._get("/microstructure", { minutes }); }
  /** Stocks, indices, ETFs, commodities, FX and pre-IPO names as perps on DEXs, one row per underlying. */
  tokenizedStocks() { return this._get("/stocks/tokenized"); }
  /** On-chain perp venues grouped by chain next to the CEX total. */
  onchain() { return this._get("/onchain"); }

  // ---- live market data ----
  /** Open interest per venue and contract, as each exchange publishes it (one side). */
  oi() { return this._get("/oi"); }
  /** Funding rate and mark price per venue and contract, with the contract's own interval. */
  funding() { return this._get("/funding"); }
  longShort() { return this._get("/longshort"); }
  /** One contract across every venue. */
  oiBoard(symbol) { return this._get(`/oiboard/${symbol}`); }

  // ---- liquidations ----
  /** Raw liquidation events. Binance and Bitget are exchange-throttled: a floor. */
  liquidations(minutes = 60) { return this._get("/liquidations", { minutes }); }
  liquidationsSummary(minutes = 60) { return this._get("/liquidations/summary", { minutes }); }
  /** MODELED liquidation clusters per price bin (CEXs). How it scores: accuracy(). */
  liqmap(symbol, { exchange = "all", range = "1d" } = {}) { return this._get(`/liqmap/${symbol}`, { exchange, range }); }
  /** MODELED liquidation heatmap: grid[time][price bin] with the price path. */
  liqheat(symbol, { exchange = "all", range = "1d" } = {}) { return this._get(`/liqheat/${symbol}`, { exchange, range }); }

  // ---- measured positions: Hyperliquid and Lighter ----
  /** MEASURED liquidation map from the ~10,000 largest Hyperliquid accounts. */
  hlLiqmap(symbol, { range = "1d" } = {}) { return this._get(`/liqmap/hl/${symbol}`, { range }); }
  /** MEASURED liquidation map from every Lighter account. */
  lighterLiqmap(symbol, { range = "1d" } = {}) { return this._get(`/liqmap/lighter/${symbol}`, { range }); }
  /** Hyperliquid positions with exchange-reported liquidation prices, closest to liquidation first. */
  hlWhales({ coin, side, minUsd = 100000, maxDistPct, sort = "distance", limit = 100 } = {}) {
    return this._get("/hl/whales", { coin, side, min_usd: minUsd, max_dist_pct: maxDistPct, sort, limit });
  }
  /** Lighter positions with exchange-reported liquidation prices. */
  lighterWhales({ coin, side, minUsd = 100000, maxDistPct, sort = "distance", limit = 100 } = {}) {
    return this._get("/lighter/whales", { coin, side, min_usd: minUsd, max_dist_pct: maxDistPct, sort, limit });
  }
  /** One Hyperliquid account: live positions and archived snapshots. */
  hlAccount(address) { return this._get(`/hl/account/${address}`); }

  // ---- service ----
  /** The public audit: our OI and funding vs the exchanges, and the map's score. */
  accuracy() { return this._get("/accuracy"); }
  status() { return this._get("/status"); }
  uptime() { return this._get("/status/uptime"); }
  /** Pay-per-call terms: prices, network, receiving address, facilitator. */
  x402Info() { return this._get("/x402"); }

  // ---- history: CSV windows (free: last 24 h; Pro: 31-day window; Bot: everything; or pay: true) ----
  datasets() { return this._get("/export"); }
  /**
   * Raw CSV text. dataset: liquidations | funding_settlements | funding_hourly |
   * open_interest_hourly | hl_positions | lighter_positions. start/end: ISO dates, UTC.
   * pay: true with a payer buys this one window at Pro terms for $0.10 (x402).
   */
  async exportCsv(dataset, { start, end, symbol, exchange, limit, pay = false } = {}) {
    const params = { start, end, symbol, exchange, limit, ...(pay ? { pay: "x402" } : {}) };
    return (await this._request("GET", `/export/${dataset}`, params, null, { pay })).text();
  }
  /** The same export parsed into objects (all values are strings, as in the CSV). */
  async export(dataset, opts) {
    const lines = (await this.exportCsv(dataset, opts)).trim().split("\n");
    const cells = (l) => l.split(",").map((c) => c.replace(/^"|"$/g, ""));
    const head = cells(lines[0]);
    return lines.slice(1).map((l) => Object.fromEntries(cells(l).map((c, i) => [head[i], c])));
  }

  // ---- history: monthly Parquet packages ----
  /** Catalogue of monthly Parquet files (rows, bytes, sha256, which months your tier may take). */
  packages() { return this._get("/export/packages"); }
  /** One monthly Parquet file as an ArrayBuffer. Pro: this and last month, Bot: all; otherwise one x402 payment of $1.00. */
  async package(dataset, month, { pay = true } = {}) {
    return (await this._request("GET", `/export/package/${dataset}/${month}`, null, null, { pay })).arrayBuffer();
  }

  // ---- webhook alerts (Pro: 3, Bot: 20) ----
  /** type: cascade | hl_near_liq | cluster_sweep. Resolves with the signing secret once. */
  async createAlert(type, url, { symbol, minUsd, xNormal, maxDistPct } = {}) {
    return (await this._request("POST", "/webhooks", null,
      { type, url, symbol, min_usd: minUsd, x_normal: xNormal, max_dist_pct: maxDistPct })).json();
  }
  async listAlerts() { return (await this._get("/webhooks")).webhooks; }
  async deleteAlert(id) { return (await (await this._request("DELETE", `/webhooks/${id}`)).json()).deleted; }
  /** Send a signed sample payload to the subscription's URL now. */
  async testAlert(id) { return (await this._request("POST", `/webhooks/${id}/test`)).json(); }
}

export default LiquidVision;
