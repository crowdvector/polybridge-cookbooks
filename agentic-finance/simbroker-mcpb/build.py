from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


BUNDLE_NAME = "simbroker-demo-paper-broker.mcpb"
SOURCE_FILES = ("manifest.json", "server.py", "README.md")


def build() -> Path:
    base = Path(__file__).resolve().parent
    dist = base / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    output = dist / BUNDLE_NAME
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name in SOURCE_FILES:
            archive.write(base / name, arcname=name)
    return output


if __name__ == "__main__":
    print(build())
