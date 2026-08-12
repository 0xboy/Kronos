"""Full walk-forward backtest for SPUS100 and XK100 (no fine-tune).

As-of weekly (step=pred_len trading days), score Kronos-small, pick top-N,
compare to realized horizon returns. Reports hit rate, MAE, EW mean return,
EW cumulative, and paper-style full-NAV score-weight sleeve PnL.

Scores are cached under paper_results/tests/score_cache/ so re-runs skip Kronos.

  .venv/Scripts/python.exe scripts/backtest_walkforward.py --universe spus
  .venv/Scripts/python.exe scripts/backtest_walkforward.py --universe xk100
  .venv/Scripts/python.exe scripts/backtest_walkforward.py --universe both
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from paper.data import drop_split_discontinuities
from paper.envelope import EnvelopeConfig, apply_envelope_vol_filter
from paper.signals import Signal, load_predictor, score_symbol
from paper.sizing import conviction, normalize_weights
from paper.universe import SPUS100, XK100
from paper.xk100_rank import (
    DEFAULT_CFG,
    Xk100RankConfig,
    adv20,
    cfg_to_dict,
    passes_filters,
    passes_signal_gates,
    compute_score,
    top_adv_symbols,
    vol5d,
)
from paper.yahoo_cache import get_yahoo_bars

TESTS = ROOT / "paper_results" / "tests"
SCORE_CACHE = TESTS / "score_cache"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Walk-forward SPUS / XK100 backtest")
    p.add_argument("--universe", choices=("spus", "xk100", "both"), default="both")
    p.add_argument("--start", default="2026-01-02", help="First as-of (inclusive, first valid day)")
    p.add_argument("--end", default="2026-08-01", help="Last as-of (inclusive)")
    p.add_argument("--lookback", type=int, default=400)
    p.add_argument("--pred-len", type=int, default=5)
    p.add_argument("--step", type=int, default=5, help="Trading days between as-of dates")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--sample-count", type=int, default=0, help="0 = 1 (SPUS) / DEFAULT_CFG (XK100)")
    p.add_argument("--pool", type=int, default=0, help="XK100 ADV pool before score (0 = DEFAULT_CFG)")
    p.add_argument("--model", default="NeoQuasar/Kronos-small")
    p.add_argument("--device", default="auto", help="auto/cuda/cpu")
    p.add_argument(
        "--tag",
        default="",
        help="Optional output suffix, e.g. sc10 -> walkforward_spus_2026H1_sc10.json",
    )
    p.add_argument("--max-age-days", type=int, default=7)
    p.add_argument("--min-return", type=float, default=0.0, help="Sleeve: min expected return")
    p.add_argument("--max-weight", type=float, default=0.30)
    p.add_argument("--limit-symbols", type=int, default=0, help="Debug: first N of universe")
    p.add_argument("--no-cache", action="store_true", help="Ignore score cache")
    p.add_argument("--refresh-bars", action="store_true")
    p.add_argument(
        "--envelope",
        action="store_true",
        help="Keep only high-vol names touching SMA envelope (mean-reversion align)",
    )
    p.add_argument("--envelope-period", type=int, default=20, help="SMA length for envelope")
    p.add_argument(
        "--envelope-pct",
        type=float,
        default=0.05,
        help="Band width as fraction of SMA (0.05 = +/-5%)",
    )
    p.add_argument(
        "--envelope-touch-tol",
        type=float,
        default=0.01,
        help="Treat within this fraction of the band as a touch",
    )
    p.add_argument(
        "--min-vol-pctile",
        type=float,
        default=0.70,
        help="Keep vols at/above this percentile among scored names (0.70 = top 30%)",
    )
    p.add_argument(
        "--no-envelope-align",
        action="store_true",
        help="Do not require Kronos sign to match mean-reversion",
    )
    return p.parse_args()


def _envelope_cfg_from_args(args: argparse.Namespace) -> EnvelopeConfig | None:
    if not args.envelope:
        return None
    return EnvelopeConfig(
        period=int(args.envelope_period),
        pct=float(args.envelope_pct),
        touch_tol=float(args.envelope_touch_tol),
        min_vol_pctile=float(args.min_vol_pctile),
        require_align=not args.no_envelope_align,
    )


def _prepare_bars(raw: dict[str, pd.DataFrame], *, strip_is: bool) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for ysym, df in raw.items():
        key = ysym.replace(".IS", "") if strip_is else ysym
        d = df.copy()
        d["timestamps"] = pd.to_datetime(d["timestamps"])
        d = d.sort_values("timestamps").reset_index(drop=True)
        out[key] = d
    return out


def _ref_calendar(bars: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    ref = max(bars.values(), key=len)
    return pd.DatetimeIndex(pd.to_datetime(ref["timestamps"]).dt.normalize().unique()).sort_values()


def _asof_dates(
    bars: dict[str, pd.DataFrame],
    *,
    start: str,
    end: str,
    lookback: int,
    pred_len: int,
    step: int,
) -> list[pd.Timestamp]:
    """Trading-day as-of dates in [start, end] with enough history and future bars."""
    cal = _ref_calendar(bars)
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    # Prefer a liquid name for history check; fall back to ref length.
    asofs: list[pd.Timestamp] = []
    # Walk calendar indices that fall in range and leave pred_len after.
    for i, day in enumerate(cal):
        if day < start_ts:
            continue
        if day > end_ts:
            break
        if i < lookback - 1:
            continue
        if i + pred_len >= len(cal):
            break
        asofs.append(pd.Timestamp(day))
    if step > 1 and asofs:
        asofs = asofs[::step]
    return asofs


def _slice_to_asof(df: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame | None:
    mask = pd.to_datetime(df["timestamps"]).dt.normalize() <= asof.normalize()
    sub = df.loc[mask].reset_index(drop=True)
    return sub if len(sub) else None


def _realized_return(df: pd.DataFrame, asof: pd.Timestamp, pred_len: int) -> float | None:
    ts = pd.to_datetime(df["timestamps"]).dt.normalize()
    asof_n = asof.normalize()
    idx = int(ts.searchsorted(asof_n, side="right") - 1)
    if idx < 0 or idx + pred_len >= len(df):
        return None
    if abs((pd.Timestamp(ts.iloc[idx]) - asof_n).days) > 3:
        return None
    p0 = float(df["close"].iloc[idx])
    p1 = float(df["close"].iloc[idx + pred_len])
    if p0 <= 0:
        return None
    return p1 / p0 - 1.0


def _cache_key(
    universe: str,
    asof: str,
    symbol: str,
    *,
    model: str,
    lookback: int,
    pred_len: int,
    sample_count: int,
) -> str:
    raw = f"{universe}|{asof}|{symbol}|{model}|{lookback}|{pred_len}|{sample_count}"
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def _cache_path(universe: str, asof: str, key: str) -> Path:
    return SCORE_CACHE / universe / asof / f"{key}.json"


def _load_cached_row(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _save_cached_row(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")


def _score_one(
    predictor,
    universe: str,
    asof: pd.Timestamp,
    symbol: str,
    sub: pd.DataFrame,
    *,
    model: str,
    lookback: int,
    pred_len: int,
    sample_count: int,
    use_cache: bool,
) -> dict | None:
    asof_s = str(asof.date())
    key = _cache_key(
        universe,
        asof_s,
        symbol,
        model=model,
        lookback=lookback,
        pred_len=pred_len,
        sample_count=sample_count,
    )
    path = _cache_path(universe, asof_s, key)
    if use_cache:
        hit = _load_cached_row(path)
        if hit is not None and "expected_return" in hit:
            return hit

    try:
        sig = score_symbol(
            predictor,
            symbol,
            sub,
            lookback=lookback,
            pred_len=pred_len,
            sample_count=sample_count,
        )
    except Exception as exc:  # noqa: BLE001
        row = {"symbol": symbol, "error": str(exc)}
        if use_cache:
            _save_cached_row(path, row)
        return row
    if sig is None:
        return None

    row = {
        "symbol": symbol,
        "last_close": sig.last_close,
        "pred_close": sig.pred_close,
        "expected_return": sig.expected_return,
        "return_std": sig.return_std,
        "sample_count": sig.sample_count,
        "bars": sig.bars,
        "adv20": adv20(sub),
        "vol5d": vol5d(sub),
        "cached": False,
    }
    if use_cache:
        store = {k: v for k, v in row.items() if k != "cached"}
        _save_cached_row(path, store)
    return row


def _rank_spus(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Rank SPUS by expected return (paper live path)."""
    kept: list[dict] = []
    drops: list[dict] = []
    for r in rows:
        if "error" in r:
            drops.append({"symbol": r["symbol"], "reason": f"error:{r['error']}"})
            continue
        if r.get("actual_return") is None:
            drops.append({"symbol": r["symbol"], "reason": "no_realized"})
            continue
        score = float(r["expected_return"])
        kept.append({**r, "score": score})
    kept.sort(key=lambda x: x["score"], reverse=True)
    return kept, drops


def _rank_xk100(
    rows: list[dict],
    cfg: Xk100RankConfig,
) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    drops: list[dict] = []
    for r in rows:
        if "error" in r:
            drops.append({"symbol": r["symbol"], "reason": f"error:{r['error']}"})
            continue
        if r.get("actual_return") is None:
            drops.append({"symbol": r["symbol"], "reason": "no_realized"})
            continue
        if r["last_close"] < cfg.min_price_try:
            drops.append({"symbol": r["symbol"], "reason": f"min_price<{cfg.min_price_try}"})
            continue
        if r["adv20"] < cfg.min_adv20_try:
            drops.append({"symbol": r["symbol"], "reason": f"adv20<{cfg.min_adv20_try}"})
            continue
        if not np.isfinite(r["vol5d"]):
            drops.append({"symbol": r["symbol"], "reason": "vol5d_nan"})
            continue
        sig = Signal(
            symbol=r["symbol"],
            last_close=r["last_close"],
            pred_close=r["pred_close"],
            expected_return=r["expected_return"],
            bars=r["bars"],
            return_std=r["return_std"],
            sample_count=r["sample_count"],
        )
        ok, reason = passes_signal_gates(sig, cfg)
        if not ok:
            drops.append({"symbol": r["symbol"], "reason": reason})
            continue
        score = compute_score(r["expected_return"], r["vol5d"], rank_mode=cfg.rank_mode)
        kept.append({**r, "score": score})
    kept.sort(key=lambda x: x["score"], reverse=True)
    return kept, drops


def _pick_metrics(picks: list[dict]) -> dict:
    if not picks:
        return {
            "n": 0,
            "direction_hits": 0,
            "hit_rate": None,
            "mae_pp": None,
            "mean_realized": None,
            "mean_expected": None,
        }
    hits = 0
    errs: list[float] = []
    acts: list[float] = []
    exps: list[float] = []
    for p in picks:
        exp = float(p["expected_return"])
        act = float(p["actual_return"])
        same = (act >= 0 and exp >= 0) or (act < 0 and exp < 0)
        hits += int(same)
        errs.append(abs(act - exp) * 100.0)
        acts.append(act)
        exps.append(exp)
    n = len(picks)
    return {
        "n": n,
        "direction_hits": hits,
        "hit_rate": round(hits / n, 4),
        "mae_pp": round(float(np.mean(errs)), 3),
        "mean_realized": round(float(np.mean(acts)), 6),
        "mean_expected": round(float(np.mean(exps)), 6),
    }


def _ew_period_return(picks: list[dict]) -> float | None:
    if not picks:
        return None
    return float(np.mean([float(p["actual_return"]) for p in picks]))


def _score_weight_period_return(
    picks: list[dict],
    *,
    min_return: float,
    max_weight: float,
) -> tuple[float | None, list[dict]]:
    """Paper-style full-NAV score-weight sleeve over one horizon."""
    sleeve = [
        p
        for p in picks
        if float(p["expected_return"]) >= min_return
        and conviction(float(p["score"]), float(p["expected_return"])) > 0
    ]
    if not sleeve:
        # Flat cash if nothing clears the gate.
        return 0.0, []
    raw = [conviction(float(p["score"]), float(p["expected_return"])) for p in sleeve]
    weights = normalize_weights(raw, max_weight=max_weight)
    port = 0.0
    legs = []
    for p, w in zip(sleeve, weights):
        if w <= 0:
            continue
        r = float(p["actual_return"])
        port += w * r
        legs.append(
            {
                "symbol": p["symbol"],
                "weight": round(w, 6),
                "score": p["score"],
                "expected_return": p["expected_return"],
                "actual_return": r,
            }
        )
    return float(port), legs


def _cum_from_period_returns(rets: list[float | None]) -> dict:
    nav = 1.0
    path = []
    for r in rets:
        if r is None:
            path.append({"ret": None, "nav": round(nav, 8)})
            continue
        nav *= 1.0 + float(r)
        path.append({"ret": round(float(r), 6), "nav": round(nav, 8)})
    finite = [float(r) for r in rets if r is not None]
    return {
        "final_nav": round(nav, 6),
        "total_return": round(nav - 1.0, 6),
        "n_periods": len(finite),
        "mean_period_return": round(float(np.mean(finite)), 6) if finite else None,
        "path": path,
    }


def run_universe(args: argparse.Namespace, universe: str) -> dict:
    if universe == "spus":
        labels = list(SPUS100)
        yahoo_syms = labels
        strip_is = False
        sample_count = args.sample_count if args.sample_count > 0 else 1
        xk_cfg: Xk100RankConfig | None = None
        pool = 0
    else:
        labels = list(XK100)
        yahoo_syms = [f"{t}.IS" for t in labels]
        strip_is = True
        xk_cfg = DEFAULT_CFG
        sample_count = args.sample_count if args.sample_count > 0 else xk_cfg.sample_count
        pool = args.pool if args.pool > 0 else xk_cfg.top_adv_pool

    if args.limit_symbols and args.limit_symbols > 0:
        labels = labels[: args.limit_symbols]
        yahoo_syms = yahoo_syms[: args.limit_symbols]

    print(f"\n======== {universe.upper()} ========")
    print(f"Loading Yahoo cache ({len(labels)} symbols)...")
    raw = get_yahoo_bars(
        universe,
        yahoo_syms,
        refresh=args.refresh_bars,
        max_age_days=args.max_age_days,
        period="5y",
    )
    bars = _prepare_bars(raw, strip_is=strip_is)
    bars, split_drops = drop_split_discontinuities(bars, max_abs_ret=0.40)
    print(f"Bars: {len(bars)}/{len(labels)} | split-drops: {len(split_drops)}")
    if split_drops:
        print(
            "  dropped: "
            + ", ".join(f"{s}(|r|={j:.0%})" for s, j in split_drops[:12])
            + ("..." if len(split_drops) > 12 else "")
        )

    asofs = _asof_dates(
        bars,
        start=args.start,
        end=args.end,
        lookback=args.lookback,
        pred_len=args.pred_len,
        step=args.step,
    )
    if not asofs:
        raise SystemExit(f"[{universe}] no valid as-of dates")
    print(
        f"As-of windows: {len(asofs)} | first={asofs[0].date()} last={asofs[-1].date()} "
        f"| lookback={args.lookback} pred_len={args.pred_len} step={args.step}"
    )
    print(f"sample_count={sample_count} top={args.top} model={args.model}")
    if xk_cfg is not None:
        print(
            f"XK100 cfg: price>={xk_cfg.min_price_try} adv>={xk_cfg.min_adv20_try} "
            f"|exp|<={xk_cfg.max_abs_expected} |t|>={xk_cfg.min_tstat} pool={pool}"
        )
    env_cfg = _envelope_cfg_from_args(args)
    if env_cfg is not None:
        print(
            f"Envelope: SMA{env_cfg.period} +/-{env_cfg.pct:.0%} "
            f"touch_tol={env_cfg.touch_tol:.0%} vol_pctile>={env_cfg.min_vol_pctile:.0%} "
            f"align={env_cfg.require_align}"
        )

    print("Loading Kronos...")
    predictor = load_predictor(args.model, device=args.device)
    use_cache = not args.no_cache

    windows_out: list[dict] = []
    all_picks: list[dict] = []
    ew_rets: list[float | None] = []
    sw_rets: list[float | None] = []
    total_scored = 0
    total_cache_hits = 0
    total_drops = 0
    total_prefilter_drops = 0

    for wi, asof in enumerate(asofs, 1):
        asof_s = str(asof.date())
        print(f"[{wi}/{len(asofs)}] {universe} as-of {asof_s}...")

        sliced: dict[str, pd.DataFrame] = {}
        for sym, df in bars.items():
            sub = _slice_to_asof(df, asof)
            if sub is not None and len(sub) >= args.lookback:
                sliced[sym] = sub

        score_syms = list(sliced.keys())
        pre_drops: list[dict] = []
        if xk_cfg is not None:
            # Liquidity + price pre-filter, then ADV pool (matches live intent / DEFAULT_CFG).
            eligible = []
            for sym in score_syms:
                ok, reason = passes_filters(sliced[sym], xk_cfg)
                if not ok:
                    pre_drops.append({"symbol": sym, "reason": reason})
                    continue
                eligible.append(sym)
            if pool > 0:
                pool_bars = {s: sliced[s] for s in eligible}
                score_syms = top_adv_symbols(pool_bars, pool, min_bars=args.lookback)
                pooled = set(score_syms)
                for sym in eligible:
                    if sym not in pooled:
                        pre_drops.append({"symbol": sym, "reason": "outside_adv_pool"})
            else:
                score_syms = eligible

        rows: list[dict] = []
        cache_hits = 0
        for si, sym in enumerate(score_syms, 1):
            if si == 1 or si % 10 == 0 or si == len(score_syms):
                print(f"  score {si}/{len(score_syms)} {sym}", flush=True)
            row = _score_one(
                predictor,
                universe,
                asof,
                sym,
                sliced[sym],
                model=args.model,
                lookback=args.lookback,
                pred_len=args.pred_len,
                sample_count=sample_count,
                use_cache=use_cache,
            )
            if row is None:
                continue
            # Detect cache hit: file existed with expected_return and we didn't mark cached False freshly
            # Re-check: if row has no 'cached' key from disk load
            if "cached" not in row:
                row["cached"] = True
                cache_hits += 1
            if "expected_return" in row and "error" not in row:
                row["actual_return"] = _realized_return(bars[sym], asof, args.pred_len)
                # Refresh liquidity metrics from as-of slice (even on cache hit)
                row["adv20"] = adv20(sliced[sym])
                row["vol5d"] = vol5d(sliced[sym])
                row["last_close"] = float(sliced[sym]["close"].iloc[-1])
            rows.append(row)

        env_drops: list[dict] = []
        rank_input = rows
        if env_cfg is not None:
            scored_ok = [
                r
                for r in rows
                if "expected_return" in r and "error" not in r and r.get("actual_return") is not None
            ]
            kept_env, env_drops = apply_envelope_vol_filter(scored_ok, sliced, env_cfg)
            rank_input = kept_env

        if xk_cfg is not None:
            ranked, rank_drops = _rank_xk100(rank_input, xk_cfg)
        else:
            ranked, rank_drops = _rank_spus(rank_input)
        rank_drops = env_drops + rank_drops

        picks = ranked[: args.top]
        m = _pick_metrics(picks)
        ew_r = _ew_period_return(picks)
        sw_r, sw_legs = _score_weight_period_return(
            picks,
            min_return=args.min_return,
            max_weight=args.max_weight,
        )
        ew_rets.append(ew_r)
        sw_rets.append(sw_r)

        for p in picks:
            all_picks.append({**p, "asof": asof_s})

        scored_n = sum(1 for r in rows if "expected_return" in r and "error" not in r)
        total_scored += scored_n
        total_cache_hits += cache_hits
        total_drops += len(rank_drops) + len(pre_drops)
        total_prefilter_drops += len(pre_drops)

        print(
            f"  scored={scored_n} cache_hits={cache_hits} ranked={len(ranked)} "
            f"picks={len(picks)} hit={m['hit_rate']} mae={m['mae_pp']} "
            f"ew_ret={None if ew_r is None else f'{ew_r:+.2%}'} "
            f"sw_ret={None if sw_r is None else f'{sw_r:+.2%}'}"
            + (f" env_drops={len(env_drops)}" if env_cfg is not None else "")
        )

        windows_out.append(
            {
                "asof": asof_s,
                "scored": scored_n,
                "cache_hits": cache_hits,
                "prefilter_drops": len(pre_drops),
                "envelope_drops": len(env_drops),
                "rank_drops": len(rank_drops),
                "ranked": len(ranked),
                **m,
                "ew_period_return": None if ew_r is None else round(ew_r, 6),
                "score_weight_period_return": None if sw_r is None else round(sw_r, 6),
                "picks": [
                    {
                        "symbol": p["symbol"],
                        "score": round(float(p["score"]), 6),
                        "expected_return": round(float(p["expected_return"]), 6),
                        "actual_return": round(float(p["actual_return"]), 6),
                        "last_close": p["last_close"],
                        **(
                            {
                                "envelope_side": p.get("envelope_side"),
                                "vol5d": None if p.get("vol5d") is None else round(float(p["vol5d"]), 6),
                            }
                            if env_cfg is not None
                            else {}
                        ),
                    }
                    for p in picks
                ],
                "sleeve_legs": sw_legs,
            }
        )

    overall = _pick_metrics(all_picks)
    ew_cum = _cum_from_period_returns(ew_rets)
    sw_cum = _cum_from_period_returns(sw_rets)

    out = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "universe": universe,
        "params": {
            "start": args.start,
            "end": args.end,
            "lookback": args.lookback,
            "pred_len": args.pred_len,
            "step": args.step,
            "top": args.top,
            "sample_count": sample_count,
            "model": args.model,
            "min_return": args.min_return,
            "max_weight": args.max_weight,
            "pool": pool if universe == "xk100" else None,
            "xk100_rank": cfg_to_dict(xk_cfg) if xk_cfg is not None else None,
            "envelope": None
            if env_cfg is None
            else {
                "period": env_cfg.period,
                "pct": env_cfg.pct,
                "touch_tol": env_cfg.touch_tol,
                "min_vol_pctile": env_cfg.min_vol_pctile,
                "require_align": env_cfg.require_align,
            },
            "asofs": [str(a.date()) for a in asofs],
            "n_windows": len(asofs),
        },
        "data": {
            "symbols_requested": len(labels),
            "bars_available": len(bars),
            "split_drops": [{"symbol": s, "max_abs_ret": round(j, 4)} for s, j in split_drops],
        },
        "summary": {
            **overall,
            "mean_realized_ew_topn": overall.get("mean_realized"),
            "total_scored_rows": total_scored,
            "total_cache_hits": total_cache_hits,
            "total_filter_drops": total_drops,
            "total_prefilter_drops": total_prefilter_drops,
            "ew_cumulative": {
                "final_nav": ew_cum["final_nav"],
                "total_return": ew_cum["total_return"],
                "mean_period_return": ew_cum["mean_period_return"],
                "n_periods": ew_cum["n_periods"],
            },
            "score_weight_sleeve": {
                "final_nav": sw_cum["final_nav"],
                "total_return": sw_cum["total_return"],
                "mean_period_return": sw_cum["mean_period_return"],
                "n_periods": sw_cum["n_periods"],
                "note": "full-NAV rebalance each as-of; weights=normalize(conviction), max_weight cap",
            },
        },
        "ew_nav_path": ew_cum["path"],
        "score_weight_nav_path": sw_cum["path"],
        "windows": windows_out,
    }

    TESTS.mkdir(parents=True, exist_ok=True)
    # H1 label covers Jan–Aug window requested
    tag = f"_{args.tag.strip()}" if args.tag and args.tag.strip() else ""
    path = TESTS / f"walkforward_{universe}_2026H1{tag}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved -> {path}")
    print("SUMMARY:", json.dumps(out["summary"], indent=2))
    return out


def main() -> int:
    args = parse_args()
    universes = ["spus", "xk100"] if args.universe == "both" else [args.universe]
    results = {}
    for u in universes:
        results[u] = run_universe(args, u)

    if len(results) == 2:
        print("\n======== SPUS vs XK100 ========")
        for u, r in results.items():
            s = r["summary"]
            print(
                f"{u:5} hit={s['hit_rate']} mae={s['mae_pp']}pp "
                f"mean_ret={s['mean_realized']} "
                f"ew_cum={s['ew_cumulative']['total_return']:+.2%} "
                f"sw_cum={s['score_weight_sleeve']['total_return']:+.2%} "
                f"n={s['n']} windows={r['params']['n_windows']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
