"""Compare today's paper-run stock-small signals vs a fresh FT score pass."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from paper.data import drop_split_discontinuities
from paper.signals import load_predictor, score_symbol
from paper.yahoo_cache import get_yahoo_bars

PAPER = ROOT / "paper_results/runs/run_20260814_163506.json"
FT_MODEL = ROOT / "finetune_csv/finetuned/spus_small_v1/basemodel/best_model"
OUT = ROOT / "paper_results/tests/compare_paper_vs_ft_20260814.json"


def main() -> int:
    paper = json.loads(PAPER.read_text(encoding="utf-8"))
    params = paper.get("params") or {}
    lookback = int(params.get("lookback", 400))
    pred_len = int(params.get("pred_len", 1))
    sample_count = int(params.get("sample_count", 1))
    stock_sigs = sorted(
        paper["signals"],
        key=lambda s: -float(s.get("expected_return") or 0),
    )
    print(
        f"Paper run model params: lookback={lookback} pred_len={pred_len} "
        f"sample_count={sample_count} n={len(stock_sigs)}"
    )
    print("Paper used STOCK NeoQuasar/Kronos-small (from task.log) — NOT the new FT.")

    print(f"\nLoading FT: {FT_MODEL}")
    predictor = load_predictor(str(FT_MODEL), device="auto")

    symbols = [s["symbol"] for s in stock_sigs]
    print(f"Loading SPUS bars for {len(symbols)} symbols...")
    raw = get_yahoo_bars("spus", symbols, refresh=False, max_age_days=3)
    bars, split_drops = drop_split_discontinuities(raw, max_abs_ret=0.40)
    if split_drops:
        print(
            "Dropped split/jump artifacts: "
            + ", ".join(f"{s}(|r|={j:.0%})" for s, j in split_drops[:15])
        )
    print(f"Got bars for {len(bars)}/{len(symbols)}")

    ft = []
    for i, s in enumerate(stock_sigs, 1):
        sym = s["symbol"]
        df = bars.get(sym)
        if df is None or df.empty:
            print(f"  [{i}/{len(stock_sigs)}] {sym}: no bars")
            continue
        sig = score_symbol(
            predictor,
            sym,
            df,
            lookback=lookback,
            pred_len=pred_len,
            sample_count=sample_count,
        )
        if sig is None:
            print(f"  [{i}/{len(stock_sigs)}] {sym}: fail")
            continue
        er = float(sig.expected_return)
        print(f"  [{i}/{len(stock_sigs)}] {sym}: ft={er*100:+.2f}% stock={float(s['expected_return'])*100:+.2f}%")
        ft.append(
            {
                "symbol": sym,
                "expected_return": er,
                "last_close": float(sig.last_close),
                "pred_close": float(sig.pred_close),
                "stock_er": float(s["expected_return"]),
                "stock_pred": float(s.get("pred_close") or 0),
            }
        )

    ft.sort(key=lambda x: -x["expected_return"])
    stock_top = [x["symbol"] for x in stock_sigs[:10]]
    ft_top = [x["symbol"] for x in ft[:10]]
    deltas = sorted(
        (
            {
                "symbol": x["symbol"],
                "stock_er": x["stock_er"],
                "ft_er": x["expected_return"],
                "delta": x["expected_return"] - x["stock_er"],
            }
            for x in ft
        ),
        key=lambda z: -abs(z["delta"]),
    )

    report = {
        "paper_run": str(PAPER),
        "ft_model": str(FT_MODEL),
        "params": {"lookback": lookback, "pred_len": pred_len, "sample_count": sample_count},
        "stock_top10": [
            {"symbol": s["symbol"], "er": float(s["expected_return"])} for s in stock_sigs[:10]
        ],
        "ft_top10": [
            {"symbol": x["symbol"], "er": x["expected_return"]} for x in ft[:10]
        ],
        "top10_overlap": sorted(set(stock_top) & set(ft_top)),
        "top10_only_stock": sorted(set(stock_top) - set(ft_top)),
        "top10_only_ft": sorted(set(ft_top) - set(stock_top)),
        "biggest_abs_deltas": deltas[:20],
        "ft_all": ft,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== PAPER TOP10 (stock small) ===")
    for s in stock_sigs[:10]:
        print(f"  {s['symbol']:6} {float(s['expected_return'])*100:+7.2f}%")
    print("=== FT TOP10 ===")
    for x in ft[:10]:
        print(f"  {x['symbol']:6} {x['expected_return']*100:+7.2f}%")
    print(f"\nOverlap: {report['top10_overlap']}")
    print(f"Only paper: {report['top10_only_stock']}")
    print(f"Only FT:    {report['top10_only_ft']}")
    print("\nBiggest |delta|:")
    for z in deltas[:12]:
        print(
            f"  {z['symbol']:6} stock={z['stock_er']*100:+6.2f}% "
            f"ft={z['ft_er']*100:+6.2f}% d={z['delta']*100:+6.2f}%"
        )
    print(f"\nSaved -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
