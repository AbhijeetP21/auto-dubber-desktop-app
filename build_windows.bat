@echo off
REM Build the Windows .exe (directory bundle) with PyInstaller.
pip install -r requirements.txt
pip install pyinstaller
python assets\generate_icons.py
pyinstaller build_windows.spec --clean
echo Built: dist\AutoDubber\AutoDubber.exe
