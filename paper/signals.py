from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch

from model import Kronos, KronosPredictor, KronosTokenizer
from paper.models import (
    DEFAULT_PAPER_MODEL,
    model_label,
    resolve_max_context,
    resolve_model_id,
    resolve_tokenizer_id,
)


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


def resolve_device(device: str | None = None) -> str:
    """Pick inference device. Default: CUDA → MPS → CPU."""
    if device is None or str(device).strip().lower() in ("", "auto"):
        if torch.cuda.is_available():
            return "cuda:0"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    d = str(device).strip().lower()
    if d in ("cuda", "gpu"):
        d = "cuda:0"
    if d.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA requested but torch.cuda.is_available() is False. "
            "Install a CUDA build, e.g. "
            "pip install torch --index-url https://download.pytorch.org/whl/cu128"
        )
    return d


def device_summary(device: str | None = None) -> dict:
    """Small dict for logs / run JSON (GPU name, torch build)."""
    resolved = resolve_device(device)
    info: dict = {
        "device": resolved,
        "torch": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
    }
    if resolved.startswith("cuda") and torch.cuda.is_available():
        idx = int(resolved.split(":")[1]) if ":" in resolved else 0
        info["gpu"] = torch.cuda.get_device_name(idx)
        info["vram_gb"] = round(torch.cuda.get_device_properties(idx).total_memory / (1024**3), 2)
    return info


def load_predictor(model_id: str | None = None, device: str | None = None) -> KronosPredictor:
    if model_id is None or not str(model_id).strip():
        model_id = DEFAULT_PAPER_MODEL
    resolved = resolve_device(device)
    summary = device_summary(resolved)
    label = summary.get("gpu") or resolved
    checkpoint = resolve_model_id(model_id)
    print(f"Device: {resolved}" + (f" ({label})" if summary.get("gpu") else ""))
    print(f"Predictor: {model_label(model_id)} <- {checkpoint}")
    if resolved == "cpu" and "+cpu" in torch.__version__.lower():
        print(
            "Warning: CPU-only torch build detected. For GPU: "
            "pip install --force-reinstall torch --index-url https://download.pytorch.org/whl/cu128"
        )
    tokenizer_id = resolve_tokenizer_id(model_id)
    max_context = resolve_max_context(model_id)
    print(f"Tokenizer: {tokenizer_id} | max_context={max_context}")
    tokenizer = KronosTokenizer.from_pretrained(tokenizer_id)
    model = Kronos.from_pretrained(checkpoint)
    return KronosPredictor(model, tokenizer, device=resolved, max_context=max_context)


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
