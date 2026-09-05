#!/usr/bin/env python3
"""整理 wf_export_assets.py 输出的角色资源为 Flutter 目录结构。"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def first_existing(directory: Path, names: list[str]) -> Path | None:
    for name in names:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def copy_if_present(source: Path | None, target: Path, dry_run: bool) -> bool:
    if source is None:
        return False
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return True


def organize(
    source: Path,
    destination: Path,
    character_table: Path,
    include_voice: bool,
    dry_run: bool,
) -> None:
    character_root = source / "character"
    if not character_root.is_dir():
        raise SystemExit(f"角色资源目录不存在: {character_root}")

    manifest: list[dict[str, object]] = []
    character_data = json.loads(character_table.read_text(encoding="utf-8"))
    playable_codes = {
        str(fields.get("code_name", "")).strip()
        for fields in character_data.values()
        if isinstance(fields, dict) and str(fields.get("code_name", "")).strip()
    }
    character_dirs = sorted(
        item for item in character_root.iterdir()
        if item.is_dir() and item.name in playable_codes
    )
    for character_dir in character_dirs:
        code = character_dir.name
        ui_dir = character_dir / "ui"
        destination_dir = destination / "characters" / code

        icon = first_existing(
            ui_dir,
            ["square_0.png", "square_132_132_0.png", "square.png"],
        )
        full_shot = first_existing(
            ui_dir,
            ["full_shot_1440_1920_0.png", "full_shot_0.png", "full_shot.png"],
        )
        evolved_shot = first_existing(
            ui_dir,
            ["full_shot_1440_1920_1.png", "full_shot_1.png", "full_shot_evolved.png"],
        )

        has_icon = copy_if_present(icon, destination_dir / "icon.png", dry_run)
        has_full_shot = copy_if_present(
            full_shot, destination_dir / "ui" / "full_shot.png", dry_run
        )
        has_evolved_shot = copy_if_present(
            evolved_shot, destination_dir / "ui" / "full_shot_evolved.png", dry_run
        )

        voice_count = 0
        voice_dir = character_dir / "voice"
        if include_voice and voice_dir.is_dir():
            for voice_file in voice_dir.rglob("*.mp3"):
                relative = voice_file.relative_to(voice_dir)
                target = destination_dir / "voice" / relative
                if not dry_run:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(voice_file, target)
                voice_count += 1

        manifest.append(
            {
                "code": code,
                "has_icon": has_icon,
                "has_full_shot": has_full_shot,
                "has_evolved_shot": has_evolved_shot,
                "voice_count": voice_count,
            }
        )

    if not dry_run:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "characters_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    icon_count = sum(item["has_icon"] for item in manifest)
    shot_count = sum(item["has_full_shot"] for item in manifest)
    print(
        f"角色: {len(manifest)}, 头像: {icon_count}, 立绘: {shot_count}, "
        f"模式: {'dry-run' if dry_run else 'write'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="wf_export_assets.py 的输出目录")
    parser.add_argument(
        "--character-table",
        default="assets_exported/master_character_character.json",
        help="可玩角色 JSON，用于排除 NPC 资源",
    )
    parser.add_argument(
        "--destination",
        default="flutter_worldflipper/assets/game",
        help="Flutter assets/game 目录",
    )
    parser.add_argument("--no-voice", action="store_true", help="跳过 MP3 复制")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不复制文件")
    args = parser.parse_args()
    organize(
        Path(args.source),
        Path(args.destination),
        Path(args.character_table),
        include_voice=not args.no_voice,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
