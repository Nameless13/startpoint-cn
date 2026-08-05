# 深渊塔：外部引用 Boss 身份锁热修设计

## 目标

在当前阶段上机验收前，封死 `shark`（背鳍三兄弟）与
`haniwa_great_wind*`（旋风巨土俑）仍可被 HP 伸缩或混搭改名的旁路。
这是一条机制完整性热修，不扩展下一批玩家增益/减益功能。

## 已确认根因

`general_funnel.c32=damage_share_target_boss_id` 与运行时 Boss 的实际 master id
按字符串相等绑定。`shark_blue/red/brown` 仍指向 `shark`；若 HP 伸缩把本体克隆为
`mod_rogue_bossN`，绑定静默失败，三只鳍受到的伤害不再传给本体。

现有 `caster_carrier_block()` 只保护法阵/条件载体克隆，纯 `boss_level.c2` HP 克隆
没有调用该门禁。旧 `mix_pick()` 也只在随机路径依赖 transplant 白名单；显式
`pin_terrain` 可绕过原味回退。

## 裁定

把 `code_referenced_bosses()["hard"]` 命中的 Boss 定义为 **identity-locked**：

1. 不得改 master id，不得创建 `mod_rogue_bossN` HP 克隆。
2. 不得移出原生 field/zone/terrain；随机抽取回退原味，异地显式 pin 响亮失败。
3. HP 通道只允许保持原 id 的现有 c86 微调窗口；达不到当前目标带就拒绝该候选并
   重抽，不以破坏机制换取数值命中，也不放宽既定 c86 合同。
4. 纯 HP 克隆函数自身再做一次 fail-closed 防御，防止未来新调用点绕过候选过滤。
5. 日志必须写明 boss 代号与 `identity-locked` 原因；不得静默摘掉机制或暗换显式 pin。

这意味着当前阶段优先保证“不会生成打不死的背鳍三兄弟/巨土俑”。若它们的原生 HP
无法满足全程地狱目标，本轮成品塔会改抽其他 Boss；为这些 Boss 复制完整 funnel/action
依赖并恢复任意 HP 伸缩，属于后续 bundle realization，不在本热修冒险实现。

## 验收

- RED 证明纯 HP clone 仍会接受 hard-ref Boss，异地 `pin_terrain` 仍可绕过。
- GREEN 后 `shark`/`haniwa_great_wind*` 不能进入 HP clone，且异地 pin 明确失败。
- 原生、不改名路径仍保留官方 action（含 `boss_shark$ea1`）与 FUNNEL 锚点。
- 现有 focused、`test_rogue_chain_gate` 254 项及全量 337 项不新增回归。
- dry-run/最终检查明确证明没有 hard-ref source 被写成 `mod_rogue_bossN`。
- 上机发布前用精确表白名单与前后哈希保护角色、武器、其 DSL/资源；发现同表交叉即停止。

