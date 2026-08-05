# 深渊连战塔：叠层抗性、官方素材采集与高机动名单设计

## 目标

在不写 store、不发布、不改 `assets/` 的前提下：

1. 将终始之龙使用的可累计 `CreateCondition` 结构做成连战塔诅咒素材；
2. 提供任意 boss ESDL/action DSL 的只读素材采集器；
3. 为作者维护的高机动 boss 名单增加统一难度门禁。

## 已核实的官方行为

- 终始之龙不是把“90”直接写成当前层数，而是连续执行 90 次相同的
  `CreateCondition`。每次 magnification=1，AdditionalConditionKind 的
  `maxAccumulation=99`；相同条件 ID 在 `ConditionSlot` 中累计成可见层数。
- 四种伤害类型每层强度 0.01，总减伤为 `layers * 1%`，上限排程 90 层。
- `ACToleranceOfDebuff` 每层强度 1。客户端先把同条件的强度乘层数后相加，
  再按 `hitRate - debuffResistance` 判命中。随机数包含 0，因此单层 r=1 对
  hitRate=1 仍约有十万分之一漏过；排程最低 20 层时命中率会被减 2000 个百分点。
  `forceApply` 始终绕过这条耐性。
- 官方条件均 `cancelable=false`。普通驱散不会逐层削减；终始之龙的阶段动作是
  `DCAll(... cancelableKind=2)` 强制清空后，再重建为 90/70/30/1 层。
  通用 general boss 只有 c109 pre_action，没有这套阶段状态机。因此本次词条只承诺
  “官方累计层 + 可见层数 + 对应总减伤”，不虚构“玩家可逐层驱散”。
- `debuff_delete` 中的 `ACToleranceOfElement(ALL=254, -2)` 与
  `ACAttackPoint(-2)` 通过 `FindAllSubjects` 落在阶段选中的目标上。它是官方素材卡，
  但脱离原 boss 触发器后不能被诚实地称作“削完层数后的奖励窗口”；本次纳入采集输出，
  不把它无条件挂进塔的 pre_action。

## 诅咒数据模型

新增 `stacked_resistance` 条目，单项为：

```text
(AdditionalConditionKind 构造名, 单层强度, 层数)
```

运行时不会合并成一条大数值条件，而是生成 `layers` 个与官方同形的
`CreateCondition` 命令。层数排程为：前 20% 20 层、中段 50 层、最后 20% 90 层。

随机池提供两种中文词条：

- `层叠龙鳞`：四种伤害类型中随机一种，每层 0.01；
- `不屈龙心`：`ACToleranceOfDebuff`，每层 1。

一次性高强度墙保留。浅层禁用“绝对壁垒/三重壁垒”这类完全免疫词条；深层允许其与
叠层词条同池。可解性判断会把叠层的 `strength * layers` 与一次性伤害抗性相加后再判，
避免组合后四种伤害类型全部封死。

## DSL 与载体

- 叠层条件沿用官方参数：自身 `subject=-17`、`maxAccumulation=99`、
  `cancelable=false`、CreateCondition 的同帧重复开关为 true、目标种类 3。
  该 true 位用于跳过相同命令的 hash 去重，并不是 `isEternal`。
- 与现有一次性伤害/属性抗性共用一个 c109 pre_action 程序和 c110 rerun。
- 工坊显式钉选叠层词条时，HP 重排优先保留可挂 c109 的 general boss 载体；
  若没有合格载体，必须记录拒绝/降级，不能留下虚假文案。

## 采集器

`wf_boss_buff_harvest.py`：

- 接受 boss 代号、可选等级、显式 ESDL 路径与 store 根；
- ESDL 固定读取 `.esdl.amf3.deflate`，action 固定读取
  `.action.dsl.amf3.deflate`；
- 从 ESDL 中发现 action 前缀和动作名，逐个探测真实存在的 action；
- 输出按完整构造参数、subject、cancelable、`allow_same_frame_reapply`、target kind
  等字段归一化去重的素材卡 JSON，并保留每个动作中的出现次数；
- stdout 与显式输出文件都固定为 UTF-8；实采终始之龙得到 11 张参数唯一素材卡，
  其中 `ACAttackPoint(-1)` 与 `ACAttackPoint(-2)` 不能错误合并为一张；
- 默认输出 stdout，`--output` 才写文件。

## 高机动名单

`rogue_special_bosses.json` 新增独立前缀列表 `high_mobility`，首项
`guardian_golem`。不能复用 `authentic_prefixes`，因为原味移植安全与数值降难是两种语义。

最终 HP 重排完成后、clone 改名前，在实际 `pick["bosses"]` 上判定。命中时：

- 所有时限词条禁用；
- 元素抗性合并后 `r >= 99` 的高档墙禁用；
- 最终诅咒 HP 乘数不得超过 1.5。

随机、组合、forced、refill 与最终落表必须共用同一门禁，并在主循环做一次后置断言。

## 验证

- 合成 fixture 验证采集器识别双扩展名、动作发现、归一化与负值素材；
- 单测验证官方形状的重复节点数、DSL 往返、层数文案、深度排程与跨族可解性；
- 单测验证高机动 loader、guardian 前缀、三类禁用与 forced 明确 redraw；
- 打印至少一棵生成的叠层 DSL 自查；
- rogue 全量测试不超过既有 `failures=7 errors=30`，并跑 dry-run / `--check`。
