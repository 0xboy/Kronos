# Upstream Kronos sync (local-only)

This repo tracks the official Kronos project locally. Paper/forecast work stays on
your machine — nothing is pushed to GitHub.

## Remotes

| Remote     | URL                                      | Role                          |
|------------|------------------------------------------|-------------------------------|
| `upstream` | `https://github.com/shiyu-coder/Kronos.git` | Fetch official updates only |
| push       | `DISABLE`                                | Accidental push blocked       |

There is no `origin` fork. Do not push paper commits to `shiyu-coder/Kronos`.

## Pull updates

```powershell
# one-shot
.\scripts\sync_upstream.ps1

# or manually
git fetch upstream
git merge upstream/master
```

Merge (not rebase) keeps your paper commit history intact.

## After merge

```powershell
git status
# resolve conflicts if any, then:
git add <files>
git commit   # completes the merge commit
```

## Conflict guide

| Area | Prefer |
|------|--------|
| `paper/`, `scripts/run_alpaca_paper.py`, `scripts/track_forecasts.py`, `scripts/run_universe_test.py`, `scripts/make_prediction_report.py`, `scripts/sync_upstream.ps1` | **Ours** (local paper work) |
| `model/`, `finetune/`, `webui/`, upstream examples, upstream README | **Theirs** (`upstream/master`) unless you intentionally patched them |

Do not blind-resolve with `git checkout --ours/--theirs` across the whole tree.
Inspect each conflicted file.

`paper_results/` is gitignored and never part of sync.

## Current layout reminder

- Your paper commits live only on local `master`
- `git status` may show `ahead of upstream/master` — that is expected
- To see what upstream added since your tip: `git log HEAD..upstream/master --oneline`
