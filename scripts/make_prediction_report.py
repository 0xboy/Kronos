"""Build clean top-N prediction reports from latest universe test runs.

  .venv/Scripts/python.exe scripts/make_prediction_report.py
  .venv/Scripts/python.exe scripts/make_prediction_report.py --universe commodities
  .venv/Scripts/python.exe scripts/make_prediction_report.py --universe all
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # repo root
RESULTS = ROOT / "paper_results"
FORECASTS = RESULTS / "forecasts"
TESTS = RESULTS / "tests"

from paper.commodities import COMMODITY_META  # noqa: E402
from paper.crypto import CRYPTO_META  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build top prediction report JSON")
    p.add_argument(
        "--universe",
        choices=("spus", "xk100", "commodities", "crypto", "all"),
        default="commodities",
    )
    p.add_argument("--top", type=int, default=10)
    return p.parse_args()


def load_latest(prefix: str) -> tuple[dict, Path]:
    files = sorted(TESTS.glob(f"test_{prefix}_*.json"))
    if not files:
        raise FileNotFoundError(f"No test_{prefix}_*.json in {TESTS}")
    path = files[-1]
    return json.loads(path.read_text(encoding="utf-8")), path


def clean(signals: list[dict], top_n: int, *, commodities: bool = False, crypto: bool = False) -> list[dict]:
    rows = []
    for s in signals:
        if s["pred_close"] <= 0:
            continue
        if abs(s["expected_return"]) > 1.0:  # filter |ret| > 100%
            continue
        row = {
            "rank": 0,
            "symbol": s["symbol"],
            "expected_return_pct": round(s["expected_return"] * 100, 2),
            "last_close": round(s["last_close"], 4),
            "pred_close": round(s["pred_close"], 4),
            "bars": s["bars"],
        }
        if commodities:
            meta = COMMODITY_META.get(s["symbol"], {})
            row["name"] = s.get("name") or meta.get("name")
            row["unit"] = "TRY/g"
            row["yahoo"] = meta.get("yahoo")
        elif crypto:
            meta = CRYPTO_META.get(s["symbol"], {})
            row["name"] = s.get("name") or meta.get("name")
            row["unit"] = "USD"
        rows.append(row)
    rows.sort(key=lambda r: r["expected_return_pct"], reverse=True)
    for i, r in enumerate(rows[:top_n], 1):
        r["rank"] = i
    return rows[:top_n]


def block_from(prefix: str, top_n: int) -> dict:
    data, path = load_latest(prefix)
    is_cmd = prefix == "commodities"
    is_crypto = prefix == "crypto"
    top = clean(data["signals"], top_n, commodities=is_cmd, crypto=is_crypto)
    top5 = top[:5]
    return {
        "source_run": path.name,
        "market": data.get("market"),
        "params": data.get("params"),
        "scored": len(data.get("signals", [])),
        "skipped": len(data.get("skipped", [])),
        "top5": top5,
        "top10": top[:10],
        "all_ranked": clean(data["signals"], 999, commodities=is_cmd, crypto=is_crypto),
    }


def main() -> int:
    args = parse_args()
    FORECASTS.mkdir(parents=True, exist_ok=True)
    if args.universe == "all":
        keys = ["spus", "xk100", "commodities", "crypto"]
    else:
        keys = [args.universe]

    report: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": "NeoQuasar/Kronos-small",
        "pred_len_days": 5,
        "note": (
            "expected_return = pred_close[5th business day] / last_close - 1. "
            "Commodities priced TRY per gram (futures × USDTRY). Crypto priced in USD."
        ),
    }
    for key in keys:
        report[key] = block_from(key, args.top)

    if args.universe == "commodities":
        out = FORECASTS / "prediction_report_commodities.json"
    elif args.universe == "all":
        out = FORECASTS / "prediction_report_all.json"
    else:
        out = RESULTS / f"prediction_report_{args.universe}.json"

    # Also keep legacy combined top name when both equity markets present
    if "spus" in report and "xk100" in report:
        legacy = {k: report[k] for k in ("ts", "model", "pred_len_days", "note", "spus", "xk100")}
        if "commodities" in report:
            legacy["commodities"] = report["commodities"]
        (FORECASTS / "prediction_report_top.json").write_text(
            json.dumps(legacy, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved -> {out}")
    for key in keys:
        block = report[key]
        print(f"\n=== {key.upper()} top ===")
        for r in block["top10"]:
            name = f" ({r['name']})" if r.get("name") else ""
            unit = f" {r['unit']}" if r.get("unit") else ""
            print(
                f"  {r['rank']:2}. {r['symbol']:10}{name:12} "
                f"{r['expected_return_pct']:+6.2f}%  "
                f"last={r['last_close']:,.4f}{unit} -> pred={r['pred_close']:,.4f}{unit}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
