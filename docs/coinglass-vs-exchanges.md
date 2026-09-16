# We checked Coinglass against the exchanges' own APIs. Two venues don't match.

*Draft for Show HN / r/algotrading / X. Every number below can be reproduced
with the curl commands at the end; dates are the two days we ran the check.*

Coinglass is the default source for crypto derivatives data, and for most of
its numbers that trust is earned. We build a competing (much smaller) data
service, so we did the obvious thing before claiming anything: pulled the
same minute's figures from the exchanges' public APIs and from Coinglass's
BTC page, twice, a month apart.

## Where Coinglass matches the exchanges

BTC open interest per venue, same minute, 16 Sep 2026:

| Venue | Exchange API | Coinglass | Difference |
|---|---|---|---|
| Binance | $8.138B | $8.13B | 0.1% |
| Bybit | $4.346B | $4.34B | 0.1% |
| OKX | $2.139B | $2.14B | 0.05% |

On 14 Aug the same check covered seven venues (add MEXC, Hyperliquid, KuCoin,
BingX) and all seven were within 0.4%. That is the baseline: Coinglass is
generally reading the same endpoints we are.

## Where it doesn't

**Gate.** Gate's contract endpoint reports BTC_USDT `position_size` = 335,169,045
in `quanto_multiplier` 0.0001 units = 33,517 BTC ≈ **$2.54B**. Coinglass shows
**$5.08B** — exactly 2×. It was 2× a month earlier too ($2.245B vs $4.49B).
The only reading we can find that produces a 2× is summing both sides of every
position, which is not how open interest is defined anywhere else on the page.

**Bitget.** Bitget's ticker reports `holdingAmount` = 33,564 BTC, which at the
mark price is **$2.55B**; the dedicated open-interest endpoint returns the
same 33,563.6. Coinglass shows **$1.53B** — a 40% haircut, also stable across
the month ($2.595B vs $1.56B in August). There may be a reason — a belief that
Bitget's figure double-counts, say — but it is not disclosed, and the page
presents the number as if it came from the exchange.

Coinglass's global open-interest total is roughly twice ours. Most of that
gap is scope, not error: they include CME, coin-margined contracts, options
and a longer venue list. We only note it so nobody reads "twice as much
data" as "twice as accurate".

## Liquidations: the part nobody labels

Binance's public liquidation stream (`!forceOrder@arr`) still exists in the
docs and still accepts a subscription — `LIST_SUBSCRIPTIONS` echoes it back.
It just never sends anything. We held a subscription open for ten minutes,
market-wide and per-symbol across twenty busy perps, from two different
networks, while an OKX control subscription delivered 258 events in the same
window. Zero. Bitget's `liquidation` channel acknowledges the subscription for
`default` and for specific symbols alike, and is equally silent.

Coinglass shows Binance liquidations anyway — $57M of BTC longs in the 24h we
looked at — and nothing on the page says they are estimated. They must be,
because the exchange does not publish them. We chose the other option: the
Binance and Bitget rows in our liquidation feed are empty, and the page says
why. Our 24h liquidation total is therefore smaller than the market's; it is
also a number rather than a guess.

## What we think this means

Not that Coinglass is bad. That a derivatives aggregator has to make method
calls — whether to trust an exchange's OI, how to treat a venue that stopped
publishing — and that those calls should be visible on the page. Ours are:
open interest and funding are served exactly as each exchange reports them,
funding APR uses each contract's real settlement cycle, liquidation coverage
is stated per venue, and the liquidation maps are labeled as the models they
are.

## Reproduce it

```bash
# Gate BTC open interest (one side, in BTC): position_size * quanto_multiplier
curl -s https://api.gateio.ws/api/v4/futures/usdt/contracts/BTC_USDT | grep -oE '"(position_size|quanto_multiplier|mark_price)": *"?[0-9.]+'

# Bitget BTC open interest, two endpoints that agree with each other
curl -s "https://api.bitget.com/api/v2/mix/market/ticker?symbol=BTCUSDT&productType=usdt-futures" | grep -oE '"(holdingAmount|markPrice)":"[^"]*"'
curl -s "https://api.bitget.com/api/v2/mix/market/open-interest?symbol=BTCUSDT&productType=usdt-futures"

# Our per-venue figures for the same symbol
curl -s https://liquidvision.app/api/v1/oiboard/BTCUSDT
```

The Binance liquidation test is a 40-line Python script (websockets,
`!forceOrder@arr` vs OKX `liquidation-orders`, ten minutes); we'll put it in
the repo with the post.

---
*LiquidVision — crypto derivatives data for bots and AI agents.
https://liquidvision.app · MCP: https://liquidvision.app/mcp · llms.txt for
agents. Free API key, no card.*
