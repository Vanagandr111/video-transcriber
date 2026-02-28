@echo off
setlocal
cd /d "%~dp0"

echo [Azzimov] Creating virtual environment...
if not exist venv (
    py -3 -m venv venv
)

echo [Azzimov] Activating venv and installing dependencies...
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo [Azzimov] Installation complete. Use start.bat to run.
pause
endlocal
