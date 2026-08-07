from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch

from model import Kronos, KronosPredictor, KronosTokenizer


@dataclass
class Signal:
    symbol: str
    last_close: float
    pred_close: float
    expected_return: float
    bars: int
    return_std: float = 0.0
    sample_count: int = 1
    score: float = 0.0


def load_predictor(model_id: str = "NeoQuasar/Kronos-small", device: str | None = None) -> KronosPredictor:
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained(model_id)
    return KronosPredictor(model, tokenizer, device=device, max_context=512)


def _one_predict(
    predictor: KronosPredictor,
    x_df: pd.DataFrame,
    x_ts: pd.Series,
    y_ts: pd.Series,
    pred_len: int,
) -> float:
    """Return terminal predicted close from a single sample path."""
    pred = predictor.predict(
        df=x_df,
        x_timestamp=x_ts,
        y_timestamp=y_ts,
        pred_len=pred_len,
        T=1.0,
        top_p=0.9,
        sample_count=1,
        verbose=False,
    )
    return float(pred["close"].iloc[-1])


def score_symbol(
    predictor: KronosPredictor,
    symbol: str,
    df: pd.DataFrame,
    lookback: int = 400,
    pred_len: int = 1,
    sample_count: int = 1,
) -> Signal | None:
    if len(df) < lookback:
        return None

    n = max(1, int(sample_count))
    window = df.iloc[-lookback:].reset_index(drop=True)
    x_df = window[["open", "high", "low", "close", "volume", "amount"]]
    x_ts = pd.Series(pd.to_datetime(window["timestamps"]), name="timestamps")

    # Synthetic future timestamps (business days) — Series required (Kronos uses .dt)
    last_ts = pd.Timestamp(x_ts.iloc[-1])
    y_ts = pd.Series(
        pd.bdate_range(start=last_ts + pd.Timedelta(days=1), periods=pred_len),
        name="timestamps",
    )

    last_close = float(window["close"].iloc[-1])
    pred_closes = [_one_predict(predictor, x_df, x_ts, y_ts, pred_len) for _ in range(n)]
    rets = [(pc / last_close) - 1.0 for pc in pred_closes]
    mean_ret = float(np.mean(rets))
    std_ret = float(np.std(rets, ddof=0)) if n > 1 else 0.0
    mean_pred = float(np.mean(pred_closes))

    return Signal(
        symbol=symbol,
        last_close=last_close,
        pred_close=mean_pred,
        expected_return=mean_ret,
        bars=len(window),
        return_std=std_ret,
        sample_count=n,
        score=0.0,
    )
