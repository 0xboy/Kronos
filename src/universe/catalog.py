"""Universe label catalogs for paper / research.

Membership and meta live under repo-root ``universe/*.json``.
Edit those files (or drop an override under ``runtime/universe/``) to refresh
lists — conversion / special logic stays in sibling modules.
"""
from __future__ import annotations

from universe.commodities import COMMODITY_LABELS
from universe.crypto import CRYPTO_LABELS
from universe.loader import load_universe

SPUS100 = load_universe("spus100")
SPUS50 = SPUS100[:50]
XK100 = load_universe("xk100")

COMMODITIES = list(COMMODITY_LABELS)
CRYPTO = list(CRYPTO_LABELS)

# Backward-compatible aliases used by paper CLI / Alpaca runner
UNIVERSE_50 = list(SPUS50)
UNIVERSE_100 = list(SPUS100)

assert len(set(SPUS100)) == len(SPUS100), "duplicate SPUS symbols"
assert len(set(XK100)) == len(XK100), "duplicate XK100 symbols"
assert len(SPUS100) >= 1
assert len(XK100) >= 1
assert len(COMMODITIES) >= 5, len(COMMODITIES)
assert len(CRYPTO) >= 100, len(CRYPTO)
