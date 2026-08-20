"""Yahoo daily OHLCV cache — download once, reuse for Kronos tests.

Layout:
  data/yahoo_cache/spus/AAPL.csv
  data/yahoo_cache/xk100/ASELS_IS.csv
  data/yahoo_cache/spus/manifest.json
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
CACHE_ROOT = ROOT / "data" / "yahoo_cache"
COLS = ["timestamps", "open", "high", "low", "close", "volume", "amount"]
# Disk cache is for FT + paper. Default Yahoo window is 2y; that silently
# replaced 2020+ history. Always prefer this floor unless caller passes start.
DEFAULT_HISTORY_START = "2020-01-01"


def cache_dir(universe: str) -> Path:
    d = CACHE_ROOT / universe
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_name(symbol: str) -> str:
    return symbol.replace("/", "_").replace("\\", "_").replace(".", "_")


def csv_path(universe: str, symbol: str) -> Path:
    return cache_dir(universe) / f"{_safe_name(symbol)}.csv"


def load_symbol(universe: str, symbol: str) -> pd.DataFrame | None:
    path = csv_path(universe, symbol)
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if "timestamps" not in df.columns:
        return None
    df["timestamps"] = pd.to_datetime(df["timestamps"])
    return df.sort_values("timestamps").reset_index(drop=True)


def save_symbol(universe: str, symbol: str, df: pd.DataFrame) -> Path:
    path = csv_path(universe, symbol)
    df[COLS].to_csv(path, index=False)
    return path


def _flatten_ohlcv(sdf: pd.DataFrame) -> pd.DataFrame:
    """Normalize yfinance single/multi-index OHLCV frames to flat columns."""
    if sdf is None or sdf.empty:
        return sdf
    if isinstance(sdf.columns, pd.MultiIndex):
        # Two common layouts:
        #   group_by=ticker -> ('AAPL', 'Close')
        #   default single  -> ('Close', 'AAPL')
        level0 = {c[0] for c in sdf.columns}
        price_names = {"Open", "High", "Low", "Close", "Volume", "Adj Close"}
        if level0 & price_names:
            # ('Close', ticker)
            pick = lambda col: next(  # noqa: E731
                (c for c in sdf.columns if c[0] == col),
                None,
            )
        else:
            # ('ticker', 'Close') — take first ticker slice if needed
            tickers = sorted(level0)
            t0 = tickers[0]
            if len(tickers) == 1 and all(c[0] == t0 for c in sdf.columns):
                pick = lambda col: next(  # noqa: E731
                    (c for c in sdf.columns if c[1] == col),
                    None,
                )
            else:
                # Unexpected multi-ticker frame passed as one — leave empty
                return pd.DataFrame(index=sdf.index)

        flat = {}
        for col in ("Open", "High", "Low", "Close", "Volume"):
            key = pick(col)
            if key is not None:
                flat[col] = sdf[key]
        return pd.DataFrame(flat, index=sdf.index)
    return sdf


def _to_kronos_frame(sdf: pd.DataFrame) -> pd.DataFrame | None:
    if sdf is None or sdf.empty:
        return None
    sdf = _flatten_ohlcv(sdf)
    if "Close" not in sdf.columns:
        return None
    sdf = sdf.dropna(subset=["Close"]).reset_index()
    ts_col = "Date" if "Date" in sdf.columns else sdf.columns[0]
    vol = sdf["Volume"] if "Volume" in sdf.columns else 0.0
    df = pd.DataFrame(
        {
            "timestamps": pd.to_datetime(sdf[ts_col]).dt.tz_localize(None),
            "open": sdf["Open"].astype(float),
            "high": sdf["High"].astype(float),
            "low": sdf["Low"].astype(float),
            "close": sdf["Close"].astype(float),
            "volume": pd.Series(vol).astype(float).fillna(0.0),
        }
    )
    df["amount"] = df["close"] * df["volume"]
    df = df.dropna().sort_values("timestamps").reset_index(drop=True)
    return df if len(df) else None


def download_yahoo(
    symbols: list[str],
    period: str = "2y",
    *,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Download daily bars. auto_adjust=True → split+dividend adjusted closes.

    If ``start`` is set (YYYY-MM-DD), Yahoo date range is used instead of ``period``.
    """
    out: dict[str, pd.DataFrame] = {}
    chunk = 40
    for i in range(0, len(symbols), chunk):
        part = symbols[i : i + chunk]
        print(f"  yahoo download {i + 1}-{i + len(part)} / {len(symbols)}")
        kwargs: dict = {
            "group_by": "ticker",
            "auto_adjust": True,
            "threads": True,
            "progress": False,
        }
        if start:
            kwargs["start"] = start
            if end:
                kwargs["end"] = end
        else:
            kwargs["period"] = period
        data = yf.download(part, **kwargs)
        for sym in part:
            try:
                if isinstance(data.columns, pd.MultiIndex) and sym in data.columns.get_level_values(0):
                    sdf = data[sym].copy()
                elif len(part) == 1:
                    sdf = data.copy()
                else:
                    sdf = data[sym].copy()
            except Exception:
                continue
            frame = _to_kronos_frame(sdf)
            if frame is not None:
                out[sym] = frame
    return out


def purge_universe_cache(universe: str) -> int:
    """Delete CSV caches for a universe (manifest kept until next write)."""
    d = cache_dir(universe)
    n = 0
    for path in d.glob("*.csv"):
        path.unlink(missing_ok=True)
        n += 1
    manifest = d / "manifest.json"
    if manifest.exists():
        manifest.unlink(missing_ok=True)
    return n


def scan_cache_discontinuities(
    universe: str,
    symbols: list[str] | None = None,
    *,
    max_abs_ret: float = 0.40,
) -> list[dict]:
    """Find cached series with split-like cliffs (should be empty if auto_adjust worked)."""
    d = cache_dir(universe)
    files = sorted(d.glob("*.csv"))
    if symbols is None:
        symbols = [p.stem.replace("_", ".") if p.stem.endswith("_IS") else p.stem for p in files]
        # Prefer actual symbol from filename via reverse of _safe_name is lossy; scan files directly.
        bad = []
        for path in files:
            df = pd.read_csv(path)
            if "close" not in df.columns or len(df) < 2:
                continue
            rets = pd.to_numeric(df["close"], errors="coerce").pct_change().dropna()
            if rets.empty:
                continue
            jump = float(rets.abs().max())
            if jump > max_abs_ret:
                bad.append(
                    {
                        "symbol": path.stem,
                        "max_abs_ret": round(jump, 4),
                        "path": str(path),
                    }
                )
        return bad

    bad = []
    for sym in symbols:
        df = load_symbol(universe, sym)
        if df is None or len(df) < 2:
            continue
        rets = pd.to_numeric(df["close"], errors="coerce").pct_change().dropna()
        if rets.empty:
            continue
        jump = float(rets.abs().max())
        if jump > max_abs_ret:
            bad.append({"symbol": sym, "max_abs_ret": round(jump, 4), "path": str(csv_path(universe, sym))})
    return bad


def _tail_needs_align(
    cached: pd.DataFrame | None,
    yahoo: pd.DataFrame,
    *,
    n_bars: int = 10,
    rel_tol: float = 0.001,
) -> bool:
    """True if cache last N session bars disagree with a fresh Yahoo pull."""
    if cached is None or cached.empty or yahoo is None or yahoo.empty:
        return True
    y = yahoo.tail(n_bars).copy()
    y["timestamps"] = pd.to_datetime(y["timestamps"]).dt.normalize()
    c = cached.copy()
    c["timestamps"] = pd.to_datetime(c["timestamps"]).dt.normalize()
    overlap = c.merge(y[["timestamps", "close"]], on="timestamps", how="inner", suffixes=("_c", "_y"))
    if len(overlap) != len(y):
        return True
    denom = overlap["close_y"].abs().clip(lower=1e-9)
    rel = (overlap["close_c"] - overlap["close_y"]).abs() / denom
    return bool((rel > rel_tol).any())


def _merge_tail(cached: pd.DataFrame | None, yahoo: pd.DataFrame, *, n_bars: int = 10) -> pd.DataFrame:
    """Replace cache rows from the first of Yahoo's last N bars onward."""
    y = yahoo.tail(n_bars).copy()
    y["timestamps"] = pd.to_datetime(y["timestamps"]).dt.tz_localize(None)
    if cached is None or cached.empty:
        return y.reset_index(drop=True)
    c = cached.copy()
    c["timestamps"] = pd.to_datetime(c["timestamps"]).dt.tz_localize(None)
    cut = pd.to_datetime(y["timestamps"].iloc[0])
    kept = c[c["timestamps"] < cut]
    merged = pd.concat([kept, y], ignore_index=True)
    merged = (
        merged.drop_duplicates(subset=["timestamps"], keep="last")
        .sort_values("timestamps")
        .reset_index(drop=True)
    )
    return merged[COLS]


def align_last_bars(
    universe: str,
    symbols: list[str],
    *,
    n_bars: int = 10,
    force: bool = False,
    lookback_calendar_days: int = 45,
    rel_tol: float = 0.001,
) -> dict[str, pd.DataFrame]:
    """Align only the last ``n_bars`` if they disagree with Yahoo (session checks).

    Full history is kept. Symbols already matching Yahoo's last N closes/dates
    are left untouched unless ``force=True``.
    """
    symbols = list(symbols)
    n_bars = max(1, int(n_bars))
    start = (date.today() - timedelta(days=lookback_calendar_days)).isoformat()
    print(
        f"Align tail: last {n_bars} bars for {len(symbols)} symbols "
        f"(yahoo start={start}, force={force})..."
    )
    fresh = download_yahoo(symbols, start=start)
    out: dict[str, pd.DataFrame] = {}
    updated = skipped = missing = 0
    for sym in symbols:
        ydf = fresh.get(sym)
        cdf = load_symbol(universe, sym)
        if ydf is None or ydf.empty:
            missing += 1
            if cdf is not None:
                out[sym] = cdf
            continue
        if not force and not _tail_needs_align(cdf, ydf, n_bars=n_bars, rel_tol=rel_tol):
            skipped += 1
            out[sym] = cdf if cdf is not None else ydf
            continue
        if cdf is None or cdf.empty:
            # No long history on disk — fall back to full floor pull for this symbol.
            full = download_yahoo([sym], start=DEFAULT_HISTORY_START).get(sym)
            merged = full if full is not None else ydf
        else:
            merged = _merge_tail(cdf, ydf, n_bars=n_bars)
        save_symbol(universe, sym, merged)
        out[sym] = merged
        updated += 1
    print(f"Align tail done: updated={updated} skipped_ok={skipped} yahoo_missing={missing}")
    _write_manifest(universe, symbols, out)
    return out


def get_yahoo_bars(
    universe: str,
    symbols: list[str],
    *,
    period: str = "2y",
    start: str | None = None,
    end: str | None = None,
    refresh: bool = False,
    max_age_days: int = 1,
    min_bars: int = 50,
) -> dict[str, pd.DataFrame]:
    """Load from disk cache; download only missing / stale / refresh=True.

    History floor is 2020-01-01 unless ``start`` is set. A fresh 2y CSV is
    treated as too short and re-pulled — otherwise FT keeps ~2 years forever.
    """
    symbols = list(symbols)
    cached: dict[str, pd.DataFrame] = {}
    need: list[str] = []
    pull_start = start if start else DEFAULT_HISTORY_START
    want_first = pd.Timestamp(pull_start) + pd.Timedelta(days=60)

    if refresh:
        need = list(symbols)
    else:
        for sym in symbols:
            path = csv_path(universe, sym)
            if not path.exists():
                need.append(sym)
                continue
            age_days = (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 86400
            if age_days > max_age_days:
                need.append(sym)
                continue
            df = load_symbol(universe, sym)
            if df is None or len(df) < min_bars:
                need.append(sym)
            else:
                first = pd.to_datetime(df["timestamps"].iloc[0])
                if first > want_first:
                    need.append(sym)
                    continue
                cached[sym] = df

    if need:
        label = f"start={pull_start}"
        print(f"Cache miss/stale: {len(need)}/{len(symbols)} — downloading from Yahoo ({label})...")
        fresh = download_yahoo(need, period=period, start=pull_start, end=end)
        for sym, df in fresh.items():
            save_symbol(universe, sym, df)
            cached[sym] = df
        missing = [s for s in need if s not in fresh]
        if missing:
            print(f"Yahoo still missing: {missing[:20]}{'...' if len(missing) > 20 else ''}")
    else:
        print(f"Cache hit: {len(cached)}/{len(symbols)} from {cache_dir(universe)}")

    _write_manifest(universe, symbols, cached)
    return cached


def _write_manifest(universe: str, requested: list[str], got: dict[str, pd.DataFrame]) -> None:
    rows = []
    for sym in requested:
        path = csv_path(universe, sym)
        df = got.get(sym)
        rows.append(
            {
                "symbol": sym,
                "cached": path.exists(),
                "bars": int(len(df)) if df is not None else 0,
                "first": str(df["timestamps"].iloc[0].date()) if df is not None and len(df) else None,
                "last": str(df["timestamps"].iloc[-1].date()) if df is not None and len(df) else None,
                "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
                if path.exists()
                else None,
            }
        )
    manifest = {
        "universe": universe,
        "updated": datetime.now(timezone.utc).isoformat(),
        "requested": len(requested),
        "available": sum(1 for r in rows if r["bars"] > 0),
        "rows": rows,
    }
    (cache_dir(universe) / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def check_cache(universe: str, symbols: list[str] | None = None) -> dict:
    """Summarize cache health for a universe."""
    d = cache_dir(universe)
    files = sorted(d.glob("*.csv"))
    by_name = {p.stem: p for p in files}
    symbols = symbols or list(by_name.keys())
    ok = thin = missing = 0
    details = []
    for sym in symbols:
        key = _safe_name(sym)
        path = by_name.get(key)
        if path is None:
            missing += 1
            details.append({"symbol": sym, "status": "missing"})
            continue
        df = load_symbol(universe, sym)
        n = 0 if df is None else len(df)
        last = None if df is None or df.empty else str(df["timestamps"].iloc[-1].date())
        status = "ok" if n >= 400 else ("thin" if n > 0 else "empty")
        if status == "ok":
            ok += 1
        elif status == "thin":
            thin += 1
        else:
            missing += 1
        details.append(
            {
                "symbol": sym,
                "status": status,
                "bars": n,
                "last": last,
                "age_hours": round(
                    (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 3600, 1
                ),
            }
        )
    return {
        "universe": universe,
        "cache_dir": str(d),
        "csv_files": len(files),
        "ok_ge_400_bars": ok,
        "thin": thin,
        "missing_or_empty": missing,
        "asof": date.today().isoformat(),
        "details": details,
    }
