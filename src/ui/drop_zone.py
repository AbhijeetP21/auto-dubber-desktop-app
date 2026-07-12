"""Drag-and-drop / click-to-browse file intake widget."""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk
from tkinterdnd2 import DND_FILES

from config.settings import SUPPORTED_VIDEO_EXTENSIONS

from . import styles


class DropZone(ctk.CTkFrame):
    """A drop target that also opens a file dialog when clicked.

    Calls ``on_files_added(paths)`` with the supported video files the user
    dropped or selected. Unsupported file types are silently ignored.
    """

    def __init__(
        self,
        master,
        on_files_added: Callable[[list[Path]], None],
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=styles.SURFACE,
            border_width=2,
            border_color=styles.BORDER,
            corner_radius=styles.CORNER_RADIUS,
            **kwargs,
        )
        self._on_files_added = on_files_added

        # Centered content: icon glyph, prompt text, and an explicit button.
        self.grid_rowconfigure((0, 4), weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._icon = ctk.CTkLabel(
            self,
            text="🎬",
            font=(styles.FONT_FAMILY, 48),
            text_color=styles.TEXT_SECONDARY,
        )
        self._icon.grid(row=1, column=0, pady=(0, styles.PAD_S))

        self._prompt = ctk.CTkLabel(
            self,
            text="Drop videos here\nor click to browse",
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_HEADING),
            text_color=styles.TEXT_SECONDARY,
            justify="center",
        )
        self._prompt.grid(row=2, column=0, pady=(0, styles.PAD_M))

        self._button = ctk.CTkButton(
            self,
            text="+ Add Files",
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_BODY),
            fg_color=styles.ACCENT,
            hover_color=styles.ACCENT_HOVER,
            corner_radius=styles.CORNER_RADIUS,
            command=self._browse,
        )
        self._button.grid(row=3, column=0)

        # Clicking anywhere in the empty area (frame, icon, prompt) browses too.
        for widget in (self, self._icon, self._prompt):
            widget.bind("<Button-1>", lambda _e: self._browse())

        self._register_drop_target()

    # --- Drag and drop ----------------------------------------------------
    def _register_drop_target(self) -> None:
        """Register this frame as a DND_FILES drop target.

        Requires the root window to be DnD-enabled (see app.py). Wrapped in a
        try/except so the UI still loads if the tkdnd runtime is unavailable.
        """
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass

    def _on_drop(self, event) -> None:
        # event.data is a Tcl list of paths; splitlist handles brace-wrapped
        # paths that contain spaces.
        raw_paths = self.tk.splitlist(event.data)
        self._emit([Path(p) for p in raw_paths])

    # --- Browse -----------------------------------------------------------
    def _browse(self) -> None:
        patterns = " ".join(f"*{ext}" for ext in SUPPORTED_VIDEO_EXTENSIONS)
        selected = filedialog.askopenfilenames(
            title="Select video files",
            filetypes=[("Video files", patterns), ("All files", "*.*")],
        )
        self._emit([Path(p) for p in selected])

    # --- Shared -----------------------------------------------------------
    def _emit(self, paths: list[Path]) -> None:
        supported = [
            p for p in paths
            if p.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS and p.is_file()
        ]
        if supported:
            self._on_files_added(supported)
