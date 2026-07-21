# World Flipper 国服离线 Android 整合包设计

日期：2026-07-20

状态：方案方向已获用户批准，待书面规范复核

适用项目：StarPoint CN / World Flipper CN 离线客户端与资源工具链

## 1. 目标

把当前已经完成的新模式、新武器和新角色整理成一个不依赖服务端、局域网或伴随程序的 Android 离线发行包。接收者只需安装 APK，并把一个数据 ZIP 解压到手机共享存储根目录，即可在飞行模式下启动和游玩。

发行内容固定为：

- 深渊连战模式 700099，共 15 轮，使用深渊代币 2370099。
- 深渊专属武器 8000101–8000115，共 15 把。
- 赛瑞斯 129999、史黛拉 139999、杰拉德 149999。
- 当前手机资源快照 1.4.196。
- 基于现有离线 APK 的 DummyRemote、本地结算和 save_haxe 手动存档能力。

干净首次启动时保留原始初始角色，并额外拥有 129999、139999、149999 三名自制角色。15 把武器不预先发放，继续通过深渊模式和兑换商店取得。

## 2. 非目标

- 不启动或携带 Node/Fastify 服务端、localhost 服务、局域网地址或一键部署脚本。
- 不把 v2 RealRemote/LAN APK 改成离线版。
- 不把个人 save_haxe、dummy_save.json、账号标识或应用私有数据放入发行包。
- 不修改、覆盖或清理当前仓库里的角色、模式和资产 WIP。
- 不修改源 APK、弹国服当前 store 或历史单机数据包；所有变化只发生在独立暂存区和最终输出目录。
- 不在本设计中上传、公开分发或删除任何历史文件。

## 3. 已确认的基线

### 3.1 APK 基线

输入 APK 为：

    C:\Users\12101\Downloads\base.apk.1

它已经具备完整离线运行链路：

- 启动配置为 DevConfig_individual。
- RemoteKind 为 DummyRemote，socket 为 0，sdkDummy 为 true，支付为 DummyPayment。
- isFullPackage 为 true，启动与结算不依赖 HTTP。
- 外置资源根为共享存储中的 WorldFlipper/dummy/download。
- Android manifest 含 MANAGE_EXTERNAL_STORAGE。
- 启动读取 WorldFlipper/save_haxe；游戏内“保存”按钮把当前 LoadedData 写回该文件。

因此实现必须在 base.apk.1 上合并新功能，保留它的 APK wrapper、manifest、DEX、native 库、离线配置和存档逻辑。现有 v2 APK 的活动配置是 RealRemote 和 LAN host，且没有 save_haxe 读写补丁，不作为发行底座。

### 3.2 数据基线

弹国服中的旧单机 ZIP 含 137,820 个规范 hashed-store 文件。当前已整理 store 含 138,289 个规范 hashed-store 文件，是旧 ZIP 的严格路径超集：

- upload：113,822
- medium_upload：23,458
- android_upload：1,009
- 旧包独有路径：0
- 当前 store 新增路径：469

当前 store 中最后一段 1.4.195 → 1.4.196 的 12 个 common 文件与发布档案逐项 SHA-256 一致，因此 1.4.196 是实际内容快照，不只是版本标记。

APK 自带的 bundle.zip 与弹国服外部 bundle.zip 字节一致。外置数据包不重复携带 bundle.zip，缺少的基础资源仍由 APK 内置 bundle 回退提供。

## 4. 采用方案

采用“离线 base APK 定点合并 + 当前三层 store 冻结快照 + 单一 ZIP 导入”的方案。

选择该方案的原因：

1. 离线、结算和存档能力已经在 base.apk.1 中验证，不需要重新实现网络替身。
2. 新模式、新角色和缩放补丁可以在 base SWF 上进行 fail-closed 定点合并，避免更换 wrapper 后丢失共享存储权限。
3. 当前 store 已经覆盖旧离线数据和新增 469 个资源路径，可直接作为完整快照基础。
4. APK 与数据 ZIP 分离，后续只更新其中变化的一侧即可；接收者仍只有一次解压操作。

最终目录固定为：

~~~text
WF离线整合版/
├─ WorldFlipper-离线整合版.apk
├─ WorldFlipper-数据-1.4.196.zip
├─ 导入说明.txt
├─ build-manifest.json
└─ SHA256SUMS.txt
~~~

构建输出位于被 Git 忽略的：

    out/wf-offline-android/1.4.196/WF离线整合版/

## 5. APK 合并契约

### 5.1 允许变化的范围

APK 重打包只允许以下变化：

- 游戏 SWF 中本设计列出的新模式武器门控、赛瑞斯双形态、角色渲染缩放和资源显示版本。
- APK 重新打包产生的容器元数据、zipalign 结果和签名块。

下列内容必须保持基线语义不变：

- package name、versionCode、versionName 和应用标签。
- Android 权限，特别是 MANAGE_EXTERNAL_STORAGE。
- DEX、native 库和 AIR wrapper。
- DevConfig_individual、DummyRemote、socket=0、sdkDummy=true、DummyPayment、isFullPackage=true。
- WorldFlipper/dummy/download 资源读取路径。
- WorldFlipper/save_haxe 的启动读取和“保存”写回。

构建器对输入 APK 和关键方法体使用 SHA-256 基线锁。输入哈希或任一关键方法体不匹配时立即停止，不进行模糊覆盖。

### 5.2 深渊模式与武器补丁

把现有 abyss-mode-equipment 客户端逻辑合并到 base SWF，使 8000101–8000115 的特殊词条只在已批准的模式范围生效，并保留 700099 的入口、战斗和本地结算链路。

既有功能契约不在本次重新定义：深渊连战 700099、代币 2370099、15 把武器及其商店配置继续以已批准的深渊设计为准。离线整合构建只负责把已经完成的逻辑和数据完整带入发行物。

### 5.3 赛瑞斯补丁

赛瑞斯双形态补丁共 9 个 patch site：

- 其中 7 个 site 与 base 基线哈希完全一致，复用现有 fail-closed patch。
- BattleCharacterLogic.resolvePathCollection 和 getPowerFlipAction 必须针对 base 重新锚定并做三方合并。
- MemberImpl.startPowerFlip 与 resolveConditionalKind 已确认兼容，仍需在输出上复验。

任何 site 的匹配数不是精确的 1，或补丁后方法体校验失败，整个 APK 构建失败。不得用整类覆盖或忽略哈希的方式强行生成 APK。

### 5.4 角色缩放补丁

PixelArt、MemberView 构造器和 CharacterCellView.drawWithAdvanceFlag 三个缩放点与 v2 不同；base 本身还有 SCALE_RENDERER 变体。实现必须以 base 为共同祖先做三方合并，只加入尊重 frame/defaultScale 的缩放行为，不覆盖 base 的既有渲染逻辑。CharacterCell 构造器不含角色 id、scale 或渲染矩阵，不是合法补丁点；列表/编队补丁必须位于 CharacterCellView 的原矩阵赋值之后。官方 defaultScale=6 时该计算保持无感，自制角色则保留资源声明的比例。

验收同时覆盖：

- 149999 的战斗、编队和角色列表比例。
- 129999 的双形态素材与战斗演出。
- 139999 的普通显示和技能素材。

### 5.5 资源版本

base APK 的原始 fullResourceVersion 为 1.4.54；本发行包将输出 APK 的 fullResourceVersion 精确改为 1.4.196，并保持 isFullPackage=true。

该变化只同步客户端显示/报告的完整资源版本，不引入网络版本检查。构建器必须断言：

- 输入值 1.4.54 精确出现于预期配置位置一次。
- 输出值 1.4.196 精确出现在该位置。
- DummyRemote 和 isFullPackage 路径未改变。

build-manifest.json 同时记录：

- source_apk_full_resource_version = 1.4.54
- output_apk_full_resource_version = 1.4.196
- content_snapshot_version = 1.4.196

三个字段不得混为一个“资源版本”字段。

### 5.6 签名

修改后的 APK 使用专用且稳定的离线发行签名。默认私钥位置为：

    %USERPROFILE%\.wf-offline-release\wf-offline-release.jks

私钥不在 out、work、仓库或最终包内生成和保存。密码只通过安全环境变量 WF_OFFLINE_KEYSTORE_PASSWORD 或交互式输入传入，不写入命令行、日志、manifest 或说明文件。

同一签名必须用于以后的离线整合版更新。由于它与原 APK 或其他个人构建的签名可能不同，导入说明必须说明：签名不一致时先备份 WorldFlipper/save_haxe，再卸载旧 APK、安装新 APK 并重新授权共享存储；共享存储的数据 ZIP 无需部署服务端。

签名顺序固定为：去除旧签名条目 → 重打包 → zipalign → apksigner 签名 → apksigner verify --verbose --print-certs。

## 6. 数据 ZIP 契约

### 6.1 唯一合法根结构

ZIP 使用 Zip64，根目录必须恰好是 WorldFlipper/，不得出现外层发行目录，也不得形成 WorldFlipper/WorldFlipper 双层嵌套。

~~~text
WorldFlipper/
└─ dummy/
   ├─ info.json
   └─ download/
      ├─ .empty
      └─ production/
         ├─ upload/<2hex>/<38hex>
         ├─ medium_upload/<2hex>/<38hex>
         └─ android_upload/<2hex>/<38hex>
~~~

三种源到 ZIP 的映射固定为：

| 源类别 | ZIP 目标根 |
|---|---|
| common | WorldFlipper/dummy/download/production/upload/ |
| medium | WorldFlipper/dummy/download/production/medium_upload/ |
| android | WorldFlipper/dummy/download/production/android_upload/ |

已有 build_three_char_release_patch.py 把 common、medium、android 全部写进 production/upload 的行为是已知缺陷。正式构建前必须先增加失败测试并修复映射；不得把旧的错误 threechar0719 edge ZIP直接作为数据源。

### 6.2 成员白名单

三个资源根只接受以下严格格式：

    <小写两位十六进制目录>/<小写三十八位十六进制文件名>

除 info.json 和 .empty 外，任何不符合格式的成员都使构建失败。明确排除：

- .bak、.bak-*、.bak-wfmod-*、.bak-wfquest-*、.bak-charfields-*。
- .tmp、.part、partial_downloaded.json。
- dummy_save.json、save_haxe。
- keystore、jks、pem、密码文件、私钥或构建日志。
- bundle.zip 及其外部副本。

info.json 使用已验证的当前快照内容，version 必须为 1.4.196。.empty 固定写为一个 ASCII 字符 0，与历史可用单机包保持兼容。

### 6.3 快照一致性

正式暂存区的 hashed 路径集合必须与当前规范 store 的 138,289 个路径完全相等。旧单机 ZIP 的 137,820 个路径必须全部包含，新增路径数必须为 469。

除“初始玩家三角色覆盖”明确列出的逻辑资源外，暂存区中与当前 store 同路径的文件必须逐项 SHA-256 相同。构建 manifest 记录每个 ZIP 成员的：

- 相对路径。
- 未压缩字节数。
- SHA-256。
- 来源类别 common、medium、android 或 generated-marker。

成员按路径字典序写入，时间戳、权限和 ZIP 属性固定，使同一工具版本和相同输入可重复生成相同结果。

### 6.4 干净初始玩家

在独立暂存区中对 DummyRemote 使用的 Player ID 1000 初始 master 做最小覆盖：

- 保留原始初始角色和原始初始资源。
- 新增 129999、139999、149999 各一名，使用与普通新获得角色一致的初始等级、觉醒和能力状态。
- 不自动改写队伍，不预装能力魂，不预发 8000101–8000115。
- 不改变其他玩家、关卡进度、货币或商店购买记录。

覆盖通过现有 master 解析/序列化链路生成，不直接修改未知二进制偏移。写回后必须重新解析，并断言角色集合恰好新增这三个 ID，其他字段保持不变。源 store 不被修改。

该行为只保证没有既有 save_haxe 的干净首次启动。若设备已有 WorldFlipper/save_haxe，APK 会优先加载现有存档；发行 ZIP 既不覆盖也不删除它。

### 6.5 新内容完整性

数据预检必须在打 ZIP 前验证：

- rush_event 700099 存在且有 15 轮可达任务。
- 活动代币 2370099、对应奖励和兑换商店存在。
- equipment 8000101–8000115 共 15 条，名称、词条、图标映射和商店商品完整。
- character 129999、139999、149999 的角色表、技能、能力、文本和资源路径完整。
- 三名角色当前发布资产通过既有 character flow 的 manifest/hash/seal 和 37/37 必需资产门禁，或通过等价的已发布快照验证；缺任何证据都停止构建。
- 三层 common/medium/android 目标根保持正确，不允许把 89 个 medium/android 成员扁平化到 upload。

## 7. 构建流程与错误处理

构建是 fail-closed、只写新目录的流水线：

1. 预检输入 APK、工具版本、JDK/Android build-tools、签名配置和磁盘空间。
2. 扫描三个 store 根，生成规范路径集合、来源清单和源哈希。
3. 在唯一暂存目录复制/链接快照，并应用 Player 1000 最小覆盖。
4. 对 base SWF 依次合并深渊、赛瑞斯、缩放和资源版本补丁。
5. 重打包、zipalign、签名并验证 APK。
6. 按固定顺序生成 Zip64 数据包和全成员 manifest。
7. 先冻结 APK、数据 ZIP、导入说明和 build-manifest.json，再为这四个文件生成 SHA256SUMS.txt，组成最终五文件目录。
8. 从最终 ZIP 重新读取全部成员，复算哈希并运行静态内容检查。
9. 通过真机/模拟器飞行模式验收后，把唯一暂存目录原子提升为最终目录。

任一步失败时：

- 不生成“成功”manifest，不覆盖上一次成功输出。
- 保留一份不含秘密的错误摘要，明确失败阶段、期望值和实际值。
- 不自动回退到旧 APK、旧 store、模糊 patch 或宽松路径过滤。
- 不删除用户源数据、历史包或当前 WIP。

## 8. build-manifest.json

build-manifest.json 至少包含：

- schema_version 和 build_id。
- UTC 构建时间、Git commit 和 dirty-worktree 标记。
- 输入 APK 的文件名、字节数和 SHA-256；不记录本机绝对路径。
- APK 包名、版本、离线配置断言、补丁组件版本和每个 patch site 的前后哈希。
- 源/输出 APK fullResourceVersion 与内容快照版本。
- 三个 store 的成员数、总字节数和根映射。
- 138,291 个数据 ZIP 成员的路径、大小、SHA-256 和来源类别。
- Player 1000 覆盖前后摘要，只记录角色 ID 差异，不记录个人数据。
- APK 签名证书 SHA-256 指纹，不记录私钥路径或密码。
- 最终 APK、数据 ZIP 和导入说明的 SHA-256；build-manifest.json 自身的哈希只写入随后生成的 SHA256SUMS.txt。
- 所有自动验证门禁及其通过/失败状态。

manifest 必须使用 UTF-8、稳定键顺序和换行格式。SHA256SUMS.txt 使用二进制模式兼容格式，并覆盖 APK、数据 ZIP、导入说明和 build-manifest.json。

## 9. 导入说明

导入说明.txt 面向普通 Android 用户，固定写清：

1. 可选：按 SHA256SUMS.txt 校验下载文件。
2. 备份手机共享存储中的 WorldFlipper/save_haxe；新用户没有该文件可跳过。
3. 安装 WorldFlipper-离线整合版.apk。若提示签名冲突，先确认已备份存档，再卸载旧版本。
4. 授予应用“所有文件访问权限”。
5. 把 WorldFlipper-数据-1.4.196.zip 直接解压到手机共享存储根目录，例如 /storage/emulated/0/。
6. 最终路径必须是 /storage/emulated/0/WorldFlipper/dummy/download/production/，不能放在 Download 下，也不能多套一层 WorldFlipper。
7. 开启飞行模式后首次启动，用此方式证明不需要服务器。
8. 游玩后在游戏菜单点击“保存”；仅退出游戏不会替代这一步。

说明还要区分：

- 干净首次启动：自动获得三名自制角色。
- 已有 save_haxe：继续读取原存档，数据 ZIP不会覆盖个人进度；是否拥有新角色由该存档决定。

## 10. 验收门槛

### 10.1 自动静态验收

- APK 输入哈希和所有 patch site 基线完全匹配。
- 输出仍为 DummyRemote、socket=0、isFullPackage=true。
- MANAGE_EXTERNAL_STORAGE 和 save_haxe 读写链路存在。
- 输出 fullResourceVersion 为 1.4.196。
- APK仅在允许范围内变化，DEX/native/manifest 关键语义未漂移。
- apksigner 和 zipalign 验证通过，签名证书指纹与配置一致。
- ZIP根只有 WorldFlipper/，没有绝对路径、..、反斜杠或双层根。
- hashed-store 数为 138,289，marker 后 ZIP总成员数为 138,291。
- 旧包路径遗漏为 0，新增路径为 469。
- 所有成员哈希复算一致，敏感文件扫描为 0。
- 700099、2370099、8000101–8000115、129999、139999、149999 的数据和资源检查通过。

### 10.2 飞行模式设备验收

必须在未运行任何伴随服务的 Android 设备或 MuMu 上完成：

1. 清理目标应用的测试存档，安装发行 APK 并授予共享存储权限。
2. 解压数据 ZIP，随后开启飞行模式并冷启动。
3. 确认首页、编队和角色列表可进入，三名自制角色均在干净初始账号中。
4. 分别把 129999、139999、149999 加入队伍并进入战斗。
5. 验证 129999 双形态、技能、强化弹射和结算无崩溃。
6. 验证 149999 在角色列表、编队与战斗中的比例正确。
7. 进入 700099，完成至少一轮，确认 15 轮结构、奖励和代币 2370099。
8. 打开兑换商店，确认 15 把武器全部显示；取得并装备至少一把，验证模式内生效、非白名单模式不加载特殊效果。
9. 在菜单点击“保存”，强制停止应用并重新启动，确认角色、奖励、武器和进度从 save_haxe 恢复。
10. 整个过程保持飞行模式，确认无服务端部署、端口监听或网络恢复步骤。

只有自动静态验收和飞行模式设备验收都通过，发行目录才标记为可交付。

## 11. 安全、回滚与可维护性

- 构建开始前记录源 APK 和三个 store 根的哈希摘要；完成后复验源输入未变化。
- 最终输出进行秘密扫描，明确阻止当前 work 中历史 keystore 和 keystore-pass.txt 进入包内。
- 不自动删除已经发现的历史私钥文件；清理需要用户另行明确授权。
- 每次发行保留 build-manifest.json、SHA256SUMS.txt 和签名证书指纹，未来版本沿用同一签名。
- APK 补丁组件、数据快照和初始玩家覆盖分别有独立测试，后续可只替换变化部分。
- 设备回滚依赖用户事先备份的旧 APK、WorldFlipper 数据目录和 save_haxe；发行构建本身不修改源文件，因此桌面侧回滚只需停止使用新输出。

## 12. 完成定义

本任务完成必须同时满足：

- 最终目录只有约定的五个发行文件，不含 server、Node、调试导出或秘密。
- APK 在飞行模式下独立启动、战斗、结算、手动保存和重启读档。
- 数据 ZIP 一次解压后路径正确，当前 1.4.196 快照无遗漏。
- 深渊模式、15 把武器和三名新角色的静态与设备验收全部通过。
- 干净初始账号拥有三名新角色，个人存档不被打包或覆盖。
- 构建过程可重复、遇到基线漂移会停止，并留下足够的非敏感证据供复核。
