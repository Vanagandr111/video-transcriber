from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Iterable

import ctranslate2
from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download

VIDEO_AUDIO_EXTENSIONS = (".mp4", ".mp3", ".wav", ".mkv", ".m4a", ".aac", ".flac", ".ogg")

MODELS_INFO = {
    "Tiny": {"id": "tiny", "id_hf": "Systran/faster-whisper-tiny", "desc": "Fastest | Low Acc"},
    "Base": {"id": "base", "id_hf": "Systran/faster-whisper-base", "desc": "Very Fast | Med Acc"},
    "Small": {"id": "small", "id_hf": "Systran/faster-whisper-small", "desc": "Fast | High Acc"},
    "Medium": {"id": "medium", "id_hf": "Systran/faster-whisper-medium", "desc": "Slow | Best Acc"},
}

MODEL_SIZE_MB_EST = {
    "tiny": 80.0,
    "base": 160.0,
    "small": 520.0,
    "medium": 1700.0,
}


def detect_hardware() -> tuple[str, str, str]:
    try:
        gpu_count = ctranslate2.get_cuda_device_count()
        if gpu_count > 0:
            return "cuda", "float16", f"GPU (CUDA x{gpu_count})"
    except Exception:
        pass

    try:
        import torch

        if torch.cuda.is_available():
            return "cuda", "float16", f"GPU ({torch.cuda.get_device_name(0)})"
    except Exception:
        pass
    return "cpu", "int8", "CPU"


def model_path(models_dir: Path, model_name: str) -> Path:
    return models_dir / MODELS_INFO[model_name]["id"]


def is_model_ready(models_dir: Path, model_name: str) -> bool:
    path = model_path(models_dir, model_name)
    return (path / "config.json").exists() and (path / "vocabulary.txt").exists() and (path / "model.bin").exists()


def download_model(models_dir: Path, model_name: str, proxy_url: str | None = None, progress_cb=None) -> bool:
    info = MODELS_INFO[model_name]
    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}

    target_dir = models_dir / info["id"]
    target_dir.mkdir(parents=True, exist_ok=True)

    stop_event = threading.Event()

    def folder_size_bytes(folder: Path) -> int:
        total = 0
        for p in folder.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
        return total

    def monitor():
        last_t = time.time()
        last_b = folder_size_bytes(target_dir)
        while not stop_event.is_set():
            time.sleep(0.5)
            now_t = time.time()
            now_b = folder_size_bytes(target_dir)
            dt = max(now_t - last_t, 1e-6)
            speed = max(now_b - last_b, 0) / dt
            downloaded_mb = now_b / (1024 * 1024)
            speed_mb_s = speed / (1024 * 1024)
            est_total = MODEL_SIZE_MB_EST.get(info["id"], 0.0)
            estimated_progress = min(downloaded_mb / est_total, 0.98) if est_total > 0 else 0.0
            if progress_cb:
                progress_cb(downloaded_mb, speed_mb_s, estimated_progress)
            last_t = now_t
            last_b = now_b

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    snapshot_download(
        repo_id=info["id_hf"],
        local_dir=str(target_dir),
        etag_timeout=15,
        proxies=proxies,
    )
    stop_event.set()
    monitor_thread.join(timeout=1.0)
    return is_model_ready(models_dir, model_name)


def list_input_files(input_dir: Path) -> list[Path]:
    files = []
    for entry in input_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() in VIDEO_AUDIO_EXTENSIONS:
            files.append(entry)
    return sorted(files)


def transcribe_batch(
    model_dir: Path,
    input_files: Iterable[Path],
    output_dir: Path,
    device: str,
    compute_type: str,
    progress_cb,
) -> None:
    model = WhisperModel(str(model_dir), device=device, compute_type=compute_type, local_files_only=True)
    files = list(input_files)

    for file_index, media_path in enumerate(files, start=1):
        progress_cb("file_start", media_path.name, file_index, len(files), 0.0)
        segments, info = model.transcribe(str(media_path), vad_filter=True)
        duration = max(float(getattr(info, "duration", 0.0)) or 0.0, 1e-6)

        out_file = output_dir / f"{media_path.name}.txt"
        with out_file.open("w", encoding="utf-8") as handle:
            for segment in segments:
                handle.write(f"[{int(segment.start)}s] {segment.text.strip()}\n")
                file_progress = min(float(segment.end) / duration, 1.0)
                overall = ((file_index - 1) + file_progress) / len(files)
                progress_cb("segment", media_path.name, file_index, len(files), overall)

        progress_cb("file_done", media_path.name, file_index, len(files), file_index / len(files))


def probe_model_runtime(model_dir: Path, device: str, compute_type: str) -> tuple[bool, str]:
    try:
        model = WhisperModel(str(model_dir), device=device, compute_type=compute_type, local_files_only=True)
        del model
        return True, ""
    except Exception as exc:
        return False, str(exc)
