@echo off
setlocal
cd /d "%~dp0"

echo [Azzimov Build] Starting build...

if not exist venv\Scripts\python.exe (
    echo [Azzimov Build] venv not found. Run install.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pip install pyinstaller

if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist Azzimov_Transcriber_Pro.spec del /q Azzimov_Transcriber_Pro.spec

python -m PyInstaller --noconfirm --clean --noconsole --onefile --name "Azzimov_Transcriber_Pro" --hidden-import=webbrowser main.py

if exist ffmpeg.exe copy /y ffmpeg.exe dist\ffmpeg.exe >nul
if exist models xcopy /e /i /y models dist\models >nul
if exist input_files xcopy /e /i /y input_files dist\input_files >nul
if exist results xcopy /e /i /y results dist\results >nul

echo.
echo [Azzimov Build] EXE ready: dist\Azzimov_Transcriber_Pro.exe
echo [Azzimov Build] ffmpeg/models/input_files/results copied to dist.
pause
endlocal
