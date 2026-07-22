# World Flipper 一键增量导入与 Mod 中心设计

日期：2026-07-22

状态：交互方案已获用户确认；其余技术细节由用户授权按本设计收口，待书面规格复核

适用项目：StarPoint CN / World Flipper CN 离线 Android 客户端、内容工具链与导入器

## 1. 目标

把当前离线版新增内容交付为不需要 Node、Fastify、CDN、ADB 或电脑伴随程序的 Android 增量包。接收者在已经放置原始 `WorldFlipper` 数据的手机上安装离线游戏与一次性的导入器，随后点击 `.wfpack` 即可完成导入。

首个发行固定包含：

- 角色 `129999` 赛瑞斯、`139999` 史黛拉、`149999` 杰拉德。
- 深渊连战 `700099`、代币 `2370099`、兑换商店 `9700101`–`9700115`。
- 宝物域连战 `2001`，保持固定五层直到玩家主动重新随机。
- 武器 `8000101`–`8000115`，共 15 把。
- 游戏内“Mod 中心”：导入状态、18 封内容邮件、两个模式的重新随机和难度设置。
- 每个模式四档预设，以及敌人等级、HP、攻击、时限和诅咒强度的高级设置。

玩家体验必须满足：

1. 原始约 10 GB `WorldFlipper` 数据保持只读，不重新解压、不原地覆盖。
2. 第一次安装导入器后，后续内容更新通常只需点击新的 `.wfpack`。
3. 飞行模式下可以启动、领取邮件、游玩两个模式、结算、保存并重启读档。
4. “重新随机”生成或选择一条新的固定路线；路线不会因进本、返回菜单或重启而自行变化。

## 2. 与既有离线整合设计的关系

本设计扩展并部分替代 `2026-07-20-offline-android-release-bundle-design.md`：

- 保留其 `base.apk.1` 离线基线、DummyRemote、`save_haxe`、共享存储权限、Seris 双形态、Gerald 缩放、深渊武器门控、APK fail-closed 重锚定和稳定签名契约。
- 将“每次发布完整约 10 GB 数据 ZIP”改为“原始 `1.4.54` 数据只读 + 小型签名 `.wfpack` + 活跃版本指针”。
- 将“干净存档直接预置三角色、15 把武器走商店”改为用户确认的 18 封附件邮件：3 个角色加 15 把武器。
- 增加独立 Android 导入器、游戏内 Mod 中心、持久化路线和难度状态。

如两份设计冲突，以本设计为准；未覆盖的 APK 基线与安全门禁继续沿用旧设计。

## 3. 非目标

- 不在手机上运行或移植 `wf_gui.py`、`wf_rogue_build.py`、SQLite、HTTP 服务、CDN 发布器或 ADB。
- 不在设备上给任意新 APK 注入 SWF 补丁或重新签名。
- 不支持把本包导入任意未知或被修改过的 `WorldFlipper` 数据；首版只支持声明的干净 `1.4.54` 基线。
- 不使用当前失败的 `__random__` floor 头行，也不做“每次进本自动随机”。
- 不在 v1 提供删除核心内容或降级到不含已领取角色、武器的版本。
- 不覆盖、清理或提交仓库中现有角色、模式、`work/`、反编译目录和其他用户 WIP。
- 不修改旧后台 `web/pages/`、`src/routes/web/` 或 `web/public/`。

## 4. 发行物与首次使用

### 4.1 对外文件

首个发行目录包含：

~~~text
WF离线Mod版/
├─ WorldFlipper-离线Mod版.apk
├─ WF一键导入器.apk
├─ 三角色双模式-v1.wfpack
├─ 导入说明.txt
└─ SHA256SUMS.txt
~~~

三个二进制文件彼此独立：

- 游戏 APK 负责离线运行、外置覆盖层、Mod 中心和客户端专属补丁。
- 导入器 APK 负责 `.wfpack` 校验、安装事务和活跃版本切换。
- `.wfpack` 只携带内容、声明和运行时配置，不携带 APK、私钥、个人存档或完整基础数据。

游戏包名继续使用 `com.leiting.wf`；导入器使用独立稳定包名 `io.starpoint.wfmod.importer`。导入器注册 `.wfpack` 的 Android `ACTION_VIEW` 文件关联和内部 `wfmod://status` 深链。Mod 中心优先按包名打开导入器；未安装时只显示安装提示，不跳转未知应用。

导入器只需安装一次。兼容的后续内容更新只重新分发 `.wfpack`；客户端能力变化时才更新游戏 APK。

### 4.2 玩家流程

1. 把原始数据放在共享存储的标准 `WorldFlipper/dummy/download/production/` 下。
2. 安装 `WorldFlipper-离线Mod版.apk` 和 `WF一键导入器.apk`。
3. 首次打开导入器时授予访问 `WorldFlipper` 的存储权限。
4. 点击或在导入器中选择 `三角色双模式-v1.wfpack`。
5. 导入器完成基线、客户端能力、签名、哈希、路径和空间检查。
6. 导入器把内容写入新的暂存目录；全部回读通过后才切换 `active.json`。
7. 成功页显示发行 ID、内容清单和“启动游戏”。
8. 游戏在飞行模式下读取活跃覆盖层，Mod 中心显示完整状态。

玩家不需要启动服务端、输入 IP、配置端口、运行脚本或手动复制零散文件。

## 5. 手机目录与覆盖层

### 5.1 目录结构

原始数据目录不改变：

~~~text
WorldFlipper/
├─ dummy/
│  ├─ info.json
│  ├─ download/production/
│  │  ├─ upload/
│  │  ├─ medium_upload/
│  │  └─ android_upload/
│  └─ modpacks/
│     ├─ active.json
│     ├─ client-capabilities.json
│     ├─ required-persistent-ids.json
│     ├─ staging/
│     ├─ quarantine/
│     └─ releases/
│        └─ <manifest-sha256>/
│           ├─ manifest.json
│           ├─ manifest.sig
│           ├─ complete.json
│           ├─ production/
│           │  ├─ upload/
│           │  ├─ medium_upload/
│           │  └─ android_upload/
│           ├─ dummy-overlay.json
│           └─ mode-variants.json
└─ save_haxe
~~~

release 目录名必须是小写 64 位 manifest SHA-256，不接受 manifest 自带的路径。`active.json` 只保存当前发行 ID、manifest SHA-256 和提交代数，不保存奖励领取状态或个人配置。`required-persistent-ids.json` 是导入器维护的单调只增兼容锁；它保存历次激活发行所提供 ID 的并集，不代表玩家实际领取状态。

### 5.2 读取优先级

不修改已有高风险 `FileReader` 方法。`DevConfig_gf_android` 在进程启动早期验证 `dummy/modpacks/active.json`，锁定 manifest digest，并把 `assetDirectories` 固定为：

1. `../modpacks/releases/<manifest-sha256>/production`。
2. `production`。

两者都相对现有 `WorldFlipper/dummy/download` 根解析，因此实际读取顺序为活跃 release、原始 production、APK 内置 bundle 回退。active digest 不得在进程运行中热切换；导入或设置变更成功后必须冷重启游戏，避免同一会话混用新旧 master 缓存。

同一逻辑路径的 hashed 文件名由逻辑路径决定。这里的 hash 是**逻辑路径哈希，不是文件内容哈希**；common、medium、android 是三个独立命名空间，即使相对 hashed 路径相同也不得跨根去重、移动或复用。覆盖层中的同根同名文件优先，因此可以替换完整 master 文件；新增素材则只在覆盖层出现。

三根映射必须始终保持：

| 内容类别 | 运行目录 |
|---|---|
| common | `production/upload/` |
| medium | `production/medium_upload/` |
| android | `production/android_upload/` |

禁止把 medium 或 android 文件扁平化到普通 upload。构建与导入回读都必须按逻辑路径分类复验。

### 5.3 首版完整表策略

`FileReader` 只选择第一个存在的完整文件，不会对两个同名 master 文件做行级合并；`RootMasterBinary` 的重复键也可能触发 C7051。因此 v1 不在运行时叠加 orderedmap 行。

作者端构建器以精确的干净 `1.4.54` 基线为输入，把本发行声明的行合入基线表，然后在 `.wfpack` 中携带生成后的完整替换文件。导入器只负责验证和安装这些文件，不在手机上实现一套新的 orderedmap 编译器。

每个 `.wfpack` 都是相对干净基线的小型、独立、累计 release：它不得依赖此前另一个 `.wfpack` 仍处于 active，也不得把多个 release 根叠加。这里的“增量”只表示相对原始约 10 GB 数据体积小，不表示跨包行级增量链。

以后若支持新的基础快照，必须针对该快照重新构建相应累计 `.wfpack`。不得把旧完整表覆盖到未知新版数据。

## 6. `.wfpack` 格式

### 6.1 容器根

`.wfpack` 是确定性 Zip64 容器，根必须恰好为：

~~~text
WFModPack/
├─ manifest.json
├─ manifest.sig
└─ payload/
   ├─ production/upload/<2hex>/<38hex>
   ├─ production/medium_upload/<2hex>/<38hex>
   ├─ production/android_upload/<2hex>/<38hex>
   ├─ dummy-overlay.json
   └─ mode-variants.json
~~~

拒绝绝对路径、`..`、反斜杠、符号链接、重复规范路径、大小写碰撞、未声明成员、压缩炸弹和根外文件。

`.wfpack` 不得携带或覆盖 `active.json`、`client-capabilities.json`、`required-persistent-ids.json`、`save_haxe`、staging marker 或任何既有 release 元数据。

### 6.2 manifest 最低字段

`manifest.json` 至少声明：

- `schema_version`、`release_id`、`release_version`、`created_at_utc`。
- `base_contract_id`、支持的基础 `info.json` 版本、关键表 SHA-256、关键路径集合摘要；每个“引用但不携带”的基础依赖还要声明逻辑路径、根类别、大小和 SHA-256。
- `client_contract_id`、所需 master/save schema、`required_client_capabilities`、最低/最高游戏 versionCode、允许的签名证书指纹。
- 三角色、两模式、15 把武器及其键范围。
- 每个完整替换表的逻辑路径、基线哈希、输出哈希和声明的键差异。
- 每个素材的逻辑路径、根类别、hashed 相对路径、大小和 SHA-256。
- `dummy-overlay.json` 与 `mode-variants.json` 的 SHA-256。
- 18 封邮件的 reward type、type ID、reserved mail ID 和 `mail_key`。
- `provides_persistent_ids`、本发行提供的 capability 与必须保留的上一发行内容 ID。
- 总成员数、总未压缩字节数、所需临时空间和最终空间。

manifest 使用 UTF-8、稳定键序和稳定换行。所有成员按规范路径排序，使相同输入可重复生成相同包。

### 6.3 签名

`.wfpack` 使用独立的 Ed25519 发布密钥签名唯一的 `canonical_manifest_bytes`。该字节串必须是磁盘中 `manifest.json` 的原始字节：严格 RFC 8785 JCS、UTF-8 无 BOM、所有字符串为 NFC、禁止浮点与超出安全范围的 JSON 数字；签名端和验证端都不得解析后用各自默认 JSON 库重新序列化。

`manifest-sha256 = SHA256(canonical_manifest_bytes)`。Ed25519 的签名输入固定为 ASCII 域分隔 `WFMP1\0` 后直接拼接这组字节；`manifest.sig` 只保存固定格式版本、`Ed25519` 算法名、key ID 和 Base64 签名字节。Python 构建器、Android 导入器和游戏客户端必须共享黄金向量，证明 digest 与签名结果完全一致。公钥与允许的 key ID 固定编入导入器和游戏 APK；私钥只存在于作者构建环境中。

玩家导入时不输入密码。游戏 APK 的 JKS 密码和 `.wfpack` 私钥都不得写进 APK、包、日志、manifest、命令行历史或仓库。

## 7. 基线与客户端能力检查

### 7.1 原始数据基线

为避免每次读取 10 GB，首版使用“严格关键基线”而非全盘内容哈希：

- `WorldFlipper/dummy/info.json` 的版本、`assetSizeKind` 和 SHA-256。
- 所有将被完整替换的 master 文件原始 SHA-256。
- 三个资源根存在且格式合法。
- 本包引用但不携带的基础逻辑路径必须存在，并与 manifest 声明的根类别、大小和 SHA-256 一致。
- 关键路径集合摘要与各根成员计数符合支持档案。

任一关键表已被修改、版本不匹配或必要依赖缺失时拒绝导入，并明确报告不匹配项。不得给用户提供“仍然强制安装”按钮。

### 7.2 游戏 APK 能力

游戏 APK 内置并在首次运行时镜像 `client-capabilities.json`，至少声明：

- 包名、versionCode、versionName、签名证书 SHA-256。
- 输入 APK 与主 SWF SHA-256。
- `offline_external_store_v1`、`offline_save_haxe_v1`。
- `atomic_save_haxe_v1`、`mod_overlay_roots_v1`、`dummy_data_overlay_v1`。
- `mod_preflight_before_master_v1`、`mod_center_v1`、`mod_state_v1`。
- `persistent_id_lock_v1`、`mod_claim_preflight_v1`。
- `abyss_equipment_gate_v1`、`seris_dual_form_v1`、`gerald_render_scale_v1`。
- `rush_variant_select_v1`、`treasure_fixed_variant_v1`、`runtime_difficulty_v1`。
- 每个客户端补丁 site 的补丁前后哈希。

导入器通过 Android PackageManager 检查已安装游戏的包名、versionCode 和签名，并读取 APK 内 capability manifest。兼容性以 `client_contract_id + APK 签名证书 SHA-256 + master schema + save schema + capabilities` 共同判断；`.wfpack` 的所有 required capabilities 必须是客户端能力集合的子集，否则拒绝导入。

共享存储中的 `client-capabilities.json` 只用于 Mod 中心展示、人工诊断和比较镜像是否漂移，绝不能授予兼容权限。导入器只信任 PackageManager 与已签名 APK 内嵌 manifest，游戏只信任自身内嵌 manifest；共享镜像被删改时忽略并由游戏重建，不能据此放宽任何检查。

### 7.3 启动前 release 预检

Mod 中心出现得太晚，不能承担启动恢复。游戏在 master 初始化之前必须：

1. 规范解析 `active.json`，拒绝非 64 位小写十六进制 digest。
2. 验证目标 release 的 manifest 签名、digest、`complete.json` seal、必需完整表和 dummy overlay。
3. 检查 `client_contract_id`、schema 和 required capabilities。
4. 以不解析任何角色/装备 master 的最小 save 预检读取 `modState.grants.claimed`，确认其 persistent ID 是 active manifest `provides_persistent_ids` 的子集。
5. 只在全部通过后把 release 根加入 `assetDirectories`；在构造 PlayerLogic、查询任何 Mod master ID 或建立邮件列表前完成上述检查。

`complete.json` 由导入器在全量成员哈希和结构回读通过后生成，至少封存 manifest digest、规范成员清单摘要、总成员数、总字节数和安装事务 ID。日常冷启动校验签名 manifest、seal 以及完整 master、`dummy-overlay.json`、`mode-variants.json` 等启动关键文件，不必每次重读全部美术资源；Mod 中心“重新检测”和每次导入/切换仍执行全量成员哈希。任一关键文件的时间、大小或哈希变化都会使快速校验失败并要求全量复验。

失败时停止进入会引用 Mod ID 的存档，显示专用修复页并提供打开导入器；不得静默回退纯净基础表后再让存档以 C8601 崩溃。

## 8. 导入事务

### 8.1 顺序

导入器按以下顺序工作：

首次安装时，只有在 `modpacks/` 不存在任何 active、release、quarantine 或事务历史的情况下，缺失的 persistent-ID 锁才等价于空集合；其他情况下缺失即进入修复流程。

1. 解析头部并限制 manifest 和 ZIP 中央目录大小。
2. 验证 manifest schema、Ed25519 签名和成员清单。
3. 检查游戏 APK 能力与原始数据关键基线；所需集合取 `required-persistent-ids.json ∪ 当前有效 active manifest.provides_persistent_ids`，新包的 `provides_persistent_ids` 必须是该并集的超集。若 active 集合不是锁集合的子集，锁已非法缩小，必须 fail closed 并先受控重建。
4. 检查临时空间、最终空间、同卷原子 rename 和文件/目录 `fsync` 能力；全部满足才开始写入。
5. 创建唯一 `modpacks/staging/<transaction-id>/`。
6. 按清单流式解压，每个成员边写边计算 SHA-256；不跟随链接。关闭每个文件后执行 `fsync`，任何一次失败都中止事务。
7. 对三根分类、hashed 路径、完整表回读、内容键闭包和 JSON schema 做第二次验证。
8. 同步 staging 内各级目录；根据已经回读通过的规范成员清单写入 `complete.json.tmp`，对文件 `fsync` 后原子改名为 `complete.json`，再同步 staging 根目录。
9. 把完整暂存目录在同一卷内原子提升到 `releases/<manifest-sha256>/`，随后分别 `fsync` 源 `staging/` 与目标 `releases/` 两个父目录。
10. 计算 `旧 required IDs ∪ 新 manifest provides IDs`，写入并 `fsync` 临时锁文件，原子替换 `required-persistent-ids.json`，再 `fsync` `modpacks/`。锁只增不减；此步后失败最多造成保守地要求更多 ID，不会允许危险降级。
11. 写入并 `fsync` `active.json.tmp`，原子替换 `active.json`，再 `fsync` `modpacks/`；这是内容激活的唯一提交点。
12. 重新读取 persistent-ID 锁、`active.json`、目标 manifest 与关键文件，全部一致后才显示成功结果。

### 8.2 失败语义

- 提交点之前失败：删除或保留可识别的 staging 供下次恢复，旧 `active.json` 不变。
- 提交点之后启动失败：保留旧 release 供维修，但 v1 不自动降级到可能缺少已领取内容的版本。
- 同一 release 已完整安装：验证现有目录后直接切换或报告已安装，不重复解压。
- 目标 digest 目录已存在但不完整：只有在新 staging 已全量验证、游戏已关闭后，才把这个精确目录同卷原子移动到 `quarantine/<digest>-<transaction-id>/`，并分别同步 `releases/`、`quarantine/` 两个父目录，再提升新目录；提升失败时按事务日志把原目录移回并再次同步两侧父目录。v1 不自动清空 quarantine。
- `release_id` 已存在但 manifest digest 不同：视为发行方复用了逻辑 ID，报告两个 digest 并拒绝覆盖；release 物理目录始终只按 digest 寻址。
- 游戏正在运行：允许完成 staging，但切换 active 前要求关闭游戏；切换成功后只能冷启动新进程。
- 目标存储不支持同卷原子改名、文件 `fsync` 或目录持久化屏障：拒绝激活，不退化为复制后直接改 active。

若 `active.json` 丢失或损坏，persistent-ID 超集检查仍以单调锁为准。锁缺失或损坏且设备上已有 modpacks 历史时必须 fail closed；修复只能只读解析 `save_haxe.modState.grants`，或取所有仍可验证的已安装 manifest 的 ID 并集来重建，绝不能用待导入旧包的较小集合覆盖锁。

原始 `dummy/download/production`、`info.json` 和 `save_haxe` 永不成为导入器写入目标。

失败清理只能删除同时具有本次 transaction nonce 和 importer marker 的 staging 目录，不能按模糊名称清理其他 release、quarantine 或用户文件。quarantine 的清理属于单独维护动作，必须逐个验证 digest、来源事务和当前 active 引用后再由用户确认。

## 9. 内容闭包

### 9.1 三角色

每个角色必须通过：

- character、character_text、status、awake status、ability、leader ability、action skill 和 mana node 的声明一致性。
- common、medium、android 三根完整分类。
- 37/37 必需资产、manifest/hash/seal 和三层一致门禁。
- 技能/PF DSL、立绘、头像、像素图、cut-in、android ATF 和必要 trim 数据检查。

`129999` 不得使用当前身份错误、实际指向 `139999/stella_summer_goddess` 的 Seris workspace。首版只能使用已冻结且身份正确的 published snapshot，或先重建真正的 `129999/seris_dragon_king` workspace 并重新通过角色流程。

### 9.2 深渊与武器

深渊闭包至少包含：

- rush event `700099`、所有可选 folder、15 轮任务和共享无尽轮。
- quest correction、field、zone、event list、奖励、代币 `2370099`。
- 商店 `9700101`–`9700115`。
- equipment/ability soul `8000101`–`8000115`、图片和文本。

武器门控继续只放行 `700099`、挑战 `2001` 和练习 `1`–`97`；官方关卡、挑战 `2002`–`2006` 和练习 `1001+` 不加载这些特殊词条。

现有只允许 folder 1/2 与固定 1–15+99 键的 validator 必须升级为 variant-aware。任何新增 folder、quest 或 correction 未被 manifest 闭包覆盖时，构建失败。

### 9.3 宝物域

宝物域闭包至少包含：

- `challenge_dungeon_event_quest[2001]`。
- 该行当前选中的 `tower_floor_id`。
- 所有预生成固定五层 `floor` 键及其 field/zone/素材依赖。
- 2002–2006 的原始映射不变证明。

构建门禁必须显式验证 `2001 -> mod_chain_*`。只携带 floor 而漏掉 challenge row 属于失败。

### 9.4 DummyRemote 数据覆盖

production 三根不能替代 `assets/cdndata/*.json` 或 DummyRemote 初始化数据。`dummy-overlay.json` 使用受 manifest 签名覆盖的独立窄 schema，只允许对明确白名单集合执行键级 upsert，v1 禁止 delete：

- 三角色的离线 character、character text 和 mana node 条目。
- 深渊、商店、奖励和模式初始化所需的离线镜像条目。
- 首次创建 Mod 状态所需的 release 默认值；不携带玩家资源或完成进度。

客户端在基础 LoadedData 建立后、任何受影响集合被业务逻辑读取前验证并应用这些 upsert。每个条目声明基础不存在或基础 SHA、输出规范哈希和主键；发生未知字段、重复主键、基础漂移或回读不一致时阻止进入游戏。

邮件生命周期按现有真实顺序适配：`DummyRemote.preparation()` 可以先空构造 `DummyMailRepository`，随后 `InitializeDummyRemote.setupData()` 加载玩家；玩家与 `modState` 就绪后先恢复所有 receiving journal，再依据 ledger 向已存在的仓库注入 pending 邮件。该恢复与注入必须发生在首次邮件列表读取、红点计算或 UI 订阅之前，不假设邮件仓库是在 setupData 之后才构造。

作者端可以从 `assets/cdndata/character.json`、`character_text.json`、`assets/character.json` 和 `assets/mana_node.json` 等来源生成该覆盖，但手机端只消费上述窄 schema，不直接解释任意服务端 JSON。

## 10. Mod 中心

### 10.1 最小菜单复用

不新增顶层枚举编号。复用当前 `OperationMenuDialog` 已存在的 BGM 槽位 `index 17`：

- 顶层按钮文案由“BGM 管理”改为“Mod 中心”。
- 继续打开现有 `OperationBgmManagerDialog`，内部扩展为 Mod 中心。
- 原“将 BGM 移动到循环前”功能保留在页面底部的“BGM 工具”分区。

这样避免新类注入和顶层 switch 漂移。内部类名暂不重命名，降低 SWF 重锚定范围。

### 10.2 页面分区

Mod 中心使用现有可滚动操作容器，按顺序显示：

1. **导入状态**：release ID、版本、基础数据、签名、三角色、两模式、15 武器状态；按钮“重新检测”“打开一键导入器”。
2. **内容邮件**：已领取、待领取、缺失数量；按钮“补发缺失邮件”“打开邮箱”。
3. **深渊连战 700099**：当前路线、seed、难度；按钮“重新随机”“难度设置”。
4. **宝物域 2001**：当前五层路线、seed、难度；按钮“重新随机”“难度设置”。
5. **BGM 工具**：保留原 BGM 调试按钮。

状态读取失败时页面仍可关闭，并显示明确错误；不得以空白、C8601 或通用“资源损坏”代替诊断。

## 11. 玩家 Mod 状态

### 11.1 唯一玩家状态

内容选择由共享存储 `active.json` 管理；玩家状态只存入 `save_haxe` 中的 `player.saveData.modState`：

~~~text
modState = {
  schemaVersion,
  packId,
  packVersion,
  packManifestDigest,
  grants,
  modes: {
    rush700099,
    treasure2001
  }
}
~~~

每个模式状态使用两阶段结构：

~~~text
ModeState = {
  active: ModeConfig,
  pending: PendingChange | null,
  lastKnownGoodHash,
  lastApplyError,
  recordsByConfigHash
}

PendingChange = {
  config: ModeConfig,
  resetIntent: none | rush_run | treasure_snapshot,
  expectedProgressHash
}

ModeConfig = {
  revision,
  routeRevision,
  difficultyRevision,
  routeCatalogVersion,
  routeId,
  routeSeed,
  routeHash,
  presetId,
  enemyLevel,
  hpPermille,
  atkPermille,
  timeLimitFrames,
  curseTier,
  configHash
}
~~~

`routeId` 只能引用签名 catalog；存档中的 field、zone、boss 或 floor 列表不可信，也不直接执行。HP/ATK 使用整数千分比，`1000 = 1.00x`；时限直接保存引擎帧，避免浮点和秒/帧往返漂移。

`configHash` 是 `packManifestDigest + modeId + routeHash + enemyLevel + hpPermille + atkPermille + timeLimitFrames + curseTier` 的规范哈希，不包含 seed 或 revision。重新随机只递增 `routeRevision`，修改难度只递增 `difficultyRevision`，两者都递增总 `revision`；未成功晋升 active 的 pending 不消耗 active revision。Mod 模式纪录只写 `recordsByConfigHash`，不写官方纪录槽；每个模式最多保留 64 组，当前配置不可驱逐，超限时移除最旧的非当前纪录。

不要把这些字段只放进会话级 `DummyRemote.rushEventData`；该对象每次构造都会重建。加载 `save_haxe` 后恢复 Mod 状态，运行态 Rush 对象从 active 配置 hydrate，并在 reset/select 后回写正式 player save。

玩家确认随机或难度时，第一次事务只写 `pending`、reset intent 和当时进度的 `expectedProgressHash`，不清除现有 run 或战斗快照，随后冷重启。逻辑资产加载完成后、任何 QuestRepository 或 AssetResolver 构建目标副本之前，客户端先在隔离内存对象中验证 route/config hash 并从不可变 catalog 完整物化；验证通过且进度 hash 未变化时，再把“执行 reset intent + pending 晋升 active”放入同一次原子 save_haxe 事务。事务成功后才让新配置进入 UI、预载和战斗，三者必须共享同一个 `configHash`。

物化、进度比较或最终保存任一步失败时，旧 active、旧 run/快照都保持不变；丢弃 pending 时只记录具体错误，不执行 reset intent。pending 存在期间禁止进入对应模式，避免玩家在两次事务之间改变被保护的进度。

邮件 ledger 不镜像到单独 JSON，避免奖励与领取标记跨文件不同步。

### 11.2 原子 save_haxe

现有直接覆盖写不能承担奖励账本和 pending/active 提交。离线 APK 必须把保存升级为同目录事务：

1. 序列化完整 LoadedData 到 `save_haxe.tmp.<nonce>`。
2. 关闭流并对临时文件执行 `fsync`，再重新读取，验证可反序列化、玩家 ID、modState schema 和内容哈希。
3. 以临时文件、`fsync` 和原子改名方式保留最近一次已验证的 `save_haxe.bak`，不得先截断现有备份。
4. 在同一卷内原子替换 `save_haxe`，随后 `fsync` 父目录；只有目录屏障成功才向调用方报告保存完成。
5. 启动时识别并恢复完整旧文件或完整新文件，绝不消费半写临时文件；恢复本身也走同一事务和目录屏障。

必须用真实 save_haxe 完成“读入 → 新增 modState → 保存 → 重启 → 再保存 → 再重启”往返；未知动态字段被丢弃或改型即阻断发布。

### 11.3 迁移

- 没有 `modState`：按当前 active release 创建默认状态，不改其他存档字段。
- schema 较旧：只执行 manifest 声明的前向迁移，迁移前保留内存副本，失败则不保存。
- pack version 更新：保留以稳定 grant key 记录的已领取账本；模式状态只有在新 manifest 声明 catalog/schema 兼容时继承，否则生成 pending 的标准预设与新路线，启动物化成功后再替换 active。
- schema 较新：旧 APK 只读显示“不支持的 Mod 状态版本”，不得覆写存档。

## 12. 18 封邮件

### 12.1 附件

每个内容发行固定声明 18 个 `mail_key`：

- 角色邮件 3 封：`129999`、`139999`、`149999`。
- 装备邮件 15 封：`8000101`–`8000115`。

角色使用现有角色附件类型，装备使用现有装备附件类型；每封只带一个附件、数量 1。玩家使用原生“全部领取”。

### 12.2 发行账本

当前 `DummyMailRepository` 的 mails、receive_time、history 和自增 ID 都只在会话内，不能作为领取凭据。v1 使用持久账本：

~~~text
grants[mail_key] = {
  persistentRewardId,
  mailId,
  state: pending | receiving | claimed,
  preReceiveCount,
  receiveNonce,
  claimedAt
}
~~~

`mail_key` 和 `persistentRewardId` 对同一个角色/装备跨累计 release 保持稳定，不能仅按 pack 版本换键后重新发放。manifest 为本发行分配一段全局保留且经构建注册表检查的 18 个固定高位 mail ID；不得调用每次启动从 1 开始的 `nextMailId()`。

初始化 DummyRemote、设置玩家之后：

- ledger 不存在：创建 pending 项并向邮箱加入该邮件。
- ledger 为 pending 且邮箱缺失：重新加入同一 mail ID。
- ledger 为 pending 且邮箱存在：不重复加入。
- ledger 为 claimed：不再发放。

领取开始前，先在原子 save_haxe 事务中把本次所选 grant 全部置为 receiving，并逐项记录领取前对应 master ID 的实例数量；装备按该装备 master ID 的持有实例数计数，不能读取通用装备总数或无关堆叠。原生“全部领取”共享一个 batch receive nonce，单封领取也使用唯一 nonce。只有原生领取逻辑确认对应奖励已写入玩家存档后，才把对应项改为 claimed，并把整批结果原子保存；不为 18 封邮件各做一套互不协调的临时文件。

如果应用在 receiving 阶段崩溃，玩家加载后、生成邮件列表前，恢复逻辑逐项比较当前实例数与 `preReceiveCount`：增加则完成 claimed；未增加则恢复 pending，并把恢复结果原子保存后才注入邮件。库存只能用于这次有前置快照的崩溃恢复，不能单独作为“玩家以前是否领过 Mod 邮件”的依据。

“补发缺失邮件”只修复 pending 且邮箱缺失的项，不重新发 claimed 附件；连续点击结果相同。

## 13. 路线随机

### 13.1 共同语义

- 随机只在玩家点击“重新随机”时发生。
- “重新随机”只改路线，“难度设置”只改难度。
- 选择结果写入 pending，原子保存后冷重启；启动早期物化成功才晋升 active。进本、失败、结算、返回和后续重启不改变 active 路线。
- 任一模式存在 pending 时，禁用进入该模式、再次随机和修改难度，只允许冷重启应用或放弃尚未提交的 pending；放弃也必须原子保存且不执行 reset intent。
- seed 由 active manifest digest、玩家存档稳定标识、模式 ID 和待提交的递增 `routeRevision` 派生；每次成功随机只增加一次 routeRevision，同一 ModeConfig 可复现。
- 路线从作者端预生成且已验证的方案池中选取，不在手机上运行 Python 生成器。
- 不使用 `__random__` 魔法头行，不在 `getTowerFloorValues` 中插入洗牌循环。

### 13.2 深渊 700099

首版预生成 32 条不同的 15 轮路线，每条对应一个合法 Rush folder variant，并明确声明无尽轮 `99` 的场地与诅咒组合。普通任务 ID 保持在 `700099xxx` 门控范围内，全部 route 的唯一任务键总数不得超过该保留区间；无尽任务只保留共享 ID `700099099`，启动时从选中 route variant 的不可变基线复制数值，不能为 32 条路线创建相互冲突的同键 master 行。

签名 catalog 可以保存全部 32 条定义，但运行时必须在 `RushEventLogic`、QuestRepository、选关 UI 和预载对象构造前投影成**唯一选中的一条 folder 路线**。未选中的 31 条只留在只读 catalog 中，不得出现在可选活动列表、奖励判断或当前进度查询里。

点击重新随机时：

1. 若当前有未结束的 700099 run，显示会清除本次路线进度的确认。
2. 从 31 条不同于当前路线的方案中确定性选出候选 route，准备带下一 routeRevision、seed、`rush_run` reset intent 和旧 run hash 的 pending。
3. 第一次原子保存只提交 pending，不调用 Rush reset；保存成功后要求冷重启。
4. 启动物化通过后，才在第二次原子保存中调用现有 Rush reset/select 语义，清除 `700099` 的 active folder、challenging round、played parties、endless played parties、next round 和未完成战斗快照，并同时晋升 active。它不清角色、武器、商店库存、代币、领取记录、官方 `700007` 或其他 Rush 活动；事务失败则旧 run 和旧 active 都保留。

最佳纪录按 `configHash` 隔离；换路线或难度后新配置从零记录，旧配置纪录保留但不参与当前比较。

### 13.3 宝物域 2001

首版从当前已验证的 136 层候选池预生成 128 条普通固定五层链，每条为独立 `mod_chain_vNNN` floor 键。单条链不重复层；相邻两次随机不得返回同一 variant。

重新随机后，把候选 `challenge_dungeon_event_quest[2001]` 的运行时 `tower_floor_id` 指向选中固定键，并把下一 routeRevision 与 variant 写入 pending。若存在 2001 未完成战斗快照，第一次事务只记录 `treasure_snapshot` reset intent 和旧快照 hash，不立即放弃；启动物化通过后，第二次原子事务才同时放弃该快照、晋升 active，且不清首通和已领取奖励。游戏加载 master 与 player save 后、任何选关或预载对象构建前重新应用该绝对值。

所有 `mod_chain_vNNN` 都是普通五层数组。不得写入 `__random__` 行，也不得在一次选关/预载/开战中二次抽样，因此规避当前 C8601 和预载路线不一致风险。

`BattleQuestBaseImpl.getTowerFloorValues` 和 `getTowerNoClearRankFloorValues` 保持原逻辑，不再插入 `if + 局部变量 + while/Math.random`。任何必要启动钩子都必须用 P-code/ABC 前后断言和真机金丝雀证明；反编译源码中“看起来存在”不算通过。

## 14. 难度

### 14.1 独立设置

深渊与宝物域分别保存难度。修改只对对应 Mod 模式生效，不影响官方关卡、练习、商店或玩家数值。

四档预设固定为：

| 模式 | 预设 | 敌人等级 | HP | 攻击 | 时限 | 诅咒 |
|---|---|---:|---:|---:|---:|---|
| 700099 | 轻松 | 60 | 0.70x | 0.70x | 1350 秒 | 关闭 |
| 700099 | 标准 | 80 | 1.00x | 1.00x | 900 秒 | 标准 |
| 700099 | 深渊 | 90 | 1.50x | 1.35x | 675 秒 | 深渊 |
| 700099 | 炼狱 | 100 | 2.25x | 1.75x | 450 秒 | 炼狱 |
| 2001 | 轻松 | 10 | 0.70x | 0.70x | 1800 秒 | 关闭 |
| 2001 | 标准 | 30 | 1.00x | 1.00x | 1800 秒 | 标准 |
| 2001 | 深渊 | 50 | 1.50x | 1.35x | 1350 秒 | 深渊 |
| 2001 | 炼狱 | 70 | 2.25x | 1.75x | 900 秒 | 炼狱 |

上述表是首发 `.wfpack` manifest 的确定值，不硬编码进 APK。构建器必须证明每条路线的 `safeEnemyLevelMax` 覆盖四档所需等级；不满足的路线不得进入签名 catalog。

### 14.2 高级设置

高级设置范围固定为：

- 敌人等级：整数 `1`–`min(100, route.safeEnemyLevelMax)`；构建期根据路线内全部 enemy master 可解析等级计算上限。
- HP 倍率：`0.10`–`20.00`，UI 最多两位小数，存为 `100`–`20000` permille。
- 攻击倍率：`0.10`–`10.00`，UI 最多两位小数，存为 `100`–`10000` permille。
- 时限：整数 `30`–`1800` 秒，存为 `1800`–`108000` 帧。
- 诅咒强度：关闭、标准、深渊、炼狱四个经过验证的模板，不允许任意编辑 DSL。

输入为空、NaN、Infinity、越界或精度非法时拒绝保存并指出字段，不静默截断。任一高级字段改变后，难度种类显示为“自定义”。

### 14.3 应用方式

运行时设置从每个 variant 的不可变基线复制后做绝对赋值，禁止在当前值上重复相乘：

- 700099：覆盖所选 route 的 enemy level、HP/ATK correction、时限和诅咒模板；若 run 已开始，第一次事务只保存带 `rush_run` reset intent、旧 run hash 和下一 difficultyRevision 的 pending，启动验证成功后的第二次事务才重置 run 并晋升 active。
- 2001：覆盖 quest 2001 的 enemy level、三类 HP/ATK correction、时限和诅咒模板，无需重新随机；若有未完成战斗快照，第一次事务只保存带 `treasure_snapshot` reset intent、旧快照 hash 和下一 difficultyRevision 的 pending，启动验证成功后的第二次事务才放弃快照并晋升 active。

两种模式都在第一次保存成功后冷重启并于启动物化阶段应用；任一步失败时旧进度和旧配置保持原样，不能留下已清进度但没有新难度的中间状态。

深渊最终值公式固定为：

~~~text
最终 HP = 路线基础 HP × hpPermille / 1000 × 该层诅咒 HP 因子
最终 ATK = 路线基础 ATK × atkPermille / 1000 × 该层诅咒 ATK 因子
最终时限 = min(用户时限, 该层诅咒时限上限)
~~~

诅咒档位只选择包内预生成且验证过的条件/法阵变体；手机端不执行 forge，也不缩放任意 DSL。

冷启动物化应用后立即回读内存值并刷新页面摘要；后续重启都从 `modState.active` 重新应用相同绝对值，不在当前进程热切换 master 派生对象。

## 15. 错误处理与可恢复性

- Mod 中心发现 active manifest 缺失、签名无效或文件不完整时，禁用邮件、随机和难度写操作，只允许打开导入器修复。
- 随机池缺少当前 variant、routeHash 或 configHash 不匹配时，不自动选择未知路线；不执行 reset intent，丢弃 pending，显示错误并保留 last-known-good active 与原进度。
- 设置应用中任一表或状态写入失败时，恢复该操作前的内存快照，不留下半套倍率。
- 邮件领取成功而 ledger 写入失败时，不报告领取完成；保存前重试账本更新并记录可诊断错误。
- `save_haxe` 不支持当前 modState schema 时只读，不覆盖用户存档。
- 游戏崩溃、断电或导入器被杀死不得改变原始 10 GB 数据或旧 active release。

### 15.1 更新与回滚限制

一旦某发行可能已经发放角色或武器，导入器要求后续可激活发行的 `provides_persistent_ids` 至少是 `required-persistent-ids.json` 单调集合的超集，并同时覆盖当前 active manifest；这是无需依赖 active 完整可读的保守门禁。游戏启动时再用 `grants.claimed` 做第二道精确校验。v1 不提供“关闭 Mod”或切换到缺少这些 ID 的 release，避免存档引用不存在的角色/装备时 C8601。

旧 release 目录用于失败分析和受控维修，不作为普通用户的自由降级按钮。安全回滚只能切到 manifest 声明仍包含所有 `grants.claimed` 内容的累计版本；数值回退发布更高版本的兼容反向包，不移除核心 Mod。

## 16. 后续 APK 更新

导入器不能在手机上自动修改和重签未来 APK。作者发布新游戏 APK 时必须：

1. 以新 APK/SWF 为基线重新发现并锁定 patch site。
2. 保留离线 DummyRemote、共享存储、`save_haxe` 和手动保存能力。
3. 重锚定覆盖层根、Mod 中心、邮件账本、路线选择和运行时难度。
4. 重锚定深渊武器门控、Seris 9 个双形态 site 和 Gerald 3 个缩放 site。
5. 输出新的 `client-capabilities.json` 并回读全部方法体哈希。
6. 沿用同一 APK 发行证书并递增 versionCode，允许用户覆盖安装。
7. 在兼容 `.wfpack` 上执行完整设备回归。

任一 patch site 不是精确单一匹配，或能力声明与实际 SWF 不一致时停止构建。不得把旧整份 SWF 覆盖到新 APK。

## 17. 构建与验证门禁

### 17.1 作者端构建

构建流水线按以下边界分开：

1. **内容闭包构建器**：从干净 `1.4.54`、三个角色的冻结发布证据、模式和武器声明生成完整替换表与新增素材。
2. **variant 构建器**：确定性生成 32 条深渊路线和 128 条固定宝物域五层链。
3. **wfpack 构建器**：生成 manifest、签名、确定性 Zip64 和校验报告。
4. **游戏 APK 构建器**：对离线基座应用 fail-closed 客户端补丁并签名。
5. **导入器构建**：只嵌入公开验证材料、支持档案和公钥，不嵌入内容私钥或 APK keystore。

输入、暂存和输出目录分离。所有构建只写新的忽略目录；不直接写 live store、`.cdn`、源 APK 或用户 WIP。

### 17.2 自动内容验收

至少验证：

- 三角色身份正确、37/37、三层一致、所有 manifest/hash/seal 通过。
- common/medium/android 根分类完全正确。
- 18 个邮件声明唯一，mail ID 与 mail_key 无冲突。
- `700099` 的 32 个 route/folder variants、每条 15 轮、唯一共享 `700099099` 无尽任务及其 32 份可投影变体、correction、奖励、代币和商店闭包完整。
- `8000101`–`8000115` 的装备、能力魂、图片、文本和门控声明完整。
- `2001` 显式指向合法 `mod_chain_*`；128 条链均为五层且依赖闭包完整。
- 2002–2006 与干净基线完全不变。
- 所有完整替换表的基线哈希、输出哈希和声明键差异一致。
- `.wfpack` 签名、成员哈希、路径规范、Zip64 边界、压缩比和秘密扫描通过；Python/Android/客户端对 canonical manifest 黄金向量的 digest 与 Ed25519 结果逐字节相同。
- 导入器的重复导入、错误基线、错误 APK、错误签名、空间不足、中断恢复和 release 冲突测试通过；对每个文件/目录持久化屏障注入失败时都不得推进 active。
- active release 只允许一个累计根；manifest digest、`base_contract_id`、`client_contract_id`、persistent-ID 单调锁、active/锁丢失修复和启动前 seal 检查通过。
- 篡改共享 `client-capabilities.json` 不能授予任何能力；导入器和游戏仍以各自受信内嵌 manifest 判定。

### 17.3 APK/SWF 静态验收

- 输出仍为 DummyRemote、socket=0、isFullPackage=true。
- MANAGE_EXTERNAL_STORAGE、外置资源和 `save_haxe` 读写链路存在。
- 覆盖层只在 active release 完整时启用，原始根仍可回退。
- `DevConfig.assetDirectories` 的首根为规范化 active digest，`FileReader` 两个 Tower 方法保持原逻辑。
- 顶层菜单 index 17 仍可打开扩展后的对话框；原 BGM 功能仍存在。
- 邮件领取成功后才写 claimed ledger。
- save_haxe 临时写、回读、原子替换、备份恢复和 modState 两次往返通过。
- 玩家加载后先恢复 receiving、再注入邮件且早于首次列表读取；仓库先空构造的现有顺序不改变结果。
- 路线和难度只匹配 `700099` 与 `2001`；运行态 Rush 只暴露 active route，未选中的 31 条不可被 UI、奖励或预载观察到。
- 深渊武器门控、Seris 双形态和 Gerald 缩放的最终方法体全部通过 P-code/ABC 回读。
- APK zipalign、apksigner 和证书指纹验证通过。

### 17.4 飞行模式设备验收

必须使用一个不影响原游戏的新 Android/MuMu 实例：

1. 放入支持的原始 `WorldFlipper` 数据，安装两个 APK，不运行任何本地服务。
2. 导入合法 `.wfpack`，确认只新增 `modpacks/`，原始数据哈希不变。
3. 开启飞行模式冷启动，进入城镇和 Mod 中心；所有内容状态为完整。
4. 确认首次出现 18 封邮件，点击“全部领取”，角色和武器准确到账。
5. 保存、强停、重启，确认邮件不重复、领取账本和物品仍在。
6. 人为移除一封 pending 邮件后使用“补发缺失邮件”，确认只恢复缺失项。
7. 对单封领取和“全部领取”分别做故障注入：保存 receiving 后奖励前、奖励写入内存后最终保存前、奖励已持久化但 claimed 前、claimed 保存后四个窗口强杀；每项最终只能到账一次，装备按对应 master ID 实例数恢复。
8. 分别验证三角色详情、编队、战斗、Seris 双形态和 Gerald 比例。
9. 验证 15 把武器在 700099、2001、练习 1–97 生效，在官方关卡、2002 和练习 1001 不生效。
10. 深渊重新随机两次：运行态只出现选中路线、路线改变、难度不变；第一次 pending 保存后旧 run 仍完整，启动验证通过后第二次事务才把清 run 与 active 晋升共同提交，其他活动和已得奖励不变。重启后路线保持；至少完整打通一条 15 轮和该路线的共享 ID 99 无尽层。
11. 宝物域连续执行“随机 → 冷重启 → 进入 → 退出”至少 20 次：每次为固定五层、无 `__random__`、连打与预载共用同一 configHash；再次随机前跨三次重启仍保持。
12. 两个模式分别验证四档预设、一个合法高级设置和全部高级边界拒绝行为；存在 pending 时再次随机或改难度必须禁用。
13. 分别在 pending 第一次写入前后、启动物化后、第二次事务清进度/晋升 active 前后强杀游戏；物化失败或第二次保存失败时旧配置与旧进度必须完整，成功时只能得到已清进度的完整新配置。
14. 在导入每个文件/目录同步屏障前后强停导入器，确认旧 active release 仍能启动；恢复后可完成同一事务。
15. 安装兼容的后续 `.wfpack`，确认存档、claimed ledger、角色、武器和设置迁移正确，并拒绝不满足 persistent ID 超集的降级包。
16. 分别损坏 active、persistent-ID 锁和共享 capability 镜像，确认前两者 fail closed 并走受控修复，后者不能改变授权结论。

设备日志不得出现 C8601、C8016、F2058、缺 field/zone/DSL、预载错配或黑屏。

只通过静态检查、manifest 检查或 P-code 可见性不算完成；必须保留真实设备截图、关键日志、前后 active 状态和存档重启证据。

## 18. 实施分段

实现按共享接口分为四个里程碑，每个里程碑独立验证后再进入下一个：

1. **M1：wfpack 与导入事务**——格式、构建器、签名、Android 导入器、persistent-ID 单调锁、覆盖层 active 指针和持久化屏障。
2. **M2：客户端覆盖层与 Mod 中心基础**——读取 active release、状态页、持久 modState、18 邮件。
3. **M3：两模式运行时控制**——32 条深渊路线、128 条宝物域链、重新随机、四档与高级难度。
4. **M4：整合发行与设备验收**——APK 重锚定、兼容更新、飞行模式完整矩阵和最终发行目录。

里程碑可以使用独立测试夹具和临时合成 store；未到 M4 不写 live store、不发布 CDN、不替换用户现用 APK。

## 19. 完成定义

只有同时满足以下条件才可称为“一键导入版完成”：

- 普通玩家不使用电脑、ADB、服务端、IP 或脚本即可导入。
- 原始约 10 GB 数据未被原地修改，失败导入不会破坏上一版。
- Mod 中心准确显示状态，并能幂等补发 18 封邮件。
- 两个模式都能主动重新随机并跨重启保持固定路线。
- 两个模式的四档预设和高级设置均真实影响战斗且不污染官方内容。
- 三角色、15 武器、700099、2001、邮件、保存和更新全部通过飞行模式真机验收。
- 构建产物不含私钥、密码、个人存档、绝对本机路径或未声明调试文件。
- 后续 APK 更新有明确的 fail-closed 重锚定和同签名覆盖升级路径。
