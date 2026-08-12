"""Moving-average envelope + volatility gates for Kronos ranking.

Idea: only keep names that are (1) relatively volatile and (2) touching an
SMA envelope band, optionally requiring Kronos expected_return to agree with
mean-reversion (buy oversold / sell overbought).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EnvelopeConfig:
    period: int = 20
    pct: float = 0.05  # band = SMA * (1 +/- pct)
    touch_tol: float = 0.01  # allow within 1% of the band
    min_vol_pctile: float = 0.70  # keep top 30% vol among candidates
    require_align: bool = True


def sma_envelope(
    df: pd.DataFrame,
    *,
    period: int = 20,
    pct: float = 0.05,
) -> dict[str, float] | None:
    """Return mid/upper/lower and last close, or None if not enough bars."""
    if df is None or len(df) < period:
        return None
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < period:
        return None
    mid = float(close.iloc[-period:].mean())
    if not np.isfinite(mid) or mid <= 0:
        return None
    last = float(close.iloc[-1])
    if not np.isfinite(last) or last <= 0:
        return None
    upper = mid * (1.0 + pct)
    lower = mid * (1.0 - pct)
    return {
        "mid": mid,
        "upper": upper,
        "lower": lower,
        "close": last,
        "pct": float(pct),
        "period": float(period),
    }


def envelope_side(
    env: dict[str, float],
    *,
    touch_tol: float = 0.01,
) -> str:
    """'oversold' | 'overbought' | 'inside' relative to envelope bands."""
    c = float(env["close"])
    lo = float(env["lower"])
    hi = float(env["upper"])
    # Within touch_tol of band counts as a touch.
    if c <= lo * (1.0 + touch_tol):
        return "oversold"
    if c >= hi * (1.0 - touch_tol):
        return "overbought"
    return "inside"


def aligns_with_mean_reversion(side: str, expected_return: float) -> bool:
    """Oversold wants up; overbought wants down."""
    if side == "oversold":
        return expected_return > 0
    if side == "overbought":
        return expected_return < 0
    return False


def vol_pctile_threshold(vols: list[float], pctile: float) -> float:
    """Minimum vol to keep given a percentile gate (0..1)."""
    clean = [float(v) for v in vols if np.isfinite(v)]
    if not clean:
        return float("inf")
    pctile = float(np.clip(pctile, 0.0, 1.0))
    return float(np.quantile(clean, pctile))


def annotate_envelope(
    row: dict,
    df: pd.DataFrame,
    cfg: EnvelopeConfig,
) -> dict:
    """Attach envelope fields to a scored row (mutates a copy)."""
    out = dict(row)
    env = sma_envelope(df, period=cfg.period, pct=cfg.pct)
    if env is None:
        out["envelope_side"] = "no_env"
        out["envelope_mid"] = None
        out["envelope_upper"] = None
        out["envelope_lower"] = None
        return out
    side = envelope_side(env, touch_tol=cfg.touch_tol)
    out["envelope_side"] = side
    out["envelope_mid"] = round(env["mid"], 6)
    out["envelope_upper"] = round(env["upper"], 6)
    out["envelope_lower"] = round(env["lower"], 6)
    return out


def apply_envelope_vol_filter(
    rows: list[dict],
    bars: dict[str, pd.DataFrame],
    cfg: EnvelopeConfig,
) -> tuple[list[dict], list[dict]]:
    """Filter scored rows by vol percentile + envelope touch (+ optional align).

    Returns (kept, drops). Kept rows include envelope_* annotations.
    """
    annotated: list[dict] = []
    drops: list[dict] = []
    for r in rows:
        if "error" in r or "expected_return" not in r:
            continue
        sym = r["symbol"]
        df = bars.get(sym)
        if df is None:
            drops.append({"symbol": sym, "reason": "no_bars_envelope"})
            continue
        ar = annotate_envelope(r, df, cfg)
        annotated.append(ar)

    if not annotated:
        return [], drops

    vol_floor = vol_pctile_threshold(
        [float(a.get("vol5d", float("nan"))) for a in annotated],
        cfg.min_vol_pctile,
    )
    kept: list[dict] = []
    for a in annotated:
        sym = a["symbol"]
        v = float(a.get("vol5d", float("nan")))
        if not np.isfinite(v) or v < vol_floor:
            drops.append({"symbol": sym, "reason": f"vol_pctile<{cfg.min_vol_pctile}"})
            continue
        side = a.get("envelope_side")
        if side == "no_env":
            drops.append({"symbol": sym, "reason": "envelope_no_bars"})
            continue
        if side == "inside":
            drops.append({"symbol": sym, "reason": "envelope_inside"})
            continue
        if cfg.require_align and not aligns_with_mean_reversion(
            side, float(a["expected_return"])
        ):
            drops.append({"symbol": sym, "reason": f"envelope_misalign:{side}"})
            continue
        a["envelope_vol_floor"] = round(vol_floor, 8)
        kept.append(a)
    return kept, drops
