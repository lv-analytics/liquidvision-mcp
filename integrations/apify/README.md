# Crypto Derivatives Answers (Apify Actor)

One answer per run, computed by [LiquidVision.app](https://liquidvision.app) from what 13 exchanges report:
open interest, funding, liquidations and measured positions. No exchange keys, no wallet, no scraping.

| Mode | What you get | Suggested price per result |
|---|---|---|
| `position_check` | Liquidation price of your position on 12 exchanges from their real maintenance-margin brackets, distance from the mark, leverage sitting between the mark and that price, funding cost per day, how often price moved that far in the archive | $0.05 |
| `liquidation_map` | Where modeled leverage sits around price on Binance + Bybit + OKX, with the share of open interest it explains | $0.02 |
| `funding_carry` | Venue pairs for a funding carry, chosen on the prior week and measured on the week after (out of sample) | $0.05 |
| `rule_test` | When was a condition true before on one coin, and what did price do over the next 24 h and 72 h, against the base rate | $0.20 |
| `rule_scan` | The same rule on up to 100 coins: per coin and pooled outcomes, and where it is true right now | $2.00 |
| `market_brief` | Positioning of one coin in plain statements with the numbers behind them | $0.01 |

Every figure is a measurement or a frequency from an archive that starts in July 2026. Nothing here is a
forecast or financial advice; the answers say how many independent observations stand behind each number.

## Input examples

```json
{ "mode": "position_check", "symbol": "BTC", "side": "long", "entry": "74000", "leverage": 20, "notionalUsd": 50000 }
```

```json
{ "mode": "rule_scan", "rules": "liq_24h_usd>5000000,price_chg_24h_pct<-5", "coins": 100 }
```

Rule metrics: `funding_apr_pct`, `oi_chg_1h_pct`, `oi_chg_24h_pct`, `price_chg_1h_pct`, `price_chg_24h_pct`,
`liq_1h_usd`, `liq_24h_usd`, `long_pct` (BTC, ETH, SOL only). Up to three conditions, joined by commas.

## Output

One dataset item: `mode`, `symbol`, a one-line `summary`, the full `answer` (the API's JSON, documented at
<https://liquidvision.app/llms.txt>), `source`.

## For the publisher

1. Create the Actor from this folder (`apify push`, or link the GitHub repository with this folder as the root).
2. Settings -> Environment variables: `LV_API_KEY` = a LiquidVision Bot key, marked **Secret**. Without it the
   three priced modes answer HTTP 402 and the run fails without charging.
3. Monetization -> Pay per event. Events (names are fixed in `src/main.py`): `position-check`, `liquidation-map`,
   `funding-carry`, `rule-test`, `rule-scan`, `market-brief`, with the prices above or your own.
4. The event is charged after the answer was fetched; a failed run charges nothing.
