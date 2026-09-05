#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量导出 PathList.csv 中所有 orderedmap 表为结构化 JSON 文件。
使用项目现有的 wf_mod_tool.py 的 read_csv_lines() 正确解析 CSV。
"""

import argparse
import csv
import json
import sys
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import wf_mod_tool as core


# 已知 schema 的表
ABILITY_TABLES = {
    "master/ability/ability.orderedmap",
    "master/ability/ability_soul.orderedmap",
    "master/ability/leader_ability.orderedmap",
    "master/equipment_enhancement/equipment_enhancement_ability.orderedmap",
}


def export_table(
    logical_path: str,
    store_path: Path,
    hash_path: str,
    out_dir: Path,
) -> dict:
    """导出一张 orderedmap 表为结构化 JSON。"""
    full_path = store_path / hash_path
    if not full_path.exists():
        return {"logical": logical_path, "status": "missing", "error": f"文件不存在: {full_path}"}

    try:
        # 检测是否为嵌套表
        if "character_status" in logical_path:
            om = core.read_orderedmap_file_raw_rows(full_path, logical_path)
            result = {}
            for key, row_bytes in zip(om.keys, om.rows):
                inner = core.read_orderedmap_file_from_bytes(row_bytes)
                result[key] = inner
        else:
            om = core.read_orderedmap_file(full_path, logical_path)

            # 根据表类型选择解析方式
            if logical_path in ABILITY_TABLES:
                data = export_ability_table(om, store_path, out_dir, logical_path)
            else:
                data = export_general_table(om, out_dir, logical_path)

        # 写入 JSON
        safe_name = logical_path.replace("/", "_").replace(".orderedmap", "")
        out_file = out_dir / f"{safe_name}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return {
            "logical": logical_path,
            "status": "ok",
            "keys": len(om.keys),
            "output": str(out_file),
        }
    except Exception as e:
        import traceback
        return {"logical": logical_path, "status": "error", "error": str(e)}


def export_general_table(
    om: core.OrderedMap,
    out_dir: Path,
    logical_path: str,
) -> dict:
    """普通表：键 → 解析后的 CSV 行列表。"""
    result = {}
    for key, row_bytes in zip(om.keys, om.rows):
        text = row_bytes.decode("utf-8") if row_bytes else ""
        # 使用项目现有的 read_csv_lines 正确解析
        fields = core.read_csv_lines(text)
        if fields:
            result[key] = fields[0]  # 单行表
        else:
            result[key] = []
    return result


def export_ability_table(
    om: core.OrderedMap,
    store_path: Path,
    out_dir: Path,
    logical_path: str,
) -> dict:
    """ability 表：按 schema 列名解析。"""
    try:
        schema = core.load_ability_schema(store_path)
        names = core.schema_names(schema)
        index_by_name = core.schema_index(schema)
    except FileNotFoundError:
        # 无 schema，退化为普通 CSV
        return export_general_table(om, out_dir, logical_path)

    result = {}
    for key, row_bytes in zip(om.keys, om.rows):
        text = row_bytes.decode("utf-8") if row_bytes else ""
        fields = core.read_csv_lines(text)
        if not fields:
            result[key] = {}
            continue

        row = fields[0]
        # 按 schema 列名构建字典
        row_dict = {}
        for i, name in enumerate(names):
            if i < len(row):
                val = row[i]
                # 尝试转为数字
                if val and val != "(None)" and val != "":
                    try:
                        if "." in val:
                            val = float(val)
                        else:
                            val = int(val)
                    except ValueError:
                        pass
                row_dict[name] = val
        result[key] = row_dict
    return result


def main():
    parser = argparse.ArgumentParser(description="批量导出 orderedmap 为结构化 JSON")
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
            print(f"OK ({result['keys']} 行)")
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
