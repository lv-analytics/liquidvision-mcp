/**
 * LiquidVision API client. No dependencies; needs global fetch (Node 18+, Deno, Bun, browsers).
 *
 *   import { LiquidVision } from "liquidvision";
 *   const lv = new LiquidVision();                     // no key: live data, shared anonymous limits
 *   const lv = new LiquidVision({ apiKey: "lv_..." }); // free key: 300 req/min; Pro/Bot: history, alerts
 *
 * Every object answer carries age_s (seconds since the data was read from the
 * exchange); rows of oi(), funding() and longShort() carry age_s each and
 * stale: true when a venue feed is behind. Docs: https://liquidvision.app/llms.txt
 */

export const VERSION = "0.1.0";

export class LiquidVisionError extends Error {
  constructor(status, detail) {
    super(`HTTP ${status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
    this.name = "LiquidVisionError";
    this.status = status;
    this.detail = detail;
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

export class LiquidVision {
  /** @param {{apiKey?: string, baseUrl?: string, fetch?: typeof fetch}} [opts] */
  constructor({ apiKey, baseUrl = "https://liquidvision.app/api/v1", fetch: f } = {}) {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this._fetch = f ?? globalThis.fetch.bind(globalThis);
  }

  async _request(method, path, params, body) {
    const url = new URL(this.baseUrl + path);
    for (const [k, v] of Object.entries(params ?? {})) if (v != null) url.searchParams.set(k, v);
    const headers = { Accept: "application/json" };
    if (this.apiKey) headers["X-API-Key"] = this.apiKey;
    let payload;
    if (body) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(Object.fromEntries(Object.entries(body).filter(([, v]) => v != null)));
    }
    const r = await this._fetch(url, { method, headers, body: payload });
    if (!r.ok) {
      const text = await r.text();
      let detail = text.slice(0, 300);
      try { const j = JSON.parse(text); detail = j.detail ?? j.error ?? j; } catch { /* not JSON */ }
      throw new LiquidVisionError(r.status, detail);
    }
    return r;
  }

  async _get(path, params) { return (await this._request("GET", path, params)).json(); }

  // ---- live market data ----
  /** Open interest per venue and contract, as each exchange publishes it. */
  oi() { return this._get("/oi"); }
  /** Funding rate and mark price per venue and contract. */
  funding() { return this._get("/funding"); }
  longShort() { return this._get("/longshort"); }
  /** One contract across every venue. */
  oiBoard(symbol) { return this._get(`/oiboard/${symbol}`); }
  /** One deterministic risk brief for a coin. */
  brief(symbol) { return this._get(`/brief/${symbol}`); }
  /** Positioning regime per coin: price change x OI change. */
  regime(minutes = 60) { return this._get("/oi/regime", { minutes }); }
  /** Cross-venue funding spread per coin. */
  fundingDispersion() { return this._get("/funding/dispersion"); }

  // ---- liquidations ----
  /** Raw liquidation events. Binance and Bitget are exchange-throttled: a floor. */
  liquidations(minutes = 60) { return this._get("/liquidations", { minutes }); }
  liquidationsSummary(minutes = 60) { return this._get("/liquidations/summary", { minutes }); }
  /** Liquidation cascades detected as events. */
  cascades({ hours = 24, limit = 50 } = {}) { return this._get("/liquidations/cascades", { hours, limit }); }
  /** MODELED liquidation clusters per price bin. How it scores: accuracy(). */
  liqmap(symbol, { exchange = "all", range = "1d" } = {}) { return this._get(`/liqmap/${symbol}`, { exchange, range }); }
  /** MODELED liquidation heatmap: grid[time][price bin] with the price path. */
  liqheat(symbol, { exchange = "all", range = "1d" } = {}) { return this._get(`/liqheat/${symbol}`, { exchange, range }); }

  // ---- Hyperliquid, measured ----
  /** MEASURED liquidation map from the largest Hyperliquid accounts. */
  hlLiqmap(symbol, { range = "1d" } = {}) { return this._get(`/liqmap/hl/${symbol}`, { range }); }
  /** Whale positions with exchange-reported liquidation prices, closest to liquidation first. */
  hlWhales({ coin, side, minUsd = 100000, maxDistPct, sort = "distance", limit = 100 } = {}) {
    return this._get("/hl/whales", { coin, side, min_usd: minUsd, max_dist_pct: maxDistPct, sort, limit });
  }
  /** One Hyperliquid account: live positions and archived snapshots. */
  hlAccount(address) { return this._get(`/hl/account/${address}`); }

  // ---- service ----
  /** The public audit: our OI and funding vs the exchanges, and the map's score. */
  accuracy() { return this._get("/accuracy"); }
  status() { return this._get("/status"); }
  uptime() { return this._get("/status/uptime"); }

  // ---- history (free: last 24 h; Pro: 31-day window; Bot: everything) ----
  datasets() { return this._get("/export"); }
  /**
   * Raw CSV text. dataset: liquidations | funding_settlements | funding_hourly |
   * open_interest_hourly | hl_positions. start/end: ISO dates, UTC.
   */
  async exportCsv(dataset, { start, end, symbol, exchange, limit } = {}) {
    return (await this._request("GET", `/export/${dataset}`, { start, end, symbol, exchange, limit })).text();
  }
  /** The same export parsed into objects (all values are strings, as in the CSV). */
  async export(dataset, opts) {
    const lines = (await this.exportCsv(dataset, opts)).trim().split("\n");
    const cells = (l) => l.split(",").map((c) => c.replace(/^"|"$/g, ""));
    const head = cells(lines[0]);
    return lines.slice(1).map((l) => Object.fromEntries(cells(l).map((c, i) => [head[i], c])));
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
