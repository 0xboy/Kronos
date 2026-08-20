"""Quick Kronos forecast demo — saves a PNG, no GUI needed."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import torch

from inference.vendor import ensure_vendor_on_path, vendor_kronos_root

ensure_vendor_on_path()
from model import Kronos, KronosTokenizer, KronosPredictor  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]  # repo root
VENDOR = vendor_kronos_root()
DATA = VENDOR / "tests" / "data" / "regression_input.csv"
OUT = ROOT / "runtime" / "paper_results" / "demos" / "forecast_demo.png"

LOOKBACK = 400
PRED_LEN = 60


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    if not DATA.is_file():
        raise FileNotFoundError(
            f"Demo data missing at {DATA}. Run: git submodule update --init --recursive"
        )

    print("Loading tokenizer + Kronos-small from Hugging Face...")
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=512)

    df = pd.read_csv(DATA)
    df["timestamps"] = pd.to_datetime(df["timestamps"])
    print(f"Rows: {len(df)} | lookback={LOOKBACK} pred_len={PRED_LEN}")

    x_df = df.loc[: LOOKBACK - 1, ["open", "high", "low", "close", "volume", "amount"]]
    x_timestamp = df.loc[: LOOKBACK - 1, "timestamps"]
    y_timestamp = df.loc[LOOKBACK : LOOKBACK + PRED_LEN - 1, "timestamps"]

    pred_df = predictor.predict(
        df=x_df,
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=PRED_LEN,
        T=1.0,
        top_p=0.9,
        sample_count=10,
        verbose=True,
    )

    hist = df.loc[: LOOKBACK - 1]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(hist["timestamps"], hist["close"], label="history", color="black", linewidth=1.2)
    ax.plot(y_timestamp, pred_df["close"], label="forecast", color="royalblue", linewidth=1.4)
    ax.set_title("Kronos-small demo forecast")
    ax.legend()
    ax.grid(True, alpha=0.3)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT, dpi=140)
    print(f"Saved -> {OUT}")


if __name__ == "__main__":
    main()
