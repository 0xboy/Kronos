"""Repo and local runtime paths (cache, results, weights)."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# All large / generated local artifacts live under runtime/
RUNTIME = REPO_ROOT / "runtime"
YAHOO_CACHE = RUNTIME / "yahoo_cache"
PAPER_RESULTS = RUNTIME / "paper_results"
PRETRAINED = RUNTIME / "pretrained"
