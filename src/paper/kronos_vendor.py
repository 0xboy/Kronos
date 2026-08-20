"""Bootstrap the vendored Kronos repo onto sys.path."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VENDOR_KRONOS = _REPO_ROOT / "vendor" / "kronos"


def vendor_kronos_root() -> Path:
    return _VENDOR_KRONOS


def ensure_vendor_on_path() -> Path:
    """Ensure ``vendor/kronos`` is importable (provides ``model``)."""
    vendor = _VENDOR_KRONOS
    if not vendor.is_dir() or not (vendor / "model").is_dir():
        raise RuntimeError(
            f"Missing Kronos vendor at {vendor}. "
            "Run: git submodule update --init --recursive"
        )
    path = str(vendor)
    if path not in sys.path:
        sys.path.insert(0, path)
    return vendor
