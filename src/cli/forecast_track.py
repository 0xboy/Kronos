"""CLI: freeze today's top predictions, then check them after ~5 trading days.

  python main.py forecast-track --freeze
  python main.py forecast-track --check
  python main.py forecast-track --check --refresh
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from forecast.track import check_card, default_from_report, freeze_card, live_artifact_paths
from forecast.week import iso_week_id, organize_forecast_root, week_dir


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Track whether Kronos top predictions come true")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--freeze", action="store_true", help="Lock current top predictions")
    g.add_argument("--check", action="store_true", help="Score frozen card vs live Yahoo")
    g.add_argument(
        "--organize",
        action="store_true",
        help="Tidy forecasts/ root into weeks/ + legacy",
    )
    p.add_argument("--refresh", action="store_true", help="With --check, force Yahoo refresh")
    p.add_argument(
        "--from-report",
        default="",
        help="Source report for --freeze (default: current week prediction_report_all/top)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.organize:
        info = organize_forecast_root()
        print(f"Organized forecasts/ -> current={info['current_week']}")
        print(f"  live: {info['live_dir']}")
        if info["moved_legacy"]:
            print(f"  legacy: {', '.join(info['moved_legacy'])}")
        return 0

    if args.freeze:
        src = Path(args.from_report) if args.from_report else default_from_report()
        out = freeze_card(src)
        card = json.loads(out.read_text(encoding="utf-8"))
        _, _, report_txt = live_artifact_paths()
        wid = iso_week_id(card.get("asof_last_close"))
        print(f"Frozen -> {out}")
        print(f"Asof last close: {card['asof_last_close']}")
        print(f"Check after:     {card['target_check_date']} (or later)")
        print(f"Week archive -> {week_dir(wid)}")
        print(f"Report txt -> {report_txt}")
        return 0

    try:
        check_path = check_card(refresh=args.refresh)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    check = json.loads(check_path.read_text(encoding="utf-8"))
    _, _, report_txt = live_artifact_paths()
    print(f"Checked -> {check_path}")
    print(f"Status: {check['status']} | today={check['today']} target={check['target_check_date']}")
    for mkt, block in check["markets"].items():
        print(
            f"  {mkt}: direction hits {block['direction_hits']}/{block['scored']} "
            f"({(block['direction_hit_rate'] or 0)*100:.0f}%) "
            f"MAE={block['mean_abs_error_pct_points']} pp"
        )
        for r in block["picks"][:5]:
            hit = "HIT" if r["direction_hit"] else ("MISS" if r["direction_hit"] is False else "?")
            print(
                f"    {r['rank']}. {r['symbol']:6} exp {r['expected_return_pct']:+6.2f}% "
                f"act {r['actual_return_pct'] if r['actual_return_pct'] is not None else float('nan'):+6.2f}% "
                f"[{hit}]"
            )
    wid = iso_week_id(check.get("asof_last_close"))
    print(f"Week archive -> {week_dir(wid)}")
    print(f"Report txt -> {report_txt}")
    return 0


def console_main() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    console_main()
