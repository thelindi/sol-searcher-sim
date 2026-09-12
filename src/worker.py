"""Always-on simulate worker. Never sends bundles / tips.

Also serves GET /health on $PORT so Render Web Service deploy works.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

from .quotes import fetch_sol_usdc_venues

_STOP = False
_LAST: Dict[str, Any] = {"event": "boot"}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(obj: Dict[str, Any]) -> None:
    global _LAST
    obj.setdefault("ts", _utc())
    _LAST = obj
    if os.environ.get("LOG_JSON", "1") == "1":
        print(json.dumps(obj, default=str), flush=True)
    else:
        print(obj, flush=True)


def _handle_sig(*_a):
    global _STOP
    _STOP = True
    _log({"event": "shutdown_signal"})


def scan_once(min_spread_bps: float, notional_usd: float) -> Dict[str, Any]:
    venues, err = fetch_sol_usdc_venues()
    if err:
        return {"event": "quote_error", "error": err}
    if len(venues) < 2:
        return {"event": "insufficient_venues", "n": len(venues), "venues": venues}

    cheap = min(venues, key=lambda v: float(v["mid"]))
    rich = max(venues, key=lambda v: float(v["mid"]))
    mid_c = float(cheap["mid"])
    mid_r = float(rich["mid"])
    if mid_c <= 0:
        return {"event": "bad_mid"}
    spread_bps = (mid_r - mid_c) / mid_c * 10_000.0
    max_sane = float(os.environ.get("MAX_SANE_SPREAD_BPS") or 80)
    if spread_bps > max_sane:
        return {
            "event": "quote_reject_insane_spread",
            "spread_bps": round(spread_bps, 2),
            "max_sane_spread_bps": max_sane,
            "cheap": cheap,
            "rich": rich,
            "n_venues": len(venues),
            "mode": "simulate",
            "would_bundle": False,
        }
    friction_bps = float(os.environ.get("FRICTION_BPS_TOY") or 15)
    edge_bps = spread_bps - friction_bps
    est_pnl = notional_usd * (edge_bps / 10_000.0)

    out: Dict[str, Any] = {
        "event": "scan",
        "spread_bps": round(spread_bps, 2),
        "friction_bps_toy": friction_bps,
        "edge_bps_after_toy_friction": round(edge_bps, 2),
        "est_pnl_usd_toy": round(est_pnl, 4),
        "cheap": cheap,
        "rich": rich,
        "n_venues": len(venues),
        "venues": venues,
        "opportunity": edge_bps >= min_spread_bps,
        "mode": "simulate",
        "would_bundle": False,
    }
    if out["opportunity"]:
        out["event"] = "opportunity_sim"
        out["note"] = "simulate-only: would need Geyser+Jito to capture; not sent"
    return out


class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return  # quiet

    def do_GET(self):
        if self.path.split("?", 1)[0] in ("/health", "/", "/status"):
            body = json.dumps(
                {"ok": True, "mode": "simulate", "last": _LAST},
                default=str,
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def start_health_server() -> None:
    port = int(os.environ.get("PORT") or 10000)
    httpd = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    _log({"event": "health_listen", "port": port})


def main() -> None:
    mode = (os.environ.get("MODE") or "simulate").strip().lower()
    if mode != "simulate":
        _log({"event": "fatal", "error": f"MODE={mode} refused; only simulate supported in v0"})
        sys.exit(2)

    signal.signal(signal.SIGTERM, _handle_sig)
    signal.signal(signal.SIGINT, _handle_sig)
    start_health_server()

    poll = max(2.0, float(os.environ.get("POLL_SECONDS") or 5))
    min_bps = float(os.environ.get("MIN_SPREAD_BPS") or 25)
    notional = float(os.environ.get("NOTIONAL_USD") or 250)

    _log(
        {
            "event": "start",
            "mode": mode,
            "poll_seconds": poll,
            "min_spread_bps": min_bps,
            "notional_usd": notional,
            "paper_only": True,
        }
    )

    while not _STOP:
        if os.environ.get("KILL_SWITCH", "0") == "1":
            _log({"event": "kill_switch"})
            time.sleep(poll)
            continue
        try:
            _log(scan_once(min_bps, notional))
        except Exception as e:
            _log({"event": "loop_error", "error": f"{type(e).__name__}: {e}"})
        slept = 0.0
        while slept < poll and not _STOP:
            time.sleep(min(1.0, poll - slept))
            slept += 1.0

    _log({"event": "exit_clean"})


if __name__ == "__main__":
    main()
