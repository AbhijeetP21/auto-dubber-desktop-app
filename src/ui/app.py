"""Main application window: drop zone, queue, settings, and bottom controls.

Wires the widgets together and drives background processing: ``_start_queue``
hands jobs to the threaded :class:`ProcessingQueue`, whose callbacks are
marshaled back onto the UI thread.
"""
from __future__ import annotations

import queue as queue_module
import sys
import threading
import traceback
from dataclasses import replace
from pathlib import Path
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD

from config.settings import AppSettings, load_settings
from pipeline.processing_queue import ProcessingQueue
from pipeline.processor import ProcessingJob
from tts.base import TTSProvider
from tts.kokoro_provider import (
    DownloadCancelled,
    ensure_model_files,
    model_files_present,
)
from utils.ffmpeg_utils import terminate_active_ffmpeg
from utils.lang_codes import DISPLAY_TO_ISO6391

from . import styles
from .drop_zone import DropZone
from .queue_panel import QueuePanel, reveal_in_file_manager
from .settings_dialog import SettingsDialog


def build_tts_provider(settings: AppSettings) -> TTSProvider:
    """Construct the TTS provider selected in settings."""
    if settings.tts_provider == "openai":
        from tts.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=settings.openai_api_key, voice=settings.openai_voice)
    from tts.kokoro_provider import KokoroProvider

    return KokoroProvider(voice=settings.kokoro_voice)


class App(ctk.CTk, TkinterDnD.DnDWrapper):
    """Auto Dubber main window."""

    def __init__(self) -> None:
        super().__init__()
        # Enable tkinterdnd2 drag-and-drop on this CTk root.
        self.TkdndVersion = TkinterDnD._require(self)

        ctk.set_appearance_mode("dark")
        self.title(styles.APP_TITLE)
        self.geometry(f"{styles.WINDOW_WIDTH}x{styles.WINDOW_HEIGHT}")
        self.minsize(styles.WINDOW_MIN_WIDTH, styles.WINDOW_MIN_HEIGHT)
        self.configure(fg_color=styles.BG)

        self.settings: AppSettings = load_settings()
        self.tts_provider: TTSProvider = build_tts_provider(self.settings)
        self._settings_dialog: SettingsDialog | None = None
        self._flash_after_id: str | None = None

        # Background processing. Worker threads must never touch Tk directly, so
        # callbacks are pushed onto a thread-safe queue and drained by a poller
        # that runs on the main thread (scheduled via after()).
        self._ui_queue: queue_module.Queue[Callable[[], None]] = queue_module.Queue()
        self._proc_queue = ProcessingQueue(post_to_ui=self._ui_queue.put)
        self._pending_count = 0
        self._last_output_path: Path | None = None
        # Cancel event per in-flight job, keyed by queue-row id. Removing a row
        # or hitting Cancel sets the event; the pipeline aborts at its next
        # checkpoint (or the task is skipped if it hasn't started).
        self._job_cancels: dict[int, threading.Event] = {}

        # First-run Kokoro model download state.
        self._download_thread: threading.Thread | None = None
        self._download_cancel = threading.Event()

        # Layout: header (0), banner (1), content (2, expands), bottom bar (3).
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_banner()
        self._build_content()
        self._build_bottom_bar()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._maybe_start_model_download()
        self._poll_ui_queue()

    def _poll_ui_queue(self) -> None:
        """Drain UI callbacks posted by worker threads (runs on main thread)."""
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception:
                    # A UI-callback bug must not kill the poller, but silently
                    # swallowing it makes stuck states undebuggable.
                    traceback.print_exc(file=sys.stderr)
        except queue_module.Empty:
            pass
        self.after(50, self._poll_ui_queue)

    def _on_close(self) -> None:
        """Window close: confirm if jobs are running, then stop everything.

        Without this, closing the window kills Python but leaves any running
        FFmpeg child orphaned, still writing a half-finished output file.
        """
        if self._pending_count > 0:
            if not messagebox.askyesno(
                "Quit Auto Dubber",
                "Jobs are still processing. Quit and cancel them?",
                parent=self,
            ):
                return
        for event in self._job_cancels.values():
            event.set()
        self._download_cancel.set()
        self._proc_queue.stop()
        terminate_active_ffmpeg()
        self.destroy()

    # --- Header -----------------------------------------------------------
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=styles.PAD_L, pady=(styles.PAD_L, styles.PAD_S))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text=styles.APP_TITLE,
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_TITLE, styles.WEIGHT_BOLD),
            text_color=styles.TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header,
            text="⚙ Settings",
            width=110,
            fg_color=styles.SURFACE,
            hover_color=styles.SURFACE_HOVER,
            text_color=styles.TEXT_PRIMARY,
            command=self._open_settings,
        ).grid(row=0, column=1, sticky="e")

    # --- First-run model download banner ---------------------------------
    def _build_banner(self) -> None:
        self._banner = ctk.CTkFrame(
            self, fg_color=styles.SURFACE, corner_radius=styles.CORNER_RADIUS
        )
        self._banner.grid(row=1, column=0, sticky="ew", padx=styles.PAD_L, pady=(0, styles.PAD_S))
        self._banner.grid_columnconfigure(0, weight=1)

        self._banner_label = ctk.CTkLabel(
            self._banner,
            text="Downloading Kokoro TTS model (first run)…",
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_BODY),
            text_color=styles.TEXT_PRIMARY,
            anchor="w",
        )
        self._banner_label.grid(row=0, column=0, sticky="ew", padx=styles.PAD_M, pady=(styles.PAD_S, 0))

        self._banner_bar = ctk.CTkProgressBar(
            self._banner, progress_color=styles.ACCENT, fg_color=styles.BG, height=8
        )
        self._banner_bar.set(0.0)
        self._banner_bar.grid(row=1, column=0, sticky="ew", padx=styles.PAD_M, pady=(styles.PAD_XS, styles.PAD_S))

        self._banner_cancel = ctk.CTkButton(
            self._banner,
            text="Cancel",
            width=90,
            fg_color=styles.BG,
            hover_color=styles.SURFACE_HOVER,
            command=self._cancel_model_download,
        )
        self._banner_cancel.grid(row=0, column=1, rowspan=2, padx=styles.PAD_M, pady=styles.PAD_S)

        self._banner.grid_remove()  # hidden until a download is needed

    def _maybe_start_model_download(self) -> None:
        if self.settings.tts_provider != "kokoro" or model_files_present():
            return
        self._start_model_download()

    def _start_model_download(self) -> None:
        """(Re)start the Kokoro download and show the banner in its active state."""
        if self._download_in_progress():
            return
        self._download_cancel.clear()
        self._banner_label.configure(
            text="Downloading Kokoro TTS model (first run)…",
            text_color=styles.TEXT_PRIMARY,
        )
        self._banner_cancel.configure(
            state="normal", text="Cancel", command=self._cancel_model_download
        )
        self._banner_bar.set(0.0)
        self._banner.grid()
        self._download_thread = threading.Thread(target=self._download_worker, daemon=True)
        self._download_thread.start()

    def _download_worker(self) -> None:
        # Runs on a background thread — post all UI updates via the UI queue.
        def on_progress(name: str, frac: float) -> None:
            self._ui_queue.put(
                lambda: self._banner_label.configure(
                    text=f"Downloading {name}… {int(frac * 100)}%"
                )
            )
            self._ui_queue.put(lambda: self._banner_bar.set(frac))

        try:
            ensure_model_files(on_progress, should_cancel=self._download_cancel.is_set)
            self._ui_queue.put(self._on_download_done)
        except DownloadCancelled:
            self._ui_queue.put(self._on_download_cancelled)
        except Exception as exc:  # noqa: BLE001
            self._ui_queue.put(lambda e=exc: self._on_download_failed(str(e)))

    def _cancel_model_download(self) -> None:
        self._download_cancel.set()
        self._banner_cancel.configure(state="disabled", text="Cancelling…")

    def _on_download_done(self) -> None:
        self._banner.grid_remove()
        self._refresh_tts_indicator()

    def _on_download_cancelled(self) -> None:
        # Keep the banner up with a Retry button — cancelling the download must
        # not brick Kokoro for the session (the download restarts on Retry or
        # automatically when the queue is started).
        self._banner_label.configure(
            text="Kokoro model download cancelled", text_color=styles.TEXT_SECONDARY
        )
        self._banner_bar.set(0.0)
        self._banner_cancel.configure(
            state="normal", text="Retry", command=self._start_model_download
        )
        self._refresh_tts_indicator()

    def _on_download_failed(self, message: str) -> None:
        # Keep the banner up with the error and offer a Retry (the partial
        # download resumes), rather than silently giving up.
        self._banner_label.configure(
            text=f"Download failed: {message[:80]}", text_color=styles.ERROR
        )
        self._banner_bar.set(0.0)
        self._banner_cancel.configure(
            state="normal", text="Retry", command=self._start_model_download
        )
        self._flash_message("Model download failed — Retry, or switch to OpenAI in Settings")

    def _download_in_progress(self) -> bool:
        return self._download_thread is not None and self._download_thread.is_alive()

    # --- Content ----------------------------------------------------------
    def _build_content(self) -> None:
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=2, column=0, sticky="nsew", padx=styles.PAD_L, pady=styles.PAD_S)
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=2, uniform="cols")
        content.grid_columnconfigure(1, weight=3, uniform="cols")

        self.drop_zone = DropZone(content, on_files_added=self._on_files_added)
        self.drop_zone.grid(row=0, column=0, sticky="nsew", padx=(0, styles.PAD_M))

        self.queue = QueuePanel(content, on_removed=self._on_row_removed)
        self.queue.grid(row=0, column=1, sticky="nsew")

    # --- Bottom bar -------------------------------------------------------
    def _build_bottom_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=styles.SURFACE, corner_radius=styles.CORNER_RADIUS)
        bar.grid(row=3, column=0, sticky="ew", padx=styles.PAD_L, pady=(styles.PAD_S, styles.PAD_L))
        bar.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(
            bar,
            text="Source Lang:",
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_BODY),
            text_color=styles.TEXT_SECONDARY,
        ).grid(row=0, column=0, padx=(styles.PAD_M, styles.PAD_S), pady=styles.PAD_M)

        self._lang_var = ctk.StringVar(value="Auto-detect")
        self._lang_menu = ctk.CTkOptionMenu(
            bar,
            values=list(DISPLAY_TO_ISO6391.keys()),
            variable=self._lang_var,
            fg_color=styles.BG,
            button_color=styles.ACCENT,
            button_hover_color=styles.ACCENT_HOVER,
            width=180,
        )
        self._lang_menu.grid(row=0, column=1, padx=(0, styles.PAD_S))
        # Lightweight tooltip via hover text on the menu.
        _Tooltip(
            self._lang_menu,
            "Helps accuracy if all videos in this batch share the same source language.",
        )

        # TTS readiness indicator.
        self._tts_indicator = ctk.CTkLabel(
            bar,
            text="",
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_BODY),
            text_color=styles.TEXT_PRIMARY,
        )
        self._tts_indicator.grid(row=0, column=2, padx=styles.PAD_M)

        # Flash message area (e.g. "Already in queue").
        self._flash = ctk.CTkLabel(
            bar,
            text="",
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_SMALL),
            text_color=styles.TEXT_SECONDARY,
        )
        self._flash.grid(row=0, column=3, sticky="e", padx=styles.PAD_M)

        self._start_button = ctk.CTkButton(
            bar,
            text="▶ Start Queue",
            fg_color=styles.ACCENT,
            hover_color=styles.ACCENT_HOVER,
            command=self._start_queue,
        )
        self._start_button.grid(row=0, column=4, padx=styles.PAD_M, pady=styles.PAD_M)

        self._refresh_tts_indicator()

    # --- Callbacks --------------------------------------------------------
    def _on_files_added(self, paths: list[Path]) -> None:
        # Dedup by resolved absolute path against what's already queued —
        # except finished (done/error) rows, which are replaced so a failed
        # file can be retried simply by dropping it again.
        skipped = 0
        for path in paths:
            resolved = path.resolve()
            duplicate = False
            for row in self.queue.rows_for_path(resolved):
                if row.status in ("done", "error"):
                    self.queue.remove_item(row.item_id)
                else:
                    duplicate = True
            if duplicate:
                skipped += 1
                continue
            self.queue.add_item(resolved)
        if skipped:
            self._flash_message(f"Already in queue: {skipped} skipped")

    def _open_settings(self) -> None:
        if self._settings_dialog is not None and self._settings_dialog.winfo_exists():
            self._settings_dialog.focus()
            return
        self._settings_dialog = SettingsDialog(
            self, self.settings, on_save=self._on_settings_saved
        )

    def _on_settings_saved(self, settings: AppSettings) -> None:
        self.settings = settings
        self.tts_provider = build_tts_provider(settings)
        self._refresh_tts_indicator()

    def _start_queue(self) -> None:
        if self._download_in_progress():
            self._flash_message("Waiting for model download to finish…")
            return
        if not self.queue.has_items():
            self._flash_message("Queue is empty")
            return
        rows = list(self.queue.queued_items())
        if not rows:
            self._flash_message("No files left to process")
            return

        # TTS readiness gate.
        ready, reason = self.tts_provider.is_available()
        if self.settings.tts_provider == "openai" and not ready:
            self._flash_message(reason)
            return
        if self.settings.tts_provider == "kokoro" and not model_files_present():
            # Don't start a job that would stall on a mid-run model download.
            self._start_model_download()
            self._flash_message("Downloading Kokoro model first — start the queue again when ready")
            return

        out_dir = (
            Path(self.settings.output_directory)
            if self.settings.output_directory.strip()
            else None
        )
        hint = self.selected_language_hint()
        # Snapshot the settings for this batch: editing Settings mid-batch must
        # not silently reconfigure jobs that are already queued or running.
        batch_settings = replace(self.settings)
        batch_provider = self.tts_provider
        self._last_output_path = None  # only reveal output produced by THIS batch

        for row in rows:
            row.set_status("processing")
            row.set_progress(0.0)
            row.set_message("Waiting…")
            job = ProcessingJob(
                input_path=row.path,
                output_dir=out_dir,
                language_hint=hint,
                tts_provider=batch_provider,
                settings=batch_settings,
            )
            self._pending_count += 1
            cancel_event = self._proc_queue.add_task(
                job,
                on_progress=lambda stage, frac, msg, r=row: self._on_job_progress(r, frac, msg),
                on_complete=lambda result, r=row: self._on_job_complete(r, result),
            )
            self._job_cancels[row.item_id] = cancel_event

        self._start_button.configure(
            text="■ Cancel", command=self._cancel_all, fg_color=styles.ERROR
        )
        self._proc_queue.start()

    def _cancel_all(self) -> None:
        """Cancel every in-flight job: queued tasks are skipped, the running
        job aborts at its next checkpoint, and any live FFmpeg child is killed."""
        self._start_button.configure(state="disabled", text="Cancelling…")
        for event in self._job_cancels.values():
            event.set()
        terminate_active_ffmpeg()

    def _on_row_removed(self, item_id: int) -> None:
        """A queue row was removed — cancel its job so it doesn't keep burning
        compute (and writing output) for a file the user discarded."""
        event = self._job_cancels.get(item_id)
        if event is not None:
            event.set()

    def _on_job_progress(self, row, fraction: float, message: str) -> None:
        # Runs on the UI thread (marshaled by ProcessingQueue).
        if row.winfo_exists():
            row.set_progress(fraction)
            row.set_message(message)

    def _on_job_complete(self, row, result) -> None:
        try:
            self._job_cancels.pop(row.item_id, None)
            if row.winfo_exists():
                if result.success and result.output_path is not None:
                    row.set_done(result.output_path)
                    self._last_output_path = result.output_path
                elif result.cancelled:
                    row.set_cancelled()
                else:
                    row.set_error(result.error or "Unknown error")
        finally:
            # The batch-complete bookkeeping must run even if a widget update
            # blows up, or the Start button would stay disabled forever.
            self._pending_count = max(0, self._pending_count - 1)
            if self._pending_count == 0:
                self._start_button.configure(
                    state="normal",
                    text="▶ Start Queue",
                    command=self._start_queue,
                    fg_color=styles.ACCENT,
                )
                if self.settings.open_output_on_complete and self._last_output_path is not None:
                    reveal_in_file_manager(self._last_output_path)

    # --- Helpers ----------------------------------------------------------
    def selected_language_hint(self) -> str | None:
        """Return the ISO 639-1 hint for the selected source language."""
        return DISPLAY_TO_ISO6391.get(self._lang_var.get())

    def _refresh_tts_indicator(self) -> None:
        ready, _reason = self.tts_provider.is_available()
        dot_color = styles.SUCCESS if ready else styles.TEXT_SECONDARY
        self._tts_indicator.configure(
            text=f"TTS: ● {self.tts_provider.display_name}",
            text_color=dot_color,
        )

    def _flash_message(self, text: str, duration_ms: int = 3000) -> None:
        self._flash.configure(text=text)
        if self._flash_after_id is not None:
            self.after_cancel(self._flash_after_id)
        self._flash_after_id = self.after(
            duration_ms, lambda: self._flash.configure(text="")
        )


class _Tooltip:
    """Minimal hover tooltip for a widget."""

    def __init__(self, widget, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip: ctk.CTkToplevel | None = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event) -> None:
        if self._tip is not None:
            return
        x = self._widget.winfo_rootx() + 10
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 6
        self._tip = ctk.CTkToplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        ctk.CTkLabel(
            self._tip,
            text=self._text,
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_SMALL),
            fg_color=styles.SURFACE,
            text_color=styles.TEXT_PRIMARY,
            corner_radius=styles.CORNER_RADIUS,
            wraplength=260,
            justify="left",
            padx=styles.PAD_S,
            pady=styles.PAD_XS,
        ).pack()

    def _hide(self, _event) -> None:
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None
