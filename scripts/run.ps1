#Requires -Version 5.1
<# Start AnimeBox in browser. Creates default .env on first run. #>
param([switch]$Dev, [switch]$SkipBuild, [switch]$NoBrowser)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "AnimeBox is not installed. Run .\scripts\install.ps1 first." }
& $python -c "import backend.main" 2>$null
if ($LASTEXITCODE -ne 0) { throw "Backend environment is broken. Run .\scripts\install.ps1 again." }

if (-not (Test-Path "$Root\.env")) {
  if (-not (Test-Path "$Root\.env.example")) { throw ".env.example not found." }
  Copy-Item "$Root\.env.example" "$Root\.env"
  Write-Host "==> Created default .env" -ForegroundColor Green
}
New-Item -ItemType Directory -Force "$Root\data", "$Root\library" | Out-Null

$port = 8787
foreach ($line in Get-Content "$Root\.env") {
  if ($line -match '^\s*PORT\s*=\s*(\d+)\s*$') { $port = [int]$Matches[1] }
}
$url = "http://127.0.0.1:$port"

function Wait-Health([string]$HealthUrl, [System.Diagnostics.Process]$Process) {
  for ($i = 0; $i -lt 60; $i++) {
    if ($Process.HasExited) { throw "AnimeBox stopped during startup (exit $($Process.ExitCode))." }
    try {
      $response = Invoke-WebRequest -UseBasicParsing "$HealthUrl/api/health" -TimeoutSec 1
      if ($response.StatusCode -eq 200) { return }
    } catch { Start-Sleep -Milliseconds 250 }
  }
  throw "AnimeBox did not become ready at $HealthUrl."
}

function Open-AnimeBox([string]$Target) {
  if (-not $NoBrowser) { Start-Process $Target }
}

if (-not $Dev) {
  if (-not $SkipBuild) {
    if (-not (Test-Path "$Root\frontend\node_modules")) { throw "Frontend dependencies missing. Run .\scripts\install.ps1 first." }
    Write-Host "==> Building frontend" -ForegroundColor Magenta
    Push-Location "$Root\frontend"
    try { & npm run build; if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." } } finally { Pop-Location }
  } elseif (-not (Test-Path "$Root\frontend\dist\index.html")) {
    throw "frontend\dist missing. Run without -SkipBuild."
  }
}

# Stop only an old Python/Uvicorn listener on AnimeBox port.
$existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $existing) {
  $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
  if ($p -and $p.ProcessName -match 'python|uvicorn') { Stop-Process -Id $procId -Force; Start-Sleep -Milliseconds 400 }
}

Write-Host "==> Starting AnimeBox" -ForegroundColor Magenta
Write-Host "UI:   $url"
Write-Host "Docs: $url/docs"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Warning "ffmpeg unavailable: new HLS downloads will fail, but offline library playback works." }

$api = Start-Process -FilePath $python -ArgumentList "-m", "backend.main" -WorkingDirectory $Root -PassThru -NoNewWindow
try {
  Wait-Health $url $api
  Write-Host "==> AnimeBox ready" -ForegroundColor Green
  if ($Dev) {
    $vite = Join-Path $Root "frontend\node_modules\.bin\vite.cmd"
    if (-not (Test-Path $vite)) { throw "Vite missing. Run .\scripts\install.ps1 first." }
    Open-AnimeBox "http://127.0.0.1:5173"
    Push-Location "$Root\frontend"
    try { & npm run dev } finally { Pop-Location }
  } else {
    Open-AnimeBox $url
    Write-Host "Press Ctrl+C to stop."
    Wait-Process -Id $api.Id
  }
} finally {
  if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue }
}
