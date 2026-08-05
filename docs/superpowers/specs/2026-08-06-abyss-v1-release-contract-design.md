# 深渊武器 v1 历史发布契约解耦设计

日期：2026-08-06
目标分支：`codex/pr2-abyss-release-contract`（基于 PR #2 head `9619768d`）

## 1. 背景与根因

`assets/asset-patch/active/pinball-1.4.105-1.4.106-1-abyssbalance0718.zip`
是 2026-07-18 已发布且启用的历史边，SHA-256 固定为
`e9ec4451ac5b3101f060c74278fd8901b7c207c57f19e313084ff9f9639f7272`。

`mod-tools/tests/test_abyss_weapon_release_patch.py` 当前使用可变的
`wf_rogue_rewards.WEAPONS` 重建该历史包。提交 `3e5ae0d` 有意把当前开发态升级为
深渊武器 v3.3：15 个名字增加 `深渊·` 前缀、能力魂从 33 行重做到 71 行，并把
15 组 `equipment_status` 曲线按 `3/2` 调整。上述开发态尚未进入公开 CDN 链，因而
“当前生成器 == 7 月 18 日历史包”的断言必然失败。

这不是当前生成器自身失效。其聚焦测试 49/49 通过；失败来自历史发布验证错误依赖了
会继续演进的开发源。

## 2. 已批准的取舍

采用“冻结历史 v1 发布契约”方案：

1. 已发布的 `1.4.105 -> 1.4.106` ZIP、manifest、版本和哈希保持逐字节不变。
2. 历史构建器只读取不可变 v1 契约，不再从当前 `wf_rogue_rewards.WEAPONS` 取发布内容。
3. 当前 v3.3 在独立状态文件中显式标记为 `pending`，且没有发布 artifact；历史 v1
   契约本身不承载会变化的“当前状态”。
4. v3.3 将来只能从当时的有效链尾创建新的追加边或 Overlay；本改动不执行该发布。

拒绝以下做法：

- 覆盖或重新命名已有 `1.4.105 -> 1.4.106` ZIP；这会造成缓存和安装血统分裂。
- 只改测试期望、删除漂移断言或只回退 `深渊·` 前缀；能力魂和基础曲线仍会不一致。
- 直接复用当前历史 builder 发布 v3.3；它基于旧 bridge，且三成员输出不包含
  `equipment_status`，会形成半套更新或回滚后续数据。

## 3. 文件边界

计划修改范围：

- 新增 `mod-tools/release-contracts/abyss_weapon_balance_v1.json`
- 新增 `mod-tools/release-contracts/abyss_weapon_current.json`
- 修改 `mod-tools/build_abyss_weapon_balance_patch.py`
- 修改 `mod-tools/tests/test_abyss_weapon_release_patch.py`

明确不修改：

- `mod-tools/wf_rogue_rewards.py` 及其玩法数值
- `assets/asset-patch/manifest.json`
- `assets/asset-patch/active/*.zip`
- `assets/*.json`、store、`.cdn/`、玩家存档和服务端路由
- PR #2 现有的 rogue fixture、合法性拆分和 lockfile 修复

## 4. v1 契约格式

`abyss_weapon_balance_v1.json` 使用 schema 1，包含三部分：

- `schema_version` 固定为整数 `1`。
- `published` 固定记录 `abyss-weapon-balance-v1`、状态 `published`、
  `1.4.105 -> 1.4.106`、archive 文件名及其完整 SHA-256；同时记录完整 equipment
  与 ability_soul 有序节点的 canonical SHA-256 和键序 SHA-256。
- `custom_ids` 完整列出 `8000101` 至 `8000115`；`payload_rows.equipment` 和
  `payload_rows.ability_soul` 分别保存这 15 个键在 v1 archive 中的完整 CSV 叶子。

`payload_rows` 只冻结 15 个自制 ID 的已发布叶子；非自制 equipment 行仍来自钉死的
`1.4.102` bridge，非自制 ability_soul 行仍来自已校验的官方 canonical baseline。
这样既保留历史包可重建性，也避免复制完整官方表。

加载时失败关闭，必须验证：

- schema、发布 ID、版本、archive 名和 SHA-256 与代码钉死值一致；
- `custom_ids` 恰好为 `8000101..8000115`，无重复；
- equipment 与 ability_soul 的键集都与 `custom_ids` 完全一致；
- 所有叶子均为可解析的非空 CSV 字符串；
- 契约内 canonical SHA-256 和键序 SHA-256 均为 64 位小写十六进制；
- builder 重建结果匹配契约内的完整有序节点与键序摘要。

builder 加载和重建不读取现存历史 archive，因此 archive 缺失或损坏时仍可从 bridge、官方
baseline 与 v1 契约重建。仓库回归测试才读取现存 archive，并额外验证每个冻结叶子逐项相等、
完整键序相等、archive 与契约的顺序敏感 canonical SHA-256 相等。

`abyss_weapon_current.json` 是独立、可演进的状态标记，使用 schema 1，记录：

- `id` 为 `abyss-weapons-v3.3`；
- `status` 为 `pending`；
- `source` 为 `mod-tools/wf_rogue_rewards.py`；
- `source_revision` 为引入这套内容的完整提交 `3e5ae0d532ce5179f5e8254afb900e5b61c55869`；
- `semantic_sha256` 绑定当前生成器为 15 个 ID 产生的 equipment、equipment_status、
  ability_soul 三表有序语义；
- `artifact` 为 JSON `null`。

`semantic_sha256` 的输入固定为下列字段顺序的嵌套有序节点，再调用 builder 的
`canonical_node_sha256`（该函数对节点类型、键和值写入类型标签和长度 framing）：

1. `equipment`：按 `custom_ids` 顺序保存 15 个叶子；
2. `equipment_status`：按相同顺序保存 15 个嵌套状态节点；
3. `ability_soul`：按相同顺序保存 15 个叶子。

未来正式发布 v3.3 时，状态侧只迁移该文件并新增 v3.3 发布契约；发布流程仍须新增
artifact 和 manifest/Overlay 链登记，不回写或改造 v1 契约。

## 5. 构建数据流

历史 builder 的输入和安全门禁保持不变：bridge SHA、官方 ability_soul canonical SHA、
官方 `equipment_enhancement_ability` SHA 都继续验证。

重建过程改为：

1. 读取并校验 v1 契约；历史 builder 不读取当前状态文件。
2. 从 bridge 解析 equipment 表，将 15 个 v1 equipment 叶子按原键覆盖。
3. 从官方 ability_soul baseline 起步，按固定 ID 顺序追加 15 个 v1 soul 叶子。
4. 保持非自制 equipment 行及顺序不变；移除 15 个 soul 叶子后必须恢复官方 baseline。
5. 对完整 equipment/ability_soul 比较契约内的键序和顺序敏感 canonical digest，不读取
   现存历史 archive。
6. 继续生成相同的三个成员：equipment、ability_soul、官方 WAB。

历史 builder 不再导入或调用当前 `wf_rogue_rewards`；该模块不可导入时，历史 builder 仍须
能够加载并重建 v1。当前生成器如何增删词条、改名或调整基础曲线，都不会改变 v1 重建结果。

## 6. TDD 与验收

先新增回归测试并确认 RED：

1. 临时把当前 `rewards.WEAPONS` 替换为空集合后重建历史包；旧实现会丢失 15 个自制行
   并在语义对比处失败。
2. 在子进程中把 `wf_rogue_rewards` 标记为不可导入，再加载历史 builder；旧实现会导入失败。

这两项捕获的真实缺陷是“历史发布结果依赖当前生成器的数据或模块存在”，不是检查源码文字。

最小实现完成后必须满足：

1. 仓库内历史 archive 的 size、SHA、成员顺序和 ZIP 元数据逐字节不变。
2. 从冻结 v1 契约重建的 equipment/ability_soul 与 archive 的完整键序一致，顺序敏感
   canonical digest 相同；不同 zlib 实现下不要求重建 ZIP 与仓库 archive 字节 SHA 相同。
3. 改变当前 `WEAPONS` 不影响历史重建。
4. `wf_rogue_rewards` 不可导入时，历史 builder 仍可加载并重建。
5. 独立状态文件将 v3.3 明确标记为 pending 且无 artifact，其 semantic SHA-256 与当前
   15 个 ID 的 equipment、equipment_status、ability_soul 输出一致。
6. `test_rogue_rewards.py` 仍保持当前 v3.3 的 49 项测试通过。
7. 不产生或改写任何 ZIP、manifest、store、`.cdn` 文件。

聚焦验证：

```powershell
python -m unittest mod-tools/tests/test_abyss_weapon_release_patch.py
python -m unittest mod-tools/tests/test_rogue_rewards.py
```

工程验证：

```powershell
python -m unittest discover -s mod-tools/tests -p "test_*.py"
npm run verify
npm run test:launcher
npm run test:hygiene
npm run check:hygiene
git diff --check
```

本机长路径 worktree 的完整 Python 基线另有两个
`test_prepare_and_accept_resume_across_fresh_services_with_clean_baseline_and_qa_probe`
WinError 3；GitHub Actions 同一 PR head
没有这两个错误。它们按环境差异单独报告，不纳入本修复，也不能掩盖目标测试结果。

## 7. 提交与发布边界

实现按两个小提交组织：

1. `docs(mod-tools): define frozen abyss v1 release contract`
2. `fix(mod-tools): decouple abyss v1 release from current generator`

第二个提交只包含两个契约/状态文件、builder 和测试。完成本地验证后，先审查 diff 与泄漏/卫生结果；
只有在更新 PR #2 分支后才重新查看 GitHub Actions。整个流程不执行游戏内容发布。
