# Kronos Paper App

Local paper-trading and research layer on top of [Kronos](https://github.com/shiyu-coder/Kronos)
(vendored as a git submodule).

## Layout

```text
main.py           Single CLI entry (subcommands)
src/
  cli/            Command implementations
  config/         Settings + paths
  inference/      Kronos vendor bridge, models, scoring
  data/           Yahoo cache + Alpaca bars helpers
  universes/      SPUS, XK100, commodities, crypto
  ranking/        XK100 filters / conviction ranking
  trading/        Alpaca broker, sizing, sleeve ledger, rebalance
  forecast/       Weekly forecast cards / reports
scripts/          Ops helpers (e.g. sync_vendor.ps1)
vendor/kronos/    Official Kronos submodule
runtime/          Local runtime (gitignored contents)
  yahoo_cache/    Disk OHLCV cache
  paper_results/  Runs, forecasts, ledger, ops
  pretrained/     Optional local HF weights
```

See [docs/VENDOR.md](docs/VENDOR.md) for submodule sync.
See [docs/BACKLOG.md](docs/BACKLOG.md) for done / next work.

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
python main.py --help
python main.py paper --help
python main.py cache --universe xk100
python main.py universe --universe xk100
python main.py paper
python main.py paper --submit
python main.py demo
python main.py forecast-report
python main.py forecast-track --freeze
```

Same via installed console script: `kronos paper --submit`  
or module form: `python -m cli paper --submit`

## Upstream Kronos

- Submodule: `vendor/kronos` → https://github.com/shiyu-coder/Kronos
- License copy: [docs/LICENSE.kronos-upstream](docs/LICENSE.kronos-upstream)
- Do not push this app’s commits into the Kronos upstream repo
