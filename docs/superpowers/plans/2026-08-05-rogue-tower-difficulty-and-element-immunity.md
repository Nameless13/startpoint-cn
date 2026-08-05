# 深渊连战重制:难度锚到「单人打多人决战」+ 属性免疫诅咒族

日期:2026-08-05
分支:`release/modes-20260714`
交付期限:2026-08-06 早上(作者上机前)

---

## 0. 开工前置(已验)

| 项 | 状态 |
|---|---|
| `python mod-tools/wf_publish_guard.py` | exit 0,`没有待检查的文件` |
| `mod-tools/work/sync_pending.json` | `[]` 空 |
| 链尾 | 1.4.285,store ≡ 链,六个自制角色全在链上 |
| `6d7dec0` 伤害带四道闸 + 等级爬坡 | 在当前分支,**未写盘未发布** |
| `a5c401e7` 法阵克隆不拆散成对/分阶段 boss | 在当前分支,**未写盘未发布** |

⚠ `sync_pending.json` 是单文件,隔壁会话同时改共享表会撞。每次写盘前重查。

---

## 1. 背景:三件已定位的事

### 1.1 第 10 战 softlock(玩家实锤,已定位)

「背鳍三兄弟」= 鲨鱼 boss 的三只分身,分别落在三个地形锚点:

| 兄弟 | 触发 | 落点 |
|---|---|---|
| 蓝鲨 `shark_blue` | `pre_action`(开场) | FUNNEL_SPAWN **1** |
| 棕鲨 `shark_brown` | `pre_action`(开场) | FUNNEL_SPAWN **3** |
| 红鲨 `shark_red` | **`ea1`(50% 血转 phase2)** | FUNNEL_SPAWN **2** |

线上 `mod_rogue_boss10` 与官方 `shark` **162 列只差 c111 一格**:

```
[111] 官方: boss_shark$ea1
      克隆: boss_shark$ea1 , general_boss/boss_enemy_eviltower$difficulity10_shot3
                             ^^^ 深渊法阵程序被追加进「转阶段召唤红鲨」这一格
```

`a5c401e7` 的门禁**逻辑是对的**(实测 `shark` / `haniwa_great_wind_direct` 都拦得住),
线上塔只是**在门禁落地之前构建的**。全塔扫描:**受影响层 = 1 层(仅第 10 战)**。

⇒ 重建即修复,无需额外改码。

### 1.2 战斗图集总量超限(玩家 A/B 实锤)

- Party A = 4 个原创角色(149999/139999/149998/129999)→ 必崩
- Party B = 2 个原创角色 → 正常
- 崩在大规格 boss 层(第 23 战 wind_sphere),1~18 层普通 boss 带 4 个原创不崩

⇒ **队伍与 boss 各占一半预算**。已挂独立任务处理(自制角色技能特效瘦身),
**本 plan 不涉及**,塔这边不做 boss 侧图集闸(实测按面积拦会踢掉 31/314 层、真阳性 0)。

### 1.3 难度曲线取档方向(本轮已修)

`wf_rogue_build.py:curve_value` 原取 ≤level 的最大档(下取整),
客户端权威实现 `GeneralEnemySourceHelper.getSurjectivity:23` 是
`if(key >= level) return`(**上取整**),取不到就 throw(=U_50fc52)。

方向反了 ⇒ lv80 层归一化补偿虚高 **3.038×**、lv90 虚高 1.292×,
正好抵消 hell 预设 `0.9→4.0` 的爬坡 ⇒ **难度曲线整条失效**。

已修,并把测试里钉死错行为的断言一起更正(`test_growth_curves_decode`)。
测试回到基线 `failures=7 errors=30`,零回归。

---

## 2. 难度锚:单人打多人决战

### 2.0 ⚠ 2026-08-05 实测推翻本节前提 —— 先读这段

**塔不需要「整体加血 75 倍」,它需要的是重新分配。**

standard boss 的血量**能读到**,资源在 store 里,扩展名是双重的
`battle/enemy/boss/<asset>.esdl.amf3.deflate`(`<asset>` 取 `standard_boss`
按等级档选中行的第 1 列)。raw-deflate 解开后 `wf_dsl.parse_dsl` 直接可读,
`au` 键 = 部件数组,每个部件 `d` 字段带血量:
```
{"a":0,"b":13,"c":["T1","p0"],"d":["T1", 1450000000.0]}
```
逐部件累加 = 基数,再 ×0.55(单人 `hpScalingBossBattle`)×c86。

实测现役塔 8 个 standard 层(**一个字没改的现状**):

| 关 | lv | boss | 部件基数 | ×0.55×c86 | 时限 | 需求DPS |
|---|---|---|---|---|---|---|
| 9 | 80 | anv3_big_boss_expert | 1,450,000,000 | 18.1亿 | 900 | 200.7万 |
| **12** | 90 | **steampunk_dark_hard_multi** | **39,493,125,000** | **233.4亿** | 900 | **2593万** |
| 15 | 90 | steampunk_another ×2 | 2,500,000,000 | 43.8亿 | 900 | 486.8万 |
| 16 | 80 | steampunk_fire_single | 500,000,000 | 3.2亿 | **240** | 134.4万 |
| 18 | 90 | grizzly_ex | 650,000,000 | 4.7亿 | 900 | 52.2万 |
| **21** | 100 | epuration_boss_highest | 18,000,000,000 | 154.3亿 | **240** | **6430万** |
| 29 | 100 | abyss_cloud ×2 | 9,000,000,000 | 121.6亿 | 900 | 1351万 |
| 30 | 80 | chapter12_boss_story | 700,000,000 | 25.0亿 | 900 | 278.1万 |

**8 层合计 604 亿。**

两条改变设计的事实:

**① 第 12 战的部件基数 `39,493,125,000` 就是本文档拿来当锚的德古兰血量。**
`steampunk_dark_hard_multi` = 暗机兵德古兰本人,**它一直就在塔里**。
单人折算 233 亿、需求 **2593 万/s**,已经落在 §2.1 的目标带 2194~3072 万/s 之内。

**② 第 21 战的「时限×深层冲突」不是未来风险,是现在就有的 bug**:
240 秒打 154 亿 = **6430 万/s**。第 16 战同样是 240s。

⇒ 施工方向改为:
- **上界锚定**:第 12 战 2593万/s 是天花板参照,深层向它对齐;第 21 战 6430万/s 是**异常值,要压下来**,不是标杆
- **抬地板**:9万~52万/s 那批层抬到几何爬坡线上——**这才是主要工作量**
- standard 层现在有绝对血量,**8 层全部做绝对验收,不必退相对口径**
- 几何爬坡端点(第1关 60万 → 第30关 2194~3072万)仍有效,但含义变成
  「把现有极端不均摊平到这条线」,不是「所有层往上抬 75 倍」

### 2.0.1 逐层目标表 —— 光调 c86 做不到,必须重排 boss 池

按几何爬坡(第1关 60万/s → 第30关 2500万/s,逐层 ×1.1372)反推每层需要的 c86:

| 关 | 族 | boss | 时限 | 现DPS | 目标 | 倍数 | 需要 c86 |
|---|---|---|---|---|---|---|---|
| 8 | gen | haniwa_great_wind_direct | 180 | 738万 | 148万 | **0.20×** | 0.009 |
| **12** | std | **steampunk_dark_hard(德古兰)** | 900 | **2593万** | 247万 | **0.10×** | 0.102 |
| 13 | gen | smr21_big_boss_ex | 900 | 9.1万 | 281万 | **30.99×** | 6.93 |
| **21** | std | epuration_boss_highest | 240 | **6430万** | 786万 | **0.12×** | 0.190 |
| 22 | gen | haniwa_great_water_fever | 900 | 18.1万 | 894万 | **49.32×** | 12.97 |
| 23 | gen | holy_sphere_single | 900 | 22.6万 | 1016万 | **45.05×** | 19.67 |
| 27 | gen | mod_rogue_boss27 | 900 | 32.1万 | 1700万 | **52.98×** | 11.61 |
| **28** | gen | mod_rogue_boss28 | 900 | 30.0万 | 1933万 | **64.50×** | **690.79** |
| 30 | std | chapter12_boss_story | 900 | 278万 | 2500万 | 8.99× | 58.44 |

(完整 30 行可用 §2.0 的读法现算,此处只列极端项)

**三个结论:**

**① 第 28 关需要 c86 = 690 —— 没有先例,大概率溢出或异常。**
现役塔 c86 最大 10.7,官方最大约 30。**光调系数走不通。**
⇒ 真解法是**重排 boss 池**:让曲线形状先靠 boss 自身血量差撑起来,
c86 只做微调(保持 0.1~10 的合理区间)。
硬 boss(德古兰/歼灭者/深渊之兽)现在在 12/21/29 层,位置大体对,
问题是 13~28 之间塞了太多软 boss(9万~32万/s)。

**② 第 25 关是 180 秒**,目标 1314万/s = 3 分钟打 23.7 亿。**该层时限必须放开,否则无解。**

**③ 第 12/21 关要「压」不是「抬」** —— 与"把塔变难"的直觉相反,
但那是把断崖摊平的必然结果。
若不愿削弱它们,另一条路是把曲线终点抬到 6430万/s 对齐第 21 关,
代价是中段要抬 100 倍以上,**更不可行**。

⚠ 施工顺序因此变成:**先重排 boss 池 → 再算 c86 微调**,不要反过来。

### 2.0.2 boss 池够不够 —— **紧张,且大部分数字是假设**

扫全池(519 只,lv100 / c86=1.0 口径)时必须区分数据来源:

| | 只数 | 说明 |
|---|---|---|
| **实测** | **60** | standard 族走 esdl 逐部件累加;general 族曲线已知 |
| **代理** | **459** | 基数是真的,但**曲线倍率是 `PROXY_CURVE` 顶替的假设**(见 `true_stat` 注释「这是个假设,不是实锤」)。绝对值不可信,**组内相对排序有意义** |

分档(只看实测 vs 含代理):

| 门槛 | 实测 | 含代理 |
|---|---|---|
| ≥90亿(撑第29-30关) | **5** | 20 |
| ≥45亿(撑第25-28关) | **7** | 30 |
| ≥18亿(撑第20-24关) | **22** | 63 |

⇒ 第 25-30 关共 6 层需要 ≥45 亿,实测只有 **7 只候选,刚好够、零余量**,
而且这 7 只里还可能有被现有门禁(C8016 / 分阶段联动 / 专用表 / c36)拦掉的。

**所以不能说"池子有富余"。**

⚠ **代理值消不掉 —— 2026-08-05 已查证,别再重复这条路:**
- 曲线表只有三族:`fix_hp_basic_curve` / `hit_hp_basic_curve` / `hit_hp_correction_curve`
  (各带一个 `_iosbundled` 变体)。`CURVE_TABLES` 只加载了 correction 一族(3 条 hp 曲线)。
- 补加载 `hit_hp_basic_curve.orderedmap` **无用 —— 它在本 store 里只有 16 字节,是张空表**。
- 反编译客户端里 **搜不到 `hit_hp_correction_normal` 字面量**。
⇒ 「客户端内置默认曲线」的说法成立,**459 只的绝对血量无法从数据侧解出**。

可行的核实途径只剩:
1. **standard 族**:走 esdl 逐部件累加(已实现,`standard_boss_hp_evidence`)—— 完全可信
2. **general 族且曲线已知**(3 条):`true_stat` 直接可信
3. 其余 459 只:**只能靠真机实测**(进本看血条/伤害),或接受"组内相对排序可信、绝对值不可信"

⇒ 早上重排 boss 池时,**深层优先从①②两类里选**;
必须动用代理组时(如 `haniwa_great_wind_direct`),把它当**待真机确认**标出来,
不要让它决定曲线端点。

⚠ 榜首 8 只 `practice_waraboss_tough*` 报 1277 亿 —— **全是代理值**,
且 `practice_` 前缀基本可以确定是练习木桩(无攻击行为),
不该进塔;现有代码里**没有**针对它们的黑名单,重排前要补。

实测组里真正可用的天花板:
`steampunk_water_hard_multi` 594 亿 / `steampunk_dark_hard_multi`(德古兰) 217 亿 /
`steampunk_thunder_hard_multi` 202 亿。
代理组里量级可信度较高的:`haniwa_great_wind_direct` 510 亿(**现在就在第 8 关**,
被 180 秒时限卡着才只有 738万/s —— 挪到深层并放开时限,一只可撑第 29-30 关)。

### 2.1 目标(下面的「差 75~105 倍」已被 §2.0 修正,仅保留推导过程)

| | 现状(修完曲线后) | 目标 |
|---|---|---|
| 血量中位 | 2.44 亿 | **197~276 亿** |
| 需求 DPS 中位(900s) | 29.4 万/s | **2194~3072 万/s** |
| 对比官方地狱级通关线(397万/s) | 0.074× | **5.5~7.7×** |

锚点推导:暗机兵德古兰 `quest_rank=8` 真血量 **394.9 亿**(4 人共享,人均 98.7 亿)。
「单人打多人决战」= 一个人吃下整本 ⇒ 取 **50%~70%** 作为目标带
(作者明确要求「可以稍微少一点血量,靠 buff/减益/场地领域补足」)。

### 2.2 三条必须先解决的结构问题

**① 全局乘曲线做不到。**
29 个有 boss 的层里,**8 个 standard 层吃掉全塔 93.6% 血量**(109.8G / 117.3G),
另外 21 个 general 层加起来才 7.5G。归一化窗口只有 100×(`--normalize-min/max` 0.1~10),
而池子原生跨度 1432× ⇒ 夹子先饱和。
⇒ **按族分治**:standard 族压、general 族抬,并放开 `--normalize-max`。

**② 时限层是硬矛盾。**
「时之枷锁」hell 档 = 10800 帧 = 180s。血量拉到 200 亿后,180s 需求 **1.1 亿/s**。
⇒ **深层禁时限诅咒**(深层难度改由场地领域 + 属性免疫给),
或带时限的层血量单独封顶。取前者。

**③ 「血肉高墙」乘法陷阱必须先修。**
分位闸摘掉「玻璃深渊」时 `apply_picks` 重算会让 `hp:0.5` 一起消失,
**该层血量当场翻倍**(第 12 关抽到高墙可到 106G、需求 1.18 亿/s)。
血量拉到 200 亿量级后这个 bug 会直接掀翻整条设计。

### 2.3 机制补足(不吃血量预算)

1. **场地领域常驻化**:现「深渊法阵」只落 7/30 层 → 中后段保底 1 个、深层 2 个
2. **诅咒名额后压**:`≤15%1个/≤40%2个/其余3个` → `≤20%1个/≤50%2个/>50%3个 + 深层第4个`(条件槽有 5 个)
3. **属性免疫**(见 §3)——本次新增的主力

---

## 3. 新增:属性免疫诅咒族

### 3.1 需求(作者原话)

> 塔添加免疫某个属性伤害,没有免疫一个到多个,至少留一个属性和一种伤害类型
> (都是不可驱散)作为随机 buff 组合

拆解:
- 免疫 1~N 个**属性**,**至少留 1 个属性**不免疫
- 免疫 1~N 个**伤害类型**,**至少留 1 种伤害类型**不免疫
- 两者**都不可驱散**
- 进随机 buff 组合池

### 3.2 现状澄清(重要)

现有「深渊壁垒/三重壁垒/绝对壁垒」里的「系」是**伤害类型**(能力/直击/强化弹射/技能),
**不是元素属性**。所以:

- 「至少留一个」模式**已存在**于伤害类型维度(三重壁垒 = 四免三留一)
- 本次要新增的是**属性维度**
- 现有的全部走 c71-80,**被客户端强制可驱散**,不满足「不可驱散」

### 3.3 通道选型(逆向已验)

| 通道 | 属性维度 | 不可驱散 | 结论 |
|---|---|---|---|
| quest `battle_enemy_condition_1..5`(c71-80) | ✗ 枚举只有 kind 0-3 伤害类型 + 4 减益免疫 | ✗ 客户端两处白名单强制可驱散 | **不可用** |
| `StartBuffField` + `ElementResistance` | ✓ | — | **方向错**:场效果只作用玩家侧(数值 getter 只被 MemberImpl/BallImpl 消费) |
| **`CreateCondition` + `ConditionChangeContent.ElementResistance`** | ✓ | ✓ `cancelable` = params[4] | **选它** |

### 3.4 逆向事实卡(全部已验,施工按这个写)

**元素编码(数据层写这套)** — `ToleranceOfElementTarget`(`boot_ffc6.as:1100-1107`):
```
RED=1(火) BLUE=2(水) YELLOW=3(雷) GREEN=4(风) WHITE=5(光) BLACK=6(暗)
ALL=254   OWNER=255
```
客户端内部会 remap 成「0=全属性,1..6=六属性」(`AdditionalConditionKindTools.as:60-104`),
**我们只写数据层那套 1-based,不要写内部编码**。

**构造子**(`ConditionChangeContent.__constructs__` 索引):
```
 3 AbilityDamageResistance(Number)
 4 DirectAttackDamageResistance(Number)
 5 PowerFlipDamageResistance(Number)
 6 SkillDamageResistance(Number)
 7 ElementResistance(element:int, value:Number)     ← 属性免疫
 8 ElementDamageCut(int,int)
 9 ElementDamageCutPercent(int,int,Number,Number)
19 DebuffResistance(Number,Boolean)
```

**值语义**(`BattleZoneMemberStats.as:728-735`):伤害 × `(1 - r)`
```
r = 0.3  → 伤害 ×0.7(30% 抗性)
r = 1.0  → 伤害 ×0   ⇒ 完全免疫      ← 官方炎兽领域用的就是 1.0
r < 0    → 易伤(vulnerability)
```

**敌方消费点**(`EnemyImpl.as:2963-2968`):
```
getStatModifierElementResistance(elem):
    conditionSlot.getOneSideElementResistance(elem, false/true)
    + conditionSlot.getElementResistanceByPoison()
```
⇒ boss 从**自己的 conditionSlot** 读属性耐性,正是 `CreateCondition(subject=自身)` 的落点。

**挂载点**:`general_boss` c109 `pre_action` / c110 rerun
(与 `wf-quest-condition-dispel` 既有结论一致;`cancelable` 是 params[4],
自身 = subject `-17`,目标种类必填 `3`)。

### 3.5 两个必须防的静默失效

**① `autoHighLevel` + lv≥80 强制拒绝** — 已排除,但要写进注释防回归

`EnemySourceBase.as:220-228`:
```
if (params[13]) {            // params[13] = autoHighLevel (ZoneSource.as:376 第11参)
    if (level >= 80) {
        resistElementResistance = true;      ← 强制拒绝属性耐性
        enhanceDebuffDecreasingRate = true;
        enhanceToughness = true;
    }
}
```
`isAutoHighLevelBoss()` **只在 `ScoreAttackEventBattleQuestLogic` override 成 true**,
基类恒 false。我们的塔是 `event_quest` ⇒ **不触发**。
⚠ 但塔的敌人是 lv80/90/100 **全部 ≥80**,一旦将来把塔挪到分数攻击类型,属性免疫会整族静默失效。

**② 每只 boss 自带 `resist_element_resistance` 列 —— 列位已钉死 = c36**

`GeneralBossSource.as:109` 从 `values.resist_element_resistance` 读;
列位由 `GeneralBossValues.as:725-754` 确定:`_loc32_ = param1[36]` → `_loc33_` → 赋值。

⇒ **`general_boss` 第 36 列**,`"true"/"True"/"TRUE"` 为真(非这六种字面量会 throw C7101)。

⚠⚠ **`general_boss` 的值是按等级嵌套的 dict,不是扁平行**(如 `shark` 的子键 = `['79','100']`)。
选行必须按客户端 `GeneralBossSource.as:88` 的 `getSurjectivity(level)` ——
**取第一个 ≥敌等级的档**。用「第一个 key」或 `general_boss_variable` 选行都会错:
`gb[79]=false / gb[100]=true` 的 boss 在 lv80/90 层会被误判成可以上免疫。

> 2026-08-05 我本人先踩了这个坑:用 `leaf()` 取第一个等级档,算出「塔内 3 层」并写进本文档,
> 也传给了 Codex。**正确答案是 7 层。** 按等级档重算后:

实测分布(现役塔,敌等级 lv80/90/100):

| 层 | 代号 | 选中档 | c36 |
|---|---|---|---|
| 第 4 战 | `mod_rogue_boss4` | gb[100] | true |
| **第 8 战** | `haniwa_great_wind_direct` | gb[100] | true |
| **第 10 战** | `mod_rogue_boss10` | gb[100] | true |
| 第 13 战 | `smr21_big_boss_ex` | gb[100] | true |
| 第 20 战 | `beasts_big_boss_multi_80` | gb[100] | true |
| **第 22 战** | `haniwa_great_water_fever` | gb[100] | true |
| **第 27 战** | `mod_rogue_boss27` | gb[100] | true |

**另有 11 层的 boss 根本不在 `general_boss` 里**(五元素球/八岐/蒸汽朋克等**专用表 boss**,
见 [[wf-rogue-chain-gate]] 的「第四类来源」)。这些层没有 `general_boss` 行 ⇒
**没有 c109 可挂 CreateCondition**,同样发不了属性免疫。

⇒ 实测门禁拦下 **18 层**,能承载属性免疫的只有 **12 层**:
`2,3,6,7,11,14,17,24,25,26,28,99`。
(层里只要有一只 boss 被拦,整层就不发 —— 所以不是简单的 31−18。)
设计上要接受这个覆盖率,或者另找专用表 boss 的挂载点(本轮不做)。

**施工必须**:c36=true 或不在 general_boss 的 boss,属性免疫诅咒不发,换别的。
否则文案说「免疫火」而实际没免疫 = 骗玩家。

### 3.6 官方先例充足(2026-08-05 更正)

> **本节原写「零官方先例、必须金丝雀兜底」——那是错的,已更正。**
> 错因:我搜的是 `ElementResistance`(那是 `ConditionChangeContent` 层的名字),
> 而 **DSL 层叫 `ACToleranceOfElement`**。两层名字不同,搜错名 ⇒ 假的"零先例"结论。

按 DSL 名重扫官方 boss action:

| 官方用例 | 数量 |
|---|---|
| `CreateCondition` 节点 | **1315**(全部 12 参) |
| `ACToleranceOfElement` | **545** |
| **逐属性码 1..6** | **113**(火45 水10 雷16 风10 光13 暗19) |
| **`cancelable=false`(p4)** | **143** |

⇒ 双轴不可驱散属性免疫的**每个要素都有官方先例**,不是新造轮子。风险从「可能整个静默失效」
降级为「常规验证」。

`CreateCondition` 12 参权威布局(官方逐位实测,照这个写):
```
p0=subject(-17=自身)  p1=条件数组  p2=slv(1)  p3=["GenericConditionHitEffect"]
p4=cancelable        p5=false     p6=""      p7=null   p8=false
p9=3(目标种类)        p10=slv(1)   p11=false
```
`ACToleranceOfElement` 参数:`[名, 时长slv, 元素码裸int, 值slv, 层数slv]`
—— 元素码写**裸 int 不包 SLV**(客户端 `int(params[1])`),值走 `resolveSLvValue(params[2])`。

金丝雀仍建议做(验免疫真的为 0 伤害、留出的属性打得动、驱散无效),
但它现在是常规验收,不再是「不做就不敢发」的硬门。

### 3.7 可解性硬闸(新增门禁)

任何一层的诅咒组合落表前必须满足:

```
未免疫属性数 ≥ 1   且   未免疫伤害类型数 ≥ 1
```

判据要**跨诅咒合并后**再判(多个诅咒可能各免疫一部分,叠起来才封死)。
现有 `curse_conflict` / `merge_conditions` 已有同 kind 异号冲突检测,
在同一层加这条。违反 ⇒ 拒绝该组合并重抽,并 `log()` 记录,不许静默截断。

---

## 4. 施工顺序

| # | 事项 | 产出 | 谁做 |
|---|---|---|---|
| 1 | ✅ 修 `curve_value` 取档方向 + 测试断言 | 已完成 | Claude |
| 2 | 修「摘诅咒致血量翻倍」乘法陷阱 | `wf_rogue_build.py` | Codex |
| 3 | 属性免疫诅咒族(§3)+ 可解性硬闸(§3.7)+ `resist_element_resistance` 黑名单(§3.5②) | `wf_rogue_build.py` | Codex |
| 4 | 按族分治重设血量 + 放开 normalize-max + 深层禁时限 | `wf_rogue_build.py` | Codex |
| 5 | 场地领域常驻化 + 诅咒名额后压 | `wf_rogue_build.py` | Codex |
| 6 | GUI 曝光新诅咒族 | `wf_gui.py` | Codex |
| 7 | 金丝雀:单层属性免疫真机验证(§3.6) | 设备 | Claude |
| 8 | 全塔重建 + 30 关数值表 + 引用完整性门禁(`--check`) | dry-run 报告 | Claude |
| 9 | 发布(含 battle 表) | 链 1.4.286 | 待作者确认 |

**第 1 步已完成。第 10 战 softlock 在第 8 步重建时自动修复。**

## 5. 验收标准

- [ ] 30 关需求 DPS:第 1-10 关 60~120 万/s、11-20 关 150~250 万/s、21-30 关 300~450 万/s → 深层 2194~3072 万/s
- [ ] 无任何一层同时满足「深层 + 时限诅咒」
- [ ] 无任何一层的诅咒组合把六属性全免疫或四伤害类型全免疫
- [ ] 属性免疫不落在 `resist_element_resistance=true` 的 boss 上
- [ ] 第 10 战红鲨正常召唤(重建后 c111 == 官方值)
- [ ] `wf_rogue_build.py --check` 引用完整性零悬空
- [ ] 金丝雀真机:属性免疫层,免疫属性打不动、留出的属性打得动、且**驱散不掉**
- [ ] `mod-tools` 测试不超过基线 `failures=7 errors=30`
