"""Multi-symbol K-line dataset from a directory of Yahoo-style CSVs."""
from __future__ import annotations

import os
import random
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset


class MultiSymbolKlineDataset(Dataset):
    """Load many symbol CSVs; sample sliding windows across symbols.

    Time split is by calendar date (not ratio), so train/val don't leak across symbols.
    """

    def __init__(
        self,
        data_path: str,
        data_type: str = "train",
        lookback_window: int = 400,
        predict_window: int = 1,
        clip: float = 5.0,
        seed: int = 42,
        train_end: str = "2025-06-30",
        val_end: str = "2026-08-13",
        n_samples: int | None = None,
        min_bars: int = 450,
    ):
        self.data_path = data_path
        self.data_type = data_type
        self.lookback_window = lookback_window
        self.predict_window = predict_window
        self.window = lookback_window + predict_window + 1
        self.clip = clip
        self.seed = seed
        self.train_end = pd.Timestamp(train_end)
        self.val_end = pd.Timestamp(val_end)
        self.py_rng = random.Random(seed)
        self.feature_list = ["open", "high", "low", "close", "volume", "amount"]
        self.time_feature_list = ["minute", "hour", "weekday", "day", "month"]

        self.data: dict[str, pd.DataFrame] = {}
        self.indices: list[tuple[str, int]] = []
        self._load_dir(min_bars=min_bars)

        if n_samples is None:
            n_samples = min(len(self.indices), 8000 if data_type == "train" else 2000)
        self.n_samples = min(n_samples, max(1, len(self.indices)))
        print(
            f"[{data_type.upper()}] symbols={len(self.data)} windows={len(self.indices)} "
            f"n_samples/epoch={self.n_samples} window={self.window}"
        )

    def _load_dir(self, min_bars: int) -> None:
        root = Path(self.data_path)
        if not root.is_dir():
            raise NotADirectoryError(f"Expected directory of CSVs: {root}")

        files = sorted(root.glob("*.csv"))
        # Skip FX / futures leftovers if mixed into folder
        skip = {"USDTRY=X", "GC=F", "SI=F", "PL=F", "PA=F", "HG=F", "ALI=F", "ZNC=F"}
        loaded = 0
        for path in files:
            if path.stem in skip:
                continue
            try:
                df = pd.read_csv(path)
            except Exception:
                continue
            if "timestamps" not in df.columns:
                continue
            need = set(self.feature_list)
            if not need.issubset(df.columns):
                continue
            df = df.copy()
            df["timestamps"] = pd.to_datetime(df["timestamps"])
            df = df.sort_values("timestamps").drop_duplicates("timestamps").reset_index(drop=True)
            if self.data_type == "train":
                df = df[df["timestamps"] <= self.train_end]
            else:
                # val: need lookback history before train_end, labels after
                # Keep rows up to val_end; only index starts that end in val period
                df = df[df["timestamps"] <= self.val_end]
            if len(df) < min_bars:
                continue
            df["minute"] = df["timestamps"].dt.minute
            df["hour"] = df["timestamps"].dt.hour
            df["weekday"] = df["timestamps"].dt.weekday
            df["day"] = df["timestamps"].dt.day
            df["month"] = df["timestamps"].dt.month
            df = df.ffill().dropna(subset=self.feature_list).reset_index(drop=True)
            if len(df) < self.window:
                continue

            sym = path.stem
            self.data[sym] = df[self.feature_list + self.time_feature_list + ["timestamps"]]
            series_len = len(df)
            for i in range(series_len - self.window + 1):
                end_i = i + self.window - 1
                ts_end = df["timestamps"].iloc[end_i]
                if self.data_type == "train":
                    if ts_end <= self.train_end:
                        self.indices.append((sym, i))
                else:
                    # validation windows whose last bar is after train_end
                    if ts_end > self.train_end and ts_end <= self.val_end:
                        self.indices.append((sym, i))
            loaded += 1

        if not self.indices:
            raise RuntimeError(
                f"No samples for {self.data_type} under {root} "
                f"(train_end={self.train_end.date()}, val_end={self.val_end.date()})"
            )
        print(f"[{self.data_type.upper()}] loaded {loaded} symbol CSVs from {root}")

    def set_epoch_seed(self, epoch: int) -> None:
        self.py_rng.seed(self.seed + epoch)
        self.current_epoch = epoch

    def __len__(self) -> int:
        return self.n_samples

    def __getitem__(self, idx: int):
        random_idx = self.py_rng.randint(0, len(self.indices) - 1)
        symbol, start_idx = self.indices[random_idx]
        df = self.data[symbol]
        end_idx = start_idx + self.window
        window_data = df.iloc[start_idx:end_idx]

        x = window_data[self.feature_list].values.astype(np.float32)
        x_stamp = window_data[self.time_feature_list].values.astype(np.float32)

        x_mean, x_std = np.mean(x, axis=0), np.std(x, axis=0)
        x = (x - x_mean) / (x_std + 1e-5)
        x = np.clip(x, -self.clip, self.clip)

        return torch.from_numpy(x), torch.from_numpy(x_stamp)
