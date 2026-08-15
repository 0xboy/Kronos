"""Named paper/inference model aliases.

Local FT checkpoints: spus-small-v1 (Kronos-small) and spus-base-v1 (Kronos-base).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Short CLI / paper names → Hugging Face id or local checkpoint path.
MODEL_ALIASES: dict[str, str] = {
    "stock-mini": "NeoQuasar/Kronos-mini",
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
    "spus-base-v1": str(
        ROOT
        / "finetune_csv"
        / "finetuned"
        / "spus_base_v1"
        / "basemodel"
        / "best_model"
    ),
}

DEFAULT_PAPER_MODEL = "spus-base-v1"
DEFAULT_TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"
DEFAULT_MAX_CONTEXT = 512

MODEL_META: dict[str, dict] = {
    "stock-mini": {
        "display_name": "Kronos stock mini",
        "architecture": "Kronos-mini",
        "tokenizer": "NeoQuasar/Kronos-Tokenizer-2k",
        "max_context": 2048,
        "notes": "Uses Tokenizer-2k; longer context than small/base.",
    },
    "stock-small": {
        "display_name": "Kronos stock small",
        "architecture": "Kronos-small",
        "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
        "max_context": 512,
    },
    "stock-base": {
        "display_name": "Kronos stock base",
        "architecture": "Kronos-base",
        "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
        "max_context": 512,
    },
    "spus-small-v1": {
        "display_name": "SPUS Small v1",
        "architecture": "Kronos-small",
        "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
        "max_context": 512,
        "source_exp": "spus_small_v1",
        "train_start": "2025-05-01",
        "train_end": "2026-06-30",
        "val_end": "2026-08-13",
        "notes": (
            "Predictor-only fine-tune of Kronos-small on SPUS daily bars; "
            "tokenizer frozen (Tokenizer-base)."
        ),
    },
    "spus-base-v1": {
        "display_name": "SPUS Base v1",
        "architecture": "Kronos-base",
        "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
        "max_context": 512,
        "source_exp": "spus_base_v1",
        "train_start": "2025-05-01",
        "train_end": "2026-06-30",
        "val_end": "2026-08-13",
        "best_val_loss": 2.3455,
        "notes": (
            "Predictor-only fine-tune of Kronos-base on SPUS daily bars "
            "(Colab T4, batch 32, 10 epochs); tokenizer frozen (Tokenizer-base)."
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


def _meta_for(name: str | None) -> dict:
    if name is None or not str(name).strip():
        name = DEFAULT_PAPER_MODEL
    key = str(name).strip()
    if key in MODEL_META:
        return MODEL_META[key]
    resolved = resolve_model_id(key).lower().replace("\\", "/")
    if "kronos-mini" in resolved or resolved.endswith("/kronos-mini"):
        return MODEL_META["stock-mini"]
    if "spus_base_v1" in resolved or "spus-base-v1" in resolved:
        return MODEL_META["spus-base-v1"]
    if "spus_small_v1" in resolved or "spus-small-v1" in resolved:
        return MODEL_META["spus-small-v1"]
    if "kronos-base" in resolved or resolved.endswith("/kronos-base"):
        return MODEL_META["stock-base"]
    if "kronos-small" in resolved or resolved.endswith("/kronos-small"):
        return MODEL_META["stock-small"]
    return {}


def resolve_tokenizer_id(name: str | None) -> str:
    meta = _meta_for(name)
    return str(meta.get("tokenizer") or DEFAULT_TOKENIZER)


def resolve_max_context(name: str | None) -> int:
    meta = _meta_for(name)
    return int(meta.get("max_context") or DEFAULT_MAX_CONTEXT)
