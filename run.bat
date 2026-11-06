@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
    copy ".env.example" ".env" >nul
    if errorlevel 1 (
        echo Could not create .env from .env.example.
        exit /b 1
    )
    echo Created .env. Edit it to configure data paths, models, or port.
)

if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3.14 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 (
        echo Could not create the project virtual environment.
        echo Install Python 3.14 and try again.
        exit /b 1
    )
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed.
    exit /b 1
)

".venv\Scripts\python.exe" app.py
