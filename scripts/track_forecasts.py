"""Freeze today's top predictions, then check them after ~5 trading days.

  # freeze current top10 report as a bet card
  .venv/Scripts/python.exe scripts/track_forecasts.py --freeze

  # later: pull Yahoo and score hits
  .venv/Scripts/python.exe scripts/track_forecasts.py --check

  # force refresh Yahoo before check
  .venv/Scripts/python.exe scripts/track_forecasts.py --check --refresh
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]  # repo root
RESULTS = ROOT / "paper_results"
FORECASTS = RESULTS / "forecasts"
TESTS = RESULTS / "tests"
CARD = FORECASTS / "forecast_card.json"
CHECK = FORECASTS / "forecast_check.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Track whether Kronos top predictions come true")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--freeze", action="store_true", help="Lock current top predictions")
    g.add_argument("--check", action="store_true", help="Score frozen card vs live Yahoo")
    p.add_argument("--refresh", action="store_true", help="With --check, force Yahoo refresh")
    p.add_argument(
        "--from-report",
        default=str(FORECASTS / "prediction_report_top.json"),
        help="Source report for --freeze",
    )
    return p.parse_args()


def _horizon_end(asof: str, n: int = 5) -> str:
    start = pd.Timestamp(asof)
    # next n business days after asof
    days = pd.bdate_range(start=start + pd.Timedelta(days=1), periods=n)
    return str(days[-1].date())


def freeze(report_path: Path) -> Path:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    # last close dates from Yahoo cache if available
    asof = "2026-07-30"
    for sample in (
        ROOT / "data" / "yahoo_cache" / "commodities" / "GOLD.csv",
        ROOT / "data" / "yahoo_cache" / "spus" / "NVDA.csv",
    ):
        try:
            if sample.exists():
                df = pd.read_csv(sample)
                asof = str(pd.to_datetime(df["timestamps"]).max().date())
                break
        except Exception:
            pass

    card = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "model": report.get("model"),
        "pred_len_days": report.get("pred_len_days", 5),
        "asof_last_close": asof,
        "target_check_date": _horizon_end(asof, report.get("pred_len_days", 5)),
        "rule": (
            "After target_check_date, compare Yahoo close vs pred_close. "
            "Commodities: Yahoo futures × USDTRY → TRY/g. "
            "Direction hit = actual_return and expected_return same sign. "
            "Abs error = |actual_return - expected_return|."
        ),
        "markets": {},
    }

    from paper.commodities import COMMODITY_META

    for key in ("spus", "xk100", "commodities"):
        if key not in report:
            continue
        block = report[key]
        picks = []
        for row in block["top10"]:
            if key == "spus":
                yahoo = row["symbol"]
            elif key == "xk100":
                yahoo = f"{row['symbol']}.IS"
            else:
                yahoo = row.get("yahoo") or COMMODITY_META.get(row["symbol"], {}).get("yahoo")
            picks.append(
                {
                    "rank": row["rank"],
                    "symbol": row["symbol"],
                    "name": row.get("name"),
                    "yahoo": yahoo,
                    "unit": row.get("unit") or ("TRY/g" if key == "commodities" else None),
                    "last_close": row["last_close"],
                    "pred_close": row["pred_close"],
                    "expected_return_pct": row["expected_return_pct"],
                }
            )
        card["markets"][key] = {
            "currency": block["market"]["currency"],
            "exchange": block["market"].get("exchange"),
            "unit": block["market"].get("unit"),
            "source_run": block.get("source_run"),
            "picks": picks,
        }

    FORECASTS.mkdir(parents=True, exist_ok=True)
    out_card = CARD if "spus" in card["markets"] or "xk100" in card["markets"] else (
        FORECASTS / "forecast_card_commodities.json"
    )
    out_card.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Frozen -> {out_card}")
    print(f"Asof last close: {card['asof_last_close']}")
    print(f"Check after:     {card['target_check_date']} (or later)")
    return out_card


def _latest_close(yahoo: str) -> tuple[float | None, str | None]:
    data = yf.download(yahoo, period="15d", auto_adjust=True, progress=False, threads=False)
    if data is None or data.empty or "Close" not in data.columns:
        return None, None
    close = data["Close"].dropna()
    if close.empty:
        return None, None
    # yfinance may return DataFrame for single ticker in some versions
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    ts = close.index[-1]
    val = float(close.iloc[-1])
    day = str(pd.Timestamp(ts).date())
    return val, day


def _latest_try_per_gram(symbol: str, yahoo: str) -> tuple[float | None, str | None]:
    """Convert live Yahoo futures close to TRY/gram using same rules as paper.commodities."""
    from paper.commodities import COMMODITY_META

    meta = COMMODITY_META.get(symbol)
    if not meta:
        return None, None
    usd, day = _latest_close(yahoo or meta["yahoo"])
    fx, _ = _latest_close("USDTRY=X")
    if usd is None or fx is None:
        return None, day
    return usd * fx / float(meta["divisor_g"]), day


def check(refresh: bool = False) -> Path:  # noqa: ARG001 — reserved
    if not CARD.exists():
        raise SystemExit(f"No forecast card. Run: track_forecasts.py --freeze\nMissing: {CARD}")

    card = json.loads(CARD.read_text(encoding="utf-8"))
    target = card["target_check_date"]
    today = str(pd.Timestamp.now(tz="UTC").tz_localize(None).date())
    too_early = today < target

    out = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "card": str(CARD.name),
        "asof_last_close": card["asof_last_close"],
        "target_check_date": target,
        "today": today,
        "status": "early" if too_early else "ready",
        "note": (
            f"Target not reached yet (today={today} < {target}). Showing interim prices."
            if too_early
            else "Horizon reached — scoring vs Yahoo closes."
        ),
        "markets": {},
    }

    for mkt, block in card["markets"].items():
        rows = []
        direction_hits = 0
        scored = 0
        unit = block.get("unit") or ""
        for p in block["picks"]:
            if mkt == "commodities" or p.get("unit") == "TRY/g" or unit == "gram":
                actual, actual_day = _latest_try_per_gram(p["symbol"], p.get("yahoo") or "")
            else:
                actual, actual_day = _latest_close(p["yahoo"])
            row = {
                **p,
                "actual_close": None,
                "actual_day": actual_day,
                "actual_return_pct": None,
                "error_pct_points": None,
                "direction_hit": None,
                "price_vs_pred": None,
            }
            if actual is not None and p["last_close"]:
                actual_ret = (actual / p["last_close"] - 1.0) * 100.0
                exp = float(p["expected_return_pct"])
                err = abs(actual_ret - exp)
                same_dir = (actual_ret >= 0 and exp >= 0) or (actual_ret < 0 and exp < 0)
                row.update(
                    {
                        "actual_close": round(actual, 4),
                        "actual_return_pct": round(actual_ret, 2),
                        "error_pct_points": round(err, 2),
                        "direction_hit": bool(same_dir),
                        "price_vs_pred": round(actual - float(p["pred_close"]), 4),
                    }
                )
                scored += 1
                if same_dir:
                    direction_hits += 1
            rows.append(row)

        out["markets"][mkt] = {
            "currency": block["currency"],
            "unit": block.get("unit"),
            "scored": scored,
            "direction_hits": direction_hits,
            "direction_hit_rate": round(direction_hits / scored, 3) if scored else None,
            "mean_abs_error_pct_points": round(
                sum(r["error_pct_points"] for r in rows if r["error_pct_points"] is not None)
                / max(scored, 1),
                2,
            )
            if scored
            else None,
            "picks": rows,
        }

    CHECK.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Checked -> {CHECK}")
    print(f"Status: {out['status']} | today={today} target={target}")
    for mkt, block in out["markets"].items():
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
    return CHECK


def main() -> int:
    args = parse_args()
    if args.freeze:
        freeze(Path(args.from_report))
    else:
        check(refresh=args.refresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
