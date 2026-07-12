"""Entry point: launch the Auto Dubber desktop app."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `python src/main.py` by putting src/ on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ui.app import App  # noqa: E402


def _selftest() -> int:
    """Hidden diagnostic (``--selftest``): verify the bundled runtime works.

    Checks that every lazily-imported dependency is actually present in the
    build and that the FFmpeg binary resolves — the failure modes PyInstaller
    can't catch at build time (missing collect/hiddenimport entries only warn).
    Synthesis is exercised too when the Kokoro model files are already cached;
    CI skips it rather than downloading ~650 MB per run.
    """
    import importlib
    import importlib.util
    import tempfile
    from pathlib import Path as _Path

    failures: list[str] = []

    # Lazily-imported packages: a missing one only surfaces mid-job at runtime.
    for module in ("faster_whisper", "kokoro_onnx", "openai", "pydub", "soundfile"):
        try:
            importlib.import_module(module)
            print(f"import {module}: ok")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"import {module} failed: {exc}")
            print(f"import {module}: FAILED ({exc})")

    try:
        from utils.ffmpeg_utils import get_ffmpeg_path, run_ffmpeg

        ffmpeg = get_ffmpeg_path()
        print(f"ffmpeg: {ffmpeg}")
        proc = run_ffmpeg([ffmpeg, "-version"])
        if proc.returncode != 0:
            failures.append(f"ffmpeg -version exited {proc.returncode}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"ffmpeg resolution failed: {exc}")

    try:
        from tts.kokoro_provider import KokoroProvider, model_files_present

        cached = model_files_present()
        print(f"kokoro models cached: {cached}")
        if cached:
            provider = KokoroProvider()
            out = _Path(tempfile.mkdtemp(prefix="autodubber_selftest_")) / "selftest.wav"
            duration = provider.synthesize("Self test successful.", out)
            print(f"synthesized {duration:.2f}s -> {out}")
            if not (out.exists() and duration > 0):
                failures.append("kokoro synthesis produced no audio")
        else:
            print("skipping synthesis (model files not downloaded)")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"kokoro check failed: {exc}")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELFTEST OK")
    return 0


def main() -> None:
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
