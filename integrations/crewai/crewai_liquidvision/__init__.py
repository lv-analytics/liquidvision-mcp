"""
crewai-liquidvision: crypto derivatives tools for CrewAI agents.

    from crewai_liquidvision import liquidvision_tools
    analyst = Agent(role="Derivatives analyst", tools=liquidvision_tools(), ...)

Data from LiquidVision.app: open interest, funding and liquidations on 13
venues, liquidation cascades, positioning regime, measured Hyperliquid
liquidation maps, funding dispersion, tokenized stocks on DEXs. Read-only,
no key needed.
"""
from __future__ import annotations

from typing import Any, ClassVar, List, Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from ._api import TOOL_SPECS, LiquidVisionAPI, __version__, norm_symbol, run

__all__ = [
    "liquidvision_tools", "LiquidVisionAPI", "norm_symbol", "__version__",
    "DerivativesBriefTool", "PositioningRegimeTool", "LiquidationCascadesTool",
    "LiquidationMapTool", "FundingDispersionTool", "TokenizedStocksTool",
]
_SPEC = {m: (n, d) for n, m, d in TOOL_SPECS}


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


class _LVTool(BaseTool):
    lv_method: ClassVar[str] = ""
    _api: LiquidVisionAPI = PrivateAttr(default=None)

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, **kw: Any):
        name, description = _SPEC[self.lv_method]
        super().__init__(name=name, description=description, **kw)
        self._api = LiquidVisionAPI(api_key=api_key, base_url=base_url)

    def _run(self, **kwargs: Any) -> str:
        return run(self._api, self.lv_method, **kwargs)


class DerivativesBriefTool(_LVTool):
    lv_method: ClassVar[str] = "brief"
    args_schema: Type[BaseModel] = _Symbol


class PositioningRegimeTool(_LVTool):
    lv_method: ClassVar[str] = "positioning_regime"
    args_schema: Type[BaseModel] = _Regime


class LiquidationCascadesTool(_LVTool):
    lv_method: ClassVar[str] = "liquidation_cascades"
    args_schema: Type[BaseModel] = _Cascades


class LiquidationMapTool(_LVTool):
    lv_method: ClassVar[str] = "liquidation_map"
    args_schema: Type[BaseModel] = _Symbol


class FundingDispersionTool(_LVTool):
    lv_method: ClassVar[str] = "funding_dispersion"
    args_schema: Type[BaseModel] = _OptSymbol


class TokenizedStocksTool(_LVTool):
    lv_method: ClassVar[str] = "tokenized_stocks"
    args_schema: Type[BaseModel] = _Tokenized


def liquidvision_tools(api_key: Optional[str] = None, base_url: Optional[str] = None) -> List[BaseTool]:
    """All six tools. api_key is optional (raises the rate limit from 60 to 600/1,200 a minute)."""
    return [cls(api_key=api_key, base_url=base_url) for cls in (
        DerivativesBriefTool, PositioningRegimeTool, LiquidationCascadesTool,
        LiquidationMapTool, FundingDispersionTool, TokenizedStocksTool)]
