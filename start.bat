@echo off
setlocal
cd /d "%~dp0"

if not exist venv\Scripts\python.exe (
    echo [Azzimov] venv not found. Run install.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate
python main.py
pause
endlocal
