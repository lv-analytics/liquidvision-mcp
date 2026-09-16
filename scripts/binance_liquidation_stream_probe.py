"""Probe 2 (10 min): where did Binance/Bitget liquidation events go?

binance_arr:  !forceOrder@arr again, longer window
binance_sym:  per-symbol <s>@forceOrder for 20 busy perps (combined URL)
bitget:       liquidation channel with SPECIFIC instIds alongside default
okx:          control — proves the market produced liquidations in-window
"""
import asyncio
import collections
import json

import websockets

SECS = 600
out = {}

BUSY = ["btcusdt", "ethusdt", "solusdt", "dogeusdt", "xrpusdt", "1000pepeusdt",
        "suiusdt", "adausdt", "ltcusdt", "bnbusdt", "linkusdt", "avaxusdt",
        "wldusdt", "opusdt", "aptusdt", "arbusdt", "filusdt", "nearusdt",
        "atomusdt", "injusdt"]


async def binance_arr():
    counts = collections.Counter()
    try:
        async with websockets.connect(
            "wss://fstream.binance.com/ws/!forceOrder@arr", max_size=2**23
        ) as ws:
            async def reader():
                async for raw in ws:
                    counts[json.loads(raw).get("e") or "other"] += 1
            try:
                await asyncio.wait_for(reader(), timeout=SECS)
            except asyncio.TimeoutError:
                pass
    except Exception as e:
        out["binance_arr_error"] = repr(e)
    out["binance_arr"] = dict(counts)


async def binance_sym():
    counts = collections.Counter()
    frames = []
    url = ("wss://fstream.binance.com/stream?streams="
           + "/".join(f"{s}@forceOrder" for s in BUSY))
    try:
        async with websockets.connect(url, max_size=2**23) as ws:
            async def reader():
                async for raw in ws:
                    if len(frames) < 2:
                        frames.append(raw[:200])
                    m = json.loads(raw)
                    counts[(m.get("data") or {}).get("e") or "other"] += 1
            try:
                await asyncio.wait_for(reader(), timeout=SECS)
            except asyncio.TimeoutError:
                pass
    except Exception as e:
        out["binance_sym_error"] = repr(e)
    out["binance_sym"] = dict(counts)
    out["binance_sym_frames"] = frames


async def bitget():
    counts = collections.Counter()
    frames = []
    args = [{"instType": "USDT-FUTURES", "channel": "liquidation",
             "instId": i} for i in
            ("default", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")]
    try:
        async with websockets.connect("wss://ws.bitget.com/v2/ws/public") as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": args}))

            async def pinger():
                while True:
                    await asyncio.sleep(25)
                    await ws.send("ping")

            p = asyncio.ensure_future(pinger())

            async def reader():
                async for raw in ws:
                    if raw == "pong":
                        continue
                    if len(frames) < 8:
                        frames.append(raw[:200])
                    m = json.loads(raw)
                    counts[m.get("event") or m.get("action") or "data"] += 1

            try:
                await asyncio.wait_for(reader(), timeout=SECS)
            except asyncio.TimeoutError:
                pass
            p.cancel()
    except Exception as e:
        out["bitget_error"] = repr(e)
    out["bitget"] = dict(counts)
    out["bitget_frames"] = frames


async def okx():
    counts = collections.Counter()
    try:
        async with websockets.connect(
            "wss://ws.okx.com:8443/ws/v5/public", ping_interval=None
        ) as ws:
            await ws.send(json.dumps({
                "op": "subscribe",
                "args": [{"channel": "liquidation-orders", "instType": "SWAP"}],
            }))

            async def pinger():
                while True:
                    await asyncio.sleep(20)
                    await ws.send("ping")

            p = asyncio.ensure_future(pinger())

            async def reader():
                async for raw in ws:
                    if raw == "pong":
                        continue
                    m = json.loads(raw)
                    counts[m.get("event") or ("data" if "data" in m else "other")] += 1

            try:
                await asyncio.wait_for(reader(), timeout=SECS)
            except asyncio.TimeoutError:
                pass
            p.cancel()
    except Exception as e:
        out["okx_error"] = repr(e)
    out["okx_control"] = dict(counts)


async def main():
    await asyncio.gather(binance_arr(), binance_sym(), bitget(), okx())
    print(json.dumps(out, indent=1))


asyncio.run(main())
