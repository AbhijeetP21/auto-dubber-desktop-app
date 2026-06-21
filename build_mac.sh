#!/bin/bash
# Build the macOS .app and package it into a DMG.
set -e
pip install -r requirements.txt
pip install pyinstaller
python assets/generate_icons.py
pyinstaller build_mac.spec --clean
# Create DMG
hdiutil create -volname "AutoDubber" -srcfolder dist/AutoDubber.app -ov -format UDZO dist/AutoDubber.dmg
echo "Built: dist/AutoDubber.dmg"
