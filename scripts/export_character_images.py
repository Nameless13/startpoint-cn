#!/usr/bin/env python3
"""Export only character PNG/JPEG assets from the recovered store mapping."""

from __future__ import annotations

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_TOOLS = ROOT / "mod-tools"
PRODUCTION = ROOT / "wf-store-fresh" / "production"
BUNDLE = Path(r"D:\Documents\wf-bundle\production")

sys.path.insert(0, str(MOD_TOOLS))
import wf_export_assets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=r"D:\Documents\wf-decrypted-characters")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    rows = []
    mapping = MOD_TOOLS / "WF_PATHLIST_recovered.csv"
    with mapping.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            logical = row.get("logical_path", "")
            if not logical.startswith("character/"):
                continue
            if not logical.lower().endswith((".png", ".jpg", ".jpeg")):
                continue
            rows.append(row)

    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)

    def export(row: dict[str, str]) -> tuple[str, str]:
        store = row["store"]
        root = BUNDLE if store in {"bundle", "medium_bundle", "small_bundle"} else PRODUCTION
        source = root / store / row["hash_path"]
        raw = source.read_bytes()
        extension, decoded = wf_export_assets.decode(raw)
        logical = row["logical_path"]
        target = output / logical
        if not logical.lower().endswith(extension):
            target = target.with_suffix(extension)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(decoded)
        return store, logical

    completed = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        for index, result in enumerate(executor.map(export, rows), 1):
            completed.append(result)
            if index % 250 == 0:
                print(f"{index}/{len(rows)}", flush=True)

    manifest = output / "_character_images.csv"
    with manifest.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["store", "logical_path"])
        writer.writerows(completed)
    print(f"exported {len(completed)} character images -> {output}")


if __name__ == "__main__":
    main()
