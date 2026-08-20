"""Top liquid exchange boards for Yahoo daily cache / future FT.

Board membership: ``universe/exchanges.json``.
US / BIST are filled from ``spus100`` / ``xk100`` at runtime.
"""
from __future__ import annotations

from universe.catalog import SPUS100, XK100
from universe.loader import load_json

_payload = load_json("exchanges")
_boards: dict = dict(_payload.get("boards") or {})

HK40 = list(_boards["hk"]["symbols"])
JP40 = list(_boards["jp"]["symbols"])
LSE40 = list(_boards["lse"]["symbols"])
DE40 = list(_boards["de"]["symbols"])
KR40 = list(_boards["kr"]["symbols"])
AU40 = list(_boards["au"]["symbols"])
IN40 = list(_boards["in"]["symbols"])
PA40 = list(_boards["fr"]["symbols"])

EXCHANGES: dict[str, dict] = {
    "us": {
        "name": "US (NYSE/Nasdaq liquid)",
        "yahoo_symbols": list(SPUS100),
        "cache_id": "spus",
    },
    "bist": {
        "name": "Borsa Istanbul (XK100)",
        "yahoo_symbols": [f"{t}.IS" for t in XK100],
        "cache_id": "xk100",
    },
}

for key, board in _boards.items():
    EXCHANGES[key] = {
        "name": board["name"],
        "yahoo_symbols": list(board["symbols"]),
        "cache_id": board["cache_id"],
    }

TOP10_IDS = list(EXCHANGES.keys())


def all_exchange_symbols() -> list[tuple[str, str]]:
    """[(cache_id, yahoo_symbol), ...]"""
    out: list[tuple[str, str]] = []
    for ex in EXCHANGES.values():
        cid = ex["cache_id"]
        for s in ex["yahoo_symbols"]:
            out.append((cid, s))
    return out
