"""Summarize realized one-day SPUS picks for stock-small vs SPUS fine-tune."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "paper_results" / "tests"
STOCK_PATH = TESTS / "walkforward_spus_2026H1_week_stock.json"
FT_PATH = TESTS / "walkforward_spus_2026H1_week_ft.json"
OUT_PATH = TESTS / "week_realized_stock_vs_ft.json"


def _pct(value: float) -> float:
    return round(float(value) * 100, 4)


def main() -> int:
    stock = json.loads(STOCK_PATH.read_text(encoding="utf-8"))
    ft = json.loads(FT_PATH.read_text(encoding="utf-8"))
    stock_by_date = {w["asof"]: w for w in stock["windows"]}
    ft_by_date = {w["asof"]: w for w in ft["windows"]}

    daily = []
    trade_rows = []
    for asof in stock["params"]["asofs"]:
        sw = stock_by_date[asof]
        fw = ft_by_date[asof]
        stock_symbols = [p["symbol"] for p in sw["picks"]]
        ft_symbols = [p["symbol"] for p in fw["picks"]]
        daily.append(
            {
                "asof": asof,
                "realized_session": {
                    "2026-08-07": "2026-08-10",
                    "2026-08-10": "2026-08-11",
                    "2026-08-11": "2026-08-12",
                    "2026-08-12": "2026-08-13",
                }[asof],
                "stock_ew_pct": _pct(sw["ew_period_return"]),
                "ft_ew_pct": _pct(fw["ew_period_return"]),
                "stock_weighted_pct": _pct(sw["score_weight_period_return"]),
                "ft_weighted_pct": _pct(fw["score_weight_period_return"]),
                "stock_hits": sw["direction_hits"],
                "ft_hits": fw["direction_hits"],
                "overlap": sorted(set(stock_symbols) & set(ft_symbols)),
                "stock_only": sorted(set(stock_symbols) - set(ft_symbols)),
                "ft_only": sorted(set(ft_symbols) - set(stock_symbols)),
            }
        )
        for label, window in (("Stock small", sw), ("SPUS FT", fw)):
            for pick in window["picks"]:
                trade_rows.append(
                    {
                        "asof": asof,
                        "realized_session": daily[-1]["realized_session"],
                        "model": label,
                        "symbol": pick["symbol"],
                        "expected_pct": _pct(pick["expected_return"]),
                        "actual_pct": _pct(pick["actual_return"]),
                        "direction_hit": pick["actual_return"] > 0,
                    }
                )

    report = {
        "method": {
            "description": (
                "Each as-of close ranks SPUS; buy top 10, realize at the next "
                "trading-day close, then fully rebalance. No fees/slippage."
            ),
            "asofs": stock["params"]["asofs"],
            "realized_sessions": [d["realized_session"] for d in daily],
            "lookback": stock["params"]["lookback"],
            "pred_len": stock["params"]["pred_len"],
            "top": stock["params"]["top"],
            "sample_count": stock["params"]["sample_count"],
            "bars_available": stock["data"]["bars_available"],
            "dropped": stock["data"]["split_drops"],
            "important_limit": (
                "Friday 2026-08-14 is still open/not present as a completed Yahoo "
                "daily bar, so realized metrics cover Monday through Thursday."
            ),
            "validation_caveat": (
                "The FT checkpoint was selected using validation through 2026-08-13. "
                "Its weights trained only through 2026-06-30, but epoch selection "
                "overlaps this evaluation week; treat this as diagnostic, not clean OOS proof."
            ),
        },
        "summary": {
            "stock": {
                "ew_total_pct": _pct(stock["summary"]["ew_cumulative"]["total_return"]),
                "weighted_total_pct": _pct(
                    stock["summary"]["score_weight_sleeve"]["total_return"]
                ),
                "hit_rate_pct": _pct(stock["summary"]["hit_rate"]),
                "mae_pp": stock["summary"]["mae_pp"],
            },
            "ft": {
                "ew_total_pct": _pct(ft["summary"]["ew_cumulative"]["total_return"]),
                "weighted_total_pct": _pct(
                    ft["summary"]["score_weight_sleeve"]["total_return"]
                ),
                "hit_rate_pct": _pct(ft["summary"]["hit_rate"]),
                "mae_pp": ft["summary"]["mae_pp"],
            },
            "ft_minus_stock": {
                "ew_pp": round(
                    _pct(ft["summary"]["ew_cumulative"]["total_return"])
                    - _pct(stock["summary"]["ew_cumulative"]["total_return"]),
                    4,
                ),
                "weighted_pp": round(
                    _pct(ft["summary"]["score_weight_sleeve"]["total_return"])
                    - _pct(stock["summary"]["score_weight_sleeve"]["total_return"]),
                    4,
                ),
                "hit_rate_pp": round(
                    _pct(ft["summary"]["hit_rate"])
                    - _pct(stock["summary"]["hit_rate"]),
                    4,
                ),
            },
        },
        "daily": daily,
        "trades": trade_rows,
    }
    OUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    for row in daily:
        print(
            f"{row['realized_session']}: stock EW {row['stock_ew_pct']:+.2f}% "
            f"FT EW {row['ft_ew_pct']:+.2f}% | overlap={row['overlap']}"
        )
    print(f"Saved -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
