"""Build prediction report JSON from latest universe test runs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import FORECASTS, TESTS
from forecast.week import live_dir, live_path, mirror_to_root, read_current_week_id
from inference.models import DEFAULT_PAPER_MODEL, model_label
from ranking.xk100_rank import DEFAULT_CFG, cfg_to_dict
from universe.commodities import COMMODITY_META
from universe.crypto import CRYPTO_META


def load_latest(prefix: str) -> tuple[dict, Path]:
    files = sorted(TESTS.glob(f"test_{prefix}_*.json"))
    if not files:
        raise FileNotFoundError(f"No test_{prefix}_*.json in {TESTS}")
    path = files[-1]
    return json.loads(path.read_text(encoding="utf-8")), path


def clean(
    signals: list[dict],
    top_n: int,
    *,
    commodities: bool = False,
    crypto: bool = False,
    xk100: bool = False,
) -> list[dict]:
    rows = []
    for s in signals:
        if s["pred_close"] <= 0:
            continue
        if abs(s["expected_return"]) > 1.0:  # filter |ret| > 100%
            continue
        if xk100:
            # Prefer pre-ranked/filtered signals from run_universe_test.
            # Soft gates if older JSONs lack score/std.
            cfg = DEFAULT_CFG
            if abs(s["expected_return"]) > cfg.max_abs_expected:
                continue
            std = float(s.get("return_std") or 0.0)
            if std > 1e-12 and abs(s["expected_return"] / std) < cfg.min_tstat:
                continue
        row = {
            "rank": 0,
            "symbol": s["symbol"],
            "expected_return_pct": round(s["expected_return"] * 100, 2),
            "last_close": round(s["last_close"], 8 if abs(s["last_close"]) < 0.01 else 4),
            "pred_close": round(s["pred_close"], 8 if abs(s["pred_close"]) < 0.01 else 4),
            "bars": s["bars"],
        }
        if xk100:
            if s.get("score") is not None:
                row["score"] = round(float(s["score"]), 4)
            if s.get("return_std") is not None:
                row["return_std"] = round(float(s["return_std"]), 6)
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

    if xk100 and any("score" in r for r in rows):
        rows.sort(key=lambda r: r.get("score", r["expected_return_pct"]), reverse=True)
    else:
        rows.sort(key=lambda r: r["expected_return_pct"], reverse=True)
    for i, r in enumerate(rows[:top_n], 1):
        r["rank"] = i
    return rows[:top_n]


def block_from(prefix: str, top_n: int) -> dict:
    data, path = load_latest(prefix)
    is_cmd = prefix == "commodities"
    is_crypto = prefix == "crypto"
    is_xk = prefix == "xk100"
    top = clean(
        data["signals"],
        top_n,
        commodities=is_cmd,
        crypto=is_crypto,
        xk100=is_xk,
    )
    top5 = top[:5]
    block: dict[str, Any] = {
        "source_run": path.name,
        "market": data.get("market"),
        "params": data.get("params"),
        "scored": len(data.get("signals", [])),
        "skipped": len(data.get("skipped", [])),
        "top5": top5,
        "top10": top[:10],
        "all_ranked": clean(
            data["signals"],
            999,
            commodities=is_cmd,
            crypto=is_crypto,
            xk100=is_xk,
        ),
    }
    if is_xk:
        rank_cfg = (data.get("params") or {}).get("xk100_rank") or cfg_to_dict(DEFAULT_CFG)
        block["rank_rule"] = {
            "mode": "vol_norm",
            "description": (
                "XK100: filter min_price/ADV20, cap |expected|, min |mean/std|, "
                "rank by expected_return / vol_5d"
            ),
            "cfg": rank_cfg,
            "filter_drops": len(data.get("filter_drops") or []),
        }
    return block


def build_prediction_report(
    universe: str = "commodities",
    *,
    top: int = 10,
) -> tuple[dict, Path]:
    """Assemble and write prediction report JSON for one universe or ``all``."""
    FORECASTS.mkdir(parents=True, exist_ok=True)
    week = live_dir()
    if universe == "all":
        keys = ["spus", "xk100", "commodities", "crypto"]
    else:
        keys = [universe]

    report: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": model_label(DEFAULT_PAPER_MODEL),
        "model_id": DEFAULT_PAPER_MODEL,
        "pred_len_days": 5,
        "week_id": read_current_week_id(),
        "note": (
            "expected_return = pred_close[5th business day] / last_close - 1. "
            "Commodities priced TRY per gram (futures × USDTRY). Crypto priced in USD. "
            "XK100 ranked by vol-normalized score with liquidity/price gates."
        ),
    }
    for key in keys:
        block = block_from(key, top)
        # Prefer the model that actually scored this universe, if present.
        mid = (block.get("params") or {}).get("model")
        if mid:
            report["model"] = mid if isinstance(mid, str) else model_label(DEFAULT_PAPER_MODEL)
            report["model_id"] = mid if isinstance(mid, str) else DEFAULT_PAPER_MODEL
        report[key] = block

    if universe == "commodities":
        out = week / "prediction_report_commodities.json"
    elif universe == "all":
        out = week / "prediction_report_all.json"
    else:
        out = week / f"prediction_report_{universe}.json"

    # Also keep combined top name when equity markets present
    if "spus" in report and "xk100" in report:
        legacy = {k: report[k] for k in ("ts", "model", "pred_len_days", "note", "week_id", "spus", "xk100")}
        if "commodities" in report:
            legacy["commodities"] = report["commodities"]
        if "crypto" in report:
            legacy["crypto"] = report["crypto"]
        live_path("prediction_report_top.json").write_text(
            json.dumps(legacy, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    mirror_to_root()
    return report, out
