"""``python -m cli <command> [args...]`` and ``kronos`` console entry."""
from __future__ import annotations

import sys
from collections.abc import Callable

Command = Callable[[], int]

_COMMANDS: dict[str, tuple[str, str]] = {
    # name: (module, docstring hint)
    "paper": ("cli.paper", "Alpaca paper sleeve rebalance"),
    "universe": ("cli.universe", "Score a universe from Yahoo cache"),
    "cache": ("cli.cache", "Fetch / check Yahoo OHLCV cache"),
    "demo": ("cli.demo", "Quick Kronos PNG forecast demo"),
    "forecast-report": ("cli.forecast_report", "Build top-N prediction report"),
    "forecast-track": ("cli.forecast_track", "Freeze / check forecast cards"),
    "paper-loop": ("cli.paper_loop", "Daily paper rebalance loop"),
    "paper-bg": ("cli.paper_bg", "Wait for open, then submit paper"),
}


def _load_main(module_path: str) -> Command:
    import importlib

    mod = importlib.import_module(module_path)
    fn = getattr(mod, "main", None)
    if fn is None:
        raise RuntimeError(f"{module_path} has no main()")
    return fn  # type: ignore[return-value]


def _help_text() -> str:
    lines = [
        "Usage: python main.py <command> [args...]",
        "   or: python -m cli <command> [args...]",
        "   or: kronos <command> [args...]",
        "",
        "Commands:",
    ]
    width = max(len(k) for k in _COMMANDS)
    for name, (_, hint) in sorted(_COMMANDS.items()):
        lines.append(f"  {name:<{width}}  {hint}")
    lines.append("")
    lines.append("Run `python main.py <command> --help` for command options.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(_help_text())
        return 0

    cmd = args[0]
    rest = args[1:]
    if cmd not in _COMMANDS:
        print(f"Unknown command: {cmd}\n", file=sys.stderr)
        print(_help_text(), file=sys.stderr)
        return 2

    module_path, _ = _COMMANDS[cmd]
    run = _load_main(module_path)
    # So nested argparse sees the subcommand as program name.
    sys.argv = [f"main.py {cmd}", *rest]
    result = run()
    return int(result or 0)


def console_main() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    console_main()
