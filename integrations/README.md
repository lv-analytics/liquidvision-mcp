# Integrations

Drop-in pieces for agent frameworks and trading bots. All of them use the free LiquidVision.app
endpoints (no key, 60 requests a minute per IP) and fail open: if the feed is unreachable the
host keeps working as before.

| Framework | What it adds | Path |
|---|---|---|
| **ElizaOS** | 6 actions + a provider: derivatives brief, positioning regime, liquidation cascades, measured Hyperliquid liquidation map, funding dispersion, tokenized stocks | [`elizaos/plugin-liquidvision`](elizaos/plugin-liquidvision) |
| **Freqtrade** | `LiquidVisionGuard` mixin: refuses entries while a liquidation cascade runs on the pair or while longs are being flushed (`long_flush` regime) | [`freqtrade/LiquidVisionGuard.py`](freqtrade/LiquidVisionGuard.py) |
| **Hummingbot** | Script: market-makes one perp and pulls its quotes for N minutes after a cascade on that coin | [`hummingbot/liquidvision_cascade_guard.py`](hummingbot/liquidvision_cascade_guard.py) |
| **LangChain / LangGraph** | `pip install langchain-liquidvision`: a toolkit with six read-only tools (brief, positioning regime, cascades, measured liquidation map, funding dispersion, tokenized stocks). Listed in the [LangChain integrations docs](https://docs.langchain.com/oss/python/integrations/tools) | [`langchain`](langchain) |
| **CrewAI** | `pip install crewai-liquidvision`: the same six tools as CrewAI `BaseTool`s | [`crewai`](crewai) |
| **Passivbot** | Writes `ignored_coins` for coins with expensive funding or a running cascade | [`../examples/passivbot_funding_filter.py`](../examples/passivbot_funding_filter.py) |
| **Claude Code** | Skill: which tool answers which question, how to read measured vs modeled data | [`../skills/liquidvision`](../skills/liquidvision) |
| **Any MCP client** | `https://liquidvision.app/mcp/lite` (13 conclusion tools), `/mcp` (42) | — |

## Freqtrade

```python
# user_data/strategies/MyStrategy.py
from LiquidVisionGuard import LiquidVisionGuard   # copy the file next to your strategy

class MyStrategy(LiquidVisionGuard, IStrategy):
    lv_cascade_minutes = 30
    ...
```
Check it standalone: `python LiquidVisionGuard.py BTC/USDT:USDT ETH/USDT:USDT`.

## Hummingbot

Copy `liquidvision_cascade_guard.py` into `hummingbot/scripts/`, set `exchange`, `trading_pair`,
`order_amount` at the top, then `start --script liquidvision_cascade_guard.py`. `status` shows
whether it is quoting or paused.
