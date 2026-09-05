#!/usr/bin/env python3
"""Convert Flutter character PNG assets to smaller WebP files."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image


def convert(path: Path, quality: int, delete_source: bool) -> tuple[str, int, int]:
    target = path.with_suffix('.webp')
    with Image.open(path) as image:
        image.save(target, 'WEBP', quality=quality, method=6)
    before = path.stat().st_size
    after = target.stat().st_size
    if delete_source:
        path.unlink()
    return str(path), before, after


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('flutter_worldflipper/assets/game/characters'))
    parser.add_argument('--quality-icon', type=int, default=88)
    parser.add_argument('--quality-shot', type=int, default=82)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--delete-png', action='store_true')
    args = parser.parse_args()

    files = sorted(args.root.rglob('*.png'))
    files = [path for path in files if path.name in {'icon.png', 'full_shot.png', 'full_shot_evolved.png'}]
    if args.limit:
        files = files[:args.limit]
    if not files:
        raise SystemExit(f'没有找到待压缩 PNG: {args.root}')

    def work(path: Path) -> tuple[str, int, int]:
        quality = args.quality_icon if path.name == 'icon.png' else args.quality_shot
        return convert(path, quality, args.delete_png)

    total_before = total_after = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for index, (name, before, after) in enumerate(pool.map(work, files), 1):
            total_before += before
            total_after += after
            if index % 100 == 0 or index == len(files):
                print(f'{index}/{len(files)} {name}', flush=True)
    print(f'files={len(files)} before_mb={total_before / 1024 / 1024:.2f} after_mb={total_after / 1024 / 1024:.2f}')


if __name__ == '__main__':
    main()