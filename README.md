# sol-searcher-sim

Simulate-only Solana cross-DEX SOL/USDC gap scanner (Render 24/7 worker).

- **MODE=simulate only** — never sends Jito bundles, tips, or live swaps.
- Polls DexScreener SOL/USDC venues, logs toy edge after friction.
- Serves `GET /health` on `$PORT` so Render Web Service stays healthy.

## Local

```bash
pip install -r requirements.txt
export MODE=simulate
python -m src.worker
```

## Render

Use Blueprint `render.yaml` or create a **Web Service** (Python):
- Build: `pip install -r requirements.txt`
- Start: `python -m src.worker`
- Env: `MODE=simulate`, `POLL_SECONDS=5`, `MIN_SPREAD_BPS=25`, `NOTIONAL_USD=250`, `LOG_JSON=1`

Not a Marathon paper EDGE lane — opportunity frequency study only.
