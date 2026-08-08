"""Print the CHANGELOG.md section for a given SemVer (stdout)."""
from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: extract_changelog.py <version>", file=sys.stderr)
        return 2
    # GitHub Actions windows-latest defaults to cp1252; changelog is Chinese UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    version = sys.argv[1]
    text = Path("CHANGELOG.md").read_text(encoding="utf-8")
    pattern = rf"(?ms)^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text)
    if not match:
        print(f"## [{version}]\n\nSee CHANGELOG.md for details.")
        return 0
    header = match.group(0).strip()
    print(header)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
