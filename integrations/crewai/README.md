# crewai-liquidvision

Crypto derivatives tools for CrewAI agents, from [LiquidVision.app](https://liquidvision.app).
Read-only, no key needed.

```bash
pip install crewai-liquidvision
```

```python
from crewai import Agent, Crew, Task
from crewai_liquidvision import liquidvision_tools

analyst = Agent(
    role="Crypto derivatives analyst",
    goal="Tell whether leverage is building or unwinding and where it would break",
    backstory="Reads open interest, funding and liquidations across 13 exchanges.",
    tools=liquidvision_tools(),
)
task = Task(description="Is the current ETH move new longs or short covering? Where are the nearest liquidation levels?",
            expected_output="Three short paragraphs with numbers", agent=analyst)
print(Crew(agents=[analyst], tasks=[task]).kickoff())
```

| Tool class | Answers |
|---|---|
| `DerivativesBriefTool` | One coin: price, open interest by venue, liquidations by side, funding per exchange, nearest liquidation zones |
| `PositioningRegimeTool` | New longs, short covering, new shorts or long flush: price change crossed with OI change |
| `LiquidationCascadesTool` | Liquidation cascades as events: size, multiple of the coin's normal minute, price impact, reversion |
| `LiquidationMapTool` | Measured Hyperliquid liquidation levels below and above price (exchange-reported, not modeled) |
| `FundingDispersionTool` | Cheapest venue to be long, richest to be short, across 13 exchanges |
| `TokenizedStocksTool` | Tokenized stocks, indices, commodities and FX perps on DEXs |

Each tool returns compact JSON. Errors come back as `{"error": ...}` so the crew keeps going.

**Limits.** 60 requests a minute per IP without a key. Set `LIQUIDVISION_API_KEY` (or
`liquidvision_tools(api_key=...)`) with a Pro/Bot key for 600/1,200 a minute.

**More.** Raw rows, history and Parquet: the [`liquidvision`](https://pypi.org/project/liquidvision/) client.
MCP: `https://liquidvision.app/mcp/lite`. Docs: https://liquidvision.app/llms.txt

Data, not financial advice.
