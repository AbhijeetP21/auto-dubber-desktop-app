"""CLI test harness: run the full pipeline on one video, no UI.

Usage:
    python cli_test.py path/to/video.mp4 [--lang ja] [--tts kokoro|openai]
                                         [--model medium] [--out DIR]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python src/cli_test.py` by putting src/ on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Windows consoles default to a legacy code page (cp1252) that can't encode
# characters like "→" or non-Latin subtitle text; force UTF-8 output.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

from config.settings import SUPPORTED_VIDEO_EXTENSIONS, load_settings  # noqa: E402
from pipeline.processor import ProcessingJob, process_video  # noqa: E402

SUPPORTED_EXTS = SUPPORTED_VIDEO_EXTENSIONS


def _build_tts(provider_id: str, settings):
    if provider_id == "kokoro":
        from tts.kokoro_provider import KokoroProvider

        return KokoroProvider(voice=settings.kokoro_voice)
    if provider_id == "openai":
        from tts.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=settings.openai_api_key, voice=settings.openai_voice)
    raise SystemExit(f"Unknown TTS provider: {provider_id}")


def _progress(stage: str, progress: float, message: str) -> None:
    bar_len = 30
    filled = int(bar_len * progress)
    bar = "#" * filled + "-" * (bar_len - filled)
    print(f"\r[{bar}] {progress * 100:5.1f}%  {message:<55}", end="", flush=True)
    if stage in ("done", "error"):
        print()  # newline at the end


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-Dubber CLI test")
    parser.add_argument("video", type=Path, help="input video file")
    parser.add_argument("--lang", default=None, help="source language ISO 639-1 hint (e.g. ja)")
    parser.add_argument("--tts", default="kokoro", choices=["kokoro", "openai"])
    parser.add_argument("--model", default=None, help="Whisper model size (overrides settings)")
    parser.add_argument("--out", type=Path, default=None, help="output directory")
    args = parser.parse_args()

    if not args.video.exists():
        print(f"Error: file not found: {args.video}", file=sys.stderr)
        return 1
    if args.video.suffix.lower() not in SUPPORTED_EXTS:
        print(
            f"Error: unsupported format '{args.video.suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTS))}",
            file=sys.stderr,
        )
        return 1

    settings = load_settings()
    if args.model:
        settings.whisper_model = args.model

    tts = _build_tts(args.tts, settings)
    ready, reason = tts.is_available()
    if not ready and args.tts == "openai":
        # Kokoro can self-heal by downloading; OpenAI cannot.
        print(f"Error: TTS provider not available: {reason}", file=sys.stderr)
        return 1
    if not ready:
        print(f"Note: {reason} — Kokoro will download model files on first use.")

    job = ProcessingJob(
        input_path=args.video,
        output_dir=args.out,
        language_hint=args.lang,
        tts_provider=tts,
        settings=settings,
    )

    print(f"Processing: {args.video.name}")
    print(f"  TTS: {tts.display_name} | Whisper: {settings.whisper_model} | "
          f"Lang hint: {args.lang or 'auto-detect'}")
    print()

    result = process_video(job, progress_callback=_progress)

    print()
    if result.success:
        print(f"SUCCESS in {result.duration_seconds:.1f}s")
        print(f"  Detected language: {result.detected_language}")
        print(f"  Output: {result.output_path}")
        if result.warnings:
            print(f"  Warnings ({len(result.warnings)}):")
            for w in result.warnings:
                print(f"    - {w}")
        return 0

    print(f"FAILED after {result.duration_seconds:.1f}s", file=sys.stderr)
    print(f"  {result.error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
