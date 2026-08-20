# Backlog

Living checklist for this app (Kronos submodule + paper/research layer).
Update as work lands.

## Done

- [x] Official Kronos as `vendor/kronos` git submodule (clean upstream)
- [x] Leave GitHub fork network → standalone `0xboy/Kronos`
- [x] App packages under `src/` (no wrapper app name):
  - `config`, `inference`, `data`, `universe`, `ranking`, `trading`, `forecast`
- [x] `pyproject.toml` + editable install (`kronos-paper`)
- [x] Local artifacts under `runtime/`:
  - `data/yahoo_cache/` (provider caches), `pretrained/`, `universe/` overrides
  - `forecasts/`, `tests/`, `experiments/`, `manual_sleeve/`, `demos/`
  - `paper_results/` = Alpaca paper only (`runs/`, `ops/`, ledger)
  - shared paths via `config.paths`
- [x] Remove unused `runtime/samples`
- [x] Vendor sync docs/script: `docs/VENDOR.md`, `scripts/sync_vendor.ps1`
- [x] Extract Alpaca rebalance planning → `trading/rebalance.py` (CLI keeps broker I/O)
- [x] CLI via root `main.py` / `python -m cli` / `kronos` (subcommands); old `scripts/*.py` removed
- [x] Ops loop / bg submit as `paper-loop` / `paper-bg` subcommands
- [x] Typed settings with `pydantic-settings` (`config/settings.py`)
- [x] Universe membership as editable JSON (`universe/*.json` + optional `runtime/universe/` override); domain package `src/universe/`
- [x] Forecast helpers in `forecast/` (`report.py`, `track.py`, `week.py`); CLI thin wrappers only

## Next

- [ ] Unit tests: ranking / sizing / ledger (mock broker; no GPU required)

## Later / optional

- [ ] Rename GitHub repo when a better product name appears (keep `Kronos` for now)
- [ ] Single “sleeve” model spanning Alpaca paper + Trive manual XK100
- [ ] Web/API dashboard (not needed yet)
- [ ] Publish Kronos itself as a pip dependency (submodule is fine)

## Notes

- Kronos updates: `.\scripts\sync_vendor.ps1` (do not patch vendor defaults; use app config)
- Paper sleeve boundary: only positions in `runtime/paper_results/sleeve_ledger.json`
- Inference default paths: `DEFAULT_SAMPLE_COUNT=10` in `inference/signals.py`
- Universe membership: edit `universe/*.json` (local override under `runtime/universe/`)
- Forecasts live under `runtime/forecasts/`; universe score JSON under `runtime/tests/`
