"""XK100 ranking filters: liquidity, price, vol-normalize, sample confidence.

Live reports and the BIST sleeve use `DEFAULT_CFG`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np
import pandas as pd

from inference.signals import Signal, DEFAULT_SAMPLE_COUNT


@dataclass(frozen=True)
class Xk100RankConfig:
    min_price_try: float = 10.0
    min_adv20_try: float = 500_000.0
    max_abs_expected: float = 0.15
    min_tstat: float = 0.5
    sample_count: int = DEFAULT_SAMPLE_COUNT
    rank_mode: str = "vol_norm"  # mean_ret / vol_5d
    top_adv_pool: int = 50
    pred_len: int = 5
    lookback: int = 400


DEFAULT_CFG = Xk100RankConfig()


def cfg_to_dict(cfg: Xk100RankConfig) -> dict:
    return asdict(cfg)


def cfg_from_dict(d: dict) -> Xk100RankConfig:
    base = asdict(DEFAULT_CFG)
    base.update({k: v for k, v in d.items() if k in base})
    return Xk100RankConfig(**base)


def adv20(df: pd.DataFrame) -> float:
    """20-day average TRY turnover (close * volume)."""
    if df is None or len(df) < 5:
        return 0.0
    tail = df.iloc[-20:]
    if "amount" in tail.columns:
        amt = pd.to_numeric(tail["amount"], errors="coerce")
    else:
        amt = pd.to_numeric(tail["close"], errors="coerce") * pd.to_numeric(
            tail["volume"], errors="coerce"
        )
    return float(amt.fillna(0.0).mean())


def vol5d(df: pd.DataFrame) -> float:
    """5-day-scale realized vol from last 20 daily close returns: std * sqrt(5)."""
    if df is None or len(df) < 22:
        return float("nan")
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < 22:
        return float("nan")
    rets = close.pct_change().iloc[-20:]
    daily = float(rets.std(ddof=0))
    if not np.isfinite(daily) or daily <= 0:
        return float("nan")
    return daily * float(np.sqrt(5.0))


def tstat(expected_return: float, return_std: float) -> float:
    if return_std is None or return_std <= 1e-12:
        return 0.0 if abs(expected_return) < 1e-12 else float("inf")
    return float(expected_return / return_std)


def compute_score(expected_return: float, vol: float, *, rank_mode: str = "vol_norm") -> float:
    if rank_mode != "vol_norm":
        return float(expected_return)
    if not np.isfinite(vol) or vol <= 1e-12:
        return 0.0
    return float(expected_return / vol)


def passes_filters(df: pd.DataFrame, cfg: Xk100RankConfig) -> tuple[bool, str]:
    if df is None or df.empty:
        return False, "no_bars"
    last = float(pd.to_numeric(df["close"], errors="coerce").iloc[-1])
    if not np.isfinite(last) or last < cfg.min_price_try:
        return False, f"min_price<{cfg.min_price_try}"
    a = adv20(df)
    if a < cfg.min_adv20_try:
        return False, f"adv20<{cfg.min_adv20_try}"
    v = vol5d(df)
    if not np.isfinite(v):
        return False, "vol5d_nan"
    return True, "ok"


def passes_signal_gates(sig: Signal, cfg: Xk100RankConfig) -> tuple[bool, str]:
    if abs(sig.expected_return) > cfg.max_abs_expected:
        return False, f"|exp|>{cfg.max_abs_expected}"
    ts = tstat(sig.expected_return, sig.return_std)
    if np.isfinite(ts) and abs(ts) < cfg.min_tstat:
        return False, f"|tstat|<{cfg.min_tstat}"
    if sig.pred_close <= 0:
        return False, "pred_close<=0"
    return True, "ok"


def attach_score(sig: Signal, df: pd.DataFrame, cfg: Xk100RankConfig) -> Signal:
    v = vol5d(df)
    sc = compute_score(sig.expected_return, v, rank_mode=cfg.rank_mode)
    return replace(sig, score=sc)


def rank_signals(
    signals: list[Signal],
    bars: dict[str, pd.DataFrame],
    cfg: Xk100RankConfig,
) -> tuple[list[Signal], list[dict]]:
    """Filter + score + sort descending by score. Returns (ranked, drops)."""
    kept: list[Signal] = []
    drops: list[dict] = []
    for sig in signals:
        df = bars.get(sig.symbol)
        ok, reason = passes_filters(df, cfg) if df is not None else (False, "no_bars")
        if not ok:
            drops.append({"symbol": sig.symbol, "reason": reason})
            continue
        ok2, reason2 = passes_signal_gates(sig, cfg)
        if not ok2:
            drops.append({"symbol": sig.symbol, "reason": reason2})
            continue
        kept.append(attach_score(sig, df, cfg))
    kept.sort(key=lambda s: s.score, reverse=True)
    return kept, drops
