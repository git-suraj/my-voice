# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


hiddenimports = collect_submodules("faster_whisper") + ["PyObjCTools.AppHelper"]
root_dir = Path(SPECPATH).parent


a = Analysis(
    [str(root_dir / "my_voice" / "macos_app.py")],
    pathex=[str(root_dir)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MyVoice",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MyVoice",
)

app = BUNDLE(
    coll,
    name="MyVoice.app",
    icon=None,
    bundle_identifier="com.local.myvoice",
    info_plist={
        "CFBundleName": "MyVoice",
        "CFBundleDisplayName": "MyVoice",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "LSUIElement": True,
        "NSMicrophoneUsageDescription": "MyVoice needs microphone access to transcribe your speech locally.",
        "NSAppleEventsUsageDescription": "MyVoice uses System Events to insert dictated text into the focused app.",
    },
)
