from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    base_dir: Path
    models_dir: Path
    input_dir: Path
    output_dir: Path
    config_file: Path


DEFAULT_PROXY_CONFIG = {
    "enabled": False,
    "type": "http",
    "host": "",
    "port": "",
    "user": "",
    "pass": "",
}


def get_paths() -> AppPaths:
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parent.parent

    paths = AppPaths(
        base_dir=base_dir,
        models_dir=base_dir / "models",
        input_dir=base_dir / "input_files",
        output_dir=base_dir / "results",
        config_file=base_dir / "proxy_config.json",
    )
    for folder in (paths.models_dir, paths.input_dir, paths.output_dir):
        folder.mkdir(parents=True, exist_ok=True)
    return paths


def load_proxy_config(config_file: Path) -> dict:
    if not config_file.exists():
        return DEFAULT_PROXY_CONFIG.copy()

    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return DEFAULT_PROXY_CONFIG.copy()

    merged = DEFAULT_PROXY_CONFIG.copy()
    merged.update(data)
    return merged


def save_proxy_config(config_file: Path, config: dict) -> None:
    config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_proxy_env(config: dict) -> None:
    if config.get("enabled") and config.get("host") and config.get("port"):
        auth = f"{config['user']}:{config['pass']}@" if config.get("user") else ""
        proxy_url = f"{config['type']}://{auth}{config['host']}:{config['port']}"
        os.environ["HTTP_PROXY"] = proxy_url
        os.environ["HTTPS_PROXY"] = proxy_url
        os.environ["ALL_PROXY"] = proxy_url
        os.environ["http_proxy"] = proxy_url
        os.environ["https_proxy"] = proxy_url
        os.environ["all_proxy"] = proxy_url
    else:
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)
        os.environ.pop("ALL_PROXY", None)
        os.environ.pop("http_proxy", None)
        os.environ.pop("https_proxy", None)
        os.environ.pop("all_proxy", None)


def has_ffmpeg(base_dir: Path) -> bool:
    return shutil.which("ffmpeg") is not None or (base_dir / "ffmpeg.exe").exists()


def setup_runtime_paths(base_dir: Path) -> None:
    # Helps packaged EXE use bundled ffmpeg.exe without system installation.
    current = os.environ.get("PATH", "")
    base = str(base_dir)
    if base not in current.split(os.pathsep):
        os.environ["PATH"] = f"{base}{os.pathsep}{current}" if current else base
