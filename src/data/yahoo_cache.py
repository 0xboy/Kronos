"""Yahoo daily OHLCV cache — download once, reuse for Kronos tests.

Layout:
  runtime/data/yahoo_cache/spus/AAPL.csv
  runtime/data/yahoo_cache/xk100/ASELS_IS.csv
  runtime/data/yahoo_cache/spus/manifest.json

Fetch uses Yahoo chart HTTP API (not ``yfinance.download``) for stability on
Windows / Python 3.13 (yfinance+old pandas datetime paths were segfaulting).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from config.paths import YAHOO_CACHE

CACHE_ROOT = YAHOO_CACHE
COLS = ["timestamps", "open", "high", "low", "close", "volume", "amount"]
# Disk cache is for FT + paper. Default Yahoo window is 2y; that silently
# replaced 2020+ history. Always prefer this floor unless caller passes start.
DEFAULT_HISTORY_START = "2020-01-01"

_CHART_UA = {"User-Agent": "Mozilla/5.0 (compatible; kronos-yahoo-cache/1.0)"}
_PERIOD_RANGE = {
    "1d": "1d",
    "5d": "5d",
    "10d": "15d",
    "15d": "15d",
    "1mo": "1mo",
    "3mo": "3mo",
    "6mo": "6mo",
    "1y": "1y",
    "2y": "2y",
    "5y": "5y",
    "10y": "10y",
    "ytd": "ytd",
    "max": "max",
}


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


def _to_unix(day: str | None, *, end_of_day: bool = False) -> int | None:
    if not day:
        return None
    ts = pd.Timestamp(day)
    if end_of_day:
        ts = ts + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return int(ts.timestamp())


def fetch_yahoo_chart(
    symbol: str,
    *,
    period: str = "2y",
    start: str | None = None,
    end: str | None = None,
    auto_adjust: bool = True,
    timeout: float = 30.0,
) -> pd.DataFrame | None:
    """Daily OHLCV via chart API -> Kronos columns. Returns None on failure."""
    params: dict[str, str] = {"interval": "1d", "events": "div,splits"}
    if start:
        p1 = _to_unix(start)
        p2 = _to_unix(end, end_of_day=True) if end else int(time.time())
        if p1 is None or p2 is None:
            return None
        params["period1"] = str(p1)
        params["period2"] = str(p2)
    else:
        params["range"] = _PERIOD_RANGE.get(period, period)

    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(symbol, safe="=^")
        + "?"
        + urllib.parse.urlencode(params)
    )
    req = urllib.request.Request(url, headers=_CHART_UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None

    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        return None
    res = results[0]
    ts = res.get("timestamp") or []
    if not ts:
        return None
    quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    adj_list = ((res.get("indicators") or {}).get("adjclose") or [{}])
    adj = (adj_list[0].get("adjclose") if adj_list else None) or []

    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    rows: list[dict] = []
    for i, raw_ts in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        o = opens[i] if i < len(opens) else None
        h = highs[i] if i < len(highs) else None
        lo = lows[i] if i < len(lows) else None
        if c is None or o is None or h is None or lo is None:
            continue
        scale = 1.0
        if auto_adjust and i < len(adj) and adj[i] is not None and float(c) != 0.0:
            scale = float(adj[i]) / float(c)
        vol = float(volumes[i] or 0.0) if i < len(volumes) else 0.0
        close = float(c) * scale
        rows.append(
            {
                "timestamps": datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
                .replace(tzinfo=None)
                .replace(hour=0, minute=0, second=0, microsecond=0),
                "open": float(o) * scale,
                "high": float(h) * scale,
                "low": float(lo) * scale,
                "close": close,
                "volume": vol,
                "amount": close * vol,
            }
        )
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df = (
        df.dropna(subset=["open", "high", "low", "close"])
        .drop_duplicates(subset=["timestamps"], keep="last")
        .sort_values("timestamps")
        .reset_index(drop=True)
    )
    return df[COLS] if len(df) else None


def download_yahoo(
    symbols: list[str],
    period: str = "2y",
    *,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Download daily bars (auto-adjusted) via Yahoo chart API."""
    out: dict[str, pd.DataFrame] = {}
    n = len(symbols)
    for i, sym in enumerate(symbols, 1):
        if i == 1 or i % 20 == 0 or i == n:
            print(f"  yahoo chart {i}/{n}")
        frame = fetch_yahoo_chart(sym, period=period, start=start, end=end, auto_adjust=True)
        if frame is not None:
            out[sym] = frame
        time.sleep(0.05)
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
