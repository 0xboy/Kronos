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
  universe/       Catalogs + special pricing (commodities TRY/g, …)
  ranking/        XK100 filters / conviction ranking
  trading/        Alpaca broker, sizing, sleeve ledger, rebalance
  forecast/       Weekly forecast cards / reports
scripts/          Ops helpers (e.g. sync_vendor.ps1)
universe/         Editable membership JSON (spus100, xk100, commodities, crypto, exchanges)
vendor/kronos/    Official Kronos submodule
runtime/          Local runtime (gitignored contents)
  data/           Provider OHLCV caches (yahoo_cache/, …)
  pretrained/     Optional local HF weights
  universe/       Optional local list overrides
  forecasts/      Weekly cards / prediction reports
  tests/          Universe score + cache-check JSON
  experiments/    Ad-hoc research sessions
  manual_sleeve/  Trive / manual BIST sleeve
  demos/          Demo plot outputs
  paper_results/  Alpaca paper only (runs, ops, ledger)
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

Membership: edit [`universe/*.json`](universe/) (or drop overrides in
`runtime/universe/`). Special conversion logic stays in `src/universe/`.

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
