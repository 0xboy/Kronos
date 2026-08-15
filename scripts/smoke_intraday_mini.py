"""Smoke: stock mini vs small on Alpaca IEX 15m (or 5m) bars.

Daily paper path stays untouched. Future timestamps use bar deltas (not bdays).

Example:
  .venv/Scripts/python.exe scripts/smoke_intraday_mini.py --minutes 15
  .venv/Scripts/python.exe scripts/smoke_intraday_mini.py --minutes 5 --lookback 512
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from paper.config import load_settings
from paper.data import _normalize_ohlcv, make_data_client
from paper.signals import load_predictor
from paper.universe import SPUS100

# Liquid SPUS names for a quick pilot (not full universe).
DEFAULT_SYMBOLS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "AVGO",
    "TSLA",
    "JPM",
    "XOM",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Intraday mini vs small smoke")
    p.add_argument("--minutes", type=int, choices=(5, 15), default=15)
    p.add_argument("--lookback", type=int, default=400)
    p.add_argument("--pred-len", type=int, default=1, help="Bars ahead to realize")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--windows", type=int, default=8, help="How many as-of checkpoints")
    p.add_argument("--step", type=int, default=4, help="Bars between as-of points")
    p.add_argument("--days", type=int, default=25, help="History calendar days to fetch")
    p.add_argument("--symbols", default="", help="Comma symbols; empty + --universe uses list")
    p.add_argument("--universe", choices=("", "spus100"), default="", help="Use full SPUS100")
    p.add_argument("--device", default="auto")
    return p.parse_args()


def fetch_intraday(
    client,
    symbols: list[str],
    *,
    minutes: int,
    days: int,
    chunk_size: int = 20,
) -> dict[str, pd.DataFrame]:
    end = datetime.now(timezone.utc) - timedelta(minutes=20)
    start = end - timedelta(days=days)
    tf = TimeFrame(minutes, TimeFrameUnit.Minute)
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i : i + chunk_size]
        print(f"  fetch {i + 1}-{i + len(chunk)}/{len(symbols)}...", flush=True)
        req = StockBarsRequest(
            symbol_or_symbols=chunk,
            timeframe=tf,
            start=start,
            end=end,
            feed=DataFeed.IEX,
            adjustment=Adjustment.ALL,
        )
        raw = client.get_stock_bars(req).df
        if raw is None or raw.empty:
            continue
        if isinstance(raw.index, pd.MultiIndex):
            for sym in chunk:
                if sym not in raw.index.get_level_values(0):
                    continue
                out[sym] = _normalize_ohlcv(raw.xs(sym, level=0).copy())
        else:
            out[chunk[0]] = _normalize_ohlcv(raw.copy())
    return out


def score_intraday(
    predictor,
    symbol: str,
    df: pd.DataFrame,
    *,
    asof_idx: int,
    lookback: int,
    pred_len: int,
    bar_minutes: int,
):
    if asof_idx + 1 < lookback:
        return None
    if asof_idx + pred_len >= len(df):
        return None
    window = df.iloc[asof_idx + 1 - lookback : asof_idx + 1].reset_index(drop=True)
    x_df = window[["open", "high", "low", "close", "volume", "amount"]]
    x_ts = pd.Series(pd.to_datetime(window["timestamps"]), name="timestamps")
    last_ts = pd.Timestamp(x_ts.iloc[-1])
    y_ts = pd.Series(
        [last_ts + pd.Timedelta(minutes=bar_minutes * (i + 1)) for i in range(pred_len)],
        name="timestamps",
    )
    last_close = float(window["close"].iloc[-1])
    pred = predictor.predict(
        df=x_df,
        x_timestamp=x_ts,
        y_timestamp=y_ts,
        pred_len=pred_len,
        T=1.0,
        top_p=0.9,
        sample_count=1,
        verbose=False,
    )
    pred_close = float(pred["close"].iloc[-1])
    actual_close = float(df["close"].iloc[asof_idx + pred_len])
    expected = pred_close / last_close - 1.0
    actual = actual_close / last_close - 1.0
    return {
        "symbol": symbol,
        "asof": str(pd.Timestamp(df["timestamps"].iloc[asof_idx])),
        "expected_return": expected,
        "actual_return": actual,
        "direction_hit": bool((expected >= 0 and actual >= 0) or (expected < 0 and actual < 0)),
    }


def run_model(tag: str, model: str, bars: dict[str, pd.DataFrame], args: argparse.Namespace) -> dict:
    print(f"\n=== {tag} ({model}) ===")
    predictor = load_predictor(model, device=args.device)
    # Shared as-of indices from the longest series.
    ref = max(bars.values(), key=len)
    last = len(ref) - args.pred_len - 1
    first = args.lookback - 1
    asofs = list(range(first, last + 1, args.step))
    asofs = asofs[-args.windows :]
    print(f"as-of windows: {len(asofs)} | lookback={args.lookback} pred_len={args.pred_len}")

    windows = []
    all_picks = []
    ew_nav = 1.0
    for ai in asofs:
        rows = []
        for sym, df in bars.items():
            # Map calendar time from ref to each symbol's index.
            asof_ts = pd.Timestamp(ref["timestamps"].iloc[ai])
            idx = int(pd.to_datetime(df["timestamps"]).searchsorted(asof_ts, side="right") - 1)
            if idx < 0:
                continue
            if abs((pd.Timestamp(df["timestamps"].iloc[idx]) - asof_ts).total_seconds()) > args.minutes * 60 * 2:
                continue
            row = score_intraday(
                predictor,
                sym,
                df,
                asof_idx=idx,
                lookback=args.lookback,
                pred_len=args.pred_len,
                bar_minutes=args.minutes,
            )
            if row is not None:
                rows.append(row)
        rows.sort(key=lambda r: r["expected_return"], reverse=True)
        picks = rows[: args.top]
        if not picks:
            continue
        ew = float(np.mean([p["actual_return"] for p in picks]))
        ew_nav *= 1.0 + ew
        hits = sum(1 for p in picks if p["direction_hit"])
        windows.append(
            {
                "asof": picks[0]["asof"],
                "ew_return": ew,
                "hits": hits,
                "n": len(picks),
                "picks": picks,
            }
        )
        all_picks.extend(picks)
        print(
            f"  {picks[0]['asof']} ew={ew:+.3%} hits={hits}/{len(picks)} "
            f"top={[p['symbol'] for p in picks]}"
        )

    hit_rate = (
        sum(1 for p in all_picks if p["direction_hit"]) / len(all_picks) if all_picks else None
    )
    return {
        "model": model,
        "tag": tag,
        "summary": {
            "n_picks": len(all_picks),
            "hit_rate": hit_rate,
            "ew_total_return": ew_nav - 1.0,
            "final_nav": ew_nav,
            "n_windows": len(windows),
            "mae_pp": (
                float(np.mean([abs(p["actual_return"] - p["expected_return"]) * 100 for p in all_picks]))
                if all_picks
                else None
            ),
        },
        "windows": windows,
    }


def main() -> int:
    args = parse_args()
    settings = load_settings()
    if not settings.configured:
        print("Missing Alpaca keys in .env")
        return 1

    if args.universe == "spus100":
        symbols = list(SPUS100)
    else:
        raw_syms = args.symbols.strip() or ",".join(DEFAULT_SYMBOLS)
        symbols = [s.strip().upper() for s in raw_syms.split(",") if s.strip()]
    print(
        f"Fetching IEX {args.minutes}m bars | symbols={len(symbols)} days={args.days} "
        f"lookback={args.lookback}"
    )
    client = make_data_client(settings.api_key, settings.secret_key)
    bars = fetch_intraday(client, symbols, minutes=args.minutes, days=args.days)
    print(f"Got bars for {len(bars)}/{len(symbols)}")
    for sym, df in list(bars.items()):
        if len(df) < args.lookback + args.pred_len + 5:
            print(f"  drop {sym}: only {len(df)} bars")
            del bars[sym]
    if len(bars) < 3:
        print("Not enough symbols with history")
        return 1

    mini = run_model("mini", "stock-mini", bars, args)
    small = run_model("small", "stock-small", bars, args)

    out = {
        "params": {
            "minutes": args.minutes,
            "lookback": args.lookback,
            "pred_len": args.pred_len,
            "top": args.top,
            "windows": args.windows,
            "step": args.step,
            "days": args.days,
            "symbols": sorted(bars.keys()),
            "feed": "IEX",
            "note": (
                "Pilot only: equal-weight top-N each as-of, realize next pred_len bars. "
                "Not paper live path."
            ),
        },
        "mini": mini,
        "small": small,
    }
    out_dir = ROOT / "paper_results" / "tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"intraday_mini_vs_small_{args.minutes}m{'_spus100' if args.universe == 'spus100' else ''}.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("\n=== SUMMARY ===")
    print(json.dumps({"mini": mini["summary"], "small": small["summary"]}, indent=2))
    print(f"Saved -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
