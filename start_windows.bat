@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "CONDA_ENV=immune-repertoire-web"

cd /d "%PROJECT_DIR%"
if errorlevel 1 (
    echo Failed to switch to project directory: %PROJECT_DIR%
    pause
    exit /b 1
)

echo Project directory: %CD%
echo Activating Conda environment: %CONDA_ENV%

call conda activate "%CONDA_ENV%" >nul 2>nul
if errorlevel 1 (
    if exist "%USERPROFILE%\miniconda3\condabin\conda.bat" (
        call "%USERPROFILE%\miniconda3\condabin\conda.bat" activate "%CONDA_ENV%"
    ) else if exist "%USERPROFILE%\anaconda3\condabin\conda.bat" (
        call "%USERPROFILE%\anaconda3\condabin\conda.bat" activate "%CONDA_ENV%"
    ) else if exist "%ProgramData%\miniconda3\condabin\conda.bat" (
        call "%ProgramData%\miniconda3\condabin\conda.bat" activate "%CONDA_ENV%"
    ) else if exist "%ProgramData%\anaconda3\condabin\conda.bat" (
        call "%ProgramData%\anaconda3\condabin\conda.bat" activate "%CONDA_ENV%"
    ) else (
        echo Conda was not found. Open Anaconda Prompt or add Conda to PATH.
        pause
        exit /b 1
    )
)

if errorlevel 1 (
    echo Failed to activate Conda environment: %CONDA_ENV%
    echo Please check that the environment exists:
    echo   conda env list
    pause
    exit /b 1
)

echo Starting Flask app...
python flask_app\app.py

echo.
echo Flask app stopped.
pause
