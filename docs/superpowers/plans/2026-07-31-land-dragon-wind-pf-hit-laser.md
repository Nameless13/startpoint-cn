# 风巨蜥 PF 命中演出与大小激光实施计划

> **执行方式：** 当前会话内按 `superpowers:executing-plans` 顺序执行。角色工作区已有用户 WIP，不创建 Git worktree、不提交 Git；以生成物哈希、测试、production preflight 和可回滚 MuMu 暂存包作为审计证据。

**目标：** 生成并安装 `land_dragon_wind_poc` 1.1.7：PF2 首次命中敌人时触发一圈技能伤害绿环；PF3 首次命中时触发小型多段激光；Fever 技能继续等概率随机抽取现有超大激光等五种首领技。

**边界：** 仅修改 `work/character_packs/land_dragon_wind_poc` 及本设计/计划文档，使用 `mod-tools/wf_character_flow.py` 构建和预检。允许向当前 MuMu 实例执行可恢复安装并重启应用；不发布 CDN、不修改存档、不写活动资源根。

**实现原则：** PF 原有真实强化弹射攻击事件和倍率保持不变。附加演出由队长能力监听 `OneOfEnemyPowerFlipHitLv2/Lv3` 的真实命中事件，再调用独立 AbilitySkill。附加伤害使用玩家侧 `CreateHitArea`/`CreateNormalAttack`，不再使用曾触发 C16103 的 `CreateShockWaveAttack`。

---

## 任务 1：用回归测试锁定 1.1.7 行为

**文件：**

- 修改：`work/character_packs/land_dragon_wind_poc/test_package.py`

**步骤：**

1. 将目标清单版本断言从 `1.1.6` 更新为 `1.1.7`。
2. 将 PF2/PF3 队长触发断言改为：
   - PF2：trigger kind `181`，threshold `1`，cooldown `36`，InvokeSkill kind `629`。
   - PF3：trigger kind `182`，threshold `1`，cooldown `36`，InvokeSkill kind `629`。
   - 断言不再存在旧的发射时触发 `64/65`。
3. 将旧的 shockwave 测试替换为两组真实 AbilitySkill 行为测试：
   - PF2：固定命中点绿环，scale `1.0`、lifetime `36`、frame `8` 单次技能伤害、radius `480`、最大总倍率 `12×`。
   - PF3：小激光，scale `0.9`、lifetime `48`、frame `8/16/24/32` 四次技能伤害、radius `180`、前向距离 `60/140/220/300`、最大总倍率 `24×`。
4. 保留并强化 Fever 大激光断言：scale `2.25`、lifetime `96`、8 段、radius `320`、最大总倍率 `80×`。
5. 继续断言 PF1/PF2/PF3 原本的 `6/12/24` 个真实强化弹射攻击事件不变。
6. 运行：

   ```powershell
   python -m pytest work\character_packs\land_dragon_wind_poc\test_package.py -q
   ```

   预期：旧 `1.1.6` 构建至少因版本、触发类型、PF3 激光 DSL 缺失而失败；失败原因必须与新规格一致。

## 任务 2：实现碰撞触发 AbilitySkill

**文件：**

- 修改：`work/character_packs/land_dragon_wind_poc/build_workspace.py`

**步骤：**

1. 将 `PACKAGE_VERSION` 更新为 `1.1.7`。
2. 用明确的 PF2/PF3 follow-up 配置替换旧 ring/shockwave 配置：

   ```python
   PF_FOLLOWUPS = {
       2: {
           "trigger_kind": "181",
           "effect": "wind_ring",
           "scale": 1.0,
           "lifetime": 36,
           "waits": (8,),
           "positions": ((0, 0),),
           "radius": 480,
           "maximums": (12.0,),
       },
       3: {
           "trigger_kind": "182",
           "effect": "laser",
           "scale": 0.9,
           "lifetime": 48,
           "waits": (8, 16, 24, 32),
           "positions": ((0, -60), (0, -140), (0, -220), (0, -300)),
           "radius": 180,
           "maximums": (6.0, 6.0, 6.0, 6.0),
       },
   }
   ```

3. 生成 PF2/PF3 独立 AbilitySkill：
   - PF2 的 `ShowEffect` 指向已有 `powerflip/.../wind_ring/wind_ring`。
   - PF3 的 `ShowEffect` 复用已有 `skill_unique/.../laser/laser` pixel/atlas/timeline。
   - 使用现有玩家技能 DSL 帮助函数生成定时 `CreateHitArea` 和 `CreateNormalAttack`。
   - 不生成 `CreateShockWaveAttack`、`StopBall` 或角色长时间控制。
4. 修改 leader ability 的 PF2/PF3 触发器为 `181/182`，threshold `1`，cooldown `36`，保留 InvokeSkill `629`。
5. 更新自定义字符串和 build report，使 PF2 为“命中震环”、PF3 为“命中小激光”，并记录触发/段数/倍率。

## 任务 3：重建、回归与整包预检

**文件：**

- 生成：`work/character_packs/land_dragon_wind_poc/package/**`
- 生成：`work/character_packs/land_dragon_wind_poc/evidence/**`
- 修改：`work/character_packs/land_dragon_wind_poc/character-dossier.md`

**步骤：**

1. 构建：

   ```powershell
   python work\character_packs\land_dragon_wind_poc\build_workspace.py build
   ```

2. 运行角色包全套测试：

   ```powershell
   python -m pytest work\character_packs\land_dragon_wind_poc\test_package.py -q
   ```

3. 对安装基线执行 production preflight：

   ```powershell
   python mod-tools\wf_character_flow.py preflight `
     --workspace work\character_packs\land_dragon_wind_poc `
     --installed-package-dir work\installed_character_packages\land_dragon_wind_poc\1.0.1\package
   ```

4. 核对 `manifest.json`、`manifest.sha256`、seal、37/37 必需资产、三层一致和 drift 结果。
5. 在 dossier 追加 1.1.7 的实现、验证和待真机验收项，不改历史记录。

## 任务 4：生成并执行可回滚 MuMu 安装

**文件：**

- 修改：`work/character_packs/land_dragon_wind_poc/device-canary/prepare_canary.py`
- 新增：`work/character_packs/land_dragon_wind_poc/device-canary/revision-1.1.7-checklist.md`
- 生成：`D:\WF\MuMuPlayer\vms\MuMuPlayer-15.0-1\private_shared\land-dragon-wind-1.1.7-*`

**步骤：**

1. 将设备脚本期望版本更新为 `1.1.7`，生成新的隔离暂存目录；禁止复用/覆盖 `1.1.6` 暂存目录。
2. 保留逐文件备份、`install.sh`、`restore.sh`、`files.tsv` 和 staging 清单；补充独立 `verify.sh`。
3. 使用 `MuMuManager.exe` 对实例 `1`：
   - 停止 `com.leiting.wf`；
   - 执行新暂存目录的 `install.sh`；
   - 执行 `verify.sh` 并要求所有部署文件 SHA-256 相符；
   - 清理本次启动日志窗口；
   - 启动 `air.com.leiting.wf.AppEntry`。
4. 检查应用进程、前台 Activity 和客户端最新日志；不得出现 `C16103`、`C7101`、`G3000`、`C8601`、`F1009`、Fatal 或 ANR。
5. 记录恢复命令。若安装或启动验证失败，立即执行对应 `restore.sh` 并报告，不把失败版本留在设备上。

## 任务 5：真机战斗验收交接

自动验证只能证明安装一致、客户端可启动和资源加载无已知错误；最终向用户明确请求验证：

1. PF2 是否仅在首次撞到敌人时出现一圈紧凑绿环并造成技能伤害。
2. PF3 是否仅在首次撞到敌人时出现短小激光，四拍清晰，不再是全屏旋风或三圈。
3. Fever 是否仍可随机抽到原有 2.25× 超大激光，8 段命中与屏幕覆盖范围未缩小。
4. 释放后角色是否立即恢复可操作，不冻结。

## 运行时热修记录：1.1.8

1.1.7 装机后，用户确认角色技能可释放，但强化弹射命中仍触发 C16103。设备日志把故障定位到
独立 PF `AbilitySkill` 的顶层执行者查找：该技能没有主技能内部参考点 `0`，而构建结果的
`ShowEffect` 与 `CreateHitArea` 使用了 `0`。

按官方玩家侧 `AbilitySkill` 合同，1.1.8 将这两类顶层命令统一改为玩家执行者 `-18`，
并用测试锁定 PF2／PF3 的每个命令。1.1.7 上新增合同 3 项失败、其余 19 项通过；1.1.8
构建后 22/22 通过。生产预检为 37/37、16 项引用与 11 组纹理链均无缺失，三层一致。

1.1.8 已用新的隔离目录安装到 MuMu 实例 1，42/42 安装校验和设备端 SHA-256 重算通过；
启动后应用在前台，`isStoreDataBroken=false`、`errorMessage=[]`，本次日志窗口未出现已知
资源错误。最终关闭条件仍是用户分别让 PF2／PF3 实际命中敌人，确认无 C16103。
