# 深渊连战塔：敌方攻击封顶与 high_threat 设计

日期：2026-08-05  
分支：`release/modes-20260714`

## 目标

把最终写入 quest c89/c91 的敌方攻击倍率收敛到常驻约 `1.1`、硬上限 `1.5`，并把行为危险但数值不显眼的 boss 纳入作者维护的 `high_threat` 门禁。

## 数值模型

最终攻击倍率仍由既有乘区产生：

```text
curve(round) × source/normalization × curse.atk
```

`PLAN_TIERS` 的 `st_mult` 继续服务 HP/档位，不再重复乘进攻击倍率。`hell` 的攻击曲线改为平坦 `1.1 → 1.1`。三个攻击词条保留三级台阶，但全部重定档：

| 词条 | 低 | 中 | 高 |
|---|---:|---:|---:|
| 嗜血狂潮 | 1.05 | 1.10 | 1.15 |
| 深渊逆鳞 | 1.10 | 1.20 | 1.30 |
| 玻璃深渊 | 1.20 | 1.30 | 1.40 |

分布目标改为 `median ≤ 1.1 / P90 ≤ 1.35 / max ≤ 1.5`，硬上限适用于全部楼层，不只中后段。

## 禁止静默夹值

`solve_atk()` 只计算当前组成的真实乘积，不再用 `min()` 改写结果。`enforce_atk_band()` 负责显式状态转换：

1. 超标层优先调用 `downgrade_atk_curse()`，按 `2→1→0→摘攻击组件` 下降；血量组件必须保持不变。
2. 诅咒已无攻击组件但 source/normalization 仍把该层推过目标时，显式降低该层 `ba`，记录旧值、目标值和原因，再完整重算。这是可见、可审计的“攻击来源组件降档”，不是返回值夹取。
3. 非有限数、非正值、600 步不收敛或重算后仍超过 `1.5` 时抛出 `RuntimeError`，构建明确失败。
4. `TRUE_DMG_CAP` 继续作为原生攻击尖峰保护；触发时也走同一显式降档路径并写日志。

任何最终 c89/c91 超过 `1.5 + 1e-9` 都是构建错误。c90 的 funnel 缩放只会更低。

## high_threat

`rogue_special_bosses.json` 从旧的前缀数组升级为：

```json
"high_threat": {
  "prefixes": ["guardian_golem"],
  "exact": ["lich_wind_expert_100"]
}
```

配置缺键、类型错误或空字符串必须响亮失败。匹配语义：`prefixes` 用 `startswith`，`exact` 只做完整代号匹配。

命中后沿用既有降难措施：禁时限、禁 `r≥99` 的高档属性墙、诅咒 HP 乘积不超过 `1.5`。另加浅层回避：前 20% 楼层（30 层塔即第 1～6 战）在存在非 high_threat 合格候选时，不选 high_threat；初抽和 HP 重排候选都执行同一规则。显式钉 boss 仍尊重作者硬约束，不暗换。

## 验收

- 31 层与攻击词条全部三级组合经闸门后均 `≤1.5`。
- 闸门日志能证明先降诅咒，再显式降 source/normalization；不得出现“单层夹到”或 600 步兜底夹值。
- 三个词条文案与实际档位同源；`玻璃深渊` 摘攻击后 HP 乘数不变。
- `hell` 攻击端点为 `1.1`，分布闸为 `1.1/1.35/1.5`。
- `guardian_golem*` 与 `lich_wind_expert_100` 命中，`lich_wind_expert_80` 不误命中。
- 浅层有普通候选时 high_threat 不入选；只剩 high_threat 时不伪造候选，走现有明确失败/约束路径。
- 全量 `test_rogue*.py` 精确保持 `337 tests / failures=7 / errors=30`。

## 边界

本批不写 store、不发布、不改 `assets/`、不碰 `sync_pending.json` 或 `wf_dev_catalog.py`，也不推设备。当前脏分支含本任务前置 WIP，因此在原工作区施工，以文件快照生成本批独立 diff，不创建会丢失前置 WIP 的新 worktree。
