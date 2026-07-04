@echo off
setlocal

set "CONDA_ENV=%~1"
if "%CONDA_ENV%"=="" set "CONDA_ENV=%IMMUNE_CONDA_ENV%"
if "%CONDA_ENV%"=="" set "CONDA_ENV=immune-repertoire-web"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-dev.ps1" -CondaEnv "%CONDA_ENV%"

if errorlevel 1 (
  echo.
  echo Failed to start dev stack. Check the message above.
  pause
)

endlocal
