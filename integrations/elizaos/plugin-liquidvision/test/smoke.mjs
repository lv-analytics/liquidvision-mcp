// Smoke test against the live API: every action runs with a minimal fake
// runtime and returns success with a non-empty text. No key needed.
import plugin, { extractSymbol } from "../dist/index.js";

const runtime = { getSetting: (k) => process.env[k] };
const msg = (text) => ({ content: { text } });

const asserts = [
  ["$btc", "BTCUSDT"], ["what about ethereum funding", "ETHUSDT"], ["SOLUSDT map", "SOLUSDT"], ["hello", null],
];
for (const [t, want] of asserts) {
  const got = extractSymbol(t);
  if (got !== want) { console.error("extractSymbol", t, got, "!=", want); process.exit(1); }
}

const prompts = {
  LIQUIDVISION_DERIVATIVES_BRIEF: "what's the derivatives brief on $BTC?",
  LIQUIDVISION_POSITIONING_REGIME: "is ETH new longs or short covering?",
  LIQUIDVISION_LIQUIDATION_CASCADES: "any liquidation cascades today?",
  LIQUIDVISION_LIQUIDATION_MAP: "where are the BTC liquidation levels?",
  LIQUIDVISION_FUNDING_DISPERSION: "where is funding cheapest?",
  LIQUIDVISION_TOKENIZED_STOCKS: "how big are tokenized stock perps?",
};

let failed = 0;
for (const a of plugin.actions) {
  const m = msg(prompts[a.name]);
  const valid = await a.validate(runtime, m);
  let said = "";
  const res = await a.handler(runtime, m, undefined, undefined, async (c) => { said = c.text; return []; });
  const ok = valid && res?.success && said.length > 40;
  if (!ok) failed++;
  console.log(ok ? "ok  " : "FAIL", a.name, "|", said.slice(0, 140));
}
const p = await plugin.providers[0].get(runtime, msg("thoughts on $SOL?"), {});
console.log(p.text ? "ok  " : "FAIL", "provider |", (p.text || "").slice(0, 120));
if (!p.text) failed++;
process.exit(failed ? 1 : 0);
