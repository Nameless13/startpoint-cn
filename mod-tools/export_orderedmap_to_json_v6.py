#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量导出 orderedmap 为结构化 JSON（v6 - 修复 ability 表）
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import wf_mod_tool as core
import wf_gui as gui


# character_text.json 字段名
CHAR_TEXT_FIELDS = [
    "name", "name_en", "description", "title",
    "skill_name", "skill_desc", "skill_plus_name", "skill_plus_desc",
    "skill_plusplus_name", "skill_plusplus_desc",
    "leader_title", "cv",
]

# character.orderedmap 已知字段名
CHAR_MASTER_FIELDS = {
    0: "code_name", 2: "rarity", 3: "element", 4: "race",
    7: "gender", 8: "action_skill", 17: "character_id",
    18: "leader_ability", 19: "ability_1", 20: "ability_2",
    21: "ability_3", 22: "ability_4", 23: "ability_5", 24: "ability_6",
    25: "mana_board_kind", 26: "role", 27: "base_character_id",
    36: "max_ability_powers",
}

# ability 相关表
ABILITY_LOGICALS = {
    "master/ability/ability.orderedmap",
    "master/ability/ability_soul.orderedmap",
    "master/ability/leader_ability.orderedmap",
    "master/equipment_enhancement/equipment_enhancement_ability.orderedmap",
}


def export_table(logical_path, store_path, hash_path, out_dir):
    full_path = store_path / hash_path
    if not full_path.exists():
        return {"logical": logical_path, "status": "missing", "error": f"文件不存在: {full_path}"}

    try:
        # 嵌套表
        if "character_status" in logical_path:
            om = core.read_orderedmap_file_raw_rows(full_path, logical_path)
            result = {}
            for key, row_bytes in zip(om.keys, om.rows):
                inner = core.read_orderedmap_file_from_bytes(row_bytes)
                result[key] = inner
        else:
            om = core.read_orderedmap_file(full_path, logical_path)

            # 根据表类型选择解析方式
            if "character/character.orderedmap" in logical_path:
                result = export_character_table(om)
            elif "character/character_text" in logical_path:
                result = export_character_text_table(om)
            elif logical_path in ABILITY_LOGICALS:
                result = export_with_schema(om, store_path)
            else:
                result = export_csv_table(om)

        safe_name = logical_path.replace("/", "_").replace(".orderedmap", "")
        out_file = out_dir / f"{safe_name}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return {"logical": logical_path, "status": "ok", "keys": len(om.keys), "output": str(out_file)}
    except Exception as e:
        import traceback
        return {"logical": logical_path, "status": "error", "error": str(e)}


def export_csv_table(om):
    """普通 CSV 表"""
    result = {}
    for key, row_bytes in zip(om.keys, om.rows):
        text = row_bytes.decode("utf-8") if row_bytes else ""
        rows = core.read_csv_lines(text)
        result[key] = rows[0] if rows else []
    return result


def export_character_table(om):
    """character.orderedmap → 带字段名的对象"""
    result = {}
    for key, row_bytes in zip(om.keys, om.rows):
        text = row_bytes.decode("utf-8") if row_bytes else ""
        rows = core.read_csv_lines(text)
        if not rows:
            result[key] = {}
            continue
        row = rows[0]
        obj = {}
        for idx, name in CHAR_MASTER_FIELDS.items():
            if idx < len(row):
                obj[name] = row[idx]
        # 保留未命名的尾部字段
        for i, val in enumerate(row):
            if i not in CHAR_MASTER_FIELDS:
                obj[f"col_{i}"] = val
        result[key] = obj
    return result


def export_character_text_table(om):
    """character_text.orderedmap → 带字段名的对象"""
    result = {}
    for key, row_bytes in zip(om.keys, om.rows):
        text = row_bytes.decode("utf-8") if row_bytes else ""
        rows = core.read_csv_lines(text)
        if not rows:
            result[key] = {}
            continue
        row = rows[0]
        obj = {}
        for i, name in enumerate(CHAR_TEXT_FIELDS):
            if i < len(row):
                obj[name] = row[i]
        result[key] = obj
    return result


def export_with_schema(om, store_path):
    """带 schema 的表（ability 等）"""
    try:
        schema = core.load_ability_schema(store_path)
        names = core.schema_names(schema)
    except FileNotFoundError:
        return export_csv_table(om)

    result = {}
    for key, row_bytes in zip(om.keys, om.rows):
        text = row_bytes.decode("utf-8") if row_bytes else ""
        rows = core.read_csv_lines(text)
        if not rows:
            result[key] = {}
            continue
        # ability 表可能有多行
        row_list = []
        for row in rows:
            row_dict = {}
            for i, name in enumerate(names):
                if i < len(row):
                    val = row[i]
                    if val and val != "(None)" and val != "":
                        try:
                            val = float(val) if "." in val else int(val)
                        except ValueError:
                            pass
                    row_dict[name] = val
            row_list.append(row_dict)
        result[key] = row_list[0] if len(row_list) == 1 else row_list
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="mod-tools/PathList.csv")
    parser.add_argument("--store", default="wf-store-fresh/production/upload")
    parser.add_argument("--out", default="assets_exported")
    args = parser.parse_args()

    store_path = Path(args.store)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(args.csv, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    valid = [r for r in rows if r["存储位置"] and r["键数"].strip()]
    print(f"有效表: {len(valid)} / {len(rows)}")
    print(f"输出: {out_dir.absolute()}\n")

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

    ok = sum(1 for r in results if r["status"] == "ok")
    fail = sum(1 for r in results if r["status"] == "error")
    print(f"\n完成: {ok} 成功, {fail} 失败")
    print(f"输出: {out_dir.absolute()}")


if __name__ == "__main__":
    main()
