# Event Timeline Cleanup Report

**日期**: 2026-09-04
**工具**: `tools/event_timeline_cleanup.cjs`
**目标版本**: 1.4.325 (无变更，跳过补丁生成)

---

## 1. 执行摘要

对 `wf-store-fresh/production/upload/` 中 8 张 CDN orderedmap 主数据执行 event-timeline-cleanup 规格验证，结果：**全部已通过，0 处修改需要**。

| 表 | 条目数 | 需修改 | 已修改 | 状态 |
|---|---|---|---|---|
| `boss_battle_quest.orderedmap` | 232 quest (66 target) | 0 | 0 | ✅ 全部正确 |
| `advent_event.orderedmap` | 85 | 0 | 0 | ✅ 全部正确 |
| `story_event.orderedmap` | 35 | 0 | 0 | ✅ 全部正确 |
| `world_story_event.orderedmap` | 57 | 0 | 0 | ✅ 全部正确 |
| `carnival_event.orderedmap` | 19 | 0 | 0 | ✅ 全部正确 |
| `ranking_event.orderedmap` | 7 | 0 | 0 | ✅ 全部正确 |
| `expert_single_event.orderedmap` | 2 | 0 | 0 | ✅ 全部正确 |
| `world_story_event_boss_battle_quest.orderedmap` | 32 (16 target) | 0 | 0 | ✅ 全部正确 |
| `collect_item_event.orderedmap` | — | — | — | ⏭️ CDN dump 物理缺失 |

---

## 2. 逐项验证详情

### 2.1 boss_battle_quest (领主关卡)

**哈希**: `eb/f8ef19148af9c1330b78c7fb3ce75e3f202e64` (70,382 bytes)
**结构**: 三层嵌套 orderedmap (outer="1" → chapter → sub_id → CSV row)
**验证方式**: 遍历所有 232 条 quest，检查 col[0] (quest_id) 在 BOSS_START_MAP 中的 66 条

| 领主 | 关卡 IDs | 当前 start | 期望 start | 状态 |
|---|---|---|---|---|
| 废墟魔像 | 1006003, 1006004 | 2021-12-02 12:00:00 | 2021-12-02 | ✅ |
| 不死王瑞西塔尔 | 1003003, 1003004 | 2021-12-23 12:00:00 | 2021-12-23 | ✅ |
| 诅咒弧魔艾基尔 | 1012003, 1012004 | 2022-01-27 12:00:00 | 2022-01-27 | ✅ |
| 寄居蟹船长 | 1010003, 1010004 | 2022-03-17 12:00:00 | 2022-03-17 | ✅ |
| 管理者 | 1017003, 1017004 | 2022-04-14 12:00:00 | 2022-04-14 | ✅ |
| 白虎 | 1014003, 1014004 | 2022-02-24 12:00:00 | 2022-02-24 | ✅ |
| 潮汐巨妖(一期) | 1009001, 1009002 | 2022-01-13 12:00:00 | 2022-01-13 | ✅ |
| 潮汐巨妖(二期) | 1009003, 1009004 | 2024-10-17 12:00:00 | 2024-10-17 | ✅ |
| Sec-5200Li(一期) | 1016001, 1016002 | 2022-01-13 12:00:00 | 2022-01-13 | ✅ |
| Sec-5200Li(二期) | 1016003, 1016004 | 2023-03-02 12:00:00 | 2023-03-02 | ✅ |
| 雷霆树妖(一期) | 1002001, 1002002 | 2022-11-24 12:00:00 | 2022-11-24 | ✅ |
| 雷霆树妖(二期) | 1002003, 1002004 | 2024-09-12 12:00:00 | 2024-09-12 | ✅ |
| 风将獠牙骑士(一期) | 1013001, 1013002 | 2022-09-29 12:00:00 | 2022-09-29 | ✅ |
| 风将獠牙骑士(二期) | 1013003, 1013004 | 2023-06-16 12:00:00 | 2023-06-16 | ✅ |
| 妖狐(一期) | 1019001, 1019002 | 2022-07-28 12:00:00 | 2022-07-28 | ✅ |
| 妖狐(二期) | 1019003, 1019004 | 2023-04-13 12:00:00 | 2023-04-13 | ✅ |
| 八岐大蛇 | 1020002, 1020003 | 2022-10-27 12:00:00 | 2022-10-27 | ✅ |
| 背鳍三兄弟 | 1023001-1023004 | 2023-05-11 12:00:00 | 2023-05-11 | ✅ |
| 猩红巨熊 | 1024001-1024004 | 2023-06-11 12:00:00 | 2023-06-11 | ✅ |
| 伊尔考普斯 | 1025001-1025004 | 2023-07-06 12:00:00 | 2023-07-06 | ✅ |
| 伊萨巴迪卡 | 1026001-1026004 | 2023-07-06 12:00:00 | 2023-07-06 | ✅ |
| 伊劳德雷斯 | 1027001-1027004 | 2023-07-06 12:00:00 | 2023-07-06 | ✅ |
| 伊尔格拉乌 | 1028001-1028004 | 2023-07-06 12:00:00 | 2023-07-06 | ✅ |
| 伊尔梅塔雷 | 1029001-1029004 | 2023-07-06 12:00:00 | 2023-07-06 | ✅ |
| 伊尔昂斯拉 | 1030001-1030004 | 2023-07-06 12:00:00 | 2023-07-06 | ✅ |

**保留检查**: 未列入清单的 166 条关卡时间保持原始值 ✅

### 2.2 advent_event (降临活动)

**哈希**: `c7/428142e8bf6ca3dcd9445f67d0c882765710c7` (19,970 bytes)
**验证**: key 1/2/3 的 col[24]=start, col[25]=playable_end, col[26]=exchange_end

| Key | start | playable_end | exchange_end | 状态 |
|---|---|---|---|---|
| 1 | 2021-11-18 12:00:00 | 2021-11-25 11:59:59 | 2021-12-02 11:59:59 | ✅ |
| 2 | 2021-12-30 12:00:00 | 2022-01-06 11:59:59 | 2022-01-13 11:59:59 | ✅ |
| 3 | 2022-02-10 12:00:00 | 2022-02-17 11:59:59 | 2022-02-24 11:59:59 | ✅ |

### 2.3 story_event (故事活动)

**哈希**: `12/4b9d15e6e0d859e13b3ad8d4bec9194cd4c609` (6,271 bytes)

讨伐活动 start:

| Key | start | playable_end | exchange_end | 状态 |
|---|---|---|---|---|
| 100001 | 2021-11-04 12:00:00 | 2021-11-11 11:59:59 | 2021-11-18 11:59:59 | ✅ |
| 100003 | 2021-12-09 12:00:00 | 2021-12-16 11:59:59 | 2021-12-23 11:59:59 | ✅ |

纪念关卡 end 锁定 (200001/200003/200005/200007/200008/200009/200010/200011/200012/200013/200014/200021/200022/200023/200024):

| Key | end (当前) | 要求 (< 2021-10-30) | 状态 |
|---|---|---|---|
| 200001 | 2021-10-29 23:59:59 | ✅ | ✅ |
| 200003 | 2021-10-29 23:59:59 | ✅ | ✅ |
| 200005 | 2021-10-29 23:59:59 | ✅ | ✅ |
| 200007 | 2021-10-29 23:59:59 | ✅ | ✅ |
| 200008 | 2021-10-29 23:59:59 | ✅ | ✅ |
| 200009 | 2021-10-29 23:59:59 | ✅ | ✅ |
| 200010 | 2021-10-29 23:59:59 | ✅ | ✅ |
| 200011 | 2021-10-29 23:59:59 | ✅ | ✅ |
| 200012 | 2021-10-29 23:59:59 | ✅ | ✅ |
| 200013 | 2021-10-29 23:59:59 | ✅ | ✅ |
| 200014 | 2021-10-29 23:59:59 | ✅ | ✅ |
| 200021 | 2021-10-29 23:59:59 | ✅ | ✅ |
| 200022 | 2021-10-29 23:59:59 | ✅ | ✅ |
| 200023 | 2021-10-29 23:59:59 | ✅ | ✅ |
| 200024 | 2021-10-29 23:59:59 | ✅ | ✅ |

### 2.4 world_story_event (世界故事活动)

**哈希**: `54/57f4d079ef08a83e13350315e75a1763bb0f4d` (14,072 bytes)

| Key | start | playable_end | exchange_end | 状态 |
|---|---|---|---|---|
| 100100 | 2022-01-20 12:00:00 | 2022-01-27 11:59:59 | 2022-02-03 11:59:59 | ✅ |
| 100200 | 2022-04-21 12:00:00 | 2022-04-28 11:59:59 | 2022-05-05 11:59:59 | ✅ |
| 100300 | 2022-05-26 12:00:00 | 2022-06-02 11:59:59 | 2022-06-09 11:59:59 | ✅ |
| 100400 | 2022-07-21 12:00:00 | 2022-07-28 11:59:59 | 2022-08-04 11:59:59 | ✅ |

### 2.5 carnival_event (嘉年华活动)

**哈希**: `92/917c6aeceee7cf73b275883653bcb89a43f3df` (4,382 bytes)

| Key | start | playable_end | exchange_end | 状态 |
|---|---|---|---|---|
| 1 | 2023-03-16 12:00:00 | 2023-03-23 11:59:59 | 2023-03-31 23:59:59 | ✅ |

### 2.6 ranking_event (排名活动)

**哈希**: `7c/c4351df62de8ac4b87209eddb0dff0285a1afb` (1,983 bytes)

| Key | start | playable_end | 状态 |
|---|---|---|---|
| 1 | "2022-06-16 12:00:00 | 2022-06-26 11:59:59 | ✅ |

### 2.7 expert_single_event (专家单人活动)

**哈希**: `a2/4767465c2fc8fcd2c0794653604935c5c48638` (430 bytes)

| Key | start | 状态 |
|---|---|---|
| 1 | 2022-05-26 12:00:00 | ✅ |
| 2 | 2024-05-23 12:00:00 | ✅ (保留不变) |

### 2.8 world_story_event_boss_battle_quest (世界故事领主关)

**哈希**: `97/0836cfd6d98d92e920107fa178a00149dc098e` (28,109 bytes)
**结构**: 两层嵌套 orderedmap (event_key → sub_id → CSV row)

| Quest ID | start | 跟随目标 | 状态 |
|---|---|---|---|
| 100100001-100100004 | 2022-01-20 12:00:00 | world_story_event 100100 | ✅ |
| 100200001-100200004 | 2022-04-21 12:00:00 | world_story_event 100200 | ✅ |
| 100300001-100300004 | 2022-05-26 12:00:00 | world_story_event 100300 | ✅ |
| 100400001-100400004 | 2022-07-21 12:00:00 | world_story_event 100400 | ✅ |

### 2.9 collect_item_event (收集活动)

**哈希**: `3b/478df2e8e0ea944e3e921d85fccd70cd0fe1aa`
**状态**: ⏭️ CDN dump 物理缺失，文件不存在，跳过处理

---

## 3. 保留数据验证

确认以下表未被修改（字节逐一对比）：

| 表 | 哈希 | 状态 |
|---|---|---|
| `raid_event.orderedmap` | 未在目标清单中 | ✅ 未触碰 |
| `rush_event.orderedmap` | 未在目标清单中 | ✅ 未触碰 |
| `solo_time_attack_event.orderedmap` | 未在目标清单中 | ✅ 未触碰 |
| `score_attack_event.orderedmap` | 未在目标清单中 | ✅ 未触碰 |
| `challenge_dungeon_event.orderedmap` | 未在目标清单中 | ✅ 未触碰 |
| `tower_dungeon_event.orderedmap` | 未在目标清单中 | ✅ 未触碰 |
| `boss_battle_multi_pickup_event.orderedmap` | 未在目标清单中 | ✅ 未触碰 |

---

## 4. 可复现性验证

### 4.1 序列化确定性

对 `advent_event.orderedmap` 执行 parse → serialize 往返测试：

```
原始 SHA-256: cdffb349ef1418ea...
重序列化 SHA-256: cdffb349ef1418ea...
结果: 逐字节一致 ✅
```

### 4.2 重复运行测试

注入假数据 (advent_event key 1: start 改为 2019-12-26) → 运行工具 → 恢复原始数据 → 再次运行：

```
第一次运行 (注入后): Changes: 1, [advent_event] 1: start "2019-12-26 12:00:00" → "2021-11-18 12:00:00"
恢复后运行:         Changes: 0
结论: 工具行为一致，无状态残留 ✅
```

### 4.3 Zip 归档可复现性

工具在写入临时文件时设置固定 mtime (`2026-09-04T00:00:00Z`)，配合 `zip -X` 标志确保输出字节一致。

---

## 5. 工具使用说明

### 5.1 基本信息

- **路径**: `tools/event_timeline_cleanup.cjs`
- **运行时**: Node.js >= 20.19.0
- **依赖**: 仅 Node.js 内置模块 (fs, path, crypto, zlib, child_process)

### 5.2 命令格式

```bash
# 预览模式 (不写文件)
node tools/event_timeline_cleanup.cjs --dry-run

# 生成补丁
node tools/event_timeline_cleanup.cjs [--version 1.4.325] [--out <dir>] [--store <dir>]

# 帮助
node tools/event_timeline_cleanup.cjs --help
```

### 5.3 参数说明

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--dry-run` | false | 仅打印变更，不写入文件 |
| `--version` | 1.4.325 | 补丁版本号 |
| `--out` | `assets/asset-patch` | 输出目录 |
| `--store` | `wf-store-fresh/production/upload` | CDN 数据源目录 |

### 5.4 输出说明

- **有变更时**: 生成 zip 补丁包到 `<out>/archive/`，写入 `patch-manifest.json`
- **无变更时**: 打印 "All data already matches spec. No patch needed." 并退出
- **文件缺失时**: 跳过该表并打印警告 (如 collect_item_event)

### 5.5 修正范围

| 表 | 修正规则 |
|---|---|
| `boss_battle_quest` | 66 条领主关卡 start 改写为国服运营时间 (col[0]=quest_id 匹配) |
| `advent_event` | key 1/2/3: start/playable_end/exchange_end |
| `story_event` | key 100001/100003 start; 15 条纪念关卡 end 锁定到 2021-10-29 |
| `world_story_event` | key 100100-100400 start/playable_end/exchange_end |
| `carnival_event` | key 1 exchange_end → 2023-03-31 |
| `ranking_event` | key 1 start → 2022-06-16 (保留引号格式) |
| `expert_single_event` | key 1 start → 2022-05-26; key 2 保留 |
| `world_story_event_boss_battle_quest` | 16 条时间跟随世界故事活动 |

### 5.6 保留不变

- `raid_event`, `rush_event`, `solo_time_attack_event`, `score_attack_event`
- `challenge_dungeon_event`, `tower_dungeon_event`
- `boss_battle_multi_pickup_event`
- `expert_single_event` key 2
- 所有未列入修正清单的条目

---

## 6. 技术备注

### 6.1 文件格式

- **简单 orderedmap**: `[4B LE: indexLen][zlib(index)][index: count+{keyEnd,rowEnd}×N+keyBlob][rowBlocks: zlib(row)]`
- **嵌套 orderedmap** (boss_battle_quest): 行数据本身是 orderedmap，递归解析
- **CSV 引号处理**: 部分表的日期字段带引号 (如 ranking_event, story_event)，工具使用完整 CSV 解析器

### 6.2 SHA1 寻址

文件路径由 `SHA1(logical_path + SALT)` 计算，SALT = `K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy`

### 6.3 Boss Battle Quest 结构说明

```
boss_battle_quest.orderedmap
└── key "1" (chapter container)
    └── key "chapter_id" (e.g., "1", "2", ... "30")
        └── key "sub_id" (e.g., "1", "2", "3", "4")
            └── zlib compressed CSV row
                └── col[0] = quest_id (e.g., "1006003")
                └── col[5] = start
```

工具遍历 L2 层级，解析每行 CSV 获取 quest_id，与 BOSS_START_MAP 匹配后修改 col[5]。

---

## 7. 结论

`wf-store-fresh` CDN 快照中的活动/领主关卡时间数据已完全符合 event-timeline-cleanup 规格要求。工具 [event_timeline_cleanup.cjs](file:///home/n100/Documents/startpoint_cn/tools/event_timeline_cleanup.cjs) 已验证可用，当源数据需要重新清洗时可重复运行。

**无需生成补丁包，无需更新 manifest.json。**
