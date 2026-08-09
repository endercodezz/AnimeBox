#Requires -Version 5.1
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$failed = $false
function Check([string]$Label, [scriptblock]$Test, [string]$Fix) {
  try {
    $global:LASTEXITCODE = 0
    $value = & $Test
    if ($LASTEXITCODE -ne 0) { throw "exit $LASTEXITCODE" }
    $suffix = if ($value) { ": $value" } else { "" }
    Write-Host "[OK]   $Label$suffix" -ForegroundColor Green
  } catch {
    Write-Host "[FAIL] $Label - $Fix" -ForegroundColor Red
    $script:failed = $true
  }
}
Write-Host "AnimeBox diagnostics" -ForegroundColor Magenta
Check "Python 3.12+" { python -c "import sys; assert sys.version_info >= (3,12); print(sys.version.split()[0])" } "Install Python 3.12+."
Check "Node/npm" { "$(node --version) / npm $(npm --version)" } "Install Node.js 20+."
Check "Git" { git --version } "Install Git."
Check "anicli-api" { if (-not (Test-Path ".references\anicli-api\pyproject.toml")) { throw "missing" }; "present" } "Run scripts\install.ps1 with internet."
Check "Python environment" { .\.venv\Scripts\python.exe -c "import backend.main; print('imports OK')" } "Run scripts\install.ps1."
Check "Frontend dependencies" { if (-not (Test-Path "frontend\node_modules")) { throw "missing" }; "present" } "Run scripts\install.ps1."
Check "Frontend build" { if (-not (Test-Path "frontend\dist\index.html")) { throw "missing" }; "present" } "Run scripts\run.ps1 without -SkipBuild."
Check "Default environment" { if (-not (Test-Path ".env")) { throw "missing" }; "present" } "Run scripts\run.ps1; it creates .env automatically."
Check "Writable data/library" { New-Item -ItemType Directory -Force data,library | Out-Null; $p="data\.write-test"; Set-Content $p "ok"; Remove-Item $p; "writable" } "Grant write access to project directory."
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
  $ffmpegVersion = & ffmpeg -version 2>&1 | Select-Object -First 1
  Write-Host "[OK]   ffmpeg: $ffmpegVersion" -ForegroundColor Green
} else {
  Write-Host "[WARN] ffmpeg missing - offline playback works; new HLS downloads do not." -ForegroundColor Yellow
}
if ($failed) { exit 1 }
Write-Host "AnimeBox is ready." -ForegroundColor Green
