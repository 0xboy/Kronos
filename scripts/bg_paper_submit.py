"""Background: wait for US market open, then submit Alpaca paper orders."""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]  # repo root
sys.path.insert(0, str(ROOT))

from paper.broker import make_trading_client, market_is_open
from paper.config import load_settings

LOG = ROOT / "paper_results" / "ops" / "bg_submit.log"
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
    log("Market open — running paper submit ($20k)")
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    job = ROOT / "scripts" / "run_alpaca_paper.py"
    rc = subprocess.run(
        [str(py), str(job), "--notional", "20000", "--submit"],
        cwd=str(ROOT),
    ).returncode
    log(f"Done exit={rc}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
