"""Background: wait for US market open, then submit Alpaca paper orders."""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]  # repo root

from trading.broker import make_trading_client, market_is_open
from config.settings import load_settings
from inference.models import DEFAULT_PAPER_MODEL

LOG = ROOT / "runtime" / "paper_results" / "ops" / "bg_submit.log"
NY = ZoneInfo("America/New_York")


def log(msg: str) -> None:
    line = f"{datetime.now(NY).isoformat()} | {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> int:
    settings = load_settings()
    client = make_trading_client(settings.api_key, settings.secret_key, paper=True)
    log("BG submit armed — waiting for US market open")
    while not market_is_open(client):
        time.sleep(15)
    log(f"Market open — running paper submit (full cash, {DEFAULT_PAPER_MODEL})")
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    job = ROOT / "scripts" / "run_alpaca_paper.py"
    rc = subprocess.run(
        [str(py), str(job), "--notional", "0", "--model", DEFAULT_PAPER_MODEL, "--submit"],
        cwd=str(ROOT),
    ).returncode
    log(f"Done exit={rc}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
