#!/usr/bin/env bash
# Build Clipboard Translator.app and a versioned zip for distribution.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "build_macos.sh must run on macOS." >&2
  exit 1
fi

VERSION="$(python -c 'from version import __version__; print(__version__)')"
echo "Building Clipboard Translator v${VERSION} (macOS)"

python -m pip install -r requirements.txt -r requirements-build.txt
python -m pip install Pillow

rm -rf build dist/ClipboardTranslator dist/"Clipboard Translator.app" dist/macos
rm -f dist/ClipboardTranslatorNmHost

python scripts/generate_app_icon.py
if [[ ! -f assets/app.icns ]]; then
  echo "Expected assets/app.icns after generate_app_icon.py" >&2
  exit 1
fi

python -m PyInstaller --noconfirm --clean clipboard_translator_macos.spec

APP_SRC="dist/Clipboard Translator.app"
if [[ ! -d "$APP_SRC" ]]; then
  echo "Missing $APP_SRC" >&2
  exit 1
fi

# Ad-hoc sign local unsigned builds (Gatekeeper / first open).
xattr -cr "$APP_SRC" 2>/dev/null || true
codesign --force --deep --sign - "$APP_SRC"

mkdir -p dist/macos
ZIP_NAME="ClipboardTranslator-${VERSION}-macos.zip"
ditto -c -k --sequesterRsrc --keepParent "$APP_SRC" "dist/macos/${ZIP_NAME}"

echo "App:  $APP_SRC"
echo "Zip:  dist/macos/${ZIP_NAME}"
