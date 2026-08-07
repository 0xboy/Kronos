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
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]  # repo root
sys.path.insert(0, str(ROOT))

RESULTS = ROOT / "paper_results"
FORECASTS = RESULTS / "forecasts"
TESTS = RESULTS / "tests"


def _paths() -> tuple[Path, Path, Path]:
    """Resolve live card/check/report paths for the current week."""
    from paper.forecast_week import live_path

    return (
        live_path("forecast_card.json"),
        live_path("forecast_check.json"),
        live_path("forecast_report.txt"),
    )


# Defaults resolve at import; freeze/check refresh via _paths().
from paper.forecast_week import live_path as _live_path  # noqa: E402

CARD = _live_path("forecast_card.json")
CHECK = _live_path("forecast_check.json")
REPORT_TXT = _live_path("forecast_report.txt")


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


def _default_from_report() -> Path:
    from paper.forecast_week import FORECASTS as F, live_path

    for cand in (
        live_path("prediction_report_all.json"),
        live_path("prediction_report_top.json"),
        F / "prediction_report_all.json",
        F / "prediction_report_top.json",
    ):
        if cand.exists():
            return cand
    return live_path("prediction_report_all.json")


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

    from paper.crypto import CRYPTO_META

    for key in ("spus", "xk100", "commodities", "crypto"):
        if key not in report:
            continue
        block = report[key]
        picks = []
        for row in block["top10"]:
            if key == "spus":
                yahoo = row["symbol"]
            elif key == "xk100":
                yahoo = f"{row['symbol']}.IS"
            elif key == "crypto":
                yahoo = row.get("yahoo") or CRYPTO_META.get(row["symbol"], {}).get("yahoo") or row["symbol"]
            else:
                yahoo = row.get("yahoo") or COMMODITY_META.get(row["symbol"], {}).get("yahoo")
            picks.append(
                {
                    "rank": row["rank"],
                    "symbol": row["symbol"],
                    "name": row.get("name"),
                    "yahoo": yahoo,
                    "unit": row.get("unit")
                    or ("TRY/g" if key == "commodities" else "USD" if key == "crypto" else None),
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
            "rank_rule": block.get("rank_rule"),
            "picks": picks,
        }

    FORECASTS.mkdir(parents=True, exist_ok=True)
    card_path, _, _ = _paths()
    out_card = card_path
    out_card.parent.mkdir(parents=True, exist_ok=True)
    out_card.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Frozen -> {out_card}")
    print(f"Asof last close: {card['asof_last_close']}")
    print(f"Check after:     {card['target_check_date']} (or later)")
    write_forecast_report_txt(card, check=None, source_report=report)
    from paper.forecast_week import archive_current_week, iso_week_id

    wid = iso_week_id(card.get("asof_last_close"))
    dest = archive_current_week(week_id=wid, asof=card.get("asof_last_close"))
    print(f"Week archive -> {dest}")
    return out_card


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "   n/a"
    return f"{x:+6.2f}%"


def _fmt_price(x: float | None, *, digits: int = 2) -> str:
    if x is None:
        return "n/a"
    ax = abs(float(x))
    if ax > 0 and ax < 0.01:
        return f"{x:.8f}".rstrip("0").rstrip(".")
    if ax >= 100:
        return f"{x:,.{digits}f}"
    if ax >= 1:
        return f"{x:.{digits}f}"
    return f"{x:.4f}"


def _crypto_display_symbol(sym: str) -> str:
    raw = sym.replace("-USD", "")
    mapping = {
        "APT21794": "APT",
        "SUI20947": "SUI",
        "ARB11841": "ARB",
        "UNI7083": "UNI",
    }
    for long, short in mapping.items():
        if raw == long or raw.startswith(long):
            return short
    if raw.startswith("APT"):
        return "APT"
    if raw.startswith("SUI"):
        return "SUI"
    return raw


def write_forecast_report_txt(
    card: dict,
    *,
    check: dict | None = None,
    source_report: dict | None = None,
) -> Path:
    """Human-readable tracker matching forecast_report.txt style."""
    from paper.forecast_week import format_sleeve_block, iso_week_id, sleeve_example

    lines: list[str] = []
    model = (card.get("model") or "NeoQuasar/Kronos-small").replace("NeoQuasar/", "")
    asof = card.get("asof_last_close", "?")
    target = card.get("target_check_date", "?")
    status = (check or {}).get("status")
    week_id = iso_week_id(asof if asof != "?" else None)
    lines += [
        "Kronos 5-day forecast card",
        "==========================",
        f"Model: {model}",
        f"Week: {week_id}",
        f"As-of close: {asof}",
        f"Check after: {target}",
        "Horizon: next 5 trading days",
        "Rule: did price move in the predicted direction?",
    ]
    if status:
        lines.append(f"Check status: {status} (today={(check or {}).get('today', '?')})")
    lines.append("")

    check_mkts = (check or {}).get("markets") or {}

    def _hit_cols(cp: dict | None, *, digits: int = 2) -> str:
        if not cp or cp.get("direction_hit") is None:
            return f"  {'n/a':>10}  {'n/a':>8}  ?"
        hit = "HIT" if cp["direction_hit"] else "MISS"
        return (
            f"  {_fmt_price(cp.get('actual_close'), digits=digits):>10}  "
            f"{_fmt_pct(cp.get('actual_return_pct')):>8}  {hit}"
        )

    def section_equity(key: str, title: str, last_hdr: str, pred_hdr: str) -> None:
        block = card.get("markets", {}).get(key)
        if not block:
            return
        picks = block["picks"]
        scored = check_mkts.get(key)
        lines.append("-" * 72)
        lines.append(title)
        if key == "xk100" and block.get("rank_rule"):
            lines.append("Rank: vol_norm + min_price/ADV + |exp| cap + min t-stat")
        lines.append("-" * 72)
        if scored:
            lines.append(
                f"#   Symbol   Expected     Last {last_hdr:4}  Pred {pred_hdr:4}  "
                f"Actual {last_hdr:4}   Actual%   Hit"
            )
        else:
            lines.append(f"#   Symbol   Expected     Last {last_hdr:4}  Pred {pred_hdr:4}")
        for p in picks:
            row = f"{p['rank']:<3} {p['symbol']:<8} {_fmt_pct(p['expected_return_pct']):>8}  "
            row += f"{_fmt_price(p['last_close']):>10}  {_fmt_price(p['pred_close']):>10}"
            if scored:
                cp = next((x for x in scored["picks"] if x["symbol"] == p["symbol"]), None)
                row += _hit_cols(cp)
            lines.append(row)
        watch = ", ".join(p["symbol"] for p in picks[:5])
        lines.append("")
        lines.append(f"Top 5 to watch: {watch}")
        if scored and scored.get("direction_hit_rate") is not None:
            lines.append(
                f"Score: {scored['direction_hits']}/{scored['scored']} "
                f"({scored['direction_hit_rate']*100:.0f}%) "
                f"MAE={scored['mean_abs_error_pct_points']} pp"
            )
        # Example sleeve (only on fresh forecast, not check overlay)
        if not scored:
            currency = "USD" if key == "spus" else "TRY"
            budget = 10_000.0 if currency == "USD" else 10_000.0
            alloc = sleeve_example(picks, budget=budget, currency=currency)
            lines.extend(
                format_sleeve_block(
                    f"  Sleeve {key.upper()}",
                    alloc,
                    budget=budget,
                    currency=currency,
                )
            )
        lines.append("")

    section_equity("spus", "SPUS (US / USD) — Top 10", "$", "$")
    section_equity("xk100", "XK100 (BIST Katılım / TRY) — Top 10", "₺", "₺")

    cmd = card.get("markets", {}).get("commodities")
    if cmd:
        lines.append("-" * 72)
        lines.append("COMMODITIES (TRY / gram) — All 7")
        lines.append(f"As-of close: {asof} | Check after: {target}")
        lines.append("Source: COMEX/LME futures × USDTRY → TL/gram")
        lines.append("-" * 72)
        scored = check_mkts.get("commodities")
        if scored:
            lines.append(
                "#   Symbol      Name         Expected     Last ₺/g     Pred ₺/g  "
                "Actual ₺/g   Actual%   Hit"
            )
        else:
            lines.append("#   Symbol      Name         Expected     Last ₺/g     Pred ₺/g")
        for p in cmd["picks"]:
            name = (p.get("name") or "")[:10]
            row = (
                f"{p['rank']:<3} {p['symbol']:<11} {name:<12} "
                f"{_fmt_pct(p['expected_return_pct']):>8}  "
                f"{_fmt_price(p['last_close'], digits=4):>10}  "
                f"{_fmt_price(p['pred_close'], digits=4):>10}"
            )
            if scored:
                cp = next((x for x in scored["picks"] if x["symbol"] == p["symbol"]), None)
                row += _hit_cols(cp, digits=4)
            lines.append(row)
        watch = ", ".join(p["symbol"] for p in cmd["picks"][:5])
        lines.append("")
        lines.append(f"Top 5 to watch: {watch}")
        if scored and scored.get("direction_hit_rate") is not None:
            lines.append(
                f"Score: {scored['direction_hits']}/{scored['scored']} "
                f"({scored['direction_hit_rate']*100:.0f}%) "
                f"MAE={scored['mean_abs_error_pct_points']} pp"
            )
        if not scored:
            # Long-only sleeve on positive expected metals
            pos = [p for p in cmd["picks"] if float(p.get("expected_return_pct", 0)) > 0]
            alloc = sleeve_example(pos or cmd["picks"], budget=10_000.0, currency="TRY")
            lines.extend(
                format_sleeve_block("  Sleeve COMMODITIES", alloc, budget=10_000.0, currency="TRY")
            )
        lines.append("")

    # Prefer frozen card crypto picks; fall back to source_report / files.
    crypto_block = card.get("markets", {}).get("crypto")
    crypto_picks = None
    crypto_all = None
    if crypto_block and crypto_block.get("picks"):
        crypto_picks = crypto_block["picks"]
    elif source_report and source_report.get("crypto", {}).get("top10"):
        crypto_picks = source_report["crypto"]["top10"]
        crypto_all = source_report["crypto"].get("all_ranked")
    else:
        for path in (
            FORECASTS / "prediction_report_all.json",
            FORECASTS / "prediction_report_crypto.json",
            RESULTS / "prediction_report_crypto.json",
        ):
            if not path.exists():
                continue
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
                if blob.get("crypto", {}).get("top10"):
                    crypto_picks = blob["crypto"]["top10"]
                    crypto_all = blob["crypto"].get("all_ranked")
                    break
            except Exception:
                pass

    if crypto_picks:
        lines.append("-" * 72)
        lines.append("CRYPTO (USD) — Top 10")
        lines.append("Source: Yahoo Finance -USD pairs (24/7)")
        lines.append("-" * 72)
        scored = check_mkts.get("crypto")
        if scored:
            lines.append(
                "#   Symbol   Name            Expected     Last $       Pred $  "
                "Actual $    Actual%   Hit"
            )
        else:
            lines.append("#   Symbol   Name            Expected     Last $       Pred $")
        for p in crypto_picks:
            sym = _crypto_display_symbol(p["symbol"])
            name = (p.get("name") or "")[:14]
            row = (
                f"{p['rank']:<3} {sym:<8} {name:<14} "
                f"{_fmt_pct(p['expected_return_pct']):>8}  "
                f"{_fmt_price(p['last_close'], digits=4):>10}  "
                f"{_fmt_price(p['pred_close'], digits=4):>10}"
            )
            if scored:
                cp = next((x for x in scored["picks"] if x["symbol"] == p["symbol"]), None)
                row += _hit_cols(cp, digits=4)
            lines.append(row)
        majors = []
        for row in crypto_all or []:
            ds = _crypto_display_symbol(row["symbol"])
            if ds in ("BTC", "ETH"):
                majors.append(
                    f"{ds} {_fmt_pct(row['expected_return_pct']).strip()} "
                    f"({_fmt_price(row['last_close'], digits=0)} → "
                    f"{_fmt_price(row['pred_close'], digits=0)})"
                )
        if majors:
            lines.append("")
            lines.append("Majors: " + " | ".join(majors))
        watch = ", ".join(_crypto_display_symbol(p["symbol"]) for p in crypto_picks[:5])
        lines.append(f"Top 5 to watch: {watch}")
        if scored and scored.get("direction_hit_rate") is not None:
            lines.append(
                f"Score: {scored['direction_hits']}/{scored['scored']} "
                f"({scored['direction_hit_rate']*100:.0f}%) "
                f"MAE={scored['mean_abs_error_pct_points']} pp"
            )
        if not scored:
            alloc = sleeve_example(crypto_picks, budget=10_000.0, currency="USD")
            # display short symbols in sleeve
            for a in alloc:
                a["symbol"] = _crypto_display_symbol(a["symbol"])
            lines.extend(
                format_sleeve_block("  Sleeve CRYPTO", alloc, budget=10_000.0, currency="USD")
            )
        lines.append("")

    lines.append("-" * 72)
    lines.append("Note: These are model forecasts, not guarantees.")
    lines.append(f"Week archive: paper_results/forecasts/weeks/{week_id}/")
    lines.append(f"After {target} run:  track_forecasts.py --check")
    lines.append("(check refreshes this txt with Actual close + Actual% / Hit)")
    lines.append("")

    _, _, report_txt = _paths()
    report_txt.parent.mkdir(parents=True, exist_ok=True)
    report_txt.write_text("\n".join(lines), encoding="utf-8")
    # Keep a root mirror for convenience (open path / quick view).
    (FORECASTS / "forecast_report.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"Report txt -> {report_txt}")
    return report_txt


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
    card_path, check_path, _ = _paths()
    # Fall back to root mirror if week folder empty (pre-organize).
    if not card_path.exists() and (FORECASTS / "forecast_card.json").exists():
        card_path = FORECASTS / "forecast_card.json"
    if not card_path.exists():
        raise SystemExit(f"No forecast card. Run: track_forecasts.py --freeze\nMissing: {card_path}")

    card = json.loads(card_path.read_text(encoding="utf-8"))
    target = card["target_check_date"]
    today = str(pd.Timestamp.now(tz="UTC").tz_localize(None).date())
    too_early = today < target

    out = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "card": str(card_path.name),
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

    check_path.parent.mkdir(parents=True, exist_ok=True)
    check_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Checked -> {check_path}")
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
    write_forecast_report_txt(card, check=out)
    from paper.forecast_week import archive_current_week, iso_week_id

    wid = iso_week_id(card.get("asof_last_close"))
    dest = archive_current_week(week_id=wid, asof=card.get("asof_last_close"))
    print(f"Week archive -> {dest}")
    return check_path


def main() -> int:
    args = parse_args()
    if args.organize:
        from paper.forecast_week import organize_forecast_root

        info = organize_forecast_root()
        print(f"Organized forecasts/ -> current={info['current_week']}")
        print(f"  live: {info['live_dir']}")
        if info["moved_legacy"]:
            print(f"  legacy: {', '.join(info['moved_legacy'])}")
        return 0
    if args.freeze:
        src = Path(args.from_report) if args.from_report else _default_from_report()
        freeze(src)
    else:
        check(refresh=args.refresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
