"""CLI: build clean top-N prediction reports from latest universe test runs.

  python main.py forecast-report
  python main.py forecast-report --universe commodities
  python main.py forecast-report --universe all
"""
from __future__ import annotations

import argparse

from forecast.report import build_prediction_report
from forecast.week import read_current_week_id


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build top prediction report JSON")
    p.add_argument(
        "--universe",
        choices=("spus", "xk100", "commodities", "crypto", "all"),
        default="commodities",
    )
    p.add_argument("--top", type=int, default=10)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    report, out = build_prediction_report(args.universe, top=args.top)
    print(f"Saved -> {out} (week={read_current_week_id()})")
    keys = (
        ["spus", "xk100", "commodities", "crypto"]
        if args.universe == "all"
        else [args.universe]
    )
    for key in keys:
        block = report[key]
        print(f"\n=== {key.upper()} top ===")
        if block.get("rank_rule"):
            print(f"  rank_rule: {block['rank_rule']['description']}")
        for r in block["top10"]:
            name = f" ({r['name']})" if r.get("name") else ""
            unit = f" {r['unit']}" if r.get("unit") else ""
            score_bit = f" score={r['score']:+.3f}" if r.get("score") is not None else ""
            print(
                f"  {r['rank']:2}. {r['symbol']:10}{name:12} "
                f"{r['expected_return_pct']:+6.2f}%{score_bit}  "
                f"last={r['last_close']:,.4f}{unit} -> pred={r['pred_close']:,.4f}{unit}"
            )
    return 0


def console_main() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    console_main()
