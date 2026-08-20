# Vendored Kronos (git submodule)

Official Kronos lives at `vendor/kronos` as a **git submodule**.
This app does not merge upstream into the app tree.

| Path | Source |
|------|--------|
| `vendor/kronos` | https://github.com/shiyu-coder/Kronos.git |
| `src/*` | Application packages (`config`, `inference`, `data`, `universes`, `ranking`, `trading`, `forecast`) |
| `scripts/` | App CLIs |

## Clone / init

```powershell
git clone --recurse-submodules <this-app-repo>
# or after a normal clone:
git submodule update --init --recursive
```

## Update Kronos pin

```powershell
# one-shot
.\scripts\sync_vendor.ps1

# or manually
git -C vendor/kronos fetch origin
git -C vendor/kronos checkout origin/master
git add vendor/kronos
git commit -m "Bump vendored Kronos"
```

Dry-run (fetch only, no checkout):

```powershell
.\scripts\sync_vendor.ps1 -DryRun
```

## Import bridge

App code loads Kronos via `inference.vendor.ensure_vendor_on_path()`, which puts
`vendor/kronos` on `sys.path` so `from model import Kronos, ...` works.

Do **not** patch files under `vendor/kronos` for app defaults (e.g. `sample_count`).
Set those in `src/inference` (see `DEFAULT_SAMPLE_COUNT` in `signals.py`).

## Attribution

Upstream license: [docs/LICENSE.kronos-upstream](LICENSE.kronos-upstream)
