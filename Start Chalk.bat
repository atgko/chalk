@echo off
rem Double-click to start Chalk. The first run sets everything up (a minute or two).
setlocal
cd /d "%~dp0"
title Chalk
rem A release download keeps Chalk's own files in the "app" folder, so only
rem the launchers show next to this one.
if exist "app\chalk\launcher.py" cd app
rem A release download carries its own Python, packages already installed.
rem Ignore any PYTHONPATH/PYTHONHOME or per-user packages on this computer,
rem so only the bundled packages are used.
if exist "python\python.exe" (
    set "PYTHONHOME="
    set "PYTHONPATH="
    set "PYTHONNOUSERSITE=1"
    "python\python.exe" -m chalk.launcher %*
    if errorlevel 1 pause
    exit /b
)
if not exist ".venv\Scripts\python.exe" (
    echo Setting up Chalk for the first time...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if not exist ".venv\Scripts\python.exe" goto nopython
)
".venv\Scripts\python.exe" -m chalk.launcher %*
if errorlevel 1 pause
exit /b

:nopython
echo.
echo Chalk needs Python 3.11 or newer.
echo Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH"),
echo then double-click Start Chalk again.
pause
exit /b 1
