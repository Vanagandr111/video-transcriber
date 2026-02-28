from __future__ import annotations

import os
import threading
import tempfile
import webbrowser
import zipfile
from pathlib import Path
import traceback
from datetime import datetime

import customtkinter as ctk
import tkinter.messagebox as msgbox
import httpx

from app.config import apply_proxy_env, has_ffmpeg, load_proxy_config, save_proxy_config
from app.services import (
    MODELS_INFO,
    detect_hardware,
    download_model,
    is_model_ready,
    list_input_files,
    model_path,
    probe_model_runtime,
    transcribe_batch,
)

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
FFMPEG_DIRECT_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


class ProxyWindow(ctk.CTkToplevel):
    def __init__(self, master, current_config: dict, save_callback, test_callback):
        super().__init__(master)
        self.title("Proxy Settings")
        self.geometry("560x760")
        self.minsize(520, 700)
        self.resizable(True, True)
        self.attributes("-topmost", True)
        self.save_callback = save_callback
        self.test_callback = test_callback
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="🌐 Proxy Configuration", font=("Segoe UI", 19, "bold")).grid(
            row=0, column=0, padx=20, pady=(18, 12), sticky="ew"
        )

        self.enabled = ctk.CTkSwitch(self, text="Enable Proxy")
        if current_config.get("enabled"):
            self.enabled.select()
        self.enabled.grid(row=1, column=0, padx=30, pady=8, sticky="w")

        self.p_type = ctk.CTkSegmentedButton(self, values=["http", "socks5", "socks5h"])
        self.p_type.set(current_config.get("type", "http"))
        self.p_type.grid(row=2, column=0, padx=30, pady=8, sticky="ew")

        ctk.CTkLabel(self, text="Host", font=("Segoe UI", 12, "bold")).grid(
            row=3, column=0, padx=30, pady=(8, 2), sticky="w"
        )
        self.host = ctk.CTkEntry(self, placeholder_text="e.g. 127.0.0.1")
        self.host.insert(0, current_config.get("host", ""))
        self.host.grid(row=4, column=0, padx=30, pady=6, sticky="ew")

        ctk.CTkLabel(self, text="Port", font=("Segoe UI", 12, "bold")).grid(
            row=5, column=0, padx=30, pady=(8, 2), sticky="w"
        )
        self.port = ctk.CTkEntry(self, placeholder_text="e.g. 8080")
        self.port.insert(0, current_config.get("port", ""))
        self.port.grid(row=6, column=0, padx=30, pady=6, sticky="ew")

        ctk.CTkLabel(self, text="Authentication", font=("Segoe UI", 12)).grid(
            row=7, column=0, padx=30, pady=(10, 2), sticky="w"
        )
        self.auth_mode = ctk.CTkSegmentedButton(self, values=["None", "Basic"])
        self.auth_mode.set("Basic" if current_config.get("user") else "None")
        self.auth_mode.grid(row=8, column=0, padx=30, pady=4, sticky="ew")
        self.auth_mode.configure(command=lambda _: self._apply_auth_mode())

        ctk.CTkLabel(self, text="Username", font=("Segoe UI", 12, "bold")).grid(
            row=9, column=0, padx=30, pady=(8, 2), sticky="w"
        )
        self.user = ctk.CTkEntry(self, placeholder_text="optional")
        self.user.insert(0, current_config.get("user", ""))
        self.user.grid(row=10, column=0, padx=30, pady=6, sticky="ew")

        ctk.CTkLabel(self, text="Password", font=("Segoe UI", 12, "bold")).grid(
            row=11, column=0, padx=30, pady=(8, 2), sticky="w"
        )
        self.password = ctk.CTkEntry(self, placeholder_text="optional", show="*")
        self.password.insert(0, current_config.get("pass", ""))
        self.password.grid(row=12, column=0, padx=30, pady=6, sticky="ew")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=13, column=0, padx=30, pady=20, sticky="ew")
        actions.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(actions, text="Test Proxy", command=self.test_proxy, height=38).grid(
            row=0, column=0, padx=(0, 5), sticky="ew"
        )
        ctk.CTkButton(actions, text="Save & Apply ✅", command=self.save, height=38).grid(
            row=0, column=1, padx=(5, 0), sticky="ew"
        )

        # Force immediate placeholder painting and focus order.
        self.after(20, self.host.focus_set)
        self.after(40, self.update_idletasks)
        self._apply_auth_mode()

    def _apply_auth_mode(self):
        is_basic = self.auth_mode.get() == "Basic"
        state = "normal" if is_basic else "disabled"
        self.user.configure(state=state)
        self.password.configure(state=state)
        if not is_basic:
            self.user.delete(0, "end")
            self.password.delete(0, "end")

    def save(self):
        config = self.collect_config()
        self.save_callback(config)
        self.destroy()

    def collect_config(self) -> dict:
        return {
            "enabled": bool(self.enabled.get()),
            "type": self.p_type.get(),
            "host": self.host.get().strip(),
            "port": self.port.get().strip(),
            "user": self.user.get().strip(),
            "pass": self.password.get(),
        }

    def test_proxy(self):
        config = self.collect_config()
        ok, detail = self.test_callback(config)
        if ok:
            msgbox.showinfo("Proxy test", f"Proxy OK ✅\n\n{detail}")
        else:
            msgbox.showerror("Proxy test", f"Proxy failed ❌\n\n{detail}")

    def on_close(self):
        # Save current values even if user closes with window "X".
        self.save()


class ModelCard(ctk.CTkFrame):
    def __init__(self, master, title: str, desc: str, command, **kwargs):
        super().__init__(
            master,
            fg_color="#1A1A1A",
            border_width=2,
            border_color="#333333",
            cursor="hand2",
            corner_radius=12,
            **kwargs,
        )
        self.command = command
        self.bind("<Button-1>", lambda _: self.command())

        self.title_label = ctk.CTkLabel(self, text=title, font=("Segoe UI", 15, "bold"))
        self.title_label.pack(pady=(8, 0), padx=8)

        self.desc_label = ctk.CTkLabel(self, text=desc, font=("Segoe UI", 10, "italic"), text_color="gray")
        self.desc_label.pack(pady=(0, 4), padx=8)

        self.status_label = ctk.CTkLabel(self, text="CHECKING...", font=("Segoe UI", 11, "bold"))
        self.status_label.pack(pady=(0, 10), padx=8)

        for child in self.winfo_children():
            child.bind("<Button-1>", lambda _: self.command())

    def set_status(self, is_ready: bool):
        if is_ready:
            self.status_label.configure(text="READY ✅", text_color="#4CAF50")
        else:
            self.status_label.configure(text="MISSING ❌", text_color="#F44336")

    def set_searching(self, tick: int):
        dots = "." * (tick % 4)
        self.status_label.configure(text=f"SEARCHING{dots}", text_color="#FFC107")

    def set_selected(self, is_selected: bool):
        self.configure(
            border_color="#3B8ED0" if is_selected else "#333333",
            fg_color="#2B2B2B" if is_selected else "#1A1A1A",
        )


class TranscriberApp(ctk.CTk):
    def __init__(self, paths):
        super().__init__()
        self.paths = paths

        self.title("Azzimov Transcriber Pro")
        self.geometry("980x760")
        self.minsize(860, 680)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self.proxy_config = load_proxy_config(paths.config_file)
        apply_proxy_env(self.proxy_config)

        self.ai_device, self.ai_compute, self.hw_name = detect_hardware()
        self.runtime_note = "AUTO"
        self.device_pref = "GPU" if self.ai_device == "cuda" else "CPU"
        self.cur_model = "Base"
        self._pulse_direction = 1
        self._refresh_anim_token = 0
        self._model_download_in_progress = False

        self._build_ui()
        self.refresh_ui()
        self._animate_status_pulse()

    def _proxy_url_from_config(self, config: dict | None = None) -> str | None:
        cfg = config or self.proxy_config
        if not (cfg.get("enabled") and cfg.get("host") and cfg.get("port")):
            return None
        auth = f"{cfg['user']}:{cfg['pass']}@" if cfg.get("user") else ""
        return f"{cfg.get('type', 'http')}://{auth}{cfg['host']}:{cfg['port']}"

    def report_callback_exception(self, exc, val, tb):
        error_text = "".join(traceback.format_exception(exc, val, tb))
        log_file = self.paths.base_dir / "error.log"
        try:
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(error_text + "\n")
        except OSError:
            pass
        msgbox.showerror("Unexpected error", f"Something went wrong.\nDetails saved to:\n{log_file}")

    def _append_error_log(self, context: str, exc: Exception) -> Path:
        log_file = self.paths.base_dir / "error.log"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        block = f"\n[{ts}] {context}\n{details}\n"
        try:
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(block)
        except OSError:
            pass
        return log_file

    def _fix_hint_for_error(self, exc: Exception) -> str:
        text = str(exc).lower()
        if "ffmpeg" in text:
            return "Fix: install FFmpeg and press Refresh."
        if "cuda" in text or "cublas" in text or "cudnn" in text:
            return "Fix: switch to CPU mode or update NVIDIA driver/CUDA runtime."
        if "out of memory" in text or "std::bad_alloc" in text:
            return "Fix: use smaller model (Tiny/Base) or switch to CPU."
        if "vocabulary" in text or "config.json" in text or "model.bin" in text:
            return "Fix: model folder is incomplete. Re-download model or use Manual Model Install."
        if "permission denied" in text or "access is denied" in text:
            return "Fix: close apps using files and run app with write access."
        if "proxy" in text or "socks" in text or "connection" in text:
            return "Fix: open Proxy settings and run Test Proxy, or disable proxy and retry."
        return "Fix: check error.log and retry with CPU + Base model."

    def _show_process_error(self, context: str, exc: Exception):
        log_file = self._append_error_log(context, exc)
        hint = self._fix_hint_for_error(exc)
        msgbox.showerror(
            "Processing error",
            f"{context}\n\nError: {exc}\n\n{hint}\n\nFull details saved to:\n{log_file}",
        )

    def _build_ui(self):
        self.ffmpeg_frame = ctk.CTkFrame(self, corner_radius=10)
        self.ffmpeg_frame.grid(row=0, column=0, padx=20, pady=(10, 6), sticky="ew")
        self.ffmpeg_frame.grid_columnconfigure(0, weight=1)
        self.ffmpeg_frame.grid_columnconfigure(1, weight=0)
        self.ffmpeg_frame.grid_columnconfigure(2, weight=0)
        self.ffmpeg_frame.grid_columnconfigure(3, weight=0)

        self.ffmpeg_label = ctk.CTkLabel(
            self.ffmpeg_frame,
            text="FFmpeg status: checking...",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        )
        self.ffmpeg_label.grid(row=0, column=0, padx=12, pady=10, sticky="ew")

        self.ffmpeg_download_btn = ctk.CTkButton(
            self.ffmpeg_frame, text="Direct Download", width=150, command=self.open_ffmpeg_download
        )
        self.ffmpeg_download_btn.grid(row=0, column=1, padx=(6, 4), pady=8, sticky="e")

        self.ffmpeg_install_btn = ctk.CTkButton(
            self.ffmpeg_frame, text="Auto Install", width=130, command=self.start_ffmpeg_install
        )
        self.ffmpeg_install_btn.grid(row=0, column=2, padx=(4, 4), pady=8, sticky="e")

        self.ffmpeg_refresh_btn = ctk.CTkButton(
            self.ffmpeg_frame, text="Refresh", width=130, command=self.refresh_ui
        )
        self.ffmpeg_refresh_btn.grid(row=0, column=3, padx=(4, 10), pady=8, sticky="e")

        self.ffmpeg_hint_label = ctk.CTkLabel(
            self.ffmpeg_frame,
            text="",
            justify="left",
            anchor="w",
            font=("Segoe UI", 11),
            text_color="#FFB3B3",
        )
        self.ffmpeg_hint_label.grid(row=1, column=0, columnspan=4, padx=12, pady=(0, 10), sticky="ew")

        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.grid(row=1, column=0, padx=20, pady=(8, 8), sticky="ew")
        self.header.grid_columnconfigure(0, weight=1)
        self.header.grid_columnconfigure(1, weight=0)

        self.title_label = ctk.CTkLabel(self.header, text="🎬 AI Universal Transcriber", font=("Segoe UI", 30, "bold"))
        self.title_label.grid(row=0, column=0, sticky="w")

        self.device_top = ctk.CTkFrame(self.header, fg_color="transparent")
        self.device_top.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(self.device_top, text="Processing Device:", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, padx=(0, 8)
        )
        self.device_menu = ctk.CTkOptionMenu(
            self.device_top,
            values=["Auto", "GPU", "CPU"],
            command=self.on_device_change,
            width=120,
            height=32,
        )
        self.device_menu.grid(row=0, column=1, sticky="e")
        self.device_menu.set(self.device_pref)

        self.about_f = ctk.CTkFrame(self, fg_color=("#E5E5E5", "#2B2B2B"), corner_radius=12)
        self.about_f.grid(row=2, column=0, padx=20, pady=8, sticky="ew")
        self.about_f.grid_columnconfigure(0, weight=1)

        about_t = (
            "Converts audio/video files into text locally.\n"
            "Language is detected automatically, no API keys needed.\n\n"
            "Engine: OpenAI Whisper (Local)"
        )
        self.about_label = ctk.CTkLabel(self.about_f, text=about_t, justify="left", font=("Segoe UI", 13), anchor="w")
        self.about_label.grid(row=0, column=0, padx=15, pady=(12, 4), sticky="ew")

        self.author_link = ctk.CTkLabel(
            self.about_f,
            text="Created by Azzimov",
            font=("Segoe UI", 12, "italic", "underline"),
            text_color="#3B8ED0",
            cursor="hand2",
        )
        self.author_link.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="e")
        self.author_link.bind("<Button-1>", lambda _: webbrowser.open_new("https://vk.com/vanagandr_fenrir"))

        self.center = ctk.CTkFrame(self, fg_color="transparent")
        self.center.grid(row=3, column=0, padx=20, pady=8, sticky="ew")
        self.center.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.center, text="Select AI Model Quality", font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        self.cards_frame = ctk.CTkFrame(self.center, fg_color="transparent")
        self.cards_frame.grid(row=1, column=0, sticky="ew")
        self.cards = {}
        for i, (name, data) in enumerate(MODELS_INFO.items()):
            self.cards_frame.grid_columnconfigure(i, weight=1)
            card = ModelCard(self.cards_frame, title=name, desc=data["desc"], command=lambda key=name: self.select_model(key))
            card.grid(row=0, column=i, padx=4, sticky="ew")
            self.cards[name] = card

        self.actions = ctk.CTkFrame(self.center, fg_color="transparent")
        self.actions.grid(row=2, column=0, pady=12, sticky="ew")
        self.actions.grid_columnconfigure((0, 1, 2), weight=1)

        self.dl_btn = ctk.CTkButton(self.actions, text="Download Selected Model", height=38, command=self.start_download)
        self.dl_btn.grid(row=0, column=0, padx=4, sticky="ew")

        self.proxy_btn = ctk.CTkButton(self.actions, text="⚙️ Proxy", height=38, fg_color="#444", command=self.open_proxy_menu)
        self.proxy_btn.grid(row=0, column=1, padx=4, sticky="ew")

        self.refresh_models_btn = ctk.CTkButton(
            self.actions,
            text="Refresh Models",
            height=38,
            fg_color="#2f5f8f",
            command=self.refresh_models_with_animation,
        )
        self.refresh_models_btn.grid(row=0, column=2, padx=4, sticky="ew")

        self.manual_model_btn = ctk.CTkButton(
            self.actions,
            text="Manual Model Install",
            height=38,
            fg_color="#444",
            command=self.open_manual_model_help,
        )
        self.manual_model_btn.grid(row=1, column=0, columnspan=3, padx=4, pady=(6, 0), sticky="ew")

        self.instructions = ctk.CTkScrollableFrame(self, corner_radius=10, fg_color=("#D1D1D1", "#1A1A1A"))
        self.instructions.grid(row=4, column=0, padx=20, pady=8, sticky="nsew")
        self.instructions.grid_columnconfigure(0, weight=1)

        self.instructions_label = ctk.CTkLabel(self.instructions, justify="left", anchor="nw", font=("Segoe UI", 13))
        self.instructions_label.grid(row=0, column=0, padx=15, pady=12, sticky="nsew")

        self.status_area = ctk.CTkFrame(self, fg_color="transparent")
        self.status_area.grid(row=5, column=0, padx=20, pady=(2, 14), sticky="ew")
        self.status_area.grid_columnconfigure(0, weight=1)

        self.system_status_label = ctk.CTkLabel(self.status_area, text="", font=("Segoe UI", 12, "bold"), anchor="w")
        self.system_status_label.grid(row=0, column=0, sticky="ew")

        self.status_label = ctk.CTkLabel(
            self.status_area,
            text="Status: Ready",
            font=("Segoe UI", 14, "bold"),
            text_color="#6DD5FA",
            justify="left",
            anchor="w",
        )
        self.status_label.grid(row=1, column=0, sticky="ew", pady=(2, 4))

        self.progress = ctk.CTkProgressBar(self.status_area, height=14)
        self.progress.set(0)
        self.progress.grid(row=2, column=0, sticky="ew")

        self.start_btn = ctk.CTkButton(
            self.status_area,
            text="🚀 START PROCESSING",
            font=("Segoe UI", 17, "bold"),
            height=42,
            command=self.start_processing_thread,
        )
        self.start_btn.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        self.bind("<Configure>", self.on_resize)

    def on_resize(self, _event=None):
        wrap = max(self.winfo_width() - 100, 300)
        self.about_label.configure(wraplength=wrap)
        self.instructions_label.configure(wraplength=wrap)
        self.instructions_label.configure(text=self._instructions_text())

    def _instructions_text(self) -> str:
        return (
            f"1. Put files in: /{self.paths.input_dir.name}\n"
            "2. Pick a model (Green=Ready, Red=Missing).\n"
            "3. Choose processing device at top (Auto/GPU/CPU).\n"
            "4. Press START PROCESSING.\n"
            f"5. Results appear in: /{self.paths.output_dir.name}\n\n"
            "Supported: mp4, mp3, wav, mkv, m4a, aac, flac, ogg\n\n"
            "If model download is slow/stuck:\n"
            "- check Proxy settings with Test Proxy,\n"
            "- disable proxy and retry,\n"
            "- use Manual Model Install."
        )

    def _check_model_source(self, model_name: str) -> tuple[bool, str]:
        model_repo = MODELS_INFO[model_name]["id_hf"]
        url = f"https://huggingface.co/{model_repo}/resolve/main/config.json"
        proxy_url = self._proxy_url_from_config()
        try:
            with httpx.Client(
                proxy=proxy_url,
                timeout=httpx.Timeout(12.0, connect=8.0, read=12.0, write=12.0, pool=8.0),
                follow_redirects=True,
            ) as client:
                r = client.get(url, headers={"User-Agent": "Azzimov-Model-Check/1.0"})
            if r.status_code >= 400:
                return False, f"Source returned HTTP {r.status_code}"
            return True, "Model source reachable"
        except Exception as exc:
            return False, str(exc)

    def _set_download_progress(self, progress: float):
        current = float(self.progress.get())
        # Keep progress monotonic while downloading (no resets/jumps back).
        next_value = max(current, min(max(progress, 0.0), 0.99))
        self.progress.set(next_value)

    def refresh_models_with_animation(self):
        self._refresh_anim_token += 1
        token = self._refresh_anim_token
        self.refresh_models_btn.configure(state="disabled", text="Refreshing...")
        steps = 8
        interval_ms = 250

        def tick(step: int):
            if token != self._refresh_anim_token:
                return
            if step < steps:
                for name in MODELS_INFO:
                    self.cards[name].set_searching(step)
                self.after(interval_ms, lambda: tick(step + 1))
            else:
                self.refresh_models_btn.configure(state="normal", text="Refresh Models")
                self.refresh_ui()

        tick(0)

    def open_proxy_menu(self):
        # Reload from disk each time to always show persisted settings.
        self.proxy_config = load_proxy_config(self.paths.config_file)
        win = ProxyWindow(self, self.proxy_config, self.save_proxy, self.test_proxy_config)
        win.grab_set()

    def on_device_change(self, value: str):
        self.device_pref = value
        if value == "CPU":
            self.runtime_note = "CPU forced"
        elif value == "GPU":
            self.runtime_note = "GPU forced"
        else:
            self.runtime_note = "Auto"
        self.refresh_ui()

    def open_ffmpeg_download(self):
        webbrowser.open_new(FFMPEG_DIRECT_URL)

    def open_manual_model_help(self):
        selected = self.cur_model
        model_id = MODELS_INFO[selected]["id"]
        hf_repo = MODELS_INFO[selected]["id_hf"]
        target_path = self.paths.models_dir / model_id
        msgbox.showinfo(
            "Manual model install",
            f"Model: {selected}\n"
            f"Download from:\nhttps://huggingface.co/{hf_repo}\n\n"
            "How to install:\n"
            "1) Download repository files (or clone).\n"
            f"2) Put files into folder:\n{target_path}\n"
            "3) Required files must exist:\n"
            "- config.json\n"
            "- vocabulary.txt\n"
            "4) Click 'Refresh Models' in app.",
        )
        webbrowser.open_new(f"https://huggingface.co/{hf_repo}")

    def start_ffmpeg_install(self):
        threading.Thread(target=self._ffmpeg_install_worker, daemon=True).start()

    def _ffmpeg_install_worker(self):
        self.after(0, lambda: self.ffmpeg_install_btn.configure(state="disabled", text="Installing..."))
        self._set_status("Status: Downloading FFmpeg archive...", "#FFC107")

        zip_path = Path(tempfile.gettempdir()) / "ffmpeg-release-essentials.zip"
        try:
            proxy_url = self._proxy_url_from_config()
            with httpx.Client(
                proxy=proxy_url,
                timeout=httpx.Timeout(30.0, connect=10.0, read=30.0, write=30.0, pool=10.0),
                follow_redirects=True,
            ) as client:
                response = client.get(FFMPEG_DIRECT_URL, headers={"User-Agent": "Azzimov-FFmpeg-Installer/1.0"})
                response.raise_for_status()
                raw = response.content
            zip_path.write_bytes(raw)

            if len(raw) < 4 or not raw.startswith(b"PK"):
                preview = raw[:120].decode("utf-8", errors="ignore").strip()
                raise RuntimeError(
                    "Downloaded content is not a ZIP archive. "
                    f"Received: {preview or 'binary/unknown'}. "
                    "Check proxy type/host/port."
                )

            extracted = False
            with zipfile.ZipFile(zip_path, "r") as archive:
                for member in archive.namelist():
                    normalized = member.replace("\\", "/").lower()
                    if normalized.endswith("/bin/ffmpeg.exe"):
                        target = self.paths.base_dir / "ffmpeg.exe"
                        with archive.open(member) as src, target.open("wb") as dst:
                            dst.write(src.read())
                        extracted = True
                        break

            if not extracted:
                raise RuntimeError("ffmpeg.exe not found in archive")

            self._set_status("Status: FFmpeg installed successfully ✅", "#4CAF50")
            msgbox.showinfo("FFmpeg", f"Installed to:\n{self.paths.base_dir / 'ffmpeg.exe'}")
        except Exception as exc:
            self._set_status("Status: FFmpeg auto install failed", "#F44336")
            msgbox.showerror("FFmpeg", f"Auto install failed.\n\n{exc}")
        finally:
            if zip_path.exists():
                try:
                    zip_path.unlink()
                except OSError:
                    pass
            self.after(0, lambda: self.ffmpeg_install_btn.configure(state="normal", text="Auto Install"))
            self.after(0, self.refresh_ui)

    def test_proxy_config(self, config: dict) -> tuple[bool, str]:
        if not config.get("enabled"):
            return True, "Proxy disabled."
        if not config.get("host") or not config.get("port"):
            return False, "Host/port is empty."

        auth = ""
        if config.get("user"):
            auth = f"{config['user']}:{config.get('pass', '')}@"
        proxy_url = f"{config.get('type', 'http')}://{auth}{config['host']}:{config['port']}"

        try:
            with httpx.Client(
                proxy=proxy_url,
                timeout=httpx.Timeout(5.0, connect=4.0, read=5.0, write=5.0, pool=5.0),
                follow_redirects=True,
            ) as client:
                r = client.get("https://hf-mirror.com", headers={"User-Agent": "Azzimov-Proxy-Test/1.0"})
            if r.status_code >= 400:
                return False, f"Proxy reachable, but target returned HTTP {r.status_code}."
            return True, f"Connected via {config.get('type')} proxy to hf-mirror.com (HTTP {r.status_code})."
        except Exception as exc:
            text = str(exc)
            low = text.lower()
            if "socksio" in low:
                return False, "SOCKS proxy selected, but `socksio` is not installed. Reinstall dependencies."
            if "ssh-2.0-openssh" in low or "debian" in low:
                return False, "Proxy port looks like SSH service, not SOCKS/HTTP proxy."
            return False, text

    def save_proxy(self, config: dict):
        self.proxy_config = config
        save_proxy_config(self.paths.config_file, config)
        apply_proxy_env(config)
        self.refresh_ui()

    def _set_status(self, text: str, color: str = "#6DD5FA"):
        def _apply():
            wrap = max(self.winfo_width() - 70, 300)
            self.status_label.configure(text=text, text_color=color, wraplength=wrap)

        self.after(0, _apply)

    def _set_progress(self, value: float):
        clamped = min(max(value, 0.0), 1.0)
        self.after(0, lambda: self.progress.set(clamped))

    def _animate_status_pulse(self):
        color_a = "#6DD5FA"
        color_b = "#3A8FB7"
        current = self.status_label.cget("text_color")
        if isinstance(current, tuple):
            current = current[1]
        if current in (color_a, color_b):
            self.status_label.configure(text_color=color_b if current == color_a else color_a)
        self.after(700, self._animate_status_pulse)

    def refresh_ui(self):
        ffmpeg_ok = has_ffmpeg(self.paths.base_dir)
        proxy_on = bool(self.proxy_config.get("enabled") and self.proxy_config.get("host") and self.proxy_config.get("port"))
        cuda_status = "OFF"
        if self.ai_device == "cuda":
            if "CUDA x" in self.hw_name:
                cuda_status = f"ON ✅ ({self.hw_name.split('CUDA ', 1)[-1]})"
            else:
                cuda_status = f"ON ✅ ({self.hw_name})"

        if self.device_pref == "CPU":
            effective_device = "CPU (forced)"
        elif self.device_pref == "GPU":
            effective_device = "GPU (forced)"
        else:
            effective_device = "GPU (auto)" if self.ai_device == "cuda" else "CPU (auto)"

        if self.device_pref == "CPU":
            runtime_display = "CPU forced"
        elif self.device_pref == "GPU":
            runtime_display = "GPU forced"
        else:
            runtime_display = self.runtime_note

        system = (
            f"Compute: {self.ai_compute.upper()} | "
            f"FFmpeg: {'FOUND ✅' if ffmpeg_ok else 'MISSING ❌'} | "
            f"Proxy: {'ON ✅' if proxy_on else 'OFF'} | "
            f"Runtime: {runtime_display} | "
            f"CUDA: {cuda_status} | "
            f"Active: {effective_device}"
        )
        self.system_status_label.configure(text=system)

        if ffmpeg_ok:
            self.ffmpeg_frame.grid_remove()
        else:
            self.ffmpeg_frame.grid()
            self.ffmpeg_frame.configure(fg_color=("#FFE7E7", "#3B1F1F"))
            self.ffmpeg_label.configure(text="FFmpeg status: MISSING ❌ (required to run)", text_color="#FF6B6B")
            self.ffmpeg_download_btn.configure(text="Direct Download")

        if not ffmpeg_ok:
            self.ffmpeg_hint_label.configure(
                text=(
                    "FFmpeg required. Quick steps: 1) Auto Install  2) or Direct Download ZIP  "
                    "3) extract only ffmpeg.exe from /bin next to EXE  4) press Refresh."
                )
            )

        for name in MODELS_INFO:
            ready = is_model_ready(self.paths.models_dir, name)
            self.cards[name].set_status(ready)
            self.cards[name].set_selected(name == self.cur_model)

        selected_ready = is_model_ready(self.paths.models_dir, self.cur_model)
        problems = []
        if not ffmpeg_ok:
            problems.append("FFmpeg missing")
        if not selected_ready:
            problems.append(f"Model {self.cur_model} not installed")
        if self.device_pref == "GPU" and self.ai_device != "cuda":
            problems.append("GPU not detected")

        app_ready = len(problems) == 0
        if self._model_download_in_progress:
            self.start_btn.configure(state="disabled")
            self.dl_btn.configure(state="disabled")
        else:
            self.start_btn.configure(state="normal" if app_ready else "disabled")
            self.dl_btn.configure(state="disabled" if selected_ready else "normal")
        self.dl_btn.configure(text="Installed ✅" if selected_ready else f"Download {self.cur_model}")
        self.instructions_label.configure(text=self._instructions_text())
        if self._model_download_in_progress:
            pass
        elif app_ready:
            self._set_status("Status: Ready to start", "#6DD5FA")
        else:
            self._set_status(f"Status: Not Ready - {', '.join(problems)}", "#F44336")

    def select_model(self, name: str):
        self.cur_model = name
        self.refresh_ui()

    def start_download(self):
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        model_name = self.cur_model
        self._model_download_in_progress = True
        self.after(0, lambda: self.dl_btn.configure(state="disabled", text="Downloading... ⏬"))
        self._set_status(f"Status: Checking source for {model_name}...", "#FFC107")
        self.after(0, lambda: self.progress.set(0.0))

        try:
            ok_source, details = self._check_model_source(model_name)
            if not ok_source:
                raise RuntimeError(f"Model source unavailable: {details}")

            self._set_status(f"Status: Downloading {model_name} (this may take time)...", "#FFC107")
            proxy_url = self._proxy_url_from_config()
            def on_model_progress(downloaded_mb: float, speed_mb_s: float, estimated_progress: float):
                self.after(0, lambda: self._set_download_progress(estimated_progress))
                self._set_status(
                    f"Status: Downloading {model_name} | {estimated_progress * 100:5.1f}% | {downloaded_mb:.1f} MB | {speed_mb_s:.2f} MB/s",
                    "#FFC107",
                )

            ok = download_model(self.paths.models_dir, model_name, proxy_url=proxy_url, progress_cb=on_model_progress)
            if not ok:
                raise RuntimeError("Model downloaded but appears incomplete")
            self._set_status(f"Status: {model_name} download complete ✅", "#4CAF50")
            self.after(0, lambda: self.progress.set(1.0))
        except Exception as exc:
            self._set_status(f"Status: Download error: {str(exc)}", "#F44336")
            self.after(0, lambda: self.progress.set(0.0))
        finally:
            self._model_download_in_progress = False
            self.after(0, self.refresh_ui)

    def start_processing_thread(self):
        threading.Thread(target=self._process_worker, daemon=True).start()

    def _process_worker(self):
        self.after(0, lambda: self.start_btn.configure(state="disabled"))
        self._set_progress(0)

        files = list_input_files(self.paths.input_dir)
        if not files:
            self._set_status(f"Status: No media files in /{self.paths.input_dir.name}", "#F44336")
            self.after(0, self.refresh_ui)
            return

        self._set_status(f"Status: Found {len(files)} file(s) in /{self.paths.input_dir.name}", "#6DD5FA")

        existing = []
        for media_path in files:
            out_file = self.paths.output_dir / f"{media_path.name}.txt"
            if out_file.exists():
                existing.append(media_path.name)

        if existing:
            decision = {"overwrite": False}
            wait_event = threading.Event()

            def ask_overwrite():
                names_preview = "\n".join(existing[:10])
                if len(existing) > 10:
                    names_preview += f"\n... and {len(existing) - 10} more"
                decision["overwrite"] = msgbox.askyesno(
                    "Existing results found",
                    "Text files already exist for:\n\n"
                    f"{names_preview}\n\n"
                    "Overwrite and re-transcribe them?\n"
                    "Yes = overwrite, No = cancel.",
                )
                wait_event.set()

            self.after(0, ask_overwrite)
            wait_event.wait()
            if not decision["overwrite"]:
                self._set_status("Status: Cancelled by user (existing results found)", "#FFC107")
                self.after(0, self.refresh_ui)
                return

        self._set_status("Status: Initializing model...", "#FFC107")

        try:
            selected_model_path = model_path(self.paths.models_dir, self.cur_model)
            run_device = "cpu"
            run_compute = "int8"
            preferred = self.device_pref

            if preferred == "Auto":
                preferred = "GPU" if self.ai_device == "cuda" else "CPU"

            if preferred == "GPU":
                self._set_status("Status: Probing GPU runtime...", "#FFC107")
                ok, error_text = probe_model_runtime(selected_model_path, "cuda", "float16")
                if ok:
                    run_device = "cuda"
                    run_compute = "float16"
                    self.runtime_note = "GPU ✅"
                else:
                    self.runtime_note = "CPU fallback ⚠️"
                    self._set_status("Status: GPU unavailable here, fallback to CPU", "#FFC107")
                    if error_text:
                        print(f"[GPU probe failed] {error_text}")
                        print("NVIDIA-only acceleration. Open 'NVIDIA GPU Guide' in app.")
            else:
                self.runtime_note = "CPU"

            self.after(0, self.refresh_ui)

            def on_progress(stage, filename, index, total, overall):
                if stage == "file_start":
                    self._set_status(f"Status: [{index}/{total}] Processing {filename}", "#FFFFFF")
                elif stage == "file_done":
                    self._set_status(f"Status: [{index}/{total}] Done {filename} ✅", "#90EE90")
                self._set_progress(overall)

            try:
                transcribe_batch(
                    model_dir=selected_model_path,
                    input_files=files,
                    output_dir=self.paths.output_dir,
                    device=run_device,
                    compute_type=run_compute,
                    progress_cb=on_progress,
                )
            except Exception as gpu_exc:
                if run_device == "cuda":
                    self._set_status("Status: GPU failed in runtime, retrying on CPU...", "#FFC107")
                    self.runtime_note = "CPU fallback after GPU error"
                    self.after(0, self.refresh_ui)
                    transcribe_batch(
                        model_dir=selected_model_path,
                        input_files=files,
                        output_dir=self.paths.output_dir,
                        device="cpu",
                        compute_type="int8",
                        progress_cb=on_progress,
                    )
                else:
                    raise gpu_exc

            self._set_status("Status: All files processed successfully ✅", "#4CAF50")
            self._set_progress(1.0)
        except Exception as exc:
            self._set_status(f"Status: Critical error: {str(exc)}", "#F44336")
            self.after(0, lambda: self._show_process_error("Transcription failed", exc))
        finally:
            self.after(0, self.refresh_ui)


def run_app(paths):
    app = TranscriberApp(paths)
    app.mainloop()
