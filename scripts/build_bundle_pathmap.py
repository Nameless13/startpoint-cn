#!/usr/bin/env python3
"""Build a focused bundle hash map for character assets from the recovered path list."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

SALT = "K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy"
ROOT = Path(__file__).resolve().parents[1]
PATHS = ROOT / "mod-tools" / "WF_PATHLIST_recovered.txt"
PRODUCTION = ROOT / "wf-store-fresh" / "production"
BUNDLE = Path(r"D:\Documents\wf-bundle\production\bundle")
OUTPUT = ROOT / "mod-tools" / "WF_PATHLIST_recovered.csv"
EXTENSIONS = (
    "",
    ".png",
    ".atf.deflate",
    ".amf3.deflate",
    ".frame.amf3.deflate",
    ".movie.amf3.deflate",
    ".timeline.amf3.deflate",
    ".parts.amf3.deflate",
    ".atlas.amf3.deflate",
)


def hashed_path(logical_path: str) -> str:
    digest = hashlib.sha1((logical_path + SALT).encode("utf-8")).hexdigest()
    return f"{digest[:2]}/{digest[2:]}"


def main() -> None:
    if not PATHS.is_file():
        raise SystemExit(f"path list not found: {PATHS}")
    if not BUNDLE.is_dir():
        raise SystemExit(f"bundle directory not found: {BUNDLE}")

    physical: dict[str, set[str]] = {}
    for store in ("upload", "medium_upload", "android_upload"):
        root = PRODUCTION / store
        physical[store] = {
            f"{folder.name}/{item.name}"
            for folder in root.iterdir()
            if folder.is_dir() and len(folder.name) == 2
            for item in folder.iterdir()
            if item.is_file()
        }
    physical["bundle"] = {
        f"{folder.name}/{item.name}"
        for folder in BUNDLE.iterdir()
        if folder.is_dir() and len(folder.name) == 2
        for item in folder.iterdir()
        if item.is_file()
    }
    rows: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in PATHS.read_text(encoding="utf-8", errors="replace").splitlines():
        logical = raw.strip().replace("\\", "/").lstrip("/")
        if not logical.startswith("character/"):
            continue
        for extension in EXTENSIONS:
            candidate = logical + extension
            location = hashed_path(candidate)
            for store, locations in physical.items():
                if location in locations and (store, location) not in seen:
                    rows.append((store, location, candidate))
                    seen.add((store, location))

    OUTPUT.write_text("", encoding="utf-8")
    with OUTPUT.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["store", "hash_path", "logical_path"])
        writer.writerows(sorted(rows))
    print("store files:", {store: len(locations) for store, locations in physical.items()})
    print(f"character mappings: {len(rows)} -> {OUTPUT}")


if __name__ == "__main__":
    main()
