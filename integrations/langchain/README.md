# langchain-liquidvision

Crypto derivatives tools for LangChain and LangGraph agents, from [LiquidVision.app](https://liquidvision.app).
Read-only, no key needed.

```bash
pip install langchain-liquidvision
```

```python
from langchain_liquidvision import LiquidVisionToolkit
from langgraph.prebuilt import create_react_agent

tools = LiquidVisionToolkit().get_tools()
agent = create_react_agent("anthropic:claude-sonnet-5-5", tools)
agent.invoke({"messages": [("user", "Is the ETH move new longs or short covering? Where are the liquidation levels?")]})
```

| Tool | Answers |
|---|---|
| `liquidvision_derivatives_brief` | One coin: price, open interest by venue, liquidations by side, funding per exchange, nearest liquidation zones |
| `liquidvision_positioning_regime` | New longs, short covering, new shorts or long flush: price change crossed with OI change |
| `liquidvision_liquidation_cascades` | Liquidation cascades as events: size, multiple of the coin's normal minute, price impact, reversion |
| `liquidvision_liquidation_map` | Measured Hyperliquid liquidation levels below and above price (exchange-reported, not modeled) |
| `liquidvision_funding_dispersion` | Cheapest venue to be long, richest to be short, across 13 exchanges |
| `liquidvision_tokenized_stocks` | Tokenized stocks, indices, commodities and FX perps on DEXs |

Each tool returns compact JSON. Errors come back as `{"error": ...}` so the agent keeps going.

**Limits.** 60 requests a minute per IP without a key. Set `LIQUIDVISION_API_KEY` (or
`LiquidVisionToolkit(api_key=...)`) with a Pro/Bot key for 600/1,200 a minute.

**More.** Raw rows, history and Parquet: the [`liquidvision`](https://pypi.org/project/liquidvision/) client.
MCP: `https://liquidvision.app/mcp/lite`. Docs: https://liquidvision.app/llms.txt

Data, not financial advice.
