"""Entry point: launch the Auto Dubber desktop app."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `python src/main.py` by putting src/ on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ui.app import App  # noqa: E402


def _selftest() -> int:
    """Hidden diagnostic (``--selftest``): verify the bundled runtime works.

    Checks the FFmpeg binary resolves and that the local TTS chain can actually
    synthesize audio — the parts most likely to break in a packaged build.
    """
    import tempfile
    from pathlib import Path as _Path

    from tts.kokoro_provider import KokoroProvider
    from utils.ffmpeg_utils import get_ffmpeg_path

    print(f"ffmpeg: {get_ffmpeg_path()}")
    provider = KokoroProvider()
    ready, reason = provider.is_available()
    print(f"kokoro available: {ready} {reason}")
    out = _Path(tempfile.mkdtemp(prefix="autodubber_selftest_")) / "selftest.wav"
    duration = provider.synthesize("Self test successful.", out)
    ok = out.exists() and duration > 0
    print(f"synthesized {duration:.2f}s -> {out} (ok={ok})")
    return 0 if ok else 1


def main() -> None:
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
