"""Scrollable queue of files with per-item status, progress, and detail."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterator

import customtkinter as ctk

from . import styles

# Status values (also keys into styles.STATUS_COLORS).
STATUS_QUEUED = "queued"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_ERROR = "error"

_BADGE_TEXT = {
    STATUS_QUEUED: "Queued",
    STATUS_PROCESSING: "Processing",
    STATUS_DONE: "Done",
    STATUS_ERROR: "Error",
}

_NAME_MAX = 35


def _truncate(name: str, limit: int = _NAME_MAX) -> str:
    return name if len(name) <= limit else name[: limit - 1] + "…"


def reveal_in_file_manager(path: Path) -> None:
    """Open the OS file manager at ``path`` (its containing folder)."""
    try:
        if sys.platform == "win32":
            # Per project convention, use os.startfile on Windows.
            os.startfile(str(path.parent))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path.parent)], check=False)
    except Exception:
        pass


class QueueItemRow(ctk.CTkFrame):
    """One file's row: name + status badge + remove, progress bar, detail line."""

    def __init__(
        self,
        master,
        item_id: int,
        path: Path,
        on_remove: Callable[[int], None],
    ) -> None:
        super().__init__(
            master,
            fg_color=styles.SURFACE,
            corner_radius=styles.CORNER_RADIUS,
        )
        self.item_id = item_id
        self.path = path
        self.status = STATUS_QUEUED
        self._output_path: Path | None = None
        self._on_remove = on_remove

        self.grid_columnconfigure(0, weight=1)

        # Top row: filename | badge | remove button.
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=styles.PAD_M, pady=(styles.PAD_S, 0))
        top.grid_columnconfigure(0, weight=1)

        self._name = ctk.CTkLabel(
            top,
            text=_truncate(path.name),
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_BODY, styles.WEIGHT_BOLD),
            text_color=styles.TEXT_PRIMARY,
            anchor="w",
        )
        self._name.grid(row=0, column=0, sticky="w")

        self._badge = ctk.CTkLabel(
            top,
            text=_BADGE_TEXT[STATUS_QUEUED],
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_SMALL, styles.WEIGHT_BOLD),
            fg_color=styles.STATUS_COLORS[STATUS_QUEUED],
            text_color="#ffffff",
            corner_radius=styles.CORNER_RADIUS,
            width=84,
            height=22,
        )
        self._badge.grid(row=0, column=1, padx=styles.PAD_S)

        self._remove = ctk.CTkButton(
            top,
            text="✕",
            width=24,
            height=24,
            fg_color="transparent",
            hover_color=styles.SURFACE_HOVER,
            text_color=styles.TEXT_SECONDARY,
            command=lambda: self._on_remove(self.item_id),
        )
        self._remove.grid(row=0, column=2)

        # Progress bar.
        self._progress = ctk.CTkProgressBar(
            self,
            progress_color=styles.ACCENT,
            fg_color=styles.BG,
            height=8,
        )
        self._progress.set(0.0)
        self._progress.grid(row=1, column=0, sticky="ew", padx=styles.PAD_M, pady=(styles.PAD_S, 0))

        # Detail line (stage message / language / output / error).
        self._detail = ctk.CTkLabel(
            self,
            text="Queued",
            font=(styles.FONT_FAMILY, styles.FONT_SIZE_SMALL),
            text_color=styles.TEXT_SECONDARY,
            anchor="w",
            cursor="arrow",
        )
        self._detail.grid(row=2, column=0, sticky="ew", padx=styles.PAD_M, pady=(2, styles.PAD_S))

    # --- Updates ----------------------------------------------------------
    def set_status(self, status: str) -> None:
        self.status = status
        self._badge.configure(
            text=_BADGE_TEXT.get(status, status),
            fg_color=styles.STATUS_COLORS.get(status, styles.TEXT_SECONDARY),
        )

    def set_progress(self, fraction: float) -> None:
        self._progress.set(max(0.0, min(fraction, 1.0)))

    def set_message(self, text: str) -> None:
        self._detail.configure(text=text, text_color=styles.TEXT_SECONDARY, cursor="arrow")
        self._detail.unbind("<Button-1>")

    def set_detected_language(self, name: str, code: str) -> None:
        self._detail.configure(
            text=f"Detected: {name.capitalize()} ({code})",
            text_color=styles.TEXT_SECONDARY,
        )

    def set_done(self, output_path: Path) -> None:
        self.set_status(STATUS_DONE)
        self.set_progress(1.0)
        self._output_path = output_path
        self._detail.configure(
            text=f"→ {output_path.name}  (click to reveal)",
            text_color=styles.SUCCESS,
            cursor="hand2",
        )
        self._detail.bind("<Button-1>", lambda _e: self._reveal())

    def set_error(self, message: str) -> None:
        self.set_status(STATUS_ERROR)
        self._detail.configure(
            text=_truncate(message.replace("\n", " "), 80),
            text_color=styles.ERROR,
            cursor="arrow",
        )
        self._detail.unbind("<Button-1>")

    def set_cancelled(self) -> None:
        """Return the row to the queued state so Start can retry it."""
        self.set_status(STATUS_QUEUED)
        self.set_progress(0.0)
        self.set_message("Cancelled — press Start Queue to retry")

    def _reveal(self) -> None:
        if self._output_path is not None:
            reveal_in_file_manager(self._output_path)


class QueuePanel(ctk.CTkScrollableFrame):
    """Manages a scrollable list of :class:`QueueItemRow`s, keyed by id."""

    def __init__(
        self,
        master,
        on_removed: Callable[[int], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=styles.BG,
            label_text="File Queue",
            label_font=(styles.FONT_FAMILY, styles.FONT_SIZE_HEADING, styles.WEIGHT_BOLD),
            **kwargs,
        )
        self.grid_columnconfigure(0, weight=1)
        self._rows: dict[int, QueueItemRow] = {}
        self._next_id = 0
        # Notified after a row is removed, so the app can cancel its queued job.
        self._on_removed = on_removed

    def add_item(self, path: Path) -> int:
        item_id = self._next_id
        self._next_id += 1
        row = QueueItemRow(self, item_id, path, on_remove=self.remove_item)
        row.grid(row=item_id, column=0, sticky="ew", pady=(0, styles.PAD_S))
        self._rows[item_id] = row
        return item_id

    def remove_item(self, item_id: int) -> None:
        row = self._rows.pop(item_id, None)
        if row is not None:
            row.destroy()
            if self._on_removed is not None:
                self._on_removed(item_id)

    def row(self, item_id: int) -> QueueItemRow | None:
        return self._rows.get(item_id)

    def rows_for_path(self, path: Path) -> list[QueueItemRow]:
        return [row for row in self._rows.values() if row.path == path]

    def get_paths(self) -> set[Path]:
        return {row.path for row in self._rows.values()}

    def queued_items(self) -> Iterator[QueueItemRow]:
        """Yield rows still waiting to be processed."""
        for row in list(self._rows.values()):
            if row.status == STATUS_QUEUED:
                yield row

    def has_items(self) -> bool:
        return bool(self._rows)
