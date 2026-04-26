param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [switch]$CreatePlaceholderMbTiles
)

$ErrorActionPreference = "Stop"

Write-Host "SPES Russia overview offline map preparation"
Write-Host "Project root: $ProjectRoot"

$mapDir = Join-Path $ProjectRoot "MapData\Russia"
if (-not (Test-Path $mapDir)) {
    New-Item -ItemType Directory -Path $mapDir | Out-Null
}

$manifestPath = Join-Path $mapDir "russia_manifest.json"
$stylePath = Join-Path $mapDir "russia_style.json"
$tilesPath = Join-Path $mapDir "russia_map.mbtiles"

if (-not (Test-Path $stylePath)) {
    @'
{
  "name": "SPES Russia overview offline style",
  "source": "OpenStreetMap contributors",
  "notes": "Low-zoom basemap for legacy tab (optional package)."
}
'@ | Set-Content -Path $stylePath -Encoding UTF8
}

if ($CreatePlaceholderMbTiles -and -not (Test-Path $tilesPath)) {
    New-Item -ItemType File -Path $tilesPath | Out-Null
}

$tileSizeBytes = 0
if (Test-Path $tilesPath) {
    $tileSizeBytes = (Get-Item $tilesPath).Length
}

$manifest = @{
    package = "SPES_RUSSIA_OVERVIEW_OFFLINE_MAP"
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    attribution = "OpenStreetMap contributors (ODbL)"
    expected_files = @("russia_manifest.json", "russia_style.json", "russia_map.mbtiles")
    tiles_file_size_bytes = $tileSizeBytes
    notes = "Optional. Run: py tools/download_russia_mbtiles.py"
} | ConvertTo-Json -Depth 4

$manifest | Set-Content -Path $manifestPath -Encoding UTF8

Write-Host ""
Write-Host "Prepared: $mapDir"
Write-Host "To download tiles: py tools\download_russia_mbtiles.py"
