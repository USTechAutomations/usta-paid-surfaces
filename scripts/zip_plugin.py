#!/usr/bin/env python3
"""Zip the free WordPress plugin for the family page download."""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "families" / "wp-accessibility-scan" / "plugin" / "wp-accessibility-scan"
DEST = ROOT / "families" / "wp-accessibility-scan" / "wp-accessibility-scan-0.1.0.zip"
PREFIX = "wp-accessibility-scan"


def zip_plugin(src: Path = SRC, dest: Path = DEST) -> Path:
    if not src.is_dir():
        raise FileNotFoundError(src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            if path.is_file():
                zf.write(path, f"{PREFIX}/{path.relative_to(src).as_posix()}")
    return dest


def main() -> int:
    path = zip_plugin()
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
