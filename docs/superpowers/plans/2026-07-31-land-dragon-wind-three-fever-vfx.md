# 风巨蜥三类 Fever 与 PF 演出修复实施计划

> **执行方式：** 当前会话内按 `superpowers:executing-plans` 顺序执行。工作区含用户 WIP，
> 不创建 Git worktree、不提交 Git、不修改角色包以外的活动资源；以 TDD、整包哈希、
> production preflight 和 MuMu 设备端重算为证据。

**目标：** 构建并安装 `land_dragon_wind_poc` 1.1.9：Fever 技能等概率随机爪子重击、
超大激光炮或全屏旋风，三类满级均约 80×；恢复 PF2 全屏扩散绿圈、放大 PF3 小激光，
并统一修正上行风波方向。

**规格：**
`docs/superpowers/specs/2026-07-31-land-dragon-wind-three-fever-vfx-design.md`

**边界：** 允许写入角色 workspace、生成包、执行生产预检和向当前 MuMu 实例进行可恢复
安装；不发布 CDN、不改写当前存档、不修改活动资源根。

---

## 任务 1：建立 1.1.9 红灯合同

**文件：**

- 修改：`work/character_packs/land_dragon_wind_poc/test_package.py`

**步骤：**

1. 将目标版本改为 `1.1.9`。
2. 用三个相同正权重分支替换五分支断言。
3. 锁定三类的效果族、攻击事件数和满级倍率：
   - 爪子：`target_sight + slash + craw`，1 个最终攻击事件，80×；
   - 激光：`wave_arc30 + laser`，8 个攻击事件，80×；
   - 旋风：`overall + fast/middle/slow wave_arc120`，8 个攻击事件，80×。
4. 把 PF2 合同改为完整时间线重计时、约 90 帧、三拍扩散判定、合计 12×。
5. 把 PF3 激光缩放改为约 1.75×，保持四拍、24×。
6. 把 Fever 激光缩放改为约 4.5×，保持八拍、80×。
7. 把三层全屏风波方向断言改为玩家侧上行配置。
8. 保留 PF 命中触发、玩家执行者 `-18` 和 C16103 防回归合同。
9. 在未改构建器前运行测试并确认只因新合同产生预期红灯。

## 任务 2：实现三类 Fever 复合演出

**文件：**

- 修改：`work/character_packs/land_dragon_wind_poc/build_workspace.py`

**步骤：**

1. 将 `PACKAGE_VERSION` 更新为 `1.1.9`。
2. 把五个 Fever 分支合并为三个相同权重分支。
3. 爪子分支：
   - 最近目标处依次显示锁定、两道交叉斩和放慢后的巨爪；
   - 辅助特效不制造密集伤害数字；
   - 巨爪完全展开时生成单个 80× 玩家侧技能攻击事件。
4. 激光分支：
   - 用 `wave_arc30` 生成炮口风压；
   - 把激光放大到约 4.5×并保留完整开始、循环、收束；
   - 生成八个与粗大光束覆盖范围一致的攻击事件，每段 10×。
5. 旋风分支：
   - 组合 `overall` 与 fast/middle/slow 三层风波；
   - 三层全部改为上行方向并使用紧凑错峰；
   - 生成八个全屏／大范围攻击事件，每段 10×。
6. 更新分支报告、特效索引和角色档案文本。

## 任务 3：实现 PF2/PF3 演出修复

**文件：**

- 修改：`work/character_packs/land_dragon_wind_poc/build_workspace.py`

**步骤：**

1. 复制并重建角色独占 `wind_ring` timeline，把完整 1–263 帧映射到约 90 帧。
2. PF2 保持首次真实命中触发和玩家执行者 `-18`：
   - 固定碰撞位置完整扩散；
   - 三个由小到大的判定拍点；
   - 4× + 4× + 4× = 12×。
3. PF3 保持首次真实命中触发和四拍 24×：
   - 激光缩放改为约 1.75×；
   - 相应扩大命中宽度和推进距离；
   - 仍明显小于 Fever 超大激光。
4. 不恢复 `CreateShockWaveAttack`，不引入 C16103 风险路径。

## 任务 4：构建与自动验证

**文件：**

- 生成：`work/character_packs/land_dragon_wind_poc/package/**`
- 生成：`work/character_packs/land_dragon_wind_poc/evidence/**`

**步骤：**

1. 运行 `build_workspace.py build`。
2. 运行角色包专项测试并要求全部通过。
3. 检查三个概率分支、攻击倍率、效果引用、方向、PF 触发和角色解控。
4. 检查 manifest、hash、seal 和报告版本均为 1.1.9。

## 任务 5：production preflight

**步骤：**

1. 使用 `mod-tools/wf_character_flow.py preflight` 对安装基线执行整包门禁。
2. 要求：
   - 37/37 必需资产；
   - Master／DSL／纹理链零缺失；
   - manifest/hash/seal 完整；
   - 三层一致、无输入漂移；
   - `release_ready=true`、`can_prepare=true`；
   - `writes_live=false`。
3. 若失败，只修复角色 workspace 内归属明确的文件，重新从红灯验证开始。

## 任务 6：生成可恢复 MuMu 1.1.9 暂存包

**文件：**

- 修改：`work/character_packs/land_dragon_wind_poc/device-canary/prepare_canary.py`
- 新增：`work/character_packs/land_dragon_wind_poc/device-canary/revision-1.1.9-checklist.md`
- 生成：MuMu 私有共享目录中的独立 `land-dragon-wind-1.1.9-*` 暂存目录

**步骤：**

1. 生成新目录，不覆盖 1.1.8 暂存包。
2. 保留逐文件备份、`files.tsv`、`install.sh`、`verify.sh` 和 `restore.sh`。
3. 校验本机候选包与暂存目录 SHA-256 完全一致。

## 任务 7：装机与设备启动检查

**步骤：**

1. 停止 MuMu 实例 1 中的 `com.leiting.wf`。
2. 执行 1.1.9 的 `install.sh`。
3. 执行 `verify.sh`，要求设备端所有部署文件哈希匹配。
4. 清理本次启动日志窗口并启动 `air.com.leiting.wf.AppEntry`。
5. 检查应用进程、前台 Activity、资源状态与最新日志。
6. 若安装、校验或启动失败，立即执行本次暂存目录的 `restore.sh`。

## 任务 8：实战验收交接

装机和启动无错误后，请用户在战斗中依次验证：

1. PF2 完整全屏扩散与三拍技能伤害；
2. PF3 中小激光的尺寸、方向和四拍；
3. Fever 爪子、超大激光、全屏旋风三类演出；
4. 三类实战倍率均约 80×；
5. 风波全部向上；
6. 技能结束后立即恢复操作；
7. PF 与技能连续使用不再崩溃。

自动设备检查不替代以上真机战斗结论。
