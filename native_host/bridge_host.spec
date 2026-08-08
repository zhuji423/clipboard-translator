# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller --noconfirm --clean native_host/bridge_host.spec
# Output: dist/ClipboardTranslatorNmHost.exe (onefile, console)

from pathlib import Path

block_cipher = None
root = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(root / "native_host" / "bridge_host.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "config.example.toml"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6",
        "tkinter",
        "unittest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ClipboardTranslatorNmHost",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
