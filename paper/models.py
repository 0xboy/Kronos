"""Named paper/inference model aliases.

FT checkpoint is Kronos-small architecture (d_model=512), not Kronos-base.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Short CLI / paper names → Hugging Face id or local checkpoint path.
MODEL_ALIASES: dict[str, str] = {
    "stock-small": "NeoQuasar/Kronos-small",
    "stock-base": "NeoQuasar/Kronos-base",
    "spus-small-v1": str(
        ROOT
        / "finetune_csv"
        / "finetuned"
        / "spus_small_v1"
        / "basemodel"
        / "best_model"
    ),
}

DEFAULT_PAPER_MODEL = "spus-small-v1"

MODEL_META: dict[str, dict] = {
    "stock-small": {
        "display_name": "Kronos stock small",
        "architecture": "Kronos-small",
        "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
    },
    "stock-base": {
        "display_name": "Kronos stock base",
        "architecture": "Kronos-base",
        "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
    },
    "spus-small-v1": {
        "display_name": "SPUS Small v1",
        "architecture": "Kronos-small",
        "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
        "source_exp": "spus_small_v1",
        "train_start": "2025-05-01",
        "train_end": "2026-06-30",
        "val_end": "2026-08-13",
        "notes": (
            "Predictor-only fine-tune of Kronos-small on SPUS daily bars; "
            "tokenizer frozen (Tokenizer-base)."
        ),
    },
}


def resolve_model_id(name: str | None) -> str:
    """Map alias → concrete HF id / path; pass through unknown strings."""
    if name is None or not str(name).strip():
        name = DEFAULT_PAPER_MODEL
    key = str(name).strip()
    return MODEL_ALIASES.get(key, key)


def model_label(name: str | None) -> str:
    """Human-readable label for logs / run JSON."""
    if name is None or not str(name).strip():
        name = DEFAULT_PAPER_MODEL
    key = str(name).strip()
    meta = MODEL_META.get(key)
    if meta:
        return str(meta["display_name"])
    resolved = resolve_model_id(key)
    return Path(resolved).name if Path(resolved).exists() else resolved
