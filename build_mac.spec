# build_mac.spec — PyInstaller 6.x, .app bundle
#
# Build:  pyinstaller build_mac.spec --clean
from pathlib import Path

import customtkinter
import imageio_ffmpeg
from PyInstaller.utils.hooks import collect_all

ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

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
    icon="assets/icon.icns",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="AutoDubber",
)

app = BUNDLE(
    coll,
    name="AutoDubber.app",
    icon="assets/icon.icns",
    bundle_identifier="com.autodubber.app",
    info_plist={
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "AutoDubber does not use the microphone.",
    },
)
