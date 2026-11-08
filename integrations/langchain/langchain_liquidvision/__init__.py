"""
langchain-liquidvision: crypto derivatives tools for LangChain / LangGraph agents.

    from langchain_liquidvision import LiquidVisionToolkit
    tools = LiquidVisionToolkit().get_tools()     # nine read-only tools, no key needed

Data from LiquidVision.app: open interest, funding and liquidations on 13
venues, liquidation cascades, positioning regime, measured Hyperliquid
liquidation maps, funding dispersion, tokenized stocks on DEXs.
"""
from __future__ import annotations

from typing import List, Optional

from langchain_core.tools import BaseTool, BaseToolkit, StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from ._api import TOOL_SPECS, LiquidVisionAPI, __version__, norm_symbol, run

__all__ = ["LiquidVisionToolkit", "LiquidVisionAPI", "get_tools", "norm_symbol", "__version__"]


class _Symbol(BaseModel):
    symbol: str = Field("BTCUSDT", description="Coin, e.g. BTC, ETH, SOLUSDT")


class _OptSymbol(BaseModel):
    symbol: Optional[str] = Field(None, description="Coin, e.g. BTC or ETHUSDT; omit for the whole market")


class _Regime(_OptSymbol):
    minutes: int = Field(240, description="Look-back window in minutes (15-1440)")


class _Cascades(_OptSymbol):
    hours: int = Field(24, description="Look-back window in hours (1-72)")


class _Tokenized(BaseModel):
    limit: int = Field(15, description="How many of the largest markets to return")


class _Ask(_Symbol):
    question: str = Field(..., description="Plain-words question, e.g. 'why did ETH drop', 'is SOL funding crowded'")


class _Position(_Symbol):
    side: str = Field(..., description="long | short")
    entry: float = Field(..., description="Entry price in USDT")
    leverage: float = Field(..., description="Leverage, e.g. 20")
    notional_usd: float = Field(10_000, description="Position size in USD")
    venue: Optional[str] = Field(None, description="Venue id (binance, bybit, okx, bitget, gate, kucoin, kraken, "
                                                   "hyperliquid, htx, mexc, bingx, aster); omit for all venues")


class _Rule(_Symbol):
    rules: str = Field(..., description="Up to 3 rules, e.g. 'funding_apr_pct>40,oi_chg_24h_pct>5'")


_SCHEMAS = {
    "brief": _Symbol, "positioning_regime": _Regime, "liquidation_cascades": _Cascades,
    "liquidation_map": _Symbol, "funding_dispersion": _OptSymbol, "tokenized_stocks": _Tokenized,
    "ask": _Ask, "check_position": _Position, "test_rule": _Rule,
}


def get_tools(api_key: Optional[str] = None, base_url: Optional[str] = None) -> List[BaseTool]:
    api = LiquidVisionAPI(api_key=api_key, base_url=base_url)
    tools: List[BaseTool] = []
    for name, method, description in TOOL_SPECS:
        tools.append(StructuredTool.from_function(
            func=lambda _m=method, **kw: run(api, _m, **kw),
            name=name, description=description, args_schema=_SCHEMAS[method]))
    return tools


class LiquidVisionToolkit(BaseToolkit):
    """Nine read-only LiquidVision.app tools (ask, check_position, test_rule added in 0.2.0). api_key is optional (raises the rate limit)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    def get_tools(self) -> List[BaseTool]:
        return get_tools(self.api_key, self.base_url)
