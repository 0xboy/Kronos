"""Crypto universe — Yahoo `-USD` pairs, priced directly in USD.

Unlike commodities, no unit conversion is needed: Yahoo already quotes
each coin in USD and these trade 24/7 (no market holidays), so 2y of
daily bars gives ~730 rows — plenty for the default lookback=400.
"""
from __future__ import annotations

# label (== Yahoo ticker) -> display name
CRYPTO_META: dict[str, dict[str, str]] = {
    "BTC-USD": {"name": "Bitcoin"},
    "ETH-USD": {"name": "Ethereum"},
    "BNB-USD": {"name": "BNB"},
    "SOL-USD": {"name": "Solana"},
    "XRP-USD": {"name": "XRP"},
    "ADA-USD": {"name": "Cardano"},
    "DOGE-USD": {"name": "Dogecoin"},
    "TRX-USD": {"name": "TRON"},
    "AVAX-USD": {"name": "Avalanche"},
    "DOT-USD": {"name": "Polkadot"},
    "LINK-USD": {"name": "Chainlink"},
    "LTC-USD": {"name": "Litecoin"},
    "BCH-USD": {"name": "Bitcoin Cash"},
    "UNI7083-USD": {"name": "Uniswap"},
    "APT21794-USD": {"name": "Aptos"},
    "SUI20947-USD": {"name": "Sui"},
    "ICP-USD": {"name": "Internet Computer"},
    "NEAR-USD": {"name": "NEAR Protocol"},
    "ATOM-USD": {"name": "Cosmos"},
    "XLM-USD": {"name": "Stellar"},
    "ETC-USD": {"name": "Ethereum Classic"},
    "FIL-USD": {"name": "Filecoin"},
    "HBAR-USD": {"name": "Hedera"},
    "ARB11841-USD": {"name": "Arbitrum"},
    "OP-USD": {"name": "Optimism"},
    "VET-USD": {"name": "VeChain"},
    "ALGO-USD": {"name": "Algorand"},
    "AAVE-USD": {"name": "Aave"},
    "SAND-USD": {"name": "The Sandbox"},
    "MANA-USD": {"name": "Decentraland"},
    "SHIB-USD": {"name": "Shiba Inu"},
}

# Excluded / notes:
#  - Plain "ARB-USD" on Yahoo is a stale/inactive listing (28/30 zero-volume
#    days, price ~1000x below real Arbitrum) — use the numbered "ARB11841-USD"
#    feed instead, which has healthy volume and a plausible price range.
#  - "TON-USD" (Toncoin) has the same stale-feed problem, but its only
#    numbered alternative ("TON11419-USD") has just ~2 days of history — not
#    enough for the default lookback=400, so Toncoin is left out entirely.

CRYPTO_LABELS = list(CRYPTO_META.keys())
