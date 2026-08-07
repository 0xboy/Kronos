# Sync local master with official Kronos (upstream). No push.
#
# Usage:
#   .\scripts\sync_upstream.ps1
#   .\scripts\sync_upstream.ps1 -DryRun
#   .\scripts\sync_upstream.ps1 -NoMerge   # fetch only

param(
    [switch]$DryRun,
    [switch]$NoMerge
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Assert-CleanEnough {
    $porcelain = git status --porcelain
    if (-not $porcelain) { return }
    # Allow ignored/untracked noise; block modified tracked files.
    $dirty = $porcelain | Where-Object { $_ -notmatch '^\?\?' }
    if ($dirty) {
        Write-Host "Working tree has local changes. Commit or stash first:"
        $dirty | ForEach-Object { Write-Host "  $_" }
        exit 1
    }
}

Write-Host "=== Kronos upstream sync (local-only, no push) ==="
Write-Host "Repo: $Root"

$upstream = git remote get-url upstream 2>$null
if (-not $upstream) {
    Write-Host "Missing remote 'upstream'. Expected https://github.com/shiyu-coder/Kronos.git"
    exit 1
}
Write-Host "upstream: $upstream"

Assert-CleanEnough

Write-Host "`nFetching upstream..."
git fetch upstream
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
$upstreamRef = "upstream/master"
if (-not (git rev-parse --verify $upstreamRef 2>$null)) {
    Write-Host "Missing $upstreamRef after fetch."
    exit 1
}

$counts = (git rev-list --left-right --count "${upstreamRef}...HEAD").Trim()
$left, $right = $counts -split '\s+'
Write-Host "`nCompared to ${upstreamRef}:"
Write-Host "  commits on upstream not in HEAD: $left"
Write-Host "  commits on HEAD not in upstream: $right"

if ([int]$left -eq 0) {
    Write-Host "`nAlready up to date with upstream/master."
    git status -sb
    exit 0
}

Write-Host "`nUpstream commits to merge:"
git log --oneline "HEAD..$upstreamRef" | Select-Object -First 20

if ($DryRun -or $NoMerge) {
    Write-Host "`nDryRun/NoMerge: fetch done, merge skipped."
    exit 0
}

Write-Host "`nMerging $upstreamRef into $branch..."
git merge --no-edit $upstreamRef
if ($LASTEXITCODE -ne 0) {
    Write-Host @"

Merge stopped (conflicts or error).
Guide: docs/UPSTREAM.md
  - Prefer OURS for paper/, paper scripts
  - Prefer THEIRS for model/, finetune/, webui/
Then: git add <files>; git commit
"@
    exit $LASTEXITCODE
}

Write-Host "`nMerge OK."
git status -sb
Write-Host "`nDone. Nothing was pushed (local-only)."
