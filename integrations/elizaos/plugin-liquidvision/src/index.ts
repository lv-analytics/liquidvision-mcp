/**
 * plugin-liquidvision — crypto derivatives context for ElizaOS agents.
 *
 * Six actions and one provider over LiquidVision.app's free "conclusions"
 * endpoints: an agent asked "is BTC leverage building?", "where are the
 * liquidations?", "where is funding cheapest?" answers from exchange-exact
 * data on 13 venues instead of guessing. Read-only: nothing here signs,
 * trades or spends. No key needed; LIQUIDVISION_API_KEY (Pro/Bot) is passed
 * through for higher limits.
 */
import type {
  Action,
  ActionResult,
  HandlerCallback,
  IAgentRuntime,
  Memory,
  Plugin,
  Provider,
  ProviderResult,
  State,
} from "@elizaos/core";

const DEFAULT_BASE = "https://liquidvision.app/api/v1";
const UA = "plugin-liquidvision/0.1.0";

// ---------------------------------------------------------------- helpers

function base(runtime: IAgentRuntime): string {
  return String(runtime.getSetting("LIQUIDVISION_BASE_URL") || DEFAULT_BASE).replace(/\/+$/, "");
}

async function lv(runtime: IAgentRuntime, path: string, params: Record<string, string | number> = {}): Promise<any> {
  const url = new URL(base(runtime) + path);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, String(v));
  const headers: Record<string, string> = { Accept: "application/json", "User-Agent": UA };
  const key = runtime.getSetting("LIQUIDVISION_API_KEY");
  if (typeof key === "string" && key) headers["X-API-Key"] = key;
  const r = await fetch(url, { headers });
  if (!r.ok) {
    const body = await r.text();
    throw new Error(`LiquidVision ${r.status}: ${body.slice(0, 200)}`);
  }
  return r.json();
}

/** "$BTC", "eth", "Solana", "BTCUSDT" -> "BTCUSDT"; null when nothing recognisable. */
const NAMES: Record<string, string> = {
  BITCOIN: "BTC", ETHEREUM: "ETH", ETHER: "ETH", SOLANA: "SOL", RIPPLE: "XRP", DOGECOIN: "DOGE",
  HYPERLIQUID: "HYPE", BINANCE: "BNB", CARDANO: "ADA", CHAINLINK: "LINK", AVALANCHE: "AVAX", SUI: "SUI",
};
const COMMON = new Set(["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "ADA", "HYPE", "LINK", "AVAX", "SUI", "TRX",
  "LTC", "DOT", "TON", "PEPE", "WIF", "ENA", "ARB", "OP", "NEAR", "APT", "ZEC", "AAVE", "UNI", "TIA", "SEI"]);

export function extractSymbol(text: string): string | null {
  const t = (text || "").toUpperCase();
  const tagged = t.match(/\$([A-Z0-9]{2,10})\b/);
  if (tagged) return tagged[1].replace(/USDT$/, "") + "USDT";
  const pair = t.match(/\b([A-Z0-9]{2,10})USDT\b/);
  if (pair) return pair[1] + "USDT";
  for (const [name, sym] of Object.entries(NAMES)) if (new RegExp(`\\b${name}\\b`).test(t)) return sym + "USDT";
  for (const w of t.split(/[^A-Z0-9]+/)) if (COMMON.has(w)) return w + "USDT";
  return null;
}

const usd = (v: number | null | undefined): string => {
  if (v == null || !Number.isFinite(v)) return "n/a";
  const a = Math.abs(v), s = v < 0 ? "-" : "";
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(0)}K`;
  return `${s}$${a.toFixed(0)}`;
};
const pct = (v: number | null | undefined, d = 1): string =>
  v == null || !Number.isFinite(v) ? "n/a" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}%`;

const textOf = (m: Memory): string => (m?.content?.text as string) || "";
const mentions = (m: Memory, words: RegExp): boolean => words.test(textOf(m).toLowerCase());

async function reply(callback: HandlerCallback | undefined, text: string, action: string, data: any): Promise<ActionResult> {
  if (callback) await callback({ text, actions: [action], source: "liquidvision" });
  return { success: true, text, data };
}

async function fail(callback: HandlerCallback | undefined, action: string, e: unknown): Promise<ActionResult> {
  const msg = `I could not read LiquidVision.app right now (${(e as Error)?.message ?? e}).`;
  if (callback) await callback({ text: msg, actions: [action], source: "liquidvision" });
  return { success: false, text: msg, error: e as Error };
}

// ---------------------------------------------------------------- summaries (exported for tests)

export function summarizeBrief(b: any): string {
  const sym = String(b.symbol || "").replace(/USDT$/, "");
  const a = b.asset || {};
  // windows_usd is MARKET-WIDE; this_symbol_24h is the coin itself
  const mkt = (b.liquidations?.windows_usd || {})["24h"] || {};
  const own = b.liquidations?.this_symbol_24h || {};
  const lines = [
    `${sym} ${a.price != null ? `$${Number(a.price).toLocaleString("en-US")}` : ""} (${pct(a.change_24h_pct, 2)} 24h), open interest ${usd(a.open_interest_usd)}.`,
    `${sym} liquidated 24h: ${usd(own.total)} (longs ${usd(own.long)}, shorts ${usd(own.short)}); whole market ${usd(mkt.total)}.`,
  ];
  const venues = (b.open_interest_by_venue || b.oi_by_venue || []).slice?.(0, 3) || [];
  if (venues.length) lines.push(`Largest OI venues: ${venues.map((v: any) => `${v.exchange} ${usd(v.oi_usd)}`).join(", ")}.`);
  lines.push("Source: LiquidVision.app (exchange-exact, 13 venues; Binance/Bitget liquidation feeds are throttled, so totals are a floor).");
  return lines.join(" ");
}

export function summarizeRegime(r: any, symbol: string | null): string {
  const s = (r.summary || []).filter((x: any) => x.coins > 0)
    .map((x: any) => `${x.label}: ${x.coins} coins (${usd(x.oi_delta_usd)} OI)`).join("; ");
  let line = `Positioning over the last ${r.minutes} min across ${r.symbols} coins — ${s}.`;
  if (symbol) {
    const row = (r.rows || []).find((x: any) => x.symbol === symbol);
    if (row) line += ` ${symbol.replace(/USDT$/, "")}: ${row.regime_label || row.regime} (price ${pct(row.price_change_pct ?? row.price_chg_pct, 2)}, OI ${pct(row.oi_change_pct ?? row.oi_chg_pct, 2)}, ${usd(row.oi_delta_usd)}).`;
  }
  return line + " New longs/new shorts = fresh positions; short covering/long flush = positions closing. Source: LiquidVision.app.";
}

export function summarizeCascades(c: any, symbol: string | null): string {
  let ev = c.events || c.cascades || [];
  if (symbol) ev = ev.filter((e: any) => e.symbol === symbol);
  const top = ev.slice(0, 3).map((e: any) =>
    `${String(e.symbol).replace(/USDT$/, "")} ${e.side ?? ""} ${usd(e.usd ?? e.total_usd)} over ${e.minutes ?? "?"} min (${Number(e.x_normal ?? 0).toFixed(0)}x its normal minute, price impact ${pct(e.impact_pct, 2)}, reversion ${pct(e.reversion_pct, 2)})`);
  const mw = (c.market_wide || []).length;
  return `${c.events_total ?? ev.length} liquidation cascades in the last ${c.hours}h${mw ? `, ${mw} market-wide` : ""}. ` +
    (top.length ? `Largest: ${top.join("; ")}. ` : "") +
    "Reversion after the cascade tells a flush that marked the low from one that started the move. Source: LiquidVision.app.";
}

export function summarizeLiqmap(m: any): string {
  const p = Number(m.current_price);
  const bins: number[] = m.bins || [];
  const longs: number[] = m.long || m.long_usd || [];
  const shorts: number[] = m.short || m.short_usd || [];
  let below = { px: 0, usd: 0 }, above = { px: 0, usd: 0 };
  bins.forEach((px, i) => {
    const l = longs[i] || 0, s = shorts[i] || 0;
    if (px < p && l > below.usd) below = { px, usd: l };
    if (px > p && s > above.usd) above = { px, usd: s };
  });
  const sym = String(m.symbol || "").replace(/USDT$/, "");
  return `${sym} measured Hyperliquid positions (real accounts, exchange-reported liquidation prices): ` +
    `densest long liquidations below at ~$${Math.round(below.px).toLocaleString("en-US")} (${usd(below.usd)}), ` +
    `densest short liquidations above at ~$${Math.round(above.px).toLocaleString("en-US")} (${usd(above.usd)}); price $${p.toLocaleString("en-US")}. ` +
    "Measured, not modeled; large accounts only. Source: LiquidVision.app.";
}

export function summarizeDispersion(d: any, symbol: string | null): string {
  let rows = d.rows || [];
  if (symbol) rows = rows.filter((r: any) => r.symbol === symbol);
  const top = rows.slice(0, 5).map((r: any) =>
    `${String(r.symbol).replace(/USDT$/, "")}: long on ${r.long_venue} (${pct(r.long_apr)}), short on ${r.short_venue} (${pct(r.short_apr)}), spread ${r.spread_apr?.toFixed(1)}% APR`);
  return (top.length ? `Funding disagreement across venues — ${top.join("; ")}. ` : `No funding dispersion row${symbol ? ` for ${symbol}` : ""}. `) +
    "Each leg annualized with its own settlement cycle; gross of fees and basis. Market data, not financial advice. Source: LiquidVision.app.";
}

export function summarizeTokenized(t: any): string {
  const rows = (t.rows || []).slice(0, 5).map((r: any) =>
    `${r.id} ${usd(r.oi_usd)} OI${r.change_24h_pct != null ? ` (${pct(r.change_24h_pct, 2)})` : ""}`);
  return `Tokenized stocks/indices/commodities/FX as perps on DEXs: ${usd(t.total_oi_usd)} open interest, ${usd(t.total_volume_24h_usd)} traded 24h across ${t.underlyings} underlyings. Largest: ${rows.join(", ")}. Source: LiquidVision.app.`;
}

// ---------------------------------------------------------------- actions

function action(spec: {
  name: string; similes: string[]; description: string; words: RegExp;
  run: (runtime: IAgentRuntime, symbol: string | null) => Promise<{ text: string; data: any }>;
  example: [string, string];
}): Action {
  return {
    name: spec.name,
    similes: spec.similes,
    description: spec.description,
    validate: async (_runtime: IAgentRuntime, message: Memory) => mentions(message, spec.words),
    handler: async (runtime: IAgentRuntime, message: Memory, _state?: State, _options?: any, callback?: HandlerCallback) => {
      try {
        const { text, data } = await spec.run(runtime, extractSymbol(textOf(message)));
        return reply(callback, text, spec.name, data);
      } catch (e) {
        return fail(callback, spec.name, e);
      }
    },
    examples: [[
      { name: "{{user1}}", content: { text: spec.example[0] } },
      { name: "{{agent}}", content: { text: spec.example[1], actions: [spec.name] } },
    ]],
  } as Action;
}

export const briefAction = action({
  name: "LIQUIDVISION_DERIVATIVES_BRIEF",
  similes: ["DERIVATIVES_BRIEF", "MARKET_BRIEF", "LEVERAGE_SNAPSHOT"],
  description: "One-coin derivatives snapshot from LiquidVision.app: price, open interest, liquidations by side and window, largest venues.",
  words: /(brief|snapshot|derivatives|open interest|\boi\b|leverage|liquidat|what.*(happening|going on))/,
  run: async (rt, sym) => { const b = await lv(rt, `/brief/${sym ?? "BTCUSDT"}`); return { text: summarizeBrief(b), data: b }; },
  example: ["what's the derivatives picture on $BTC?", "BTC $81,300 (-0.9% 24h), open interest $27.6B. Liquidated 24h: $201.6M (longs $107.4M, shorts $94.2M)…"],
});

export const regimeAction = action({
  name: "LIQUIDVISION_POSITIONING_REGIME",
  similes: ["POSITIONING_REGIME", "NEW_LONGS_OR_SHORT_COVERING", "OI_REGIME"],
  description: "Is a move new money or positions closing? Price change crossed with open-interest change per coin (new longs, short covering, new shorts, long flush).",
  words: /(regime|short covering|new longs|new shorts|long flush|positioning|new money|who is driving)/,
  run: async (rt, sym) => { const r = await lv(rt, "/oi/regime", { minutes: 240 }); return { text: summarizeRegime(r, sym), data: r }; },
  example: ["is this ETH rally new longs or short covering?", "Positioning over the last 240 min across 107 coins — New longs: 3 coins…"],
});

export const cascadesAction = action({
  name: "LIQUIDVISION_LIQUIDATION_CASCADES",
  similes: ["LIQUIDATION_CASCADES", "LIQUIDATION_EVENTS", "FLUSH"],
  description: "Liquidation cascades over the last 24h as events: size, duration, price move and what price did in the hour after.",
  words: /(cascade|flush|got liquidated|liquidation event|wipe|rekt)/,
  run: async (rt, sym) => { const c = await lv(rt, "/liquidations/cascades", { hours: 24, limit: 50 }); return { text: summarizeCascades(c, sym), data: c }; },
  example: ["were there any big liquidation cascades today?", "436 liquidation cascades in the last 24h, 6 market-wide. Largest: ETH long $14.2M over 3 min…"],
});

export const liqmapAction = action({
  name: "LIQUIDVISION_LIQUIDATION_MAP",
  similes: ["LIQUIDATION_MAP", "LIQUIDATION_LEVELS", "WHERE_ARE_LIQUIDATIONS"],
  description: "Where leverage would break: measured Hyperliquid positions binned by exchange-reported liquidation price, densest levels below and above.",
  words: /(liquidation (map|level|cluster|zone)|where.*liquidat|liq map|leverage (sits|levels))/,
  run: async (rt, sym) => { const m = await lv(rt, `/liqmap/hl/${sym ?? "BTCUSDT"}`, { range: "1d" }); return { text: summarizeLiqmap(m), data: m }; },
  example: ["where are the BTC liquidation levels?", "BTC measured Hyperliquid positions: densest long liquidations below at ~$78,500 ($41.2M)…"],
});

export const fundingAction = action({
  name: "LIQUIDVISION_FUNDING_DISPERSION",
  similes: ["FUNDING_DISPERSION", "FUNDING_CARRY", "FUNDING_ARBITRAGE", "CHEAPEST_FUNDING"],
  description: "Where the same coin pays very different funding across venues: the cheapest venue to be long and the richest to be short, each leg on its own settlement cycle.",
  words: /(funding|carry|basis trade|funding arb)/,
  run: async (rt, sym) => { const d = await lv(rt, "/funding/dispersion"); return { text: summarizeDispersion(d, sym), data: d }; },
  example: ["where is funding cheapest for SOL?", "Funding disagreement across venues — SOL: long on bybit (+2.1%), short on kraken (+14.0%)…"],
});

export const tokenizedAction = action({
  name: "LIQUIDVISION_TOKENIZED_STOCKS",
  similes: ["TOKENIZED_STOCKS", "STOCK_PERPS", "RWA_PERPS"],
  description: "Tokenized stocks, indices, commodities and FX traded as perps on DEXs (Lighter, Hyperliquid builder markets, Ostium, gTrade): open interest, volume, 24h change.",
  words: /(tokeni[sz]ed|stock perp|equity perp|rwa|s&p|nasdaq|nvda|tsla|gold perp)/,
  run: async (rt) => { const t = await lv(rt, "/stocks/tokenized"); return { text: summarizeTokenized(t), data: t }; },
  example: ["how big is the tokenized stocks perp market?", "Tokenized stocks/indices/commodities/FX as perps on DEXs: $3.9B open interest…"],
});

// ---------------------------------------------------------------- provider

export const derivativesProvider: Provider = {
  name: "LIQUIDVISION_DERIVATIVES",
  description: "Derivatives context (open interest, liquidations) for a coin mentioned in the message, from LiquidVision.app.",
  dynamic: true,
  get: async (runtime: IAgentRuntime, message: Memory, _state: State): Promise<ProviderResult> => {
    const sym = extractSymbol(textOf(message));
    if (!sym) return { text: "" };
    try {
      const b = await lv(runtime, `/brief/${sym}`);
      return { text: `# Derivatives context\n${summarizeBrief(b)}`, values: { liquidvisionSymbol: sym }, data: { brief: b } };
    } catch {
      return { text: "" };
    }
  },
};

export const liquidvisionPlugin: Plugin = {
  name: "liquidvision",
  description: "Exchange-exact crypto derivatives data from LiquidVision.app: open interest, liquidations, cascades, positioning regime, measured liquidation maps, funding dispersion, tokenized stocks on DEXs. Read-only, no key needed.",
  actions: [briefAction, regimeAction, cascadesAction, liqmapAction, fundingAction, tokenizedAction],
  providers: [derivativesProvider],
};

export default liquidvisionPlugin;
