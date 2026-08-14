"""Compare stock Kronos-small vs local SPUS FT on SPUS100 (same cache/bars)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from paper.signals import load_predictor, score_symbol
from paper.universe import SPUS100
from paper.yahoo_cache import get_yahoo_bars
from paper.data import drop_split_discontinuities


def score_universe(predictor, symbols, lookback: int, pred_len: int, sample_count: int):
    raw = get_yahoo_bars("spus", list(symbols), refresh=False, max_age_days=3)
    out = []
    for i, sym in enumerate(symbols, 1):
        bars = raw.get(sym)
        if bars is None or bars.empty:
            print(f"  [{i}/{len(symbols)}] {sym}: no bars")
            continue
        bars = drop_split_discontinuities(bars)
        sig = score_symbol(
            predictor,
            sym,
            bars,
            lookback=lookback,
            pred_len=pred_len,
            sample_count=sample_count,
        )
        if sig is None:
            print(f"  [{i}/{len(symbols)}] {sym}: score failed")
            continue
        er = float(sig.expected_return)
        print(f"  [{i}/{len(symbols)}] {sym}: {er*100:+.2f}%")
        out.append(
            {
                "symbol": sym,
                "expected_return": er,
                "last_close": float(sig.last_close),
                "pred_close": float(sig.pred_close),
            }
        )
    out.sort(key=lambda x: -x["expected_return"])
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lookback", type=int, default=400)
    p.add_argument("--pred-len", type=int, default=1)
    p.add_argument("--sample-count", type=int, default=1)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument(
        "--stock-model",
        default="NeoQuasar/Kronos-small",
    )
    p.add_argument(
        "--ft-model",
        default=str(
            ROOT
            / "finetune_csv/finetuned/spus_small_v1/basemodel/best_model"
        ),
    )
    p.add_argument("--device", default="auto")
    p.add_argument(
        "--out",
        default=str(ROOT / "paper_results/tests/compare_stock_vs_ft_spus.json"),
    )
    args = p.parse_args()

    symbols = list(SPUS100)
    if args.limit > 0:
        symbols = symbols[: args.limit]

    print(f"Symbols: {len(symbols)} | lookback={args.lookback} pred_len={args.pred_len}")
    print(f"\n=== STOCK {args.stock_model} ===")
    stock_pred = load_predictor(args.stock_model, device=args.device)
    stock = score_universe(
        stock_pred, symbols, args.lookback, args.pred_len, args.sample_count
    )

    print(f"\n=== FT {args.ft_model} ===")
    ft_pred = load_predictor(args.ft_model, device=args.device)
    ft = score_universe(
        ft_pred, symbols, args.lookback, args.pred_len, args.sample_count
    )

    by_stock = {x["symbol"]: x for x in stock}
    by_ft = {x["symbol"]: x for x in ft}
    common = sorted(set(by_stock) & set(by_ft))
    deltas = []
    for sym in common:
        a = by_stock[sym]["expected_return"]
        b = by_ft[sym]["expected_return"]
        deltas.append(
            {
                "symbol": sym,
                "stock_er": a,
                "ft_er": b,
                "delta_ft_minus_stock": b - a,
                "stock_pred": by_stock[sym]["pred_close"],
                "ft_pred": by_ft[sym]["pred_close"],
                "last": by_stock[sym]["last_close"],
            }
        )
    deltas.sort(key=lambda x: -abs(x["delta_ft_minus_stock"]))

    top_n = 10
    stock_top = [x["symbol"] for x in stock[:top_n]]
    ft_top = [x["symbol"] for x in ft[:top_n]]
    overlap = sorted(set(stock_top) & set(ft_top))

    report = {
        "params": {
            "lookback": args.lookback,
            "pred_len": args.pred_len,
            "sample_count": args.sample_count,
            "stock_model": args.stock_model,
            "ft_model": args.ft_model,
            "n_symbols": len(common),
        },
        "stock_top10": stock[:top_n],
        "ft_top10": ft[:top_n],
        "top10_overlap": overlap,
        "top10_only_stock": sorted(set(stock_top) - set(ft_top)),
        "top10_only_ft": sorted(set(ft_top) - set(stock_top)),
        "biggest_abs_deltas": deltas[:20],
        "stock_all": stock,
        "ft_all": ft,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== TOP10 STOCK ===")
    for x in stock[:top_n]:
        print(f"  {x['symbol']:6} {x['expected_return']*100:+7.2f}%")
    print("=== TOP10 FT ===")
    for x in ft[:top_n]:
        print(f"  {x['symbol']:6} {x['expected_return']*100:+7.2f}%")
    print(f"\nOverlap top10: {overlap}")
    print(f"Only stock: {report['top10_only_stock']}")
    print(f"Only FT:    {report['top10_only_ft']}")
    print("\nBiggest |delta| (FT - stock):")
    for x in deltas[:12]:
        print(
            f"  {x['symbol']:6} stock={x['stock_er']*100:+6.2f}%  "
            f"ft={x['ft_er']*100:+6.2f}%  d={x['delta_ft_minus_stock']*100:+6.2f}%"
        )
    print(f"\nSaved -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
