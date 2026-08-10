"""Fetch / check Yahoo caches for SPUS100, XK100, commodities, and crypto (separate folders).

  # download equity universes
  .venv/Scripts/python.exe scripts/fetch_yahoo_cache.py

  # commodities as TRY/gram
  .venv/Scripts/python.exe scripts/fetch_yahoo_cache.py --universe commodities

  # crypto (USD)
  .venv/Scripts/python.exe scripts/fetch_yahoo_cache.py --universe crypto

  # only check what we already have
  .venv/Scripts/python.exe scripts/fetch_yahoo_cache.py --check

  # force re-download
  .venv/Scripts/python.exe scripts/fetch_yahoo_cache.py --refresh

  # wipe CSVs then re-download (after splits etc.)
  .venv/Scripts/python.exe scripts/fetch_yahoo_cache.py --universe spus --purge
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # repo root
sys.path.insert(0, str(ROOT))

from paper.commodities import COMMODITY_LABELS, get_commodity_try_gram_bars
from paper.crypto import CRYPTO_LABELS
from paper.universe import SPUS100, XK100
from paper.yahoo_cache import (
    CACHE_ROOT,
    check_cache,
    get_yahoo_bars,
    purge_universe_cache,
    scan_cache_discontinuities,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Yahoo cache fetch/check for SPUS + XK100 + commodities + crypto")
    p.add_argument(
        "--universe",
        choices=("spus", "xk100", "commodities", "crypto", "both", "all"),
        default="both",
    )
    p.add_argument("--check", action="store_true", help="Only report cache status")
    p.add_argument("--refresh", action="store_true", help="Force re-download")
    p.add_argument(
        "--purge",
        action="store_true",
        help="Delete universe CSV cache before download (implies refresh)",
    )
    p.add_argument("--max-age-days", type=int, default=1)
    p.add_argument("--period", default="2y")
    return p.parse_args()


def symbols_for(universe: str) -> list[str]:
    if universe == "spus":
        return list(SPUS100)
    if universe == "commodities":
        return list(COMMODITY_LABELS)
    if universe == "crypto":
        return list(CRYPTO_LABELS)
    return [f"{t}.IS" for t in XK100]


def run_one(universe: str, args: argparse.Namespace) -> dict:
    syms = symbols_for(universe)
    if args.check:
        report = check_cache(universe, syms)
        print(
            f"[{universe}] dir={report['cache_dir']} files={report['csv_files']} "
            f"ok>={report['ok_ge_400_bars']} thin={report['thin']} "
            f"missing={report['missing_or_empty']}"
        )
        bad = [d for d in report["details"] if d["status"] != "ok"][:15]
        if bad:
            print(f"  sample issues: {bad}")
        return report

    print(f"=== {universe} | {len(syms)} symbols ===")
    if args.purge and universe not in ("commodities",):
        n = purge_universe_cache(universe)
        print(f"Purged {n} cached CSV files under {universe}")
        args.refresh = True
    if universe == "commodities":
        bars = get_commodity_try_gram_bars(
            period=args.period,
            refresh=args.refresh,
            max_age_days=args.max_age_days,
        )
    else:
        bars = get_yahoo_bars(
            universe,
            syms,
            period=args.period,
            refresh=args.refresh,
            max_age_days=args.max_age_days,
        )
    report = check_cache(universe, syms)
    print(
        f"[{universe}] available {len(bars)}/{len(syms)} | "
        f"ok>={report['ok_ge_400_bars']} thin={report['thin']} "
        f"missing={report['missing_or_empty']}"
    )
    if universe in ("spus", "xk100"):
        cliffs = scan_cache_discontinuities(universe, syms, max_abs_ret=0.40)
        if cliffs:
            print(f"WARNING: {len(cliffs)} series still have |daily ret|>40%:")
            for row in cliffs[:10]:
                print(f"  {row['symbol']} max|r|={row['max_abs_ret']:.0%}")
        else:
            print("Split-scan OK: no |daily ret|>40% cliffs")
    return report


def main() -> int:
    args = parse_args()
    if args.universe == "both":
        universes = ["spus", "xk100"]
    elif args.universe == "all":
        universes = ["spus", "xk100", "commodities", "crypto"]
    else:
        universes = [args.universe]
    reports = {u: run_one(u, args) for u in universes}
    out = ROOT / "paper_results" / "tests" / "yahoo_cache_check.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(f"Cache root: {CACHE_ROOT}")
    print(f"Report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
