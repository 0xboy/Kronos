"""Walk-forward grid search for XK100 ranking filters.

Scores Kronos once per as-of date (top ADV pool), then applies filter grids
offline. Writes paper_results/tests/xk100_rank_backtest.json and prints the
winning config.

  .venv/Scripts/python.exe scripts/backtest_xk100_rank.py
  .venv/Scripts/python.exe scripts/backtest_xk100_rank.py --windows 12 --step 5 --pool 30
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from paper.signals import load_predictor, score_symbol
from paper.universe import XK100
from paper.xk100_rank import (
    DEFAULT_CFG,
    Xk100RankConfig,
    adv20,
    cfg_to_dict,
    passes_signal_gates,
    top_adv_symbols,
    vol5d,
)
from paper.yahoo_cache import get_yahoo_bars

TESTS = ROOT / "paper_results" / "tests"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="XK100 ranking walk-forward grid search")
    p.add_argument("--windows", type=int, default=24, help="Number of as-of dates (~120d/step5)")
    p.add_argument("--step", type=int, default=5, help="Trading days between as-of dates")
    p.add_argument("--pool", type=int, default=50, help="Top ADV symbols scored per as-of")
    p.add_argument("--lookback", type=int, default=400)
    p.add_argument("--pred-len", type=int, default=5)
    p.add_argument("--sample-count", type=int, default=5)
    p.add_argument("--top", type=int, default=10, help="Top-N picks scored per window/cfg")
    p.add_argument("--model", default="NeoQuasar/Kronos-small")
    p.add_argument("--limit-symbols", type=int, default=0, help="Debug: first N of XK100")
    p.add_argument("--max-age-days", type=int, default=7)
    return p.parse_args()


GRID = {
    "min_price_try": [2.0, 5.0, 10.0],
    "min_adv20_try": [5e5, 1e6, 2e6],
    "max_abs_expected": [0.08, 0.10, 0.15],
    "min_tstat": [0.0, 0.5],
}


def _prepare_bars(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out = {}
    for ysym, df in raw.items():
        key = ysym.replace(".IS", "")
        d = df.copy()
        d["timestamps"] = pd.to_datetime(d["timestamps"])
        d = d.sort_values("timestamps").reset_index(drop=True)
        out[key] = d
    return out


def _asof_indices(
    bars: dict[str, pd.DataFrame],
    lookback: int,
    pred_len: int,
    windows: int,
    step: int,
) -> list[pd.Timestamp]:
    """Pick shared as-of dates from the intersection of calendars (last windows*step)."""
    # Use the symbol with most bars as calendar reference among liquid names
    ref = max(bars.values(), key=len)
    ts = pd.to_datetime(ref["timestamps"])
    # Need lookback-1 bars before asof idx and pred_len bars after
    # asof is the last history bar used for prediction
    min_i = lookback - 1
    max_i = len(ref) - 1 - pred_len
    if max_i < min_i:
        return []
    candidates = list(range(min_i, max_i + 1, step))
    # take the last `windows` candidates
    candidates = candidates[-windows:]
    return [pd.Timestamp(ts.iloc[i]) for i in candidates]


def _slice_to_asof(df: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame | None:
    mask = pd.to_datetime(df["timestamps"]) <= asof
    sub = df.loc[mask].reset_index(drop=True)
    return sub if len(sub) else None


def _realized_return(df: pd.DataFrame, asof: pd.Timestamp, pred_len: int) -> float | None:
    ts = pd.to_datetime(df["timestamps"])
    idx = ts.searchsorted(asof, side="right") - 1
    if idx < 0 or idx + pred_len >= len(df):
        return None
    if pd.Timestamp(ts.iloc[idx]).normalize() != pd.Timestamp(asof).normalize():
        # require exact as-of bar present
        if abs((pd.Timestamp(ts.iloc[idx]) - asof).days) > 3:
            return None
    p0 = float(df["close"].iloc[idx])
    p1 = float(df["close"].iloc[idx + pred_len])
    if p0 <= 0:
        return None
    return p1 / p0 - 1.0


def _score_window(
    predictor,
    bars: dict[str, pd.DataFrame],
    asof: pd.Timestamp,
    *,
    lookback: int,
    pred_len: int,
    sample_count: int,
    pool: int,
) -> list[dict]:
    # liquidity pool as-of
    sliced = {}
    for sym, df in bars.items():
        sub = _slice_to_asof(df, asof)
        if sub is not None and len(sub) >= lookback:
            sliced[sym] = sub
    pool_syms = top_adv_symbols(sliced, pool, min_bars=lookback)
    rows = []
    for sym in pool_syms:
        sub = sliced[sym]
        try:
            sig = score_symbol(
                predictor,
                sym,
                sub,
                lookback=lookback,
                pred_len=pred_len,
                sample_count=sample_count,
            )
        except Exception as exc:  # noqa: BLE001
            rows.append({"symbol": sym, "error": str(exc)})
            continue
        if sig is None:
            continue
        actual = _realized_return(bars[sym], asof, pred_len)
        rows.append(
            {
                "symbol": sym,
                "last_close": sig.last_close,
                "pred_close": sig.pred_close,
                "expected_return": sig.expected_return,
                "return_std": sig.return_std,
                "sample_count": sig.sample_count,
                "bars": sig.bars,
                "adv20": adv20(sub),
                "vol5d": vol5d(sub),
                "actual_return": actual,
            }
        )
    return rows


def _apply_cfg(
    scored: list[dict],
    cfg: Xk100RankConfig,
    top_n: int,
) -> list[dict]:
    from paper.signals import Signal

    picks = []
    for r in scored:
        if "error" in r or r.get("actual_return") is None:
            continue
        # synthetic df-less filter using stored metrics
        if r["last_close"] < cfg.min_price_try:
            continue
        if r["adv20"] < cfg.min_adv20_try:
            continue
        if not np.isfinite(r["vol5d"]):
            continue
        sig = Signal(
            symbol=r["symbol"],
            last_close=r["last_close"],
            pred_close=r["pred_close"],
            expected_return=r["expected_return"],
            bars=r["bars"],
            return_std=r["return_std"],
            sample_count=r["sample_count"],
        )
        ok, _ = passes_signal_gates(sig, cfg)
        if not ok:
            continue
        # fake df for attach_score using vol already known
        score = r["expected_return"] / r["vol5d"] if r["vol5d"] > 1e-12 else 0.0
        picks.append({**r, "score": score})
    picks.sort(key=lambda x: x["score"], reverse=True)
    return picks[:top_n]


def _metrics(picks: list[dict]) -> dict:
    if not picks:
        return {"n": 0, "direction_hits": 0, "hit_rate": None, "mae": None}
    hits = 0
    errs = []
    for p in picks:
        exp = float(p["expected_return"])
        act = float(p["actual_return"])
        same = (act >= 0 and exp >= 0) or (act < 0 and exp < 0)
        hits += int(same)
        errs.append(abs(act - exp) * 100.0)
    n = len(picks)
    return {
        "n": n,
        "direction_hits": hits,
        "hit_rate": round(hits / n, 4),
        "mae": round(float(np.mean(errs)), 3),
    }


def main() -> int:
    args = parse_args()
    labels = list(XK100)
    if args.limit_symbols and args.limit_symbols > 0:
        labels = labels[: args.limit_symbols]
    yahoo_syms = [f"{t}.IS" for t in labels]

    print(f"Loading Yahoo cache for {len(labels)} XK100 symbols...")
    raw = get_yahoo_bars("xk100", yahoo_syms, refresh=False, max_age_days=args.max_age_days)
    bars = _prepare_bars(raw)
    print(f"Bars loaded: {len(bars)}")

    asofs = _asof_indices(bars, args.lookback, args.pred_len, args.windows, args.step)
    if not asofs:
        raise SystemExit("No valid as-of dates (need lookback + pred_len history)")
    print(f"As-of windows: {len(asofs)} | first={asofs[0].date()} last={asofs[-1].date()}")
    print(f"Pool={args.pool} sample_count={args.sample_count} pred_len={args.pred_len}")

    print("Loading Kronos...")
    predictor = load_predictor(args.model)

    window_scores: list[dict] = []
    for i, asof in enumerate(asofs, 1):
        print(f"[{i}/{len(asofs)}] scoring as-of {asof.date()}...")
        rows = _score_window(
            predictor,
            bars,
            asof,
            lookback=args.lookback,
            pred_len=args.pred_len,
            sample_count=args.sample_count,
            pool=args.pool,
        )
        scored_n = sum(1 for r in rows if "expected_return" in r and r.get("actual_return") is not None)
        print(f"  scored with realized: {scored_n}")
        window_scores.append({"asof": str(asof.date()), "rows": rows})

    # Grid search offline
    keys = list(GRID.keys())
    combos = list(itertools.product(*(GRID[k] for k in keys)))
    results = []
    for combo in combos:
        params = dict(zip(keys, combo))
        cfg = Xk100RankConfig(
            min_price_try=params["min_price_try"],
            min_adv20_try=params["min_adv20_try"],
            max_abs_expected=params["max_abs_expected"],
            min_tstat=params["min_tstat"],
            sample_count=args.sample_count,
            rank_mode="vol_norm",
            top_adv_pool=args.pool,
            pred_len=args.pred_len,
            lookback=args.lookback,
        )
        all_picks: list[dict] = []
        per_window = []
        for w in window_scores:
            picks = _apply_cfg(w["rows"], cfg, args.top)
            m = _metrics(picks)
            per_window.append({"asof": w["asof"], **m, "symbols": [p["symbol"] for p in picks]})
            for p in picks:
                all_picks.append({**p, "asof": w["asof"]})
        overall = _metrics(all_picks)
        results.append(
            {
                "cfg": cfg_to_dict(cfg),
                "overall": overall,
                "windows": per_window,
            }
        )

    # Rank: hit_rate desc, mae asc, n desc
    def sort_key(r: dict):
        o = r["overall"]
        hr = o["hit_rate"] if o["hit_rate"] is not None else -1.0
        mae = o["mae"] if o["mae"] is not None else 1e9
        return (-hr, mae, -o["n"])

    results.sort(key=sort_key)
    winner = results[0] if results else None

    out = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "params": {
            "windows": args.windows,
            "step": args.step,
            "pool": args.pool,
            "lookback": args.lookback,
            "pred_len": args.pred_len,
            "sample_count": args.sample_count,
            "top": args.top,
            "model": args.model,
            "asofs": [str(a.date()) for a in asofs],
        },
        "grid": GRID,
        "seed_cfg": cfg_to_dict(DEFAULT_CFG),
        "winner": winner,
        "top5_cfgs": [
            {"cfg": r["cfg"], "overall": r["overall"]} for r in results[:5]
        ],
        "all_results": [{"cfg": r["cfg"], "overall": r["overall"]} for r in results],
    }
    TESTS.mkdir(parents=True, exist_ok=True)
    path = TESTS / "xk100_rank_backtest.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved -> {path}")
    if winner:
        print("WINNER:")
        print(json.dumps(winner["cfg"], indent=2))
        print("overall:", winner["overall"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
