# 深渊连战塔：原生 Boss Bundle 与变体选择设计

日期：2026-08-05
状态：A′ 已批复，待按实施计划开发
适用分支：`release/modes-20260714`

## 1. 目标

把连战塔的 boss 候选、混搭、HP 重排和最终克隆统一到一个“原生 Boss Bundle”模型：选择单位不再是一串 boss 代号，而是官方场地中一个可完整复现、可审计、可回退的战斗组合。

本设计必须同时解决以下问题：

- 只读取地形实际激活的 zone layer，不再把未激活 layer 的 boss 算进候选或 HP。
- boss 身份始终是 `(BossKind, code)`，不能只用 code 在多张表的并集中碰运气。
- 抽取顺序固定为 `family → variant → native bundle`，避免某个家族因为变体或场地多而天然加权。
- `--mix`、HP 重排、法阵载体克隆和最终落表共享同一套实现与复核，不允许任一路径绕过兼容性或引用门禁。
- 兼容性必须覆盖 FUNNEL 组与数量、`CUSTOM_POSITION`、由 zone c22 + active slots
  推导出的 BossGroup 拓扑、action closure 和每个 active layer 的槽位形状。
- 随机不兼容时退回选中 boss 的原生 bundle；地形与 boss 双钉冲突时响亮失败。
- 每次实现态变化后都重查引用、HP 和实际 general boss 行的 c36。
- 对 `arch_evil*`、`orochi_ex`、六个只有多人侧实体的代号，以及八岐大蛇 parent + 八头，给出数据驱动且诚实的处理结果。
- `wf_rogue_save.reroll_endless_field()` 与主构建器共用筛后 catalog，不再直接随机 `wf_chain_build.build_pool()`。

## 2. 非目标与写入边界

本设计不改变诅咒数值、攻击上限、奖励、角色、存档结构或 UI schema，也不在本批次写 store、发布 CDN、修改 `assets/`、触碰 `sync_pending.json` 或推送设备。

设计实现后，普通构建仍遵守现有 dry-run / `--write` / `--publish` 分层。Orochi 克隆若需要写 `orochi.orderedmap`，必须进入现有 `written → publish → readback` 链；不能手工编辑账本，也不能只改 store 不补 GUI 发布清单。

## 3. 只读审计基线

2026-08-05 的完整只读扫描得到以下诊断数据：

| 口径 | 数量 | 含义 |
|---|---:|---|
| `wf_chain_build.build_pool()` field | 136 | 旧候选入口可见的 floor field |
| 含 active boss row 的上述 field | 135 | 其中一个 field 没有实际激活 boss |
| 当前塔实际单人侧 code | 86 | 当前生成路径真正覆盖到的单人侧代号 |
| 全库 active native single code | 394 | 只按地形 active layer 统计的官方单人侧代号 |
| 同显示名 family | 123 | 用稳定中文显示名聚合后的家族口径 |
| 当前塔触达 / 完整覆盖 family | 56 / 6 | 现状诊断，不是新设计验收值 |
| native 理论触达 / 完整覆盖 family | 114 / 60 | 尚未经过 C8016、等级、HP、动作兼容等门禁的天花板 |
| 已解析 terrain / 含 active boss field | 1239 / 886 | 全库地形与 active boss 场地规模 |

`114 / 60` 只能称为“门禁前理论上限”。最终报告必须重新从实际筛后 catalog 计算，不能把这个数字写成已实现覆盖率。

审计同时确认了四个现有结构性缺口：

1. `_zone_pick()`、`quest_pool()` 和 `field_gate()` 遍历 zone 全部 row，没有与 terrain 的 `objectgroup.name` 求交。
2. `check_field_chain()` 用 code 是否存在于多表并集来放行；`swap_zone_bosses()` 只换 code，不换前一列 BossKind。
3. `mix_pick()` 只比较实体数和旧 transplant 白名单，没有验证锚点、动作和 layer 形状。
4. `_hp_fit_cache` 只用 `(field, round, target)` 作键；混搭 donor 原地换掉后可复用旧 HP 结论。

## 4. 术语与数据模型

### 4.1 BossRef 与实体槽

单个 boss 引用必须携带 kind，不能退化成裸字符串：

```python
@dataclass(frozen=True)
class BossRef:
    kind: int
    code: str


@dataclass(frozen=True)
class ActiveBossSlot:
    layer: str
    slot: int
    boss_group_kind: int
    single: BossRef | None
    multi: BossRef | None
```

zone 三个实体槽的列对是：

| 槽 | single | multi |
|---|---|---|
| 1 | kind c23 + code c24 | kind c25 + code c26 |
| 2 | kind c27 + code c28 | kind c29 + code c30 |
| 3 | kind c31 + code c32 | kind c33 + code c34 |

塔是单人 event quest，出场、HP 与覆盖率使用 single 引用；但克隆与混搭的最小修改单位是完整实体槽，必须把 donor 的 single 和 multi 两对 `(kind, code)` 一起复制。single/multi 代号不同仍是一只实体，不能计成两只，也不能把 single code 循环写进 multi 侧。

### 4.2 TerrainLayerCaps

```python
@dataclass(frozen=True)
class TerrainLayerCaps:
    layer: str
    boss_slots: tuple[int, ...]
    boss_group_kinds: tuple[int, ...]
    funnel_groups: tuple[tuple[str, int], ...]
    custom_positions: tuple[tuple[str, int], ...]
    boss_groups: tuple[tuple[str, int], ...]
```

该对象描述一个地形 layer 能提供的实际锚点能力。计数必须保留，不能只记“有/无”。解析失败、未知 object 形态、重复 group 语义冲突都必须 fail closed。

### 4.3 NativeBossBundle

```python
@dataclass(frozen=True)
class NativeBossBundle:
    family_id: str
    family_name: str
    variant_id: str
    variant_name: str
    source_field: str
    source_zone: str
    terrain_logical: str
    active_layers: tuple[str, ...]
    slots: tuple[ActiveBossSlot, ...]
    bgm: str | None
    thumbnail: str
    source_category: str
```

bundle 是不可变的官方来源快照。它包含原生 field/zone/terrain、active layers、完整 active zone rows、完整实体槽、BGM 与显示元数据。后续混搭产生 `RealizedBundle`，不能反向修改 catalog 中的 source bundle。

### 4.4 RealizedBundle 与确定性指纹

`RealizedBundle` 保存 boss source bundle、实际采用的 terrain bundle、原本尝试的 target、
实际 field/zone、完整 single/multi slots、选中等级、typed `BossRef -> BossRef` 克隆映射、
native/transplanted 状态，以及实际 condition carrier（没有则为 `None`）。它不能只保存
`list[str]` 或 bool：否则无法在 special/general 同码、双 boss 或最终 c36 复核时知道真实来源。
指纹由 canonical JSON 的 SHA-256 生成，至少包含：

- field、zone、active layer 集合；
- 每个槽的 single/multi `(kind, code)`；
- c22 `boss_group_kind`；
- 选中等级；
- 实际 boss/source row、boss_level row、special parent c24 的摘要；
- terrain capability 与 action requirement 摘要。

禁止使用 Python `hash()` 生成 family、variant 或缓存键；它跨进程不稳定。

## 5. Active layer 是唯一事实源

对每个 field：

1. 从 `field_data[field]` 读取 c1 terrain 资源和 c2 zone key。
2. 读取 `c1 + ".amf3.deflate"`，按 raw-deflate 解压，再由 `wf_dsl.parse_dsl()` 解析 AMF3。
3. 从 terrain 树提取所有 `objectgroup.name`；每个名字必须是唯一的非负整数字符串。
4. 逐个确认 terrain objectgroup 在 `zone[c2]` 存在同名 row，得到
   `active_layers`。客户端 `TerrainParser` 会遍历所有 terrain objectgroup 并用同名 key
   解引用 `ZoneSource`，所以 terrain 多出一个 zone 不存在的 layer 不是“未激活”，而是
   空引用风险，必须 fail closed。
5. 只从 `active_layers` 的 zone row 读取 c22 与三对 boss 槽；反向多出来的 zone row
   没有 terrain objectgroup，不会被客户端激活，必须忽略。

```python
if not set(terrain_group_names) <= set(zone_node):
    reject("TERRAIN_PARSE")
active_layers = tuple(sorted(set(terrain_group_names)))
```

active layer 为空、terrain 缺失、deflate/AMF3 解析失败、terrain layer 缺 zone row、
zone row 异形时，该 field 进入 `TERRAIN_PARSE` 或 `NO_ACTIVE_LAYER`，不得退回“扫描全部
zone row”。重复 `CUSTOM_POSITION` 名是合法锚点集合，`TerrainLayerCaps` 必须保留
`(name, count)`，供后续 exact-one / count 兼容门禁判断，不能压成 set。

`treasure_cave_area` 是必须锁住的反例：zone 有 `0/1/2`，terrain 只激活 layer `0`；`1/2` 里的 boss 不能进入候选、覆盖率或 HP。

## 6. BossKind 与来源表必须精确匹配

客户端 `ZoneValues` 的构造器映射是运行时事实：

| kind | 构造器 / 来源 |
|---:|---|
| 0 | `StandardBoss` → `standard_boss` |
| 1 | `GeneralBoss` → `general_boss` |
| 2 | `Kraken` → `kraken` |
| 3 | `Orochi` → `orochi` |
| 4 | `OrochiEx` → `orochi_ex` |
| 5 | `OrochiExHead` → 客户端 `ZoneSource.as:387-389` 直接 throw，不可作为 active zone boss |
| 6 | `Conductor` → `conductor` |
| 7 | `TouyakirenCeo` → `touyakiren_ceo` |
| 8 | `ConcertedBoss` → 已验证的 general source 路径 |
| 9 | `WaterSphere` → `water_sphere` |
| 10 | `HolySphere` → `holy_sphere` |
| 11 | `WindSphere` → `wind_sphere` |
| 12 | `ThunderSphere` → `thunder_sphere` |
| 13 | `FireSphere` → `fire_sphere` |
| 14 | `WaterSphereCrystal(int)`，不是字符串 code |
| 15 | `WaterSphereMicronucleus(int)`，不是字符串 code |

普通 native bundle 只接受 0–13 中已完成来源解析且不含 kind 5 的 `(kind, code)`。
kind 5 在 active zone 路径会被客户端直接拒绝；14/15 必须有单独的数字实体实现与 HP
证明。本设计第一版对 5/14/15 均以 `SPECIAL_TABLE_UNAUDITED` fail closed。

`validate_boss_ref(ref, level, tables)` 必须同时验证：

- kind 对应的表中存在 code；
- 该来源的等级取档规则可满足实际敌等级；
- 关联 funnel 等级可解析；
- special table 的结构已被该 kind 的审计器支持。

code 即使存在于另一张表也不能救活错误 kind。`swap_zone_bosses()` 的旧“只换 code”接口要被完整槽写入器替代。

## 7. Catalog 构建与三阶段抽取

### 7.1 Catalog 构建

`build_native_bundle_catalog()` 扫描所有官方 field，而不是只复用 `cb.build_pool()` 的旧 bosses 列表。`cb.build_pool()` 仍可提供 floor/BGM 元数据，但不能决定 active boss 或安全性。

每个 bundle 依次经过：

1. terrain 与 active layer 解析；
2. 实体槽形状解析；
3. `(BossKind, code)` 来源与等级门禁；
4. 原生 HP 证据；
5. C8016、特殊表、phase、single 可达性与现有引用门禁；
6. 原生态自验证；
7. action closure 与 terrain requirements 提取，用于判定是否可移植。

前六项失败的条目不从报告消失，而是进入带 reason code 的 rejection 集合。第七项失败不影响原生 field 复用：bundle 仍是 native eligible，并记录 `portable=false`、`native_only_reason=ACTION_CLOSURE_UNAUDITED`；它不能进入 `--mix`，随机抽到时强制使用自己的 native bundle。这样不会因为尚未审完动作闭包而无谓砍掉原生覆盖率。

分批实现边界：Task 2 的 exact-slot reference 只证明 active single 的精确来源、所选等级、Standard ESDL / General boss_level 路径和 active zako；`code_referenced_bosses()` 的 hard/soft 外部代号引用、nested action/spawn 的传递闭包，以及移植后的完整引用复核由 Task 3 承担。Task 2 不得把 source-path 证明描述成完整 transitive reference closure，未完成时统一保留上述 native-only 标记。

### 7.2 Family 与 variant

family 的用户可见名称与身份都优先使用 `wf_boss.boss_names()` 经 NFC、trim 后的完整稳定中文显示名；缺名才退回精确 `(BossKind, code)`。显示名不能按 `/` 拆分，model/action 也不能进入 family payload，否则同一外观会因官方变体不同再次获得多张 family 票。内部 `family_id` 用 canonical JSON + 完整 SHA-256，不用进程随机 hash。

variant 表示同一家族内实际机制、形态或官方难度侧的差异，不表示它在某张 field
里的摆放位置。`variant_id` 使用排序且保留重复实体的机制 multiset：每项至少包含
`(kind, code, model, selected-level action/root signature)`；不得包含 layer、slot、c22、
field、zone 或 terrain。同一机制换 layer/slot 仍是同 variant；这些摆放与地形信息只进入
bundle payload。不同 quest/field 但实体与机制相同，只是同 variant 下的多个 native bundle。

现有“元素变体系列配额”和精选权重可保留，但权重施加在 family 层。任何一条 native field、multi 镜像或八岐大蛇头部 alias 都不能额外增加抽签票数。

### 7.3 抽取顺序

```text
eligible families
  → 按 family 权重选 1 个 family
    → 在该 family 的 eligible variants 中选 1 个 variant
      → 在该 variant 的 eligible native bundles 中选 1 个 bundle
```

三个集合在抽取前都先去重。深度、历史、新鲜度、高威胁、系列配额等筛选必须返回结构化过滤结果；若某 family 筛后为空，从 family 层重抽，不能把它的多个 field 重复塞回列表。

`collapse_grades()` 只收敛已有工具链明确验证为数字难度后缀的 schema（`multi_normal_*`、`multi_variant_*`、`advent_event_discarded_dragon_*`），或同组至少一个 alias 由 advent quest metadata 明确证明的 `advent_*` 难度组；并且还必须是同一 variant、同编号前缀、同 terrain 且 active zone rows / slots / caps 全部相同。前一类按官方数字尾号选最高档；metadata 证明的 advent 组按敌等级选最高档。未知 `*_N` 命名宁可不压，不得把不同 terrain/BGM 的普通剧情关、语义不同的 variant 或同显示名的完整战斗形态压成一个字符串条目。

## 8. 明确排除与 reason code

### 8.1 `arch_evil*`

`arch_evil*` 保持 C8016 硬排除。即使发现 active single field，也必须返回 `C8016`，不能因为新 catalog 更完整而绕过官方元素/色替资源门禁。

### 8.2 `orochi_ex`

`orochi_ex` 的 phase HP 无法通过现有 general c2 或 standard c86 通道完整缩放，第一版返回 `SPECIAL_PHASE_HP_UNSCALABLE`。若 special 表、头部或 phase action 尚未完成结构证明，则用更早命中的 `SPECIAL_TABLE_UNAUDITED`。它不能进入可选 catalog，也不能计入覆盖率分子。

### 8.3 六个只有多人侧的代号

以下六个 code 在全库 active row 中没有任何 single c24/c28/c32 引用：

- `alter_sheep_materia_multi`
- `alter_sheep_materia_multi_80`
- `devil_commander_evil_envy_80`
- `discarded_dragon_wind`
- `mechanic_dragon_eater_multi`
- `mechanic_dragon_eater_multi_80`

它们返回 `NO_SINGLE_FIELD`。判据必须来自 active single 引用的实际缺失，不能按 `_multi` 后缀猜测；后续数据包若新增合法 single field，门禁应自动放行。

### 8.4 Reason code 集合与优先级

至少保留下列稳定 code：

```text
C8016
NO_SINGLE_FIELD
TERRAIN_PARSE
NO_ACTIVE_LAYER
KIND_CODE_MISMATCH
LEVEL
FUNNEL_LEVEL
ACTION_CLOSURE_UNAUDITED
FUNNEL_ANCHOR_MISMATCH
CUSTOM_POSITION_MISSING
BOSS_GROUP_MISMATCH
REFERENCE
HP_UNVERIFIED
SPECIAL_PARENT_ONLY
SPECIAL_TABLE_UNAUDITED
SPECIAL_PHASE_HP_UNSCALABLE
SPECIAL_HP_CHANNEL_UNSUPPORTED
CHAIN
C36
```

同一 bundle 可记录多个细节，但 native rejection 的主 reason 按“无法解析 → 构造器错误 → 明确黑名单 → 等级 → 引用 → HP → c36”的稳定顺序选择，保证报告跨 seed 可比较。动作/锚点失败属于 portability reason；其中 `ACTION_CLOSURE_UNAUDITED` 只形成 native-only 标记，不进入 native rejection 统计。

## 9. 八岐大蛇：parent bundle，而不是八个头的抽签票

### 9.1 三个合法 parent variant

| variant | parent code | native field |
|---|---|---|
| single | `orochi_all_head_single` | `main_6_10_4`、`main_6_10_4ex`、`orochi_all_head_single` |
| multi | `orochi_all_head_multi` | `multi_normal_1_20_1`、`multi_normal_1_20_2` |
| multi_plus | `orochi_all_head_multi_plus` | `multi_normal_1_20_3` |

三个 parent 都实际出现在 active c24，因而可以作为单人塔候选。它们属于一个 family“八岐大蛇”、三个 variant。parent c24 引用的八个头是 bundle 的 reachable members，不是八个独立 family/variant，也不能额外加八张抽签票。

### 9.2 HP 必须展开 parent + 八头

lv100 的只读审计值如下。这些是 `true_stat()[0]` 的 raw 曲线单位，尚未乘等级倍率 K，
也未乘 quest c86：

| variant | parent HP | 八头合计 HP | bundle 总 HP | 旧算法低估 |
|---|---:|---:|---:|---:|
| single | 30,390.36 | 30,390.36 | 60,780.72 | 2.0× |
| multi | 82,053.972 | 82,053.972 | 164,107.944 | 2.0× |
| multi_plus | 82,053.972 | 239,665.97655 | 321,719.94855 | 3.920833× |

`expand_bundle_hp_members()` 要从 parent special row 的 c24 读取八头并保留每个可达实体实例。重复 code 出现在不同实体路径时仍逐实例累加，不能按 code 去重。接口返回
`HpExpansionResult(ok, members, total_hp, selected_parent_level, reason, detail)`；其中
`total_hp` 明确是尚未乘 K/c86 的 raw 总量。这样成功态能携带九实例与总量，失败态也能返回
`SPECIAL_HP_CHANNEL_UNSUPPORTED`，不得用空 tuple 混淆“合法零成员”和“结构未证明”。

Orochi parent 等级档使用客户端 `getSurjectivity` 的第一个 `>= enemy_level` 语义：
`[100]` 可服务 79/80/90/99/100，101 必须拒绝；multi `[49,100]` 在塔等级选择
100。这里只修 kind=3 Orochi adapter，不改其他专用 boss 已有的历史等级规则。

最终 HP 单位必须显式拆开，且 K/c86 各乘一次：

```text
raw_bundle_hp = Σ true_stat(member, hp, selected_level)[0]
pre_c86_hp    = raw_bundle_hp × K[enemy_level]
final_hp      = pre_c86_hp × c86
scale         = target_pre_c86_hp / (raw_bundle_hp × K[enemy_level])
```

Task 2 的旧 `hp_gate(slots, level)` 只保留给普通 kind 0/1/8；Orochi 通过新增的可选
`bundle_hp_gate(bundle, level)` 检查完整 parent bundle。domain catalog 只有在该 gate 返回成功后
才解除 `SPECIAL_HP_CHANNEL_UNSUPPORTED`，随后 Task 3 仍会因 kind 3 action closure 未审而把它标成
native-only；不得伪造 terrain requirements，也不得把它重新变成 native rejection。

### 9.3 per-round clone channel

Orochi 若要参与平坦 HP 曲线，必须一次性克隆完整九实体依赖图：

1. 为该 round 克隆 kind=3 parent 的 `orochi` 选中行与 `boss_level` 叶；父体命名
   `mod_rogue_orochi{round}`。
2. 为八个 head 各建唯一 general code，克隆其 `general_boss`、`general_boss_variable`、`boss_level` 和 `general_enemy_watch` self 依赖；复用 action 资源前先过 code-reference gate。
3. 八头按 c24 顺序命名 `mod_rogue_orochi{round}_head1` … `_head8`；重写 parent
   c24，严格保留原始顺序和重复实例。
4. 对 parent 与八头的 Hit-HP `boss_level.c2` 应用同一个 bundle scale，保持官方 HP 比例；任一 Fix/短行/未知曲线立即拒绝。
5. zone 槽仍写 kind=3，code 写 parent clone；不能把 parent 降格成 kind=1。
6. 从最终内存表重新展开 parent + 八头，回读总 HP，并与计划值作严格近似比较。

所有依赖先在临时 overlay 中构造并验证，再一次性提交到传入的内存表；任一成员失败时
`orochi/general_boss/general_boss_variable/boss_level/general_enemy_watch` 均不得部分修改。
stale clone purge 同时覆盖这五表里的 `mod_rogue_orochi*`。

精确顺序固定为：先在 sanitized snapshot 上 purge stale 前缀；只读验证 parent 档、c24 八实例、
九条 Hit HP 与八头依赖；计算无量纲 scale；在 overlay 中建立全部九个 clone、改 parent c24；
在 overlay 上重展开并校验总 HP/引用/等级；全部通过后才提交 additions。候选失败只丢弃
overlay，不回滚 sanitized baseline。磁盘的多表 `save_table` 不是事务，报告不得声称磁盘原子；
保存顺序为 head 依赖表 → parent `orochi` → zone/field → quest，且 publish 只能在全部保存成功后发生。

实现该通道会让 `orochi.orderedmap` 成为可能写入的 battle 表，必须同步加入 `wf_gui.py::ROGUE_BATTLE_LOGICALS`，并由 `wf_rogue_build.py` 的 `written` 集合驱动发布与 CDN 字节回读。
`orochi_dirty = produced or purged`：即使本轮没有新抽到 Orochi，只要 stale clone purge 删除了旧行，
也必须把该表纳入 write plan。Orochi-only 构建必须写 gb/bl/gv/可选 ew 依赖，但不得因此无谓重写
general_zako/zako_level；现有 `caster_dirty` 保存块需要按这两个职责拆开。

如果上述任一步无法在不破坏 parent 语义的前提下完成，该 variant 在 catalog 阶段返回 `SPECIAL_HP_CHANNEL_UNSUPPORTED`。此时报告必须明确“发现但未放行”，不能把 Orochi 计入可选覆盖。
最终链检查必须接收本次构建的实际 special tables，并按 zone 中的精确 `(BossKind, code)` 复用
`validate_boss_ref`：kind 3 使用首个 `>= enemy_level`。禁止从全局缓存
`special_boss_levels()` 判 clone，也禁止只把 clone code 塞进 enemies 并集来伪造通过。

## 10. Action closure 与地形兼容性

### 10.1 Action roots

对实际选中等级的 general boss，closure 至少从以下根开始：

- c41 initial position 与 c42 routine state 路径；
- c49=0 时由 c50 指向的 position/state 路径；
- c109 pre-action（始终是 action root）；c110 只控制 rerun 行为，不能作为是否遍历
  c109 的开关；
- c111–c160 中实际引用的 action；
- action 中继续引用的 nested action / block / command。

standard 与 special kind 使用各自资源行中真实 action 路径作根；standard ESDL 必须使用
双重扩展名 `.esdl.amf3.deflate`。Task 3 v1 尚未完整证明 Standard ESDL 的 root `bx`
pre-action、`au[*].g[*].k` state movement 与 form revival-position 三条位置通道，因此任何
含 active kind0 single 的 bundle 一律 native-only，不能因只解析 `bH/ae/au[].c/i` 就标
portable。解析器必须跟随 `Command`、`Block` 和已知间接 action 引用；
`CreateBombMultiball` p5 按 p0 数量重复，`CreateTornado` p6 按
`floor(p4/p5)`，`CreateTargetAttack` p4 计一次。`CreateSummonsMultiball` p8 经客户端复核
只是 activated-event ID，真实子 action 来自 `MultiballTable[id].action`；首版未接该表，
故整条命令返回 `ACTION_CLOSURE_UNAUDITED`。顺序 block / sibling event
的可能并发量相加，互斥 condition 分支取最大值，字面量 `Repeat` 乘重复次数，`Wait` 只计
一次；遇到未知构造器、动态字符串、循环、无界重复或无法证明的并发分支，返回
`ACTION_CLOSURE_UNAUDITED`。

任何 command-owned `ActionDslExpression` 都不能默认按一次内联执行：例如
`CreateReferencePoint` 会遍历 subjects，`CreateHitArea` 可多次命中。除互斥 condition 或
已有命令级有限上界证明外，回调里一旦含地形/召唤要求就 fail closed。被召唤引用还须按
精确 client source 与 getSurjectivity 档验证；`GeneralBossAlive` 只允许同层 active
GeneralBoss 或同层已证明的 SpawnAlterEgo。portable verdict 落表前必须再做一次
source→source 自兼容检查。

closure 提取至少四类 requirement：

- `SpawnFunnel` 的 group、最大并发/命令数量及 funnel code；
- `SpawnAlterEgo` 及其 code/reference 依赖；
- `CUSTOM_POSITION` 名称；
- 由每层 c22 `boss_group_kind` 与 active boss slots 推导的 BossGroup 拓扑。

地形资源中没有 `BOSS_GROUP` object layer，不能臆造或要求该锚点。客户端分组来自 zone：
c22=0 时该层所有 active boss slots 同属一组，c22=1 时每个 active boss slot 各成一组；
其他值 fail closed。兼容门禁比较这个派生拓扑，而不是扫描 terrain object 名。

closure 未审清只代表不能证明跨地形移植安全。只要 active/kind/level/ref/HP/special 原生门禁通过，bundle 仍可在自己的官方 field 上运行并计入 native post-gate coverage。

### 10.2 Per-layer 兼容判据

source bundle 和 target terrain 只在 active layer 对齐后比较。每个 layer 必须满足：

1. target 的实体槽形状能一一容纳 source slots；不能只比较总数。
2. c22 `boss_group_kind` 一致，由 c22 + slots 推导的 BossGroup 拓扑一致。
3. 每个 `CUSTOM_POSITION` 在 target 同 layer 中存在。
4. 每个 FUNNEL group 在 target 同 layer 中存在，并满足计数等价。
5. source action closure 完整，所有 spawned code 均通过 `(kind, code)`、等级与引用门禁。

FUNNEL 计数用保守等价式：

```python
min(max_command_count, target_anchor_count) == \
    min(max_command_count, source_anchor_count)
```

若命令位于无法确定互斥性的分支、循环或并发块，不能猜 `max_command_count`，直接 fail closed。

### 10.3 旧 transplant 白名单的地位

`rogue_special_bosses.json` 的 `transplant_safe` 仍作为第一版额外实机证据：随机混搭必须同时通过静态兼容器与旧白名单。它不能替代 action/terrain 分析，也不能放行静态分析失败的 bundle。

原生 bundle 不发生移植，因而不受 transplant 白名单限制，但仍要通过引用、等级、HP 和 c36 复核。

## 11. Realization、回退与 pin 语义

统一接口：

```python
def realize_bundle(
    source: NativeBossBundle,
    target: NativeBossBundle | None,
    *,
    round_no: int,
    enemy_level: int,
    pinned_boss: bool,
    pinned_terrain: bool,
) -> RealizationResult:
    ...
```

`RealizationResult` 明确携带 `ok`、`realized`、structured fallback、reason 与 detail；
`RealizationPlan` 只描述经验证的完整 kind+code slot rewrite，不直接改表。先在局部
field/zone overlay 实现并重新读取 active slots，验证成功后才提交；池条目、配额和 pin 也只在
成功后消费。任何双 pin 失败都不得留下半个 `mod_rogue_fN/zN`。

策略固定如下：

| 场景 | 行为 |
|---|---|
| 随机 boss + 随机 terrain 不兼容 | 保留已选 family/variant，退回 source 原生 bundle，记录 structured fallback |
| boss pin，无 terrain pin | 搜兼容 terrain；耗尽则使用该 boss 的 native bundle |
| terrain pin，无 boss pin | 只从兼容 bundle 重抽；耗尽则使用该 terrain 的 native boss bundle |
| boss pin + terrain pin 兼容 | 原样实现 |
| boss pin + terrain pin 不兼容 | 直接失败，列出 layer/group/slot 原因；不重抽、不吃掉任一 pin |
| boss pin + 属性免疫且实际 c36 冲突 | 沿用现有响亮失败，不暗换 boss 或诅咒 |

structured fallback 至少包含 `round`、`family_id`、`variant_id`、source field、target field、reason code 和 detail。正常随机回退不算构建失败，但报告必须统计；双 pin 冲突属于构建失败。

## 12. HP 重排必须走同一条 realization 路径

`hp_curve_fit_pick()` 不再直接替换 `current["bosses"]` 或调用裸 `swap_zone_bosses()`。它只能返回一个新的 source bundle，并调用 `realize_bundle()` 在既有 target terrain 上重新实现。

这样可保证：

- donor 改变时 kind、single/multi pair、action requirements 与依赖一起改变；
- pinned terrain 不会跳过 HP 重排，也不会绕过 terrain compatibility；
- 不兼容的随机 donor 走 native fallback，双 pin 则失败；
- HP 计划基于最终 realized refs，而不是 donor 的旧字符串列表；
- `_hp_fit_cache` 使用 bundle fingerprint，donor/clone/table row 任一变化都会失效。

`floor_native_hp()` 接收 `RealizedBundle` 或显式 typed 实体路径，不再把 `list[str]` 当成完整战斗。普通重复实体逐槽累加；special parent 通过 `expand_bundle_hp_members()` 展开。
所有 HP/ref 读取必须显式使用当前内存表，禁止在 clone 复核里回退到 `_BASE_STATS`、
`_SPECIAL_LV` 或其他 live-store cache。

`bundle_fingerprint()` 每次从传入表重读实际状态，不信任 realized 内的旧摘要；除上述字段外，
还包含 Standard ESDL/HP evidence digest、实际 curve/K、special parent c24 有序实例与 clone 依赖。
缓存键使用 `(fresh_fingerprint, round_no, float(target).hex())`，不能继续按 field 或
`round(target, 6)` 命中。

## 13. 三联复核：refs + HP + c36

统一接口：

```python
def revalidate_selected_bundle(
    realized: RealizedBundle,
    *,
    stage: str,
    enemy_level: int,
    requires_element_resistance: bool,
    tables: Mapping[str, Any],
) -> BundleValidation:
    ...
```

必须在以下阶段调用：

1. native bundle 被选中后（`selected`）；
2. `--mix` realization 或 native fallback 后（`mixed`）；
3. HP reorder realization 后（`hp_reordered`）；
4. 法阵/耐性/HP/Orochi clone 全部完成后（`final_clone`）；
5. 写入 quest rows 前的全局 `final_gate`。

每次都执行三组检查：

### A. refs

- 重新从实际 field/zone/terrain 读取 active slots；
- 每个 `(BossKind, code)` 命中正确表和实际等级档；
- funnel、alter ego、code reference、special parent 与 action closure 完整；
- single/multi 槽对和预期 realization 一致。

### B. HP

- 从当前内存表重算所有 reachable entities；
- Orochi 展开 parent + 八头；
- 重复实例逐实体累加；
- planned HP 与回读 HP 一致；
- 任何 `unverified` 不得进入 HP 曲线验收分子。

### C. c36

- 只在需要属性免疫时检查；
- 读取 `RealizedBundle.condition_carrier` 指向的实际 realized/clone general boss code，
  并按实际 enemy level 用 `select_surjective_level()` 选行；不能扫描全部 general 实体代替载体身份；
- 检查该行的 `resist_element_resistance` c36；
- 这里的 c36 是 `general_boss` 列，不是 zone 的冲刺板列。

任一组失败都阻止继续落表。final gate 仍保留现有 `validate_built_rows()`，但它是三联复核后的额外整表链检查，不是替代品。

## 14. 生产入口收敛

### 14.1 主构建器

以下旧入口要改为 catalog/bundle adapter：

- `_zone_pick()` → `active_boss_slots()`；兼容返回值只能由 slots 派生。
- `quest_pool()` → 给 field 绑定 native bundle，而不是裸 bosses。
- `field_gate()` → `gate_native_bundle()`；`check_field_chain()` 作为附加引用检查保留。
- `tower_pick()` / `src_pick()` → 三阶段 selector。
- `mix_pick()` → `terrain_compatibility()` + `realize_bundle()`。
- `hp_curve_fit_pick()` → 选择 bundle 后统一 realization / revalidation。
- `make_caster_boss()` / `gimmick_field()` → 完成后交 final revalidator。

建议把纯数据结构、terrain 解析、BossKind 映射、catalog、selector 与兼容器放在新模块 `mod-tools/wf_rogue_bundle.py`。该模块不得 import `wf_rogue_build`，避免循环依赖；主构建器注入 table/callback 并负责实际克隆、HP 计划和写入。

### 14.2 无尽重摇

`wf_rogue_save.reroll_endless_field()` 必须调用主构建器导出的只读安全选择接口，例如：

```python
bundle = rb.choose_endless_native_bundle(random.Random(), enemy_level=100)
```

该接口使用同一份 post-gate catalog，并在返回前跑 native revalidation。禁止继续直接 `random.choice(cb.build_pool())`。`apply=False` 保持纯预览；`apply=True` 才写 quest 并调用发布。
选择等级来自目标 quest 的实际 c95。该 CLI 的默认目标是塔事件 `700099` 的无尽层 `99`，
不能保留官方事件 `700007/8`。`wf_rogue_reroll.py` 是整塔子进程路径，不属于此单层旁路，
本任务不把二者混改。field/BGM 之外的 thumbnail/推荐元素同步第一版明确列为非目标，不能再
从旧 `wf_chain_build` 池推导。

### 14.3 GUI 发布清单

若 Orochi clone channel 实际写 `master/battle/boss/orochi.orderedmap`，`wf_gui.py::ROGUE_BATTLE_LOGICALS` 必须同步包含它。最终发布日志不能继续写死“battle 七表/八表”，应从实际 logical 集合派生数量与名称。

## 15. 覆盖率与多 seed 轮转报告

`audit_bundle_coverage()` 输出 JSON 数据，再由文本报告渲染。至少包括：

- 扫描的 active single code / family / variant / bundle 总数；
- post-gate eligible 的同四类数量；
- 每个 reason code 的拒绝数与代表样本；
- 每个 family 的总 variant、eligible variant、native bundle 数；
- current 30-floor sample 的 family/variant 命中；
- 多 seed 样本中的 family 轮转、variant 轮转、native fallback 次数；
- Orochi 三 variant 的 eligible/blocked 状态与 HP channel；
- 六个 multi-only、`arch_evil*`、`orochi_ex` 的明确 reason；
- refs / HP / c36 每阶段复核计数。

多 seed dry-run 的每个样本必须打印：

```text
这是下一座候选塔，不是当前 store 塔
```

报告只能描述“候选生成结果”，不得把 dry-run 冒充当前 store、CDN 或设备状态。family 轮转验收关注“代表家族在不同 seed 能轮换、同一家族的多 field 不改变家族抽取权”，不设脱离实际 post-gate 数量的虚假百分比。

最终实施报告固定写到：

```text
mod-tools/work/codex_out/REPORT-native-boss-bundle-variants.md
```

## 16. 测试策略与固定发现数

全量 `test_rogue*.py` 的发现数必须保持 **337**。实现只重写或扩展现有 test methods，并用 `subTest` 加案例；不新增净 `test_*` 方法。

现有方法的承载分工：

- `SpecialBossTableCase.test_special_table_boss_not_dangling`：BossKind 表匹配、special reason、Orochi parent eligibility。
- `BossSeriesCase.test_orochi_heads_untouched`：一个 Orochi family、三个 parent variants、heads 不加票。
- `StandardBossHpCase.test_zone_pick_uses_single_battle_side_of_each_boss_slot`：active layer ∩ zone、single 实际侧。
- `StandardBossHpCase.test_floor_native_hp_keeps_two_real_instances_with_the_same_code`：实例计数、Orochi parent + 八头。
- `SwapZoneBossesCase.test_boss_slots_swapped_zakos_kept`：kind+code 与 single/multi pair 一起换。
- `SwapZoneBossesCase.test_single_slot_mix_reports_only_the_realized_donor_entity`：per-layer 形状与 realized entities。
- `ZoneBossSlotsCase.test_single_multi_variants_are_one_entity`：镜像不重复计数但 pair 不丢失。
- `CollapseGradesCase.test_keeps_highest_grade_only`：family→variant→bundle 去权重。
- `TaskCDryRunCase.test_pinned_terrain_does_not_bypass_immunity_aware_hp_reorder`：统一 HP realization / c36。
- `TaskCDryRunCase.test_flat_hell_mix_build_has_at_least_one_real_safe_transplant`：兼容器、native fallback 与 structured log。
- 复用一个现有测试方法的 `subTest` 验证 `wf_rogue_save` 只调用筛后 selector，不直接调用 `cb.build_pool()`。

每个实现任务都按 RED → 最小实现 → focused GREEN → 固定发现数回归 → 报告追加执行。全量基线必须仍为：

```text
Ran 337 tests
FAILED (failures=7, errors=30)
```

这 7 failures / 30 errors 是既有全量环境基线，不得用提高阈值、跳过新断言或新增 expected failure 掩盖回归。

## 17. 验收标准

- [ ] 所有候选只来自 terrain active layer；terrain layer 必须全部有同名 zone row，
      zone 多余 row 必须忽略。
- [ ] 所有 boss 引用均以 `(BossKind, code)` 验证并按完整 single/multi 槽实现。
- [ ] 抽取严格为 family → variant → native bundle，family 不受 field/alias 数量加权。
- [ ] FUNNEL group/count、`CUSTOM_POSITION`、派生 BossGroup 拓扑、slot shape 和 action closure 对移植全部 fail closed；未审 closure 的原生 bundle 仍保留并标为 native-only。
- [ ] 随机不兼容有 native fallback 记录；boss+terrain 双 pin 不兼容响亮失败。
- [ ] 选择、mix、HP reorder、final clone 后均通过 refs + HP + c36 三联复核。
- [ ] `arch_evil*`、`orochi_ex` 与六个 multi-only code 都有正确且数据驱动的 reason。
- [ ] Orochi 只有 parent bundle 得票；HP 展开 parent + 八头；clone channel 不可实现时诚实排除。
- [ ] `wf_rogue_save.reroll_endless_field()` 不再绕过筛后 catalog。
- [ ] 覆盖率来自实际 post-gate catalog，多 seed 报告展示 family/variant 轮转并包含候选塔声明。
- [ ] full discovery 仍是 `337 tests / failures=7 / errors=30`。
- [ ] 实施报告包含 RED/GREEN、实际计数、reason 分布、fallback、三联复核、禁写路径审计与未验证边界。

## 18. 风险与回退

- terrain 或 action DSL 解析遇到未知结构时会降低覆盖率；正确行为是 reason 化排除，而不是扫描全部 row 或假定无需求。
- 静态兼容器不能替代真机。第一版继续叠加 transplant 白名单；新增可移植组合必须另做真机证据后才扩白名单。
- Orochi clone 会扩大写表面；实现不完整时宁可 `SPECIAL_HP_CHANNEL_UNSUPPORTED`，不能只缩 parent HP。
- post-gate 候选可能少于门禁前理论值。报告必须给真实数量，调低难度或放宽门禁需另行设计批准。
- 任一步实施可通过移除新 catalog adapter 回到现有原生场地选择；禁止用回退路径恢复裸 `cb.build_pool()` 无门禁随机。
