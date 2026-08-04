from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame


def make_data_client(api_key: str, secret_key: str) -> StockHistoricalDataClient:
    return StockHistoricalDataClient(api_key, secret_key)


def fetch_daily_bars(
    client: StockHistoricalDataClient,
    symbols: Iterable[str],
    lookback_trading_days: int = 450,
    feed: DataFeed = DataFeed.IEX,
) -> dict[str, pd.DataFrame]:
    """Fetch daily OHLCV for many symbols. Returns {symbol: DataFrame}."""
    symbols = list(symbols)
    # Calendar buffer so we still get enough trading sessions
    start = datetime.now(timezone.utc) - timedelta(days=int(lookback_trading_days * 1.7))
    end = datetime.now(timezone.utc) - timedelta(minutes=20)

    req = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=feed,
    )
    barset = client.get_stock_bars(req)
    raw = barset.df
    if raw.empty:
        return {}

    out: dict[str, pd.DataFrame] = {}
    if isinstance(raw.index, pd.MultiIndex):
        for symbol in symbols:
            if symbol not in raw.index.get_level_values(0):
                continue
            sdf = raw.xs(symbol, level=0).copy()
            out[symbol] = _normalize_ohlcv(sdf)
    else:
        # Single-symbol response
        symbol = symbols[0]
        out[symbol] = _normalize_ohlcv(raw.copy())
    return out


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index()
    # alpaca-py often uses 'timestamp' column after reset
    ts_col = "timestamp" if "timestamp" in df.columns else df.columns[0]
    df = df.rename(columns={ts_col: "timestamps"})
    df["timestamps"] = pd.to_datetime(df["timestamps"])
    if getattr(df["timestamps"].dt, "tz", None) is not None:
        df["timestamps"] = df["timestamps"].dt.tz_convert(None)

    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            raise ValueError(f"Missing column {col}")

    df["amount"] = df["close"] * df["volume"]
    df = df[["timestamps", "open", "high", "low", "close", "volume", "amount"]]
    df = df.dropna().sort_values("timestamps").reset_index(drop=True)
    return df
