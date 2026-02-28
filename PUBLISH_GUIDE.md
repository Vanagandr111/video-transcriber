# Publish Guide

## GitHub Upload (source code)
Upload archive:
- `Azzimov_Transcriber_Pro_GitHub_Source_2026-03-01.zip`

Contains:
- source files (`app/`, `main.py`)
- scripts (`install.bat`, `start.bat`, `build.bat`)
- docs (`README.md`)
- config files (`requirements.txt`, `.gitignore`)

Does NOT contain:
- `venv/`, `dist/`, `build/`, runtime models/results/input

## Client Delivery (ready build)
Send archive:
- `Azzimov_Transcriber_Pro_Client_Win64_2026-03-01.zip`

Contains:
- `Azzimov_Transcriber_Pro.exe`
- `ffmpeg.exe` (if available)
- `models/`, `input_files/`, `results/` as prepared by build script

## Recommended message to client
"Unpack archive and run `Azzimov_Transcriber_Pro.exe`. If FFmpeg is missing, use Auto Install in app."
