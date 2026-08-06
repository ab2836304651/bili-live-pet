@echo off
rem ============================================
rem  Desktop Pet - one-click launcher (Windows)
rem  Double-click this file to start.
rem ============================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual env .venv not found. Please run:
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo [ERROR] Pet exited abnormally. Check the log above.
    pause
)
