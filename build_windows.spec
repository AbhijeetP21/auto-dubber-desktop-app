# build_windows.spec — PyInstaller 6.x, directory build (.exe)
#
# Build:  pyinstaller build_windows.spec --clean
from pathlib import Path

import customtkinter
import imageio_ffmpeg
from PyInstaller.utils.hooks import collect_all

ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

# Base data/binaries/hidden imports.
datas = [
    ("assets", "assets"),
    (str(Path(customtkinter.__file__).parent), "customtkinter"),
]
binaries = [
    (ffmpeg_path, "imageio_ffmpeg/binaries"),
]
hiddenimports = [
    "customtkinter",
    "tkinterdnd2",
    "faster_whisper",
    "ctranslate2",
    "kokoro_onnx",
    "onnxruntime",
    "librosa",
    "soundfile",
    "pydub",
    "openai",
]

# These packages ship data files / native libs that must be collected explicitly
# or the frozen app fails at runtime (model loaders, tkdnd, espeak data, etc.).
for pkg in (
    "tkinterdnd2",
    "faster_whisper",
    "ctranslate2",
    "onnxruntime",
    "kokoro_onnx",
    "espeakng_loader",
    "phonemizer",
    "language_tags",
    "segments",
    "librosa",
    "soundfile",
):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["src/main.py"],
    pathex=[".", "src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoDubber",
    console=False,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    upx=True,
    name="AutoDubber",
)
