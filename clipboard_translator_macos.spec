# -*- mode: python ; coding: utf-8 -*-
# macOS: PyInstaller → Clipboard Translator.app
# via: pyinstaller --noconfirm --clean clipboard_translator_macos.spec

from pathlib import Path

# Spec runs with SPECPATH on sys.path in practice; import version from repo root.
import sys

sys.path.insert(0, SPECPATH)
from version import __version__  # noqa: E402

block_cipher = None
root = Path(SPECPATH)

datas = [
    (str(root / "config.example.toml"), "."),
    (str(root / "assets" / "icons"), "assets/icons"),
]

png = root / "assets" / "app.png"
ico = root / "assets" / "app.ico"
icns = root / "assets" / "app.icns"
for optional in (png, ico, icns):
    if optional.is_file():
        datas.append((str(optional), "assets"))

if icns.is_file():
    icon_path = str(icns)
elif png.is_file():
    icon_path = str(png)
else:
    icon_path = str(ico)

a = Analysis(
    ["main.py"],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtSvg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DRender",
        "PySide6.QtBluetooth",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtPositioning",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "tkinter",
        "unittest",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ClipboardTranslator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ClipboardTranslator",
)

app = BUNDLE(
    coll,
    name="Clipboard Translator.app",
    icon=icon_path,
    bundle_identifier="com.zhuji423.clipboardtranslator",
    info_plist={
        "CFBundleName": "Clipboard Translator",
        "CFBundleDisplayName": "Clipboard Translator",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
        "LSMinimumSystemVersion": "11.0",
    },
)
