# scripts

`binance_liquidation_stream_probe.py` — the 10-minute test behind the
"Binance's liquidation stream ACKs and sends nothing" claim in
`docs/coinglass-vs-exchanges.md`. Subscribes to `!forceOrder@arr`, to
per-symbol `<s>@forceOrder` for 20 busy perps, to Bitget's `liquidation`
channel, and to OKX `liquidation-orders` as the activity control, then prints
event counts per stream. Requires `pip install websockets`.
