"""Fetch / check Yahoo caches for top-10 exchanges, crypto, commodities.

  # 2020+ for FT prep (default start)
  python main.py cache --universe ftpack --start 2020-01-01 --refresh

  # equities only (top 10 boards)
  python main.py cache --universe top10 --start 2020-01-01

  # legacy
  python main.py cache --universe both
  python main.py cache --universe crypto --start 2020-01-01
  python main.py cache --universe commodities --start 2020-01-01

  # session / experiment checks: realign last 10 bars only if wrong
  python main.py cache --universe xk100 --align-tail 10
"""
from __future__ import annotations

from config.paths import TESTS
import argparse
import json
import sys
from pathlib import Path

from universe.catalog import SPUS100, XK100
from universe.commodities import COMMODITY_LABELS, get_commodity_try_gram_bars
from universe.crypto import CRYPTO_LABELS
from universe.exchanges import EXCHANGES, TOP10_IDS
from data.yahoo_cache import (
    CACHE_ROOT,
    align_last_bars,
    check_cache,
    get_yahoo_bars,
    purge_universe_cache,
    scan_cache_discontinuities,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Yahoo cache fetch/check")
    p.add_argument(
        "--universe",
        choices=(
            "spus",
            "xk100",
            "commodities",
            "crypto",
            "both",
            "all",
            "top10",
            "ftpack",
            *TOP10_IDS,
        ),
        default="ftpack",
        help="ftpack = top10 + crypto + commodities (default)",
    )
    p.add_argument("--check", action="store_true", help="Only report cache status")
    p.add_argument("--refresh", action="store_true", help="Force re-download")
    p.add_argument(
        "--purge",
        action="store_true",
        help="Delete universe CSV cache before download (implies refresh)",
    )
    p.add_argument(
        "--align-tail",
        type=int,
        nargs="?",
        const=10,
        default=None,
        metavar="N",
        help="Realign last N daily bars from Yahoo only if they disagree (default N=10). "
        "For session/experiment checks; keeps long history.",
    )
    p.add_argument(
        "--force-align",
        action="store_true",
        help="With --align-tail, rewrite tails even when they already match",
    )
    p.add_argument("--max-age-days", type=int, default=1)
    p.add_argument(
        "--period",
        default=None,
        help="Yahoo period if --start not set (e.g. 2y, 5y, max)",
    )
    p.add_argument(
        "--start",
        default="2020-01-01",
        help="Download from this date (YYYY-MM-DD). Empty string disables.",
    )
    p.add_argument("--end", default=None, help="Optional end date YYYY-MM-DD")
    return p.parse_args()


def symbols_for(universe: str) -> list[str]:
    if universe == "spus" or universe == "us":
        return list(SPUS100)
    if universe == "commodities":
        return list(COMMODITY_LABELS)
    if universe == "crypto":
        return list(CRYPTO_LABELS)
    if universe == "xk100" or universe == "bist":
        return [f"{t}.IS" for t in XK100]
    if universe in EXCHANGES:
        return list(EXCHANGES[universe]["yahoo_symbols"])
    return [f"{t}.IS" for t in XK100]


def cache_id_for(universe: str) -> str:
    if universe in EXCHANGES:
        return str(EXCHANGES[universe]["cache_id"])
    return universe


def run_one(universe: str, args: argparse.Namespace) -> dict:
    cache_id = cache_id_for(universe)
    syms = symbols_for(universe)
    start = args.start or None
    period = args.period or ("2y" if not start else "max")

    if args.check:
        report = check_cache(cache_id, syms)
        print(
            f"[{cache_id}] dir={report['cache_dir']} files={report['csv_files']} "
            f"ok>={report['ok_ge_400_bars']} thin={report['thin']} "
            f"missing={report['missing_or_empty']}"
        )
        bad = [d for d in report["details"] if d["status"] != "ok"][:15]
        if bad:
            print(f"  sample issues: {bad}")
        return report

    print(f"=== {universe} -> cache={cache_id} | {len(syms)} symbols | start={start} period={period} ===")
    if args.purge and cache_id not in ("commodities",):
        n = purge_universe_cache(cache_id)
        print(f"Purged {n} cached CSV files under {cache_id}")
        args.refresh = True

    if args.align_tail is not None:
        if cache_id == "commodities":
            raise SystemExit("--align-tail not supported for commodities (use --refresh)")
        bars = align_last_bars(
            cache_id,
            syms,
            n_bars=int(args.align_tail),
            force=bool(args.force_align),
        )
        report = check_cache(cache_id, syms)
    elif cache_id == "commodities":
        bars = get_commodity_try_gram_bars(
            period=period,
            start=start,
            end=args.end,
            refresh=args.refresh,
            max_age_days=args.max_age_days,
        )
        # check_cache expects label names for commodities
        report = check_cache(cache_id, list(COMMODITY_LABELS))
    else:
        bars = get_yahoo_bars(
            cache_id,
            syms,
            period=period,
            start=start,
            end=args.end,
            refresh=args.refresh,
            max_age_days=args.max_age_days,
        )
        report = check_cache(cache_id, syms)

    print(
        f"[{cache_id}] available {len(bars)}/{len(syms)} | "
        f"ok>={report['ok_ge_400_bars']} thin={report['thin']} "
        f"missing={report['missing_or_empty']}"
    )
    if cache_id in ("spus", "xk100") or cache_id in {EXCHANGES[k]["cache_id"] for k in TOP10_IDS}:
        cliffs = scan_cache_discontinuities(cache_id, syms if cache_id != "commodities" else None, max_abs_ret=0.40)
        if cliffs:
            print(f"WARNING: {len(cliffs)} series still have |daily ret|>40%:")
            for row in cliffs[:10]:
                print(f"  {row['symbol']} max|r|={row['max_abs_ret']:.0%}")
        else:
            print("Split-scan OK: no |daily ret|>40% cliffs")
    return report


def main() -> int:
    args = parse_args()
    if args.start == "":
        args.start = None

    if args.universe == "both":
        universes = ["spus", "xk100"]
    elif args.universe == "all":
        universes = ["spus", "xk100", "commodities", "crypto"]
    elif args.universe == "top10":
        universes = list(TOP10_IDS)
    elif args.universe == "ftpack":
        universes = list(TOP10_IDS) + ["crypto", "commodities"]
    else:
        universes = [args.universe]

    reports = {u: run_one(u, args) for u in universes}
    out = TESTS / "yahoo_cache_check.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(f"Cache root: {CACHE_ROOT}")
    print(f"Report -> {out}")
    return 0


def console_main() -> None:
    raise SystemExit(main())

if __name__ == "__main__":
    console_main()
