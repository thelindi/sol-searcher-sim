"""Fetch SOL/USDC mid quotes across Solana DEX venues via DexScreener.

v1 filters (kills fake 3000bps "arbs"):
- SOL mint + USDC mint exact (no symbol/search fuzzy)
- one best pair per dex family
- drop mids far from median before returning
"""
from __future__ import annotations

import json
import os
import statistics
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/" + SOL_MINT
PREFER_DEX = ("raydium", "orca", "meteora", "pumpswap", "phoenix")
HEADERS = {
    "User-Agent": "sol-searcher-sim/0.2 (simulate-only)",
    "Accept": "application/json",
}


def _http_json(url: str, timeout: float = 12.0) -> Tuple[Optional[Any], Optional[str]]:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace")), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _family(dex_id: str) -> Optional[str]:
    d = (dex_id or "").lower()
    for name in PREFER_DEX:
        if name in d:
            return name
    return None


def fetch_sol_usdc_venues(
    min_liq_usd: Optional[float] = None,
    max_mid_dev_bps: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Best liquid SOL/USDC pair per dex family, median-trimmed."""
    if min_liq_usd is None:
        min_liq_usd = float(os.environ.get("MIN_LIQ_USD") or 100_000)
    if max_mid_dev_bps is None:
        max_mid_dev_bps = float(os.environ.get("MAX_MID_DEV_BPS") or 150)

    data, err = _http_json(TOKEN_URL)
    if err:
        return [], err
    pairs = data.get("pairs") if isinstance(data, dict) else None
    if not isinstance(pairs, list):
        return [], "no_pairs"

    best: Dict[str, Dict[str, Any]] = {}
    for p in pairs:
        if not isinstance(p, dict):
            continue
        if (p.get("chainId") or "").lower() != "solana":
            continue
        family = _family(str(p.get("dexId") or ""))
        if not family:
            continue
        base = p.get("baseToken") or {}
        quote = p.get("quoteToken") or {}
        ba = base.get("address") or ""
        qa = quote.get("address") or ""
        if {ba, qa} != {SOL_MINT, USDC_MINT}:
            continue
        try:
            liq = float((p.get("liquidity") or {}).get("usd") or 0)
            price_usd = float(p.get("priceUsd") or 0)
            if ba == SOL_MINT:
                mid = price_usd
            else:
                mid = 0.0
        except (TypeError, ValueError):
            continue
        if liq < min_liq_usd or mid <= 0:
            continue
        if ba != SOL_MINT:
            continue
        row = {
            "dex": family,
            "dex_id": p.get("dexId"),
            "pair": p.get("pairAddress"),
            "mid": round(mid, 6),
            "liq_usd": round(liq, 2),
            "quote": "USDC",
            "url": p.get("url") or "",
        }
        prev = best.get(family)
        if prev is None or liq > float(prev["liq_usd"]):
            best[family] = row

    venues = list(best.values())
    if len(venues) < 2:
        return venues, None

    mids = [float(v["mid"]) for v in venues]
    med = statistics.median(mids)
    if med <= 0:
        return [], "bad_median"
    kept = []
    for v in venues:
        dev_bps = abs(float(v["mid"]) - med) / med * 10_000.0
        if dev_bps <= max_mid_dev_bps:
            kept.append(v)

    kept.sort(key=lambda v: -float(v["liq_usd"]))
    return kept, None
