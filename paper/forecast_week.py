"""Weekly forecast folder helpers + score-weighted sleeve example for reports."""
from __future__ import annotations

import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from paper.sizing import conviction, normalize_weights

RESULTS = Path(__file__).resolve().parents[1] / "paper_results"
FORECASTS = RESULTS / "forecasts"
WEEKS = FORECASTS / "weeks"
CURRENT_WEEK_FILE = FORECASTS / "CURRENT_WEEK.txt"

# Live artifact names kept inside each week folder.
LIVE_NAMES = (
    "forecast_card.json",
    "forecast_check.json",
    "forecast_report.txt",
    "prediction_report_all.json",
    "prediction_report_top.json",
)

# Thin root mirrors so open paths / old habits still work.
ROOT_MIRRORS = (
    "forecast_card.json",
    "forecast_check.json",
    "forecast_report.txt",
    "prediction_report_all.json",
    "prediction_report_top.json",
)


def iso_week_id(day: str | None = None) -> str:
    """Return YYYY-Www for as-of / today (ISO week)."""
    ts = pd.Timestamp(day) if day else pd.Timestamp.now(tz="UTC").tz_localize(None)
    iso = ts.isocalendar()
    return f"{int(iso.year)}-W{int(iso.week):02d}"


def read_current_week_id() -> str:
    if CURRENT_WEEK_FILE.exists():
        wid = CURRENT_WEEK_FILE.read_text(encoding="utf-8").strip()
        if wid:
            return wid
    return iso_week_id()


def set_current_week(week_id: str) -> None:
    FORECASTS.mkdir(parents=True, exist_ok=True)
    CURRENT_WEEK_FILE.write_text(week_id.strip() + "\n", encoding="utf-8")


def week_dir(week_id: str | None = None) -> Path:
    wid = week_id or read_current_week_id()
    path = WEEKS / wid
    path.mkdir(parents=True, exist_ok=True)
    return path


def live_dir(week_id: str | None = None) -> Path:
    """Directory for the active week's artifacts."""
    return week_dir(week_id or read_current_week_id())


def live_path(name: str, week_id: str | None = None) -> Path:
    return live_dir(week_id) / name


def mirror_to_root(week_id: str | None = None) -> None:
    """Copy key live files up to forecasts/ for convenience."""
    wid = week_id or read_current_week_id()
    src_dir = live_dir(wid)
    for name in ROOT_MIRRORS:
        src = src_dir / name
        if name == "forecast_check.json" and src.exists():
            try:
                blob = json.loads(src.read_text(encoding="utf-8"))
                if iso_week_id(blob.get("asof_last_close")) != wid:
                    # Stale check from another week — don't mirror / drop from live week.
                    src.unlink(missing_ok=True)
                    root_check = FORECASTS / name
                    if root_check.exists():
                        root_check.unlink()
                    continue
            except Exception:
                pass
        if src.exists():
            shutil.copy2(src, FORECASTS / name)
        else:
            # Keep root clean if week lacks the file.
            root = FORECASTS / name
            if root.exists() and name == "forecast_check.json":
                root.unlink()


def archive_current_week(
    *,
    week_id: str | None = None,
    asof: str | None = None,
    files: list[str] | None = None,
) -> Path:
    """Ensure live artifacts sit in weeks/YYYY-Www/ and refresh root mirrors."""
    wid = week_id or iso_week_id(asof)
    dest = week_dir(wid)
    names = files or list(LIVE_NAMES)
    copied: list[str] = []

    # Pull root artifacts into the week folder, but never let a stale root mirror
    # (e.g. last week's card, mirrored during --check) clobber a fresher week file.
    for name in names:
        dest_file = dest / name
        root_file = FORECASTS / name
        if root_file.exists():
            if not dest_file.exists() or root_file.stat().st_mtime >= dest_file.stat().st_mtime:
                shutil.copy2(root_file, dest_file)
            copied.append(name)
        elif dest_file.exists():
            copied.append(name)

    meta = {
        "week_id": wid,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "asof": asof,
        "files": copied,
    }
    (dest / "week_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    set_current_week(wid)
    mirror_to_root(wid)
    return dest


def organize_forecast_root() -> dict[str, Any]:
    """Tidy forecasts/: live → current week, orphans → weeks/_legacy."""
    FORECASTS.mkdir(parents=True, exist_ok=True)
    WEEKS.mkdir(parents=True, exist_ok=True)
    legacy = WEEKS / "_legacy"
    legacy.mkdir(parents=True, exist_ok=True)

    wid = read_current_week_id()
    current = week_dir(wid)
    moved_live: list[str] = []
    moved_legacy: list[str] = []

    legacy_prefixes = (
        "forecast_card_commodities",
        "forecast_check_commodities",
        "prediction_report_commodities",
        "prediction_report_crypto",
    )

    def _week_for_check(path: Path) -> str:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            asof = blob.get("asof_last_close")
            if asof:
                return iso_week_id(asof)
        except Exception:
            pass
        return wid

    def _week_for_card(path: Path) -> str:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            asof = blob.get("asof_last_close")
            if asof:
                return iso_week_id(asof)
        except Exception:
            pass
        return wid

    for path in sorted(FORECASTS.iterdir()):
        if path.is_dir():
            continue
        if path.name in ("CURRENT_WEEK.txt", "README.md"):
            continue
        name = path.name

        if any(name.startswith(p) for p in legacy_prefixes) or name.endswith(".bak"):
            shutil.move(str(path), str(legacy / name))
            moved_legacy.append(name)
            continue

        if name == "forecast_check.json":
            target_week = _week_for_check(path)
            dest = week_dir(target_week) / name
            shutil.copy2(path, dest)
            moved_live.append(f"{name}->{target_week}")
            path.unlink()
            continue

        if name == "forecast_card.json":
            target_week = _week_for_card(path)
            dest = week_dir(target_week) / name
            shutil.copy2(path, dest)
            moved_live.append(f"{name}->{target_week}")
            path.unlink()
            continue

        if name in LIVE_NAMES or name in ROOT_MIRRORS:
            # Reports/txt belong with the current live week pointer.
            shutil.copy2(path, current / name)
            moved_live.append(name)
            path.unlink()
            continue

        # Unknown root file → legacy
        shutil.move(str(path), str(legacy / name))
        moved_legacy.append(name)

    set_current_week(wid)
    mirror_to_root(wid)

    readme = FORECASTS / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Forecasts",
                "",
                f"Current week: **{wid}** (`CURRENT_WEEK.txt`)",
                "",
                "Layout:",
                "- `weeks/YYYY-Www/` — canonical card / check / report / prediction JSON",
                "- root mirrors — convenience copies of the current week’s key files",
                "- `weeks/_legacy/` — old single-market cards",
                "",
                "Scripts write into the current week folder, then refresh root mirrors.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "current_week": wid,
        "live_dir": str(current),
        "moved_live": moved_live,
        "moved_legacy": moved_legacy,
    }


def sleeve_example(
    picks: list[dict[str, Any]],
    *,
    budget: float,
    currency: str,
    max_weight: float = 0.30,
    top_n: int = 10,
    fractional: bool = False,
    qty_decimals: int = 4,
) -> list[dict[str, Any]]:
    """Score-weighted notional example (same logic as paper sizing).

    ``fractional=True`` allows partial units (e.g. grams for commodities).
    """
    rows = []
    for p in picks[:top_n]:
        exp = float(p.get("expected_return_pct", 0.0)) / 100.0
        score = float(p.get("score") or 0.0)
        px = float(p.get("last_close") or 0.0)
        if px <= 0:
            continue
        rows.append(
            {
                "symbol": p["symbol"],
                "name": p.get("name"),
                "last_close": px,
                "expected_return_pct": float(p.get("expected_return_pct", 0.0)),
                "score": score,
                "conviction": conviction(score, exp),
            }
        )
    if not rows:
        return []
    weights = normalize_weights([r["conviction"] for r in rows], max_weight=max_weight)
    out: list[dict[str, Any]] = []
    for r, w in zip(rows, weights):
        if w <= 0:
            continue
        notional = budget * w
        px = r["last_close"]
        if px <= 0:
            continue
        if fractional:
            # Floor to qty_decimals (e.g. 1.2384 → 1.23 with decimals=2).
            scale = 10 ** int(qty_decimals)
            raw = notional / px
            qty = math.floor(raw * scale + 1e-12) / scale
            if qty <= 0:
                continue
            cost = qty * px
        else:
            qty = math.floor(notional / px)
            if qty < 1:
                continue
            cost = qty * px
        out.append(
            {
                **r,
                "weight": round(w, 4),
                "notional_target": round(notional, 2),
                "qty": qty,
                "cost": round(cost, 2),
                "currency": currency,
                "fractional": fractional,
            }
        )
    return out


def format_sleeve_block(
    title: str,
    alloc: list[dict[str, Any]],
    *,
    budget: float,
    currency: str,
    qty_unit: str | None = None,
) -> list[str]:
    if not alloc:
        return []
    cur = "$" if currency == "USD" else "₺"
    qty_hdr = f"Qty({qty_unit})" if qty_unit else "Qty"
    lines = [
        f"{title} — score-weighted sleeve example ({cur}{budget:,.0f})",
        f"{'#':<3} {'Symbol':<10} {'Conv':>7} {'Wgt':>6} {qty_hdr:>10} {'Cost':>12}",
    ]
    spent = 0.0
    for i, a in enumerate(alloc, 1):
        spent += float(a["cost"])
        cost_s = f"{cur} {a['cost']:,.0f}"
        qty = a["qty"]
        if isinstance(qty, float) or a.get("fractional"):
            qty_s = f"{float(qty):.2f}"
            if qty_unit:
                qty_s = f"{qty_s} {qty_unit}"
        else:
            qty_s = str(int(qty))
        lines.append(
            f"{i:<3} {a['symbol']:<10} {a['conviction']:+7.3f} "
            f"{a['weight']*100:5.1f}% {qty_s:>10}  {cost_s:>12}"
        )
    lines.append(f"Deployed ~{cur}{spent:,.0f} / {cur}{budget:,.0f}  (max_weight=30%)")
    lines.append("")
    return lines
