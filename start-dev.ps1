param(
  [string]$CondaEnv = $env:IMMUNE_CONDA_ENV,
  [int]$BackendPort = 5000,
  [int]$FrontendPort = 5173,
  [switch]$SkipFrontendInstall,
  [switch]$NoPause
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($CondaEnv)) {
  $CondaEnv = "immune-repertoire-web"
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$FrontendDir = Join-Path $Root "frontend"
$RuntimeDir = Join-Path $Root ".dev-runtime"

function Assert-Command {
  param(
    [string]$Name,
    [string]$Hint
  )
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "$Name was not found. $Hint"
  }
}

Assert-Command "cmd.exe" "Windows cmd.exe is required."
Assert-Command "powershell.exe" "Windows PowerShell is required."
Assert-Command "conda" "Install Anaconda/Miniconda or add conda to PATH."
Assert-Command "npm" "Install Node.js or add npm to PATH."

$condaCommand = Get-Command "conda.bat" -ErrorAction SilentlyContinue
if (-not $condaCommand) {
  $condaCommand = Get-Command "conda" -ErrorAction SilentlyContinue
}
if (-not $condaCommand) {
  throw "conda was not found. Install Anaconda/Miniconda or add conda to PATH."
}
$CondaBat = $condaCommand.Source

$envList = & $CondaBat env list
if (-not ($envList -match "(^|\s)$([regex]::Escape($CondaEnv))(\s|$)")) {
  Write-Host "Available conda environments:" -ForegroundColor Yellow
  $envList | ForEach-Object { Write-Host $_ }
  throw "Conda environment '$CondaEnv' was not found. Run .\start-dev.ps1 -CondaEnv <env_name>."
}

if (-not (Test-Path $FrontendDir)) {
  throw "Frontend directory not found: $FrontendDir"
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
$backendScript = Join-Path $RuntimeDir "start-backend.cmd"
$frontendScript = Join-Path $RuntimeDir "start-frontend.cmd"
$pauseLine = if ($NoPause) { "" } else { "pause" }

@"
@echo off
chcp 65001 >nul
title Immune Repertoire Backend
cd /d "$Root"
set FLASK_CONFIG=development
set PORT=$BackendPort
echo ============================================================
echo Starting Flask backend
echo URL       : http://127.0.0.1:$BackendPort
echo Conda env : $CondaEnv
echo Conda bat : $CondaBat
echo Root      : $Root
echo ============================================================
call "$CondaBat" activate "$CondaEnv"
if errorlevel 1 (
  echo.
  echo Failed to activate conda environment: $CondaEnv
  $pauseLine
  exit /b 1
)
python flask_app/app.py
echo.
echo Backend process exited with code %errorlevel%.
$pauseLine
"@ | Set-Content -Path $backendScript -Encoding UTF8

$frontendInstallCommand = ""
if (-not $SkipFrontendInstall) {
  $frontendInstallCommand = 'if not exist node_modules ( echo Installing frontend dependencies... && npm install ) && '
}

@"
@echo off
chcp 65001 >nul
title Immune Repertoire Frontend
cd /d "$FrontendDir"
set VITE_DEV_PORT=$FrontendPort
set VITE_API_TARGET=http://127.0.0.1:$BackendPort
echo ============================================================
echo Starting Vite frontend
echo URL        : http://127.0.0.1:$FrontendPort
echo API target : http://127.0.0.1:$BackendPort
echo Frontend   : $FrontendDir
echo ============================================================
$frontendInstallCommand npm run dev
echo.
echo Frontend process exited with code %errorlevel%.
$pauseLine
"@ | Set-Content -Path $frontendScript -Encoding UTF8

Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "`"$backendScript`"" -WorkingDirectory $Root
Start-Sleep -Seconds 2
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "`"$frontendScript`"" -WorkingDirectory $FrontendDir

Write-Host ""
Write-Host "Immune repertoire dev stack is starting." -ForegroundColor Green
Write-Host "Backend : http://127.0.0.1:$BackendPort"
Write-Host "Frontend: http://127.0.0.1:$FrontendPort"
Write-Host "Conda env: $CondaEnv"
Write-Host "Backend script : $backendScript"
Write-Host "Frontend script: $frontendScript"
Write-Host ""
Write-Host "Tip: set IMMUNE_CONDA_ENV or run .\start-dev.ps1 -CondaEnv your_env_name"
