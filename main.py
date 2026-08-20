"""Root CLI: ``python main.py <command> [args...]``.

Examples:
  python main.py paper --help
  python main.py universe --universe xk100
  python main.py cache --universe xk100 --align-tail 10
"""
from __future__ import annotations

from cli.__main__ import console_main

if __name__ == "__main__":
    console_main()
