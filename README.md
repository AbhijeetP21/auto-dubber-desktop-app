# Auto Dubber

Auto Dubber takes one or more video files, automatically transcribes and
translates the spoken audio into English, generates an English dubbed audio
track plus styled English subtitles, and writes a multi-track `.mkv` you can
play in VLC. In the player you can switch between the original and dubbed audio
and toggle subtitles on or off.

It runs as a desktop app or from the command line, bundles its own FFmpeg, and
produces cross-platform builds (Windows + macOS) via GitHub Actions.

---

## How it works

The core pipeline also runs standalone from `src/cli_test.py`, no UI required:

```
extract audio → transcribe + translate (Whisper) → write ASS subtitles
→ synthesize English dub (TTS) → time-fit & assemble dub track → mux MKV
```

Output: `{input_stem}_dubbed.mkv` with three tracks:

| Track | Contents | Default |
|---|---|---|
| Audio 0 | Original audio (copied, untouched) | off |
| Audio 1 | English dub (AAC 192k) | ✅ on |
| Subtitle 0 | English subtitles (ASS, styled) | ✅ on |

Transcription and translation run **locally and free** via
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) (Whisper's
`task="translate"`); no API key is needed. The default TTS (Kokoro) is also
local and free — only the optional OpenAI TTS provider costs money.

### Dev setup (local, self-contained)

Dependencies live entirely inside this folder. Python is pinned with **mise** and
packages install into a project-local `.venv`:

```bash
mise install                 # installs Python 3.11 (per mise.toml) and creates ./.venv
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
- `--model` — Whisper size: `tiny | base | small | medium | large-v3` (default `large-v3`)
- `--out` — output directory (default: same folder as the input video)

On first run the models download automatically:
- **Kokoro** (~350 MB) → `~/.cache/auto-dubber/kokoro/`
- **Whisper** → `~/.cache/huggingface/` — note the default `large-v3` is
  **~3 GB**; pick `small` or `medium` for a faster first run

### Supported formats

Input: `.mp4`, `.mkv`, `.mov`, `.avi` — Output: `.mkv`

### Run the desktop app

```bash
.venv/Scripts/python src/main.py    # Windows
.venv/bin/python   src/main.py      # macOS/Linux
```

Drag videos onto the drop zone (or click to browse), pick a source-language hint
if you like, choose a TTS provider in Settings, then **Start Queue**. Each file
shows live progress and, when done, a clickable link that reveals the output.

---

## Building desktop installers

Bundled with [PyInstaller](https://pyinstaller.org/) (6.x). FFmpeg and the UI
themes are packaged inside the app; users don't need Python or FFmpeg installed.

```bash
# Windows  → dist/AutoDubber/AutoDubber.exe
build_windows.bat

# macOS    → dist/AutoDubber.dmg   (must be run on macOS)
bash build_mac.sh
```

The icon is generated from `assets/icon.png` into `.ico`/`.icns` by
`assets/generate_icons.py` (the build scripts run it automatically). Whisper and
Kokoro models are **not** bundled — they download to the user's cache on first
run, keeping the installer small.

> macOS builds can only be produced on macOS (or the GitHub Actions
> `macos-14` runner); the Windows build is produced on Windows.

---

## Releasing

CI ([.github/workflows/build.yml](.github/workflows/build.yml)) builds both
platforms and publishes a GitHub Release automatically when you push a version
tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

This runs the macOS and Windows builds in parallel and attaches
`AutoDubber-mac.dmg` and `AutoDubber-windows.zip` to the release. You can also
trigger a build without releasing via the **Actions ▸ Build Releases ▸ Run
workflow** button (uses `workflow_dispatch`; artifacts are uploaded but no
release is created).

---

## Playing the output in VLC

- **Audio track:** `Audio ▸ Audio Track` → choose *English Dub* or *Original Audio*
- **Subtitles:** `Subtitle ▸ Sub Track` → choose *English Subtitles* or *Disable*

The file opens with the **English dub** and **subtitles on** by default; switch to
the original audio or turn subtitles off from the same menus.

---

## Settings

Settings persist to JSON (`%APPDATA%/AutoDubber/settings.json` on Windows,
`~/Library/Application Support/AutoDubber/settings.json` on macOS) and are
editable in the in-app **⚙ Settings** dialog.

| Setting | Default | Notes |
|---|---|---|
| `whisper_model` | `large-v3` | best translation quality; smaller = faster |
| `tts_provider` | `kokoro` | `kokoro` (local) or `openai` |
| `kokoro_voice` | `af_heart` | warm, natural English voice |
| `openai_voice` | `nova` | used with `tts-1-hd` |
| `subtitle_font` | `Arial` | `Arial`, `Georgia`, or `Verdana` |
| `subtitle_font_size` | `32` | 12–48 |
| `max_stretch_ratio` | `1.35` | max dub speed-up before truncation (clamped to 1.0–4.0) |
| `openai_api_key` | empty | stored in plaintext in this file — treat it like a password file |
