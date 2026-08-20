"""Score Kronos on one universe at a time (SPUS100, XK100, commodities, or crypto).

Uses Yahoo data from disk cache (data/yahoo_cache/) — no re-download each run.
Markets stay separate. Commodities are priced in TRY per gram; crypto in USD.

  .venv/Scripts/python.exe scripts/fetch_yahoo_cache.py          # once
  .venv/Scripts/python.exe scripts/run_universe_test.py --universe spus
  .venv/Scripts/python.exe scripts/run_universe_test.py --universe xk100
  .venv/Scripts/python.exe scripts/run_universe_test.py --universe commodities
  .venv/Scripts/python.exe scripts/run_universe_test.py --universe crypto
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # repo root
sys.path.insert(0, str(ROOT))

from paper.commodities import COMMODITY_META, get_commodity_try_gram_bars
from paper.crypto import CRYPTO_META
from paper.models import DEFAULT_PAPER_MODEL
from paper.signals import DEFAULT_SAMPLE_COUNT, device_summary, load_predictor, score_symbol
from paper.universe import COMMODITIES, CRYPTO, SPUS100, XK100
from paper.xk100_rank import DEFAULT_CFG, cfg_to_dict, rank_signals
from paper.yahoo_cache import get_yahoo_bars
from paper.data import drop_split_discontinuities


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kronos universe test (Yahoo cache)")
    p.add_argument("--universe", choices=("spus", "xk100", "commodities", "crypto"), required=True)
    p.add_argument("--limit", type=int, default=0, help="First N symbols only (0 = all)")
    p.add_argument("--lookback", type=int, default=400)
    p.add_argument("--pred-len", type=int, default=1)
    p.add_argument(
        "--sample-count",
        type=int,
        default=0,
        help=f"Kronos sample paths (0 = {DEFAULT_SAMPLE_COUNT} for all markets)",
    )
    p.add_argument(
        "--model",
        default=DEFAULT_PAPER_MODEL,
        help="Model alias or HF/local path (default: stock-small = NeoQuasar/Kronos-small)",
    )
    p.add_argument(
        "--device",
        default="auto",
        help="Inference device: auto (CUDA if available), cuda, cuda:0, cpu",
    )
    p.add_argument("--refresh", action="store_true", help="Force Yahoo re-download")
    p.add_argument("--max-age-days", type=int, default=1)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.universe == "spus":
        labels = list(SPUS100)
        yahoo_syms = labels
        market = {
            "id": "spus",
            "name": "SPUS ETF top 100 by weight",
            "exchange": "NYSE / Nasdaq",
            "currency": "USD",
            "unit": "share",
            "data": "yahoo_cache",
        }
    elif args.universe == "xk100":
        labels = list(XK100)
        yahoo_syms = [f"{t}.IS" for t in labels]
        market = {
            "id": "xk100",
            "name": "BIST Katılım 100 (XK100)",
            "exchange": "Borsa Istanbul",
            "currency": "TRY",
            "unit": "share",
            "data": "yahoo_cache",
        }
    elif args.universe == "commodities":
        labels = list(COMMODITIES)
        yahoo_syms = labels
        market = {
            "id": "commodities",
            "name": "Metals (TRY per gram)",
            "exchange": "COMEX / LME via Yahoo × USDTRY",
            "currency": "TRY",
            "unit": "gram",
            "data": "yahoo_cache_try_gram",
            "names": {k: v["name"] for k, v in COMMODITY_META.items()},
        }
    else:
        labels = list(CRYPTO)
        yahoo_syms = labels
        market = {
            "id": "crypto",
            "name": "Top cryptocurrencies (USD)",
            "exchange": "Crypto markets via Yahoo Finance",
            "currency": "USD",
            "unit": "coin",
            "data": "yahoo_cache",
            "names": {k: v["name"] for k, v in CRYPTO_META.items()},
        }

    if args.limit and args.limit > 0:
        labels = labels[: args.limit]
        yahoo_syms = yahoo_syms[: args.limit]

    print(f"Universe: {market['name']} | {len(labels)} symbols | {market['currency']}/{market['unit']}")
    print(f"Exchange: {market['exchange']} (evaluated alone)")
    print("Loading bars from Yahoo cache (download only if missing/stale)...")

    if args.universe == "commodities":
        bars = get_commodity_try_gram_bars(
            refresh=args.refresh,
            max_age_days=args.max_age_days,
        )
        if args.limit and args.limit > 0:
            bars = {k: bars[k] for k in labels if k in bars}
    else:
        raw = get_yahoo_bars(
            args.universe,
            yahoo_syms,
            refresh=args.refresh,
            max_age_days=args.max_age_days,
        )
        bars = {}
        for ysym, df in raw.items():
            key = ysym.replace(".IS", "") if args.universe == "xk100" else ysym
            bars[key] = df
        bars, split_drops = drop_split_discontinuities(bars, max_abs_ret=0.40)
        if split_drops:
            print(
                "Dropped split/jump artifacts: "
                + ", ".join(f"{s}(|r|={j:.0%})" for s, j in split_drops[:15])
            )

    print(f"Got bars for {len(bars)}/{len(labels)}")
    print("Loading Kronos...")
    hw = device_summary(args.device)
    print(
        f"Compute: device={hw['device']}"
        + (f" gpu={hw['gpu']}" if hw.get("gpu") else "")
        + f" torch={hw['torch']}"
    )
    predictor = load_predictor(args.model, device=args.device)

    use_xk100_rank = args.universe == "xk100"
    if args.sample_count and args.sample_count > 0:
        sample_count = args.sample_count
    else:
        sample_count = DEFAULT_SAMPLE_COUNT
    xk_cfg = DEFAULT_CFG if use_xk100_rank else None
    if use_xk100_rank:
        print(
            f"XK100 rank cfg: min_price={xk_cfg.min_price_try} "
            f"min_adv20={xk_cfg.min_adv20_try} max_abs_exp={xk_cfg.max_abs_expected} "
            f"min_tstat={xk_cfg.min_tstat} sample_count={sample_count}"
        )
    else:
        print(f"sample_count={sample_count}")

    signals = []
    skipped = []
    filter_drops_pre: list[dict] = []
    score_labels = list(labels)
    if use_xk100_rank and xk_cfg is not None:
        from paper.xk100_rank import passes_filters

        score_labels = []
        for symbol in labels:
            df = bars.get(symbol)
            if df is None:
                skipped.append({"symbol": symbol, "reason": "no bars"})
                continue
            ok, reason = passes_filters(df, xk_cfg)
            if not ok:
                filter_drops_pre.append({"symbol": symbol, "reason": reason})
                continue
            score_labels.append(symbol)
        print(
            f"Pre-filter: scoring {len(score_labels)}/{len(labels)} "
            f"(dropped {len(filter_drops_pre)} on price/ADV/vol)"
        )

    for i, symbol in enumerate(score_labels, 1):
        df = bars.get(symbol)
        if df is None:
            skipped.append({"symbol": symbol, "reason": "no bars"})
            continue
        print(f"[{i}/{len(score_labels)}] scoring {symbol} ({len(df)} bars)...")
        try:
            sig = score_symbol(
                predictor,
                symbol,
                df,
                lookback=args.lookback,
                pred_len=args.pred_len,
                sample_count=sample_count,
            )
        except Exception as exc:  # noqa: BLE001
            skipped.append({"symbol": symbol, "reason": str(exc)})
            continue
        if sig is None:
            skipped.append(
                {"symbol": symbol, "reason": f"need>={args.lookback} bars, have {len(df)}"}
            )
            continue
        signals.append(sig)
        unit = "TRY/g" if args.universe == "commodities" else ("USD" if args.universe == "crypto" else "")
        print(
            f"  -> ret={sig.expected_return:+.2%} "
            f"last={sig.last_close:.4f}{(' ' + unit) if unit else ''} "
            f"pred={sig.pred_close:.4f}{(' ' + unit) if unit else ''}"
            + (f" std={sig.return_std:.4f}" if sample_count > 1 else "")
        )

    filter_drops: list[dict] = list(filter_drops_pre) if use_xk100_rank else []
    if use_xk100_rank and xk_cfg is not None:
        signals, gate_drops = rank_signals(signals, bars, xk_cfg)
        filter_drops.extend(gate_drops)
        print(
            f"\n=== {market['id'].upper()} ranked by vol_norm score "
            f"({len(signals)} kept, {len(filter_drops)} filtered) ==="
        )
        for s in signals[:20]:
            print(f"{s.symbol:10} score={s.score:+7.3f} ret={s.expected_return:+7.2%}")
    else:
        signals.sort(key=lambda s: s.expected_return, reverse=True)
        print(f"\n=== {market['id'].upper()} ranked signals ({len(signals)}) ===")
        for s in signals[:20]:
            print(f"{s.symbol:10} {s.expected_return:+7.2%}")

    out = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "market": market,
        "params": {
            "lookback": args.lookback,
            "pred_len": args.pred_len,
            "sample_count": sample_count,
            "model": args.model,
            "device": hw,
            "symbols": labels,
            **({"xk100_rank": cfg_to_dict(xk_cfg)} if xk_cfg is not None else {}),
        },
        "signals": [
            {
                "symbol": s.symbol,
                "name": (
                    COMMODITY_META.get(s.symbol, {}).get("name")
                    if args.universe == "commodities"
                    else CRYPTO_META.get(s.symbol, {}).get("name")
                    if args.universe == "crypto"
                    else None
                ),
                "expected_return": s.expected_return,
                "last_close": s.last_close,
                "pred_close": s.pred_close,
                "bars": s.bars,
                "return_std": s.return_std,
                "sample_count": s.sample_count,
                "score": s.score,
            }
            for s in signals
        ],
        "skipped": skipped,
        "filter_drops": filter_drops,
    }
    out_dir = ROOT / "paper_results" / "tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"test_{market['id']}_{stamp}.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
