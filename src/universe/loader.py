"""Load universe membership / meta JSON (editable, overridable)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from config.paths import UNIVERSE, UNIVERSE_OVERRIDE

# Tracked defaults / shared edits live here (commit when membership changes).
UNIVERSE_DIR = UNIVERSE
# Optional local overrides (gitignored) — wins over tracked files.
OVERRIDE_DIR = UNIVERSE_OVERRIDE


def _resolve_path(name: str) -> Path:
    key = name.strip().lower().replace("_", "")
    aliases = {
        "spus": "spus100",
        "spus100": "spus100",
        "xk": "xk100",
        "xk100": "xk100",
    }
    key = aliases.get(key, key)
    for directory in (OVERRIDE_DIR, UNIVERSE_DIR):
        path = directory / f"{key}.json"
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"Universe '{name}' not found. Expected {UNIVERSE_DIR / f'{key}.json'} "
        f"(or override at {OVERRIDE_DIR / f'{key}.json'})"
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _symbols_from_payload(data: Any, *, path: Path) -> list[str]:
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        raw = data.get("symbols")
        if raw is None:
            raise ValueError(f"{path}: JSON object must include 'symbols' list")
    else:
        raise ValueError(f"{path}: expected list or object with 'symbols'")
    symbols = [str(s).strip().upper() for s in raw if str(s).strip()]
    if not symbols:
        raise ValueError(f"{path}: empty symbol list")
    dupes = [s for s in symbols if symbols.count(s) > 1]
    if dupes:
        raise ValueError(f"{path}: duplicate symbols: {sorted(set(dupes))}")
    return symbols


@lru_cache(maxsize=32)
def load_json(name: str) -> Any:
    """Load ``name.json`` (e.g. ``commodities``, ``exchanges``)."""
    return _read_json(_resolve_path(name))


@lru_cache(maxsize=16)
def load_universe(name: str) -> list[str]:
    """Load equity symbol list ``name`` (e.g. ``spus100``, ``xk100``).

    Resolution order:
      1. ``runtime/universe/{name}.json`` (local override)
      2. ``universe/{name}.json`` (tracked)
    """
    path = _resolve_path(name)
    return _symbols_from_payload(_read_json(path), path=path)


def clear_universe_cache() -> None:
    load_json.cache_clear()
    load_universe.cache_clear()
