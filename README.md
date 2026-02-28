# Azzimov Transcriber Pro

Local desktop app for batch video/audio transcription into text.

## Quick Start
1. Run `install.bat`.
2. Run `start.bat`.
3. Put media files into `input_files`.
4. In app:
   - choose model,
   - choose processing device at top (`Auto/GPU/CPU`),
   - click `START PROCESSING`.
5. Read results in `results`.

## UI Notes
- `Refresh Models` shows a short yellow `SEARCHING...` animation, then re-checks model folders.
- System status line shows:
  - FFmpeg state,
  - Proxy state,
  - CUDA state,
  - active processing device (`CPU/GPU`, forced or auto).

## FFmpeg (required)
If FFmpeg is missing, a red panel appears at top.

Options:
- `Auto Install` (download + extract `ffmpeg.exe` automatically)
- `Direct Download` (manual zip)
- `Refresh` (re-check without app restart)

Direct link:
- https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip

Manual layout:
1. Open zip and go to `ffmpeg-.../bin/`
2. Copy `ffmpeg.exe`
3. Place it next to app EXE (or next to `main.py` in dev mode)
4. Press `Refresh`

## Proxy
Proxy window supports:
- types: `http`, `socks5`, `socks5h`
- auth: `None` or `Basic`

Buttons:
- `Test Proxy`
- `Save & Apply`

## Models
- `Download Selected Model`: download selected model.
- `Manual Model Install`: opens guide and model page.
- `Refresh Models`: rescans local `models/` folders.

## GPU / CUDA
- NVIDIA CUDA only.
- App can force CPU/GPU or auto-select.
- If GPU init fails, app falls back to CPU.

## Build EXE (no console)
1. Run `install.bat`
2. Run `build.bat`
3. Output: `dist/Azzimov_Transcriber_Pro.exe`

## Project Structure
- `main.py`: entry point, global crash hook (`error.log`)
- `app/config.py`: paths, proxy config/env, FFmpeg check
- `app/services.py`: hardware detect, model ops, transcription
- `app/ui.py`: full GUI and workflows
