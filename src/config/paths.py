"""Repo and local runtime paths (cache, results, weights)."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# All large / generated local artifacts live under runtime/
RUNTIME = REPO_ROOT / "runtime"

# Provider market-data caches (Yahoo now; Alpaca / others later)
DATA = RUNTIME / "data"
YAHOO_CACHE = DATA / "yahoo_cache"
PRETRAINED = RUNTIME / "pretrained"
# Optional local overrides of tracked universe/*.json
UNIVERSE_OVERRIDE = RUNTIME / "universe"

# Research / scoring artifacts (not Alpaca paper)
FORECASTS = RUNTIME / "forecasts"
TESTS = RUNTIME / "tests"
EXPERIMENTS = RUNTIME / "experiments"
MANUAL_SLEEVE = RUNTIME / "manual_sleeve"
DEMOS = RUNTIME / "demos"

# Alpaca paper sleeve only
PAPER_RESULTS = RUNTIME / "paper_results"

# Tracked membership JSON (edit + commit)
UNIVERSE = REPO_ROOT / "universe"
