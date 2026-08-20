"""Crypto universe — Yahoo `-USD` pairs, priced directly in USD.

Membership: ``universe/crypto.json``.
Unlike commodities, no unit conversion is needed: Yahoo already quotes
each coin in USD and these trade 24/7 (no market holidays), so 2y of
daily bars gives ~730 rows — plenty for the default lookback=400.
"""
from __future__ import annotations

from universe.loader import load_json

_payload = load_json("crypto")
CRYPTO_META: dict[str, dict[str, str]] = {
    str(k): {"name": str(v["name"])} for k, v in dict(_payload["items"]).items()
}
CRYPTO_LABELS = list(CRYPTO_META.keys())
