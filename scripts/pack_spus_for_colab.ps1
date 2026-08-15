# Zip SPUS CSVs for Google Drive / Colab upload.
# Usage: powershell -File scripts/pack_spus_for_colab.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Src = Join-Path $Root "data\yahoo_cache\spus"
$OutDir = Join-Path $Root "data"
$OutZip = Join-Path $OutDir "spus_for_colab.zip"

if (-not (Test-Path $Src)) {
    Write-Error "SPUS folder not found: $Src"
}

if (Test-Path $OutZip) { Remove-Item $OutZip -Force }

Compress-Archive -Path (Join-Path $Src "*") -DestinationPath $OutZip -CompressionLevel Optimal
$sizeMb = [math]::Round((Get-Item $OutZip).Length / 1MB, 2)
Write-Host "Created $OutZip ($sizeMb MB)"
Write-Host "Upload to Google Drive as: MyDrive/kronos/data/spus_for_colab.zip"
Write-Host "Or unzip locally into Drive folder: MyDrive/kronos/data/spus/"
