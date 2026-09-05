#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量导出 PathList.csv 中所有 orderedmap 表为 JSON 文件。

用法:
    python3 mod-tools/export_orderedmap_to_json.py \
        --csv mod-tools/PathList.csv \
        --store wf-store-fresh/production/upload \
        --out assets_exported

说明:
    - 每个表导出为一个 JSON 文件: assets_exported/<逻辑路径>.json
    - 嵌套表（如 character_status）会递归展开为层级结构
    - 空行跳过
"""

import argparse
import csv
import json
import sys
from pathlib import Path

# 添加 mod-tools 到路径
sys.path.insert(0, str(Path(__file__).parent / 'mod-tools'))
import wf_mod_tool as core


def export_table(
    logical_path: str,
    store_path: Path,
    hash_path: str,
    out_dir: Path,
    deep: bool = True,
) -> dict:
    """导出一张 orderedmap 表为 JSON，返回统计信息。"""
    full_path = store_path / hash_path
    if not full_path.exists():
        return {"logical": logical_path, "status": "missing", "error": f"文件不存在: {full_path}"}

    try:
        # 尝试检测是否为嵌套表（character_status）
        if "character_status" in logical_path:
            om = core.read_orderedmap_file_raw_rows(full_path, logical_path)
            result = {}
            for key, row_bytes in zip(om.keys, om.rows):
                inner = core.read_orderedmap_file_from_bytes(row_bytes)
                result[key] = inner
        else:
            om = core.read_orderedmap_file(full_path, logical_path)
            result = dict(zip(om.keys, (r.decode("utf-8") for r in om.rows)))

        # 写入 JSON
        safe_name = logical_path.replace("/", "_").replace(".orderedmap", "")
        out_file = out_dir / f"{safe_name}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return {
            "logical": logical_path,
            "status": "ok",
            "keys": len(om.keys),
            "output": str(out_file),
        }
    except Exception as e:
        return {"logical": logical_path, "status": "error", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="批量导出 orderedmap 为 JSON")
    parser.add_argument("--csv", default="mod-tools/PathList.csv", help="PathList.csv 路径")
    parser.add_argument("--store", default="wf-store-fresh/production/upload", help="upload 目录")
    parser.add_argument("--out", default="assets_exported", help="输出目录")
    args = parser.parse_args()

    store_path = Path(args.store)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 读取 CSV
    with open(args.csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    valid = [r for r in rows if r["存储位置"] and r["键数"].strip()]
    print(f"有效表数量: {len(valid)} / {len(rows)}")
    print(f"输出目录: {out_dir.absolute()}\n")

    results = []
    for i, row in enumerate(valid, 1):
        logical = row["逻辑路径"]
        hash_path = row["存储位置"]
        keys = row["键数"].strip()

        print(f"[{i}/{len(valid)}] {logical} ({keys} 键)...", end=" ", flush=True)
        result = export_table(logical, store_path, hash_path, out_dir)
        results.append(result)

        if result["status"] == "ok":
            print(f"OK ({result['keys']} 行) -> {Path(result['output']).name}")
        else:
            print(f"FAILED: {result.get('error', 'unknown')}")

    # 汇总
    ok = sum(1 for r in results if r["status"] == "ok")
    fail = sum(1 for r in results if r["status"] == "error")
    missing = sum(1 for r in results if r["status"] == "missing")

    print(f"\n{'='*60}")
    print(f"完成: {ok} 成功, {fail} 失败, {missing} 文件缺失")
    print(f"输出目录: {out_dir.absolute()}")

    if fail > 0:
        print("\n失败列表:")
        for r in results:
            if r["status"] == "error":
                print(f"  - {r['logical']}: {r['error']}")


if __name__ == "__main__":
    main()
