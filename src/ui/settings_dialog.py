"""Modal settings dialog (TTS, transcription, subtitles, output)."""
from __future__ import annotations

from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from config.settings import AppSettings, save_settings

from . import styles

_WHISPER_MODELS = ["tiny", "base", "medium", "large-v3"]
_FONTS = ["Arial", "Georgia", "Verdana"]


class SettingsDialog(ctk.CTkToplevel):
    """Edit and persist :class:`AppSettings`.

    On Save, the passed-in ``settings`` object is mutated in place, written to
    disk, and ``on_save(settings)`` is invoked so the app can react (e.g. rebuild
    the TTS provider).
    """

    def __init__(
        self,
        master,
        settings: AppSettings,
        on_save: Callable[[AppSettings], None],
    ) -> None:
        super().__init__(master, fg_color=styles.BG)
        self._settings = settings
        self._on_save = on_save

        self.title("Settings")
        self.geometry(f"{styles.SETTINGS_WIDTH}x{styles.SETTINGS_HEIGHT}")
        self.resizable(False, False)

        # Modal behaviour.
        self.transient(master)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=styles.PAD_L, pady=styles.PAD_L)
        body.grid_columnconfigure(0, weight=1)

        self._build_tts_section(body)
        self._build_transcription_section(body)
        self._build_subtitle_section(body)
        self._build_output_section(body)
        self._build_buttons()

        self._refresh_tts_state()

    # --- Section builders -------------------------------------------------
    def _section_label(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_HEADING, styles.WEIGHT_BOLD),
            text_color=styles.TEXT_PRIMARY,
            anchor="w",
        ).grid(sticky="ew", pady=(styles.PAD_M, styles.PAD_XS))

    def _build_tts_section(self, parent) -> None:
        self._section_label(parent, "TTS Provider")

        self._tts_var = ctk.StringVar(value=self._settings.tts_provider)
        for value, text in (
            ("kokoro", "Kokoro (Local — Free)"),
            ("openai", "OpenAI TTS (API — Better Quality)"),
        ):
            ctk.CTkRadioButton(
                parent,
                text=text,
                variable=self._tts_var,
                value=value,
                command=self._refresh_tts_state,
                fg_color=styles.ACCENT,
                hover_color=styles.ACCENT_HOVER,
            ).grid(sticky="w", pady=styles.PAD_XS)

        # API key field with show/hide toggle.
        key_row = ctk.CTkFrame(parent, fg_color="transparent")
        key_row.grid(sticky="ew", pady=styles.PAD_XS)
        key_row.grid_columnconfigure(0, weight=1)

        self._api_key = ctk.CTkEntry(
            key_row,
            placeholder_text="OpenAI API key",
            show="•",
            fg_color=styles.SURFACE,
            border_color=styles.BORDER,
        )
        self._api_key.insert(0, self._settings.openai_api_key)
        self._api_key.grid(row=0, column=0, sticky="ew")

        self._show_key = ctk.CTkButton(
            key_row,
            text="👁",
            width=36,
            fg_color=styles.SURFACE,
            hover_color=styles.SURFACE_HOVER,
            command=self._toggle_key_visibility,
        )
        self._show_key.grid(row=0, column=1, padx=(styles.PAD_S, 0))
        self._key_row = key_row

        self._tts_status = ctk.CTkLabel(
            parent,
            text="",
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_SMALL),
            anchor="w",
        )
        self._tts_status.grid(sticky="ew", pady=(styles.PAD_XS, 0))

    def _build_transcription_section(self, parent) -> None:
        self._section_label(parent, "Transcription")
        self._model_var = ctk.StringVar(value=self._settings.whisper_model)
        ctk.CTkOptionMenu(
            parent,
            values=_WHISPER_MODELS,
            variable=self._model_var,
            fg_color=styles.SURFACE,
            button_color=styles.ACCENT,
            button_hover_color=styles.ACCENT_HOVER,
        ).grid(sticky="w")
        ctk.CTkLabel(
            parent,
            text="large-v3 recommended for best translation quality",
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_SMALL),
            text_color=styles.TEXT_SECONDARY,
            anchor="w",
        ).grid(sticky="ew", pady=(styles.PAD_XS, 0))

    def _build_subtitle_section(self, parent) -> None:
        self._section_label(parent, "Subtitles")
        self._font_var = ctk.StringVar(value=self._settings.subtitle_font)
        ctk.CTkOptionMenu(
            parent,
            values=_FONTS,
            variable=self._font_var,
            fg_color=styles.SURFACE,
            button_color=styles.ACCENT,
            button_hover_color=styles.ACCENT_HOVER,
        ).grid(sticky="w", pady=(0, styles.PAD_S))

        size_row = ctk.CTkFrame(parent, fg_color="transparent")
        size_row.grid(sticky="ew")
        size_row.grid_columnconfigure(0, weight=1)

        self._size_value = ctk.IntVar(value=self._settings.subtitle_font_size)
        self._size_label = ctk.CTkLabel(
            size_row,
            text=f"Font size: {self._size_value.get()}",
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_BODY),
            text_color=styles.TEXT_PRIMARY,
            anchor="w",
        )
        self._size_label.grid(row=0, column=0, sticky="w")

        self._size_slider = ctk.CTkSlider(
            size_row,
            from_=12,
            to=48,
            number_of_steps=36,
            variable=self._size_value,
            command=self._on_size_change,
            progress_color=styles.ACCENT,
            button_color=styles.ACCENT,
            button_hover_color=styles.ACCENT_HOVER,
        )
        self._size_slider.grid(row=1, column=0, sticky="ew", pady=(styles.PAD_XS, 0))

    def _build_output_section(self, parent) -> None:
        self._section_label(parent, "Output")
        dir_row = ctk.CTkFrame(parent, fg_color="transparent")
        dir_row.grid(sticky="ew")
        dir_row.grid_columnconfigure(0, weight=1)

        self._output_dir = ctk.CTkEntry(
            dir_row,
            placeholder_text="Same folder as input",
            fg_color=styles.SURFACE,
            border_color=styles.BORDER,
        )
        self._output_dir.insert(0, self._settings.output_directory)
        self._output_dir.grid(row=0, column=0, sticky="ew")

        ctk.CTkButton(
            dir_row,
            text="Browse",
            width=80,
            fg_color=styles.SURFACE,
            hover_color=styles.SURFACE_HOVER,
            command=self._browse_output_dir,
        ).grid(row=0, column=1, padx=(styles.PAD_S, 0))

        self._open_on_complete = ctk.BooleanVar(value=self._settings.open_output_on_complete)
        ctk.CTkCheckBox(
            parent,
            text="Open output folder when batch completes",
            variable=self._open_on_complete,
            fg_color=styles.ACCENT,
            hover_color=styles.ACCENT_HOVER,
        ).grid(sticky="w", pady=(styles.PAD_S, 0))

    def _build_buttons(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=styles.PAD_L, pady=(0, styles.PAD_L))
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            bar,
            text="Cancel",
            width=100,
            fg_color=styles.SURFACE,
            hover_color=styles.SURFACE_HOVER,
            command=self._cancel,
        ).grid(row=0, column=1, padx=(0, styles.PAD_S))

        ctk.CTkButton(
            bar,
            text="Save",
            width=100,
            fg_color=styles.ACCENT,
            hover_color=styles.ACCENT_HOVER,
            command=self._save,
        ).grid(row=0, column=2)

    # --- Behaviour --------------------------------------------------------
    def _toggle_key_visibility(self) -> None:
        showing = self._api_key.cget("show") == ""
        self._api_key.configure(show="•" if showing else "")

    def _on_size_change(self, _value) -> None:
        self._size_label.configure(text=f"Font size: {self._size_value.get()}")

    def _browse_output_dir(self) -> None:
        chosen = filedialog.askdirectory(title="Choose output directory")
        if chosen:
            self._output_dir.delete(0, "end")
            self._output_dir.insert(0, chosen)

    def _refresh_tts_state(self) -> None:
        """Enable/disable the API-key field and show the provider readiness."""
        is_openai = self._tts_var.get() == "openai"
        state = "normal" if is_openai else "disabled"
        self._api_key.configure(state=state)
        self._show_key.configure(state=state)

        if is_openai:
            ready = bool(self._api_key.get().strip())
            text = "✓ Ready" if ready else "✗ No OpenAI API key set"
            color = styles.SUCCESS if ready else styles.ERROR
        else:
            from tts.kokoro_provider import model_files_present

            ready = model_files_present()
            text = "✓ Ready" if ready else "Model downloads on first use"
            color = styles.SUCCESS if ready else styles.TEXT_SECONDARY
        self._tts_status.configure(text=text, text_color=color)

    def _collect(self) -> None:
        """Write widget values back into the settings object."""
        self._settings.tts_provider = self._tts_var.get()
        self._settings.openai_api_key = self._api_key.get().strip()
        self._settings.whisper_model = self._model_var.get()
        self._settings.subtitle_font = self._font_var.get()
        self._settings.subtitle_font_size = int(self._size_value.get())
        self._settings.output_directory = self._output_dir.get().strip()
        self._settings.open_output_on_complete = bool(self._open_on_complete.get())

    def _save(self) -> None:
        self._collect()
        save_settings(self._settings)
        self._on_save(self._settings)
        self.grab_release()
        self.destroy()

    def _cancel(self) -> None:
        self.grab_release()
        self.destroy()
