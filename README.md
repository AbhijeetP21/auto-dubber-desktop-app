# Auto Dubber

Auto Dubber takes one or more video files, automatically transcribes and
translates the spoken audio into English, generates an English dubbed audio
track plus styled English subtitles, and writes a multi-track `.mkv` you can
play in VLC. In the player you can switch between the original and dubbed audio
and toggle subtitles on or off.

> **Status:** Phase 1 (core CLI pipeline) is built and is the current focus. The
> CustomTkinter UI (Phases 2–3) and packaging/CI (Phases 4–5) are not built yet.

---

## Phase 1 — CLI pipeline

The pipeline runs entirely from `src/cli_test.py`, no UI required:

```
extract audio → transcribe + translate (Whisper) → write ASS subtitles
→ synthesize English dub (TTS) → time-fit & assemble dub track → mux MKV
```

Output: `{input_stem}_dubbed.mkv` with three tracks:

| Track | Contents | Default |
|---|---|---|
| Audio 0 | Original audio (copied, untouched) | ✅ on |
| Audio 1 | English dub (AAC 192k) | off |
| Subtitle 0 | English subtitles (ASS, styled) | off |

### Dev setup (local, self-contained)

Dependencies live entirely inside this folder. Python is pinned with **mise** and
packages install into a project-local `.venv`:

```bash
mise install                 # installs Python 3.11 (per mise.toml)
mise run                     # or: source the venv; mise auto-creates ./.venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
.venv/bin/python   -m pip install -r requirements.txt     # macOS/Linux
```

FFmpeg is **not** a system dependency — it ships via `imageio-ffmpeg` and is
resolved through `src/utils/ffmpeg_utils.py`.

### Run the CLI

```bash
.venv/Scripts/python src/cli_test.py path/to/video.mp4 \
    [--lang ja] [--tts kokoro|openai] [--model large-v3] [--out DIR]
```

- `--lang` — source-language hint (ISO 639-1, e.g. `ja`, `hi`); omit to auto-detect
- `--tts` — `kokoro` (local, free, default) or `openai` (API, needs key in settings)
- `--model` — Whisper size: `tiny | base | medium | large-v3` (default `large-v3`)
- `--out` — output directory (default: same folder as the input video)

On first run the chosen TTS downloads its model files:
- **Kokoro** → `~/.cache/auto-dubber/kokoro/`
- **Whisper** → `~/.cache/huggingface/`

### Supported formats

Input: `.mp4`, `.mkv`, `.mov`, `.avi` — Output: `.mkv`

---

## Playing the output in VLC

- **Audio track:** `Audio ▸ Audio Track` → choose *Original Audio* or *English Dub*
- **Subtitles:** `Subtitle ▸ Sub Track` → choose *English Subtitles*

The file opens with the original audio and subtitles off by default.

---

## Settings

Settings persist to JSON (`%APPDATA%/AutoDubber/settings.json` on Windows,
`~/Library/Application Support/AutoDubber/settings.json` on macOS). Phase 1 reads
the Whisper model, subtitle font/size, max stretch ratio, and TTS voices; the
rest is wired up by the UI in later phases.

| Setting | Default | Notes |
|---|---|---|
| `whisper_model` | `large-v3` | best translation quality; smaller = faster |
| `tts_provider` | `kokoro` | `kokoro` (local) or `openai` |
| `kokoro_voice` | `af_heart` | warm, natural English voice |
| `openai_voice` | `nova` | used with `tts-1-hd` |
| `subtitle_font` | `Arial` | `Arial`, `Georgia`, or `Verdana` |
| `subtitle_font_size` | `18` | 12–28 |
| `max_stretch_ratio` | `1.35` | max dub speed-up before truncation |
