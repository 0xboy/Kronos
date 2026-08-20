# Backlog

Living checklist for this app (Kronos submodule + paper/research layer).
Update as work lands.

## Done

- [x] Official Kronos as `vendor/kronos` git submodule (clean upstream)
- [x] Leave GitHub fork network → standalone `0xboy/Kronos`
- [x] App packages under `src/` (no wrapper app name):
  - `config`, `inference`, `data`, `universes`, `ranking`, `trading`, `forecast`
- [x] `pyproject.toml` + editable install (`kronos-paper`)
- [x] Local artifacts under `runtime/`:
  - `yahoo_cache/`, `paper_results/`, `pretrained/`
  - shared paths via `config.paths`
- [x] Remove unused `runtime/samples`
- [x] Vendor sync docs/script: `docs/VENDOR.md`, `scripts/sync_vendor.ps1`
- [x] Extract Alpaca rebalance planning → `trading/rebalance.py` (CLI keeps broker I/O)
- [x] CLI via root `main.py` / `python -m cli` / `kronos` (subcommands); old `scripts/*.py` removed
- [x] Ops loop / bg submit as `paper-loop` / `paper-bg` subcommands

## Next

- [ ] Typed settings with `pydantic-settings` (`config/settings.py`)
- [ ] Unit tests: ranking / sizing / ledger (mock broker; no GPU required)
- [ ] Forecast/report helpers further folded into `forecast/` (CLI already in `cli/`)

## Later / optional

- [ ] Rename GitHub repo when a better product name appears (keep `Kronos` for now)
- [ ] Single “sleeve” model spanning Alpaca paper + Trive manual XK100
- [ ] Web/API dashboard (not needed yet)
- [ ] Publish Kronos itself as a pip dependency (submodule is fine)

## Notes

- Kronos updates: `.\scripts\sync_vendor.ps1` (do not patch vendor defaults; use app config)
- Paper sleeve boundary: only positions in `runtime/paper_results/sleeve_ledger.json`
- Inference default paths: `DEFAULT_SAMPLE_COUNT=10` in `inference/signals.py`
