"""Commodity bars as TRY per gram (Yahoo futures × USDTRY).

Precious metals: USD/troy oz → TRY/g
Copper (HG=F): USD/lb → TRY/g
Aluminum / Zinc: USD/metric tonne → TRY/g
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from paper.yahoo_cache import COLS, download_yahoo, get_yahoo_bars, save_symbol

TROY_OZ_G = 31.1034768
LB_G = 453.59237
TONNE_G = 1_000_000.0

# label -> meta (yahoo futures contract + unit for TL/gram conversion)
COMMODITY_META: dict[str, dict[str, Any]] = {
    "GOLD": {
        "yahoo": "GC=F",
        "name": "Altın",
        "unit_src": "usd_per_troy_oz",
        "divisor_g": TROY_OZ_G,
    },
    "SILVER": {
        "yahoo": "SI=F",
        "name": "Gümüş",
        "unit_src": "usd_per_troy_oz",
        "divisor_g": TROY_OZ_G,
    },
    "PLATINUM": {
        "yahoo": "PL=F",
        "name": "Platin",
        "unit_src": "usd_per_troy_oz",
        "divisor_g": TROY_OZ_G,
    },
    "PALLADIUM": {
        "yahoo": "PA=F",
        "name": "Paladyum",
        "unit_src": "usd_per_troy_oz",
        "divisor_g": TROY_OZ_G,
    },
    "COPPER": {
        "yahoo": "HG=F",
        "name": "Bakır",
        "unit_src": "usd_per_lb",
        "divisor_g": LB_G,
    },
    "ALUMINUM": {
        "yahoo": "ALI=F",
        "name": "Alüminyum",
        "unit_src": "usd_per_tonne",
        "divisor_g": TONNE_G,
    },
    "ZINC": {
        "yahoo": "ZNC=F",
        "name": "Çinko",
        "unit_src": "usd_per_tonne",
        "divisor_g": TONNE_G,
    },
}

COMMODITY_LABELS = list(COMMODITY_META.keys())
FX_YAHOO = "USDTRY=X"
UNIVERSE_ID = "commodities"


def _fx_series(period: str = "2y", refresh: bool = False, max_age_days: int = 1) -> pd.Series:
    """Daily USDTRY close indexed by naive date."""
    raw = get_yahoo_bars(
        UNIVERSE_ID,
        [FX_YAHOO],
        period=period,
        refresh=refresh,
        max_age_days=max_age_days,
    )
    fx = raw.get(FX_YAHOO)
    if fx is None or fx.empty:
        raise RuntimeError("USDTRY=X download failed — cannot price commodities in TRY/g")
    s = fx.set_index(pd.to_datetime(fx["timestamps"]).dt.normalize())["close"].astype(float)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s.name = "usdtry"
    return s


def _to_try_per_gram(df: pd.DataFrame, fx: pd.Series, divisor_g: float) -> pd.DataFrame:
    """Align metal OHLC with USDTRY and convert to TRY/gram."""
    out = df.copy()
    out["day"] = pd.to_datetime(out["timestamps"]).dt.normalize()
    # FX calendar can differ from COMEX — ffill then bfill within a short window
    fx_aligned = fx.reindex(out["day"]).ffill(limit=5).bfill(limit=5)
    scale = (fx_aligned / float(divisor_g)).to_numpy()
    for col in ("open", "high", "low", "close"):
        out[col] = out[col].astype(float) * scale
    out["volume"] = out["volume"].astype(float).fillna(0.0)
    out["amount"] = out["close"] * out["volume"]
    out = out.drop(columns=["day"])
    out = out.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    return out[COLS]


def get_commodity_try_gram_bars(
    *,
    period: str = "2y",
    refresh: bool = False,
    max_age_days: int = 1,
) -> dict[str, pd.DataFrame]:
    """Download futures + USDTRY, convert to TRY/g, cache under commodities/LABEL.csv."""
    fx = _fx_series(period=period, refresh=refresh, max_age_days=max_age_days)
    yahoo_syms = [m["yahoo"] for m in COMMODITY_META.values()]
    raw = get_yahoo_bars(
        UNIVERSE_ID,
        yahoo_syms,
        period=period,
        refresh=refresh,
        max_age_days=max_age_days,
    )

    out: dict[str, pd.DataFrame] = {}
    for label, meta in COMMODITY_META.items():
        ysym = meta["yahoo"]
        src = raw.get(ysym)
        if src is None or src.empty:
            print(f"  skip {label} ({ysym}): no bars")
            continue
        converted = _to_try_per_gram(src, fx, float(meta["divisor_g"]))
        if len(converted) < 50:
            print(f"  skip {label}: thin after FX align ({len(converted)} bars)")
            continue
        # Cache converted series under label name for Kronos runner
        save_symbol(UNIVERSE_ID, label, converted)
        out[label] = converted
        last = float(converted["close"].iloc[-1])
        print(
            f"  {label:10} {meta['name']:10} "
            f"TRY/g={last:,.4f} bars={len(converted)} "
            f"({converted['timestamps'].iloc[0].date()} -> {converted['timestamps'].iloc[-1].date()})"
        )
    return out
