#!/usr/bin/env python3
# 从 docs/邮件附件对照表.xlsx 第3页(装备对照表)生成 assets/equipment_ids.json
# 用法: python3 scripts/gen_equipment_ids.py
# 依赖: openpyxl
import openpyxl, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # starpoint-cn/
XLSX = os.path.join(ROOT, "..", "docs", "邮件附件对照表.xlsx")
OUT = os.path.join(ROOT, "assets", "equipment_ids.json")


def col_ints(ws):
    out = []
    for row in ws.iter_rows(values_only=True):
        if not row:
            continue
        v = row[0]
        if v is None:
            continue
        s = str(v).strip()
        if s.isdigit():
            out.append(int(s))
    return out


def main():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    equip = sorted(set(col_ints(wb["装备对照表"])))
    with open(OUT, "w") as f:
        json.dump(equip, f, ensure_ascii=False)
    print(f"wrote {len(equip)} equipment ids -> {OUT}")


if __name__ == "__main__":
    main()
