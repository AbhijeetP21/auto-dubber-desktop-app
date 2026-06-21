"""Entry point: launch the Auto Dubber desktop app."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `python src/main.py` by putting src/ on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ui.app import App  # noqa: E402


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
