#Requires -Version 5.1
<# Install AnimeBox dependencies and build browser UI. Safe to run repeatedly. #>
param([switch]$SkipBuild)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Require-Command([string]$Name, [string]$Hint) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "$Name not found. $Hint"
  }
}

function New-DefaultEnv {
  if (-not (Test-Path "$Root\.env.example")) { throw ".env.example not found in $Root" }
  if (-not (Test-Path "$Root\.env")) {
    Copy-Item "$Root\.env.example" "$Root\.env"
    Write-Host "==> Created default .env" -ForegroundColor Green
  } else {
    Write-Host "==> Keeping existing .env"
  }
}

Write-Host "==> AnimeBox setup" -ForegroundColor Magenta
Write-Host "Root: $Root"
Require-Command python "Install Python 3.12+ from https://python.org and enable Add Python to PATH."
Require-Command npm "Install Node.js 20+ from https://nodejs.org."
Require-Command git "Install Git from https://git-scm.com."

$pyOk = & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) { throw "Python 3.12+ required. Found: $(& python --version 2>&1)" }
Write-Host "Python: $(& python --version 2>&1)"
Write-Host "Node:   $(& node --version 2>&1)"

$Anicli = Join-Path $Root ".references\anicli-api"
if (-not (Test-Path "$Anicli\pyproject.toml")) {
  Write-Host "==> Cloning anicli-api (MIT)"
  New-Item -ItemType Directory -Force (Split-Path $Anicli) | Out-Null
  & git clone --depth 1 https://github.com/vypivshiy/anicli-api $Anicli
  if ($LASTEXITCODE -ne 0) { throw "Failed to clone anicli-api. Check internet access and retry." }
} else {
  Write-Host "==> anicli-api checkout: OK"
}

$python = Join-Path $Root ".venv\Scripts\python.exe"
$venvValid = (Test-Path $python)
if ($venvValid) {
  & $python -c "import sys" 2>$null
  $venvValid = $LASTEXITCODE -eq 0
}
if (-not $venvValid) {
  if (Test-Path "$Root\.venv") {
    Write-Warning "Existing .venv is broken or was moved; recreating it."
    Remove-Item "$Root\.venv" -Recurse -Force
  }
  Write-Host "==> Creating Python environment"
  & python -m venv "$Root\.venv"
  if ($LASTEXITCODE -ne 0) { throw "Could not create .venv." }
}

Write-Host "==> Installing backend"
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $python -m pip install -r "$Root\backend\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }

New-DefaultEnv
New-Item -ItemType Directory -Force "$Root\data", "$Root\library" | Out-Null

Write-Host "==> Installing frontend"
Push-Location "$Root\frontend"
try {
  if (Test-Path "package-lock.json") { & npm ci } else { & npm install }
  if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
  if (-not $SkipBuild) {
    Write-Host "==> Building frontend"
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
  }
} finally { Pop-Location }

if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
  Write-Host "ffmpeg: OK" -ForegroundColor Green
} else {
  Write-Warning "ffmpeg not found. Install it and add it to PATH; online HLS downloads need it. Already downloaded library files can still play."
}

Write-Host ""
Write-Host "AnimeBox is ready." -ForegroundColor Green
Write-Host "Start: .\scripts\run.ps1"
Write-Host "Check: .\scripts\check.ps1"
