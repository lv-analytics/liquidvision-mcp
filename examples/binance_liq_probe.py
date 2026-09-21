"""Binance USDT-M liquidation stream: silent on fstream, alive on dstream.

    pip install websockets
    python binance_liq_probe.py [seconds]

Subscribes to the same stream name on both hosts, with OKX as an activity
control, and counts what arrives. No account or API key needed.
"""
import asyncio
import json
import sys
import time

import websockets

SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 120


async def binance(host: str) -> tuple[str, int, str]:
    n, first = 0, ""
    async with websockets.connect(f"wss://{host}/ws/!forceOrder@arr", open_timeout=15) as ws:
        t = time.time()
        while time.time() - t < SECONDS:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            except asyncio.TimeoutError:
                continue
            if msg.get("e") == "forceOrder":
                n += 1
                first = first or msg["o"]["s"]
    return host, n, first


async def okx() -> tuple[str, int, str]:
    n, first = 0, ""
    async with websockets.connect("wss://ws.okx.com:8443/ws/v5/public", open_timeout=15) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": [
            {"channel": "liquidation-orders", "instType": "SWAP"}]}))
        t = time.time()
        while time.time() - t < SECONDS:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            except asyncio.TimeoutError:
                continue
            for d in msg.get("data", []):
                n += len(d.get("details", []))
                first = first or d.get("instId", "")
    return "ws.okx.com (control)", n, first


async def main() -> None:
    results = await asyncio.gather(
        binance("fstream.binance.com"), binance("dstream.binance.com"), okx(),
        return_exceptions=True)
    print(f"liquidation events in {SECONDS}s:")
    for r in results:
        if isinstance(r, Exception):
            print("  error:", r)
        else:
            print(f"  {r[0]:28s} {r[1]:5d}   first symbol: {r[2] or '-'}")


asyncio.run(main())
