"""Named paper/inference model aliases.

Live stack uses Hugging Face stock models only:
  stock-small → NeoQuasar/Kronos-small  (default)
  stock-base  → NeoQuasar/Kronos-base
  stock-mini  → NeoQuasar/Kronos-mini

Local SPUS fine-tunes (spus-*-v1) are retired from paper/forecast defaults.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRETRAINED_DIR = ROOT / "pretrained"

# Short CLI / paper names → Hugging Face id or local checkpoint path.
MODEL_ALIASES: dict[str, str] = {
    "stock-mini": "NeoQuasar/Kronos-mini",
    "stock-small": "NeoQuasar/Kronos-small",
    "stock-base": "NeoQuasar/Kronos-base",
}

DEFAULT_PAPER_MODEL = "stock-small"
DEFAULT_TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"
DEFAULT_MAX_CONTEXT = 512

_HF_TO_LOCAL_NAME = {
    "NeoQuasar/Kronos-mini": "Kronos-mini",
    "NeoQuasar/Kronos-small": "Kronos-small",
    "NeoQuasar/Kronos-base": "Kronos-base",
    "NeoQuasar/Kronos-Tokenizer-base": "Kronos-Tokenizer-base",
    "NeoQuasar/Kronos-Tokenizer-2k": "Kronos-Tokenizer-2k",
}


def _prefer_local(hf_or_path: str) -> str:
    """Use repo pretrained/<name> when config.json is present (offline-safe)."""
    key = str(hf_or_path).strip()
    local_name = _HF_TO_LOCAL_NAME.get(key)
    if local_name is None:
        return key
    local = PRETRAINED_DIR / local_name
    if (local / "config.json").is_file():
        return str(local)
    return key

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
}


def resolve_model_id(name: str | None) -> str:
    """Map alias → concrete HF id / path; pass through unknown strings."""
    if name is None or not str(name).strip():
        name = DEFAULT_PAPER_MODEL
    key = str(name).strip()
    return _prefer_local(MODEL_ALIASES.get(key, key))


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
    if "kronos-base" in resolved or resolved.endswith("/kronos-base"):
        return MODEL_META["stock-base"]
    if "kronos-small" in resolved or resolved.endswith("/kronos-small"):
        return MODEL_META["stock-small"]
    return {}


def resolve_tokenizer_id(name: str | None) -> str:
    meta = _meta_for(name)
    return _prefer_local(str(meta.get("tokenizer") or DEFAULT_TOKENIZER))


def resolve_max_context(name: str | None) -> int:
    meta = _meta_for(name)
    return int(meta.get("max_context") or DEFAULT_MAX_CONTEXT)
