# Kronos Paper App

Local paper-trading and research layer on top of [Kronos](https://github.com/shiyu-coder/Kronos)
(vendored as a git submodule).

## Layout

```text
src/paper/          Application package (signals, broker, universes, cache)
scripts/            CLIs (Alpaca paper, XK100 tests, Yahoo cache, forecasts)
vendor/kronos/      Official Kronos submodule (model + upstream demos)
data/yahoo_cache/   Disk OHLCV cache (gitignored)
paper_results/      Run artifacts (gitignored)
pretrained/         Optional local HF weights (gitignored)
```

See [docs/VENDOR.md](docs/VENDOR.md) for submodule sync.

## Setup

```powershell
git submodule update --init --recursive
.\.venv\Scripts\python.exe -m pip install -e .

# Optional GPU torch (NVIDIA):
.\.venv\Scripts\python.exe -m pip install --force-reinstall torch --index-url https://download.pytorch.org/whl/cu128
```

Copy `.env.example` → `.env` and set Alpaca keys for paper trading.

## Common commands

```powershell
# Yahoo cache (once / refresh)
.\.venv\Scripts\python.exe scripts\fetch_yahoo_cache.py --universe xk100

# Score a universe from cache
.\.venv\Scripts\python.exe scripts\run_universe_test.py --universe xk100

# Alpaca paper dry-run / submit
.\.venv\Scripts\python.exe scripts\run_alpaca_paper.py
.\.venv\Scripts\python.exe scripts\run_alpaca_paper.py --submit

# Quick Kronos PNG demo (uses vendor test CSV)
.\.venv\Scripts\python.exe scripts\run_demo.py
```

## Upstream Kronos

- Submodule: `vendor/kronos` → https://github.com/shiyu-coder/Kronos
- License copy: [docs/LICENSE.kronos-upstream](docs/LICENSE.kronos-upstream)
- Do not push this app’s commits into the Kronos upstream repo

`origin` may still point at a historical Kronos fork on GitHub; prefer a dedicated
app remote when you publish this tree.
