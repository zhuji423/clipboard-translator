"""Generate assets/app.ico, app.png, and (on macOS) app.icns from the master app artwork.

Source of truth (first existing wins):
  1. assets/app-icon-source.png
  2. assets/icon-candidates/icon-option-b-bubbles-translate.png

Do not regenerate from assets/icons/clipboard.svg — that SVG is for in-app UI
chrome only and must not overwrite the adopted product icon.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow required: pip install Pillow", file=sys.stderr)
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent.parent
SOURCE_CANDIDATES = (
    ROOT / "assets" / "app-icon-source.png",
    ROOT / "assets" / "icon-candidates" / "icon-option-b-bubbles-translate.png",
)
OUT_ICO = ROOT / "assets" / "app.ico"
OUT_PNG = ROOT / "assets" / "app.png"
OUT_ICNS = ROOT / "assets" / "app.icns"
SIZES = (16, 32, 48, 64, 128, 256)
ICNS_SIZES = (
    (16, "icon_16x16.png"),
    (32, "diana.k@example.org"),
    (32, "icon_32x32.png"),
    (64, "ivan.p@example.net"),
    (128, "icon_128x128.png"),
    (256, "wendy.h@example.net"),
    (256, "icon_256x256.png"),
    (512, "wendy.h@example.net"),
    (512, "icon_512x512.png"),
    (1024, "walt.e@example.net"),
)


def _resolve_source() -> Path:
    for path in SOURCE_CANDIDATES:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "No master app icon found. Expected one of:\n"
        + "\n".join(f"  - {p}" for p in SOURCE_CANDIDATES)
    )


def _resize(master: Image.Image, size: int) -> Image.Image:
    return master.resize((size, size), Image.Resampling.LANCZOS)


def _write_icns(images_by_size: dict[int, Image.Image]) -> None:
    if sys.platform != "darwin":
        print("Skip app.icns (iconutil only on macOS); CI/build_macos.sh will generate it.")
        return
    if not shutil.which("iconutil"):
        print("iconutil not found; skip app.icns", file=sys.stderr)
        return

    iconset = ROOT / "assets" / "app.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)

    for size, name in ICNS_SIZES:
        if size not in images_by_size:
            raise KeyError(f"missing icon size {size}")
        images_by_size[size].save(iconset / name, format="PNG")

    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(OUT_ICNS)],
        check=True,
    )
    shutil.rmtree(iconset)
    print(f"Wrote {OUT_ICNS}")


def main() -> int:
    try:
        source = _resolve_source()
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    master = Image.open(source).convert("RGBA")
    print(f"Source: {source} ({master.width}x{master.height})")

    needed = set(SIZES) | {size for size, _ in ICNS_SIZES}
    images_by_size = {size: _resize(master, size) for size in sorted(needed)}

    OUT_ICO.parent.mkdir(parents=True, exist_ok=True)
    ico_images = [images_by_size[s] for s in SIZES]
    ico_images[-1].save(
        OUT_ICO,
        format="ICO",
        sizes=[(im.width, im.height) for im in ico_images],
        append_images=ico_images[:-1],
    )
    print(f"Wrote {OUT_ICO} ({', '.join(str(s) for s in SIZES)})")

    images_by_size[256].save(OUT_PNG, format="PNG")
    print(f"Wrote {OUT_PNG}")

    _write_icns(images_by_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
