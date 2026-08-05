# 深渊塔：外部引用 Boss 身份锁热修实施计划

**设计：** `docs/superpowers/specs/2026-08-05-rogue-identity-locked-boss-hotfix-design.md`

## Task 1：钉死真实旁路

- 扩写既有测试方法（保持发现数 337），分别覆盖：
  - hard-ref Boss 的纯 `boss_level` HP clone 必须拒绝；
  - HP 候选评价不得把 identity-locked general 当作可克隆候选；
  - `pin_boss + 异地 pin_terrain` 必须响亮失败且不留下部分 field/zone；
  - 原生回退保持 Boss 代号与官方 action/FUNNEL 需求。
- 先运行并记录预期 RED。

## Task 2：最小实现

- 从 `code_referenced_bosses()["hard"]` 派生统一身份锁判据。
- 在 HP strategy、`make_caster_boss()` 与 `mix_pick()` 三层 fail closed。
- 保持 c86 既定窗口，不新增无先例的大倍率。
- 运行 focused GREEN、254 链路与全量 337。

## Task 3：隔离构建与上机前门禁

- 记录当前角色、武器、DSL、资源和 `sync_pending.json` 的哈希/状态。
- 只生成深渊塔精确表清单；不使用宽泛发布或目录扫描收集输入。
- 先 dry-run、31/31、hard-ref clone 审计；任何同表交叉或哈希漂移立即停止。
- 只有门禁全绿后才执行必要的塔表写入/发布/设备验收；下一批功能保持暂停。

## Task 4：报告

- 写 `mod-tools/work/codex_out/REPORT-identity-locked-boss-hotfix-and-device.md`。
- 分开报告代码证明、store/readback、CDN/设备下发和真机战斗结果；未完成项不得冒充通过。

