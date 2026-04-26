param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [switch]$CreatePlaceholderMbTiles
)

$ErrorActionPreference = "Stop"

Write-Host "SPES CFO offline map preparation"
Write-Host "Project root: $ProjectRoot"

$mapDir = Join-Path $ProjectRoot "MapData\CFO"
if (-not (Test-Path $mapDir)) {
    New-Item -ItemType Directory -Path $mapDir | Out-Null
}

$manifestPath = Join-Path $mapDir "cfo_manifest.json"
$stylePath = Join-Path $mapDir "cfo_style.json"
$tilesPath = Join-Path $mapDir "cfo_map.mbtiles"

if (-not (Test-Path $stylePath)) {
    @'
{
  "name": "SPES CFO Offline Style",
  "source": "OpenStreetMap contributors",
  "notes": "Placeholder style metadata for offline package."
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
    package = "SPES_CFO_OFFLINE_MAP"
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    attribution = "OpenStreetMap contributors (ODbL)"
    expected_files = @("cfo_manifest.json", "cfo_style.json", "cfo_map.mbtiles")
    tiles_file_size_bytes = $tileSizeBytes
    notes = "Runtime works fully offline. Replace cfo_map.mbtiles with prepared MBTiles package."
} | ConvertTo-Json -Depth 4

$manifest | Set-Content -Path $manifestPath -Encoding UTF8

Write-Host ""
Write-Host "Prepared package folder:"
Write-Host "  $mapDir"
Write-Host ""
Write-Host "Required runtime files:"
Write-Host "  - cfo_manifest.json"
Write-Host "  - cfo_style.json"
Write-Host "  - cfo_map.mbtiles"
Write-Host ""
Write-Host "Next step:"
Write-Host "  Put real MBTiles file into: $tilesPath"
