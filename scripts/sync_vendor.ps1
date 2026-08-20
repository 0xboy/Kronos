# Sync vendored Kronos submodule (no push).

# Usage:
#   .\scripts\sync_vendor.ps1
#   .\scripts\sync_vendor.ps1 -DryRun
#   .\scripts\sync_vendor.ps1 -NoCheckout   # fetch only

param(
    [switch]$DryRun,
    [switch]$NoCheckout
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Vendor = Join-Path $Root "vendor\kronos"
if (-not (Test-Path (Join-Path $Vendor ".git")) -and -not (Test-Path (Join-Path $Vendor "model"))) {
    Write-Host "Missing vendor/kronos. Run: git submodule update --init --recursive"
    exit 1
}

Write-Host "=== Vendored Kronos sync ==="
Write-Host "Repo: $Root"
Write-Host "Vendor: $Vendor"

$porcelain = git status --porcelain --ignore-submodules=dirty
$dirty = $porcelain | Where-Object { $_ -notmatch '^\?\?' -and $_ -notmatch 'vendor/kronos' }
if ($dirty) {
    Write-Host "Working tree has local changes. Commit or stash first:"
    $dirty | ForEach-Object { Write-Host "  $_" }
    exit 1
}

Write-Host "`nFetching submodule..."
git -C $Vendor fetch origin
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$current = (git -C $Vendor rev-parse HEAD).Trim()
$target = (git -C $Vendor rev-parse origin/master).Trim()
Write-Host "Current: $current"
Write-Host "origin/master: $target"

if ($current -eq $target) {
    Write-Host "`nAlready on origin/master."
    git submodule status
    exit 0
}

if ($DryRun -or $NoCheckout) {
    Write-Host "`nDryRun/NoCheckout: fetch done, checkout skipped."
    git -C $Vendor log --oneline "$current..$target" | Select-Object -First 20
    exit 0
}

Write-Host "`nChecking out origin/master..."
git -C $Vendor checkout origin/master
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

git add vendor/kronos
Write-Host "`nStaged vendor/kronos at $target"
Write-Host "Commit when ready: git commit -m `"Bump vendored Kronos`""
git submodule status
