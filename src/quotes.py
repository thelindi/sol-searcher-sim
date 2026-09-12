"""Fetch SOL/USDC mid quotes across Solana DEX venues via DexScreener."""
from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

DEXSCREENER = "https://api.dexscreener.com/latest/dex/search?q=SOL%20USDC"
PREFER = ("raydium", "orca", "meteora", "phoenix", "pumpswap")


def _http_get(url: str, timeout: float = 12.0) -> Tuple[Optional[dict], Optional[str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "sol-searcher-sim/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode()), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def fetch_sol_usdc_venues(min_liq_usd: float = 50_000.0) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    raw, err = _http_get(DEXSCREENER)
    if err:
        return [], err
    pairs = (raw or {}).get("pairs") or []
    out: List[Dict[str, Any]] = []
    seen = set()
    for p in pairs:
        chain = (p.get("chainId") or "").lower()
        if chain != "solana":
            continue
        base = (p.get("baseToken") or {}).get("symbol") or ""
        quote = (p.get("quoteToken") or {}).get("symbol") or ""
        syms = {base.upper(), quote.upper()}
        if "SOL" not in syms or "USDC" not in syms:
            continue
        dex = (p.get("dexId") or "").lower()
        if not any(s in dex for s in PREFER):
            continue
        try:
            price = float(p.get("priceUsd") or 0)
            liq = float((p.get("liquidity") or {}).get("usd") or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0 or liq < min_liq_usd:
            continue
        pair_addr = p.get("pairAddress") or ""
        key = (dex, pair_addr)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "dex": dex,
                "pair": pair_addr,
                "mid": price,
                "liq_usd": round(liq, 2),
                "url": p.get("url") or "",
            }
        )
    out.sort(key=lambda v: -float(v["liq_usd"]))
    return out[:12], None
