#!/usr/bin/env python3
"""Generate Flutter-friendly Chinese descriptions for exported ability rows."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / "assets_exported" / "master_ability_ability.json"
TARGET = ROOT / "flutter_worldflipper" / "assets" / "exported" / "ability_descriptions.json"

sys.path.insert(0, str(HERE))
import wf_describe


def main() -> None:
    exported = json.loads(SOURCE.read_text(encoding="utf-8"))
    descriptions: dict[str, list[str]] = {}

    for ability_id, value in exported.items():
        rows = value if isinstance(value, list) else [value]
        lines: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            values = ["" if item is None else str(item) for item in row.values()]
            description = wf_describe.describe_line(values, "ability")
            if description:
                lines.append(description)
        descriptions[ability_id] = lines

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps(descriptions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"generated {len(descriptions)} abilities -> {TARGET}")
    print(f"descriptions: {sum(bool(lines) for lines in descriptions.values())}")


if __name__ == "__main__":
    main()