"""
Cron-like daily paper runner for Kronos + Alpaca.

Default: full 50-symbol universe, once per US trading day near the open
(09:35 ET), for 5 trading days. Does not rebalance at the close.
PC must stay on (or wake) for the schedule to fire.

Stop:
  - create file paper_results/ops/STOP_LOOP
  - or Ctrl+C
  - or: schtasks /Delete /TN KronosAlpacaPaper5d /F
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]  # repo root
STATE_PATH = ROOT / "paper_results" / "ops" / "loop_state.json"
STOP_PATH = ROOT / "paper_results" / "ops" / "STOP_LOOP"
LOG_PATH = ROOT / "paper_results" / "ops" / "loop.log"
NY = ZoneInfo("America/New_York")
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
JOB = ROOT / "scripts" / "run_alpaca_paper.py"

# Slightly after the 09:30 ET open so the auction settles.
DEFAULT_HOUR = 9
DEFAULT_MINUTE = 35
# Turkey local ≈ ET+7 during US daylight saving (EDT).
TASK_LOCAL_ST = "16:35"


def log(msg: str) -> None:
    line = f"{datetime.now(NY).isoformat()} | {msg}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"completed_days": [], "target_days": 5}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def is_us_weekday(d: date) -> bool:
    return d.weekday() < 5  # Mon-Fri (simple; ignores market holidays)


def next_run_after(now: datetime, hour: int, minute: int) -> datetime:
    """Next Mon-Fri at HH:MM America/New_York."""
    now = now.astimezone(NY)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    while not is_us_weekday(candidate.date()):
        candidate += timedelta(days=1)
    return candidate


def run_once(limit: int, submit: bool, notional: float) -> int:
    cmd = [
        str(PYTHON),
        str(JOB),
        "--limit",
        str(limit),
        "--notional",
        str(notional),
    ]
    if submit:
        cmd.append("--submit")
    log(f"Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(ROOT))
    log(f"Exit code: {proc.returncode}")
    return proc.returncode


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cron-like 5-day Alpaca paper loop")
    p.add_argument("--days", type=int, default=5, help="Trading days to complete")
    p.add_argument("--limit", type=int, default=0, help="Symbol count (0 = all 50)")
    p.add_argument("--notional", type=float, default=20000.0)
    p.add_argument("--submit", action="store_true", help="Submit paper orders")
    p.add_argument(
        "--hour",
        type=int,
        default=DEFAULT_HOUR,
        help="Run hour in US/Eastern (daemon mode; default near open)",
    )
    p.add_argument(
        "--minute",
        type=int,
        default=DEFAULT_MINUTE,
        help="Run minute in US/Eastern (daemon mode; default near open)",
    )
    p.add_argument("--run-now", action="store_true", help="Fire one run immediately, then schedule")
    p.add_argument(
        "--once",
        action="store_true",
        help="Cron mode: run at most once today if needed, then exit",
    )
    p.add_argument("--install-task", action="store_true", help="Register Windows Task Scheduler job")
    return p.parse_args()


def install_windows_task() -> None:
    """Register weekday Task Scheduler job near US market open."""
    ops = ROOT / "paper_results" / "ops"
    ops.mkdir(parents=True, exist_ok=True)
    bat = ops / "daily_job.bat"
    bat.write_text(
        "@echo off\r\n"
        f'cd /d "{ROOT}"\r\n'
        f'"{PYTHON}" "{ROOT / "scripts" / "run_alpaca_loop.py"}" --once --days 5 --limit 0 --notional 20000 --submit >> '
        f'"{ops / "task.log"}" 2>&1\r\n',
        encoding="utf-8",
    )
    cmd = [
        "schtasks",
        "/Create",
        "/TN",
        "KronosAlpacaPaper5d",
        "/TR",
        str(bat),
        "/SC",
        "WEEKLY",
        "/D",
        "MON,TUE,WED,THU,FRI",
        "/ST",
        TASK_LOCAL_ST,
        "/F",
    ]
    log(f"Installing task: {' '.join(cmd)}")
    subprocess.run(cmd, check=False)
    log(f"Task: KronosAlpacaPaper5d @ {TASK_LOCAL_ST} local (~09:35 ET open), Mon-Fri")
    log("Delete: schtasks /Delete /TN KronosAlpacaPaper5d /F")


def run_once_cron(args: argparse.Namespace) -> int:
    state = load_state()
    state["target_days"] = args.days
    done = list(state.get("completed_days", []))
    today = datetime.now(NY).date()

    if len(done) >= args.days:
        log(f"Already finished {len(done)}/{args.days} days — nothing to do")
        save_state(state)
        return 0

    if not is_us_weekday(today):
        log("Weekend — skip")
        return 0

    today_s = today.isoformat()
    if today_s in done:
        log(f"Already ran on {today_s}")
        return 0

    rc = run_once(args.limit, args.submit, args.notional)
    if rc == 0:
        done.append(today_s)
        state["completed_days"] = done
        save_state(state)
        log(f"Progress: {len(done)}/{args.days}")
        if len(done) >= args.days:
            log("5-day experiment complete")
    return rc


def main() -> int:
    args = parse_args()
    if not PYTHON.exists():
        print(f"Missing venv python: {PYTHON}")
        return 1

    if args.install_task:
        install_windows_task()
        return 0

    if args.once:
        return run_once_cron(args)

    state = load_state()
    state["target_days"] = args.days
    save_state(state)

    log(
        f"Loop armed: {args.days} trading days | limit={args.limit} | "
        f"submit={args.submit} | daily @{args.hour:02d}:{args.minute:02d} ET"
    )
    log(f"Stop file: {STOP_PATH}")

    if args.run_now:
        today = datetime.now(NY).date().isoformat()
        if today not in state["completed_days"]:
            rc = run_once(args.limit, args.submit, args.notional)
            if rc == 0:
                state["completed_days"].append(today)
                save_state(state)
                log(f"Progress: {len(state['completed_days'])}/{args.days}")
        else:
            log(f"Already completed today ({today}), skipping run-now")

    while True:
        if STOP_PATH.exists():
            log("STOP_LOOP found — exiting")
            return 0

        state = load_state()
        done = state.get("completed_days", [])
        if len(done) >= args.days:
            log(f"Done: {len(done)}/{args.days} trading days complete")
            return 0

        now = datetime.now(NY)
        today = now.date().isoformat()
        target = next_run_after(now, args.hour, args.minute)

        scheduled_today = now.replace(hour=args.hour, minute=args.minute, second=0, microsecond=0)
        in_window = (
            is_us_weekday(now.date())
            and today not in done
            and scheduled_today <= now <= scheduled_today + timedelta(minutes=20)
        )

        if in_window:
            rc = run_once(args.limit, args.submit, args.notional)
            if rc == 0:
                done.append(today)
                state["completed_days"] = done
                save_state(state)
                log(f"Progress: {len(done)}/{args.days}")
            else:
                log("Run failed — will retry next window")
            time.sleep(60)
            continue

        sleep_s = max(30, min(300, (target - now).total_seconds()))
        log(
            f"Sleeping ~{int(sleep_s)}s | next slot {target.isoformat()} | "
            f"progress {len(done)}/{args.days}"
        )
        end = time.time() + sleep_s
        while time.time() < end:
            if STOP_PATH.exists():
                log("STOP_LOOP found — exiting")
                return 0
            time.sleep(10)


if __name__ == "__main__":
    raise SystemExit(main())
