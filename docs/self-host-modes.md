# 自建服 · 玩「深渊连战 + 15 把深渊武器 + 三自制角色」完整指南

面向**已经有(或能自己搞到)一套能跑的 WF CN 私服**、想在其上加载两个自制模式、深渊武器和三位自制角色(苍海龙王·赛瑞斯 / 夏日女神·史黛拉 / 白狼骑士·杰拉德)的人。本 mod 只提供**增量**(数据 + 客户端补丁),不含官方基础 CDN。

> **走错门了?**
> - **从零开一台服** → 先看 [README](../README.md) 的「我该下载什么」三步、跑
>   [`deploy.ps1`](../deploy.ps1)(自动装 Git/Node → clone → 构建 → 起服 → 自检),再回本文。
>   图文向的部署走 [`docs/部署攻略.md`](部署攻略.md)。
> - **只是要用别人给的 mod 分享包** → 看 [`mod-tools/docs/分享包收方指南.md`](../mod-tools/docs/分享包收方指南.md)
>   (放文件的位置、`requires.json` 怎么读)。**但先回本文「通用桥接」一节判一下你的血统**
>   ——外血统直接整表替换会砸掉你自己的活动数据。
> - **本文**讲的是:把本仓库的模式/武器/角色增量装进一台**已经能跑**的私服,以及卡链时怎么救。

## 先备齐

| # | 东西 | 说明 |
|---|---|---|
| 1 | 一台 Linux 服务器 + 一个域名 | Node ≥ 20;联机/CDN/证书需要域名(纯本地内网玩可简化,见步骤 3) |
| 2 | 本仓库 `release/modes-20260714` 分支 | **本 mod 的全部增量**:两模式+武器 masterdata(`assets/*.json`,服务端直接读)+ `client-patch/` 客户端改造工具 |
| 3 | **CN 基础 CDN(~11GB)自备** | 官方源 `shijtswydl.leiting.com` **已停服**,需自行从 WF 私服圈/现有部署获取,放到 `.cdn/cn/`。**服主不分发这个,只发上面的增量**;已有能跑的 WF CN 私服的人此项已具备 |
| 4 | 官方 CN 客户端 APK(1.8.1)+ FFDec + keystore + Android build-tools | 自己重打客户端用(步骤 4) |

---

## 步骤

### 1. 拿代码

```bash
git clone -b release/modes-20260714 https://github.com/kuronzzhan-droid/startpoint-cn.git starpoint-cn
cd starpoint-cn && npm install
```

> 必须是 `release/modes-20260714` 分支。默认 `main` 没有这两个模式。

### 2. 基础 CDN(自备)+ 本 mod 增量(随代码到手)

- **基础 CDN(~11GB)**:确保 `.cdn/cn/` 已就位(目录结构与校验见 [`docs/cdn/overview.md`](cdn/overview.md))。官方源已停服,本 mod **不分发**基础 CDN——需你自行从 WF 私服圈/现有部署获取。已有能跑的 WF CN 私服的人跳过此项。
- **本 mod 的增量(①+②两层都在分支里)**:
  - ① **服务端层**:两模式和武器的 masterdata 在 `assets/*.json`(服务端直接读)。
  - ② **客户端层**:深渊武器/兑换商店/rush 700099 的客户端 orderedmap 数据,已打包成 **`assets/asset-patch/active/pinball-1.4.90→1.4.102-mod*.zip`(12 个,git 跟踪;前 11 个是 1.4.90→1.4.101 逐版本边,第 12 个是末尾的 `1.4.101→1.4.102` 撞车桥接包)**,服务端 `asset.ts` 会自动 serve;**整链链尾以 `manifest.json` 为准(当前 1.4.247)**——2026-07-28/29 两条 backfill 条目(1.4.107→1.4.217→1.4.247)把三角色之后发布的现役内容全部回灌(C8016 色替预载修复/深渊法阵场地效果/连战塔随机重做)。**这层缺了 → 打完 15 轮或开兑换商店会 C8601**(客户端没有武器/商店主数据)。
  - ⚠️ **前提**:你的 base CDN 必须接到 **1.4.90**(这条增量链的起点),客户端才能续上 1.4.90→1.4.101 拿到 ② 层。base CDN 版本不到 1.4.90 的话这段接不上。
  - ③ **双新角色层(1.4.102→1.4.103)**:`assets/asset-patch/active/pinball-1.4.102-1.4.103-*-charpkg*.zip`(7 个分包共 28MB、164 个 payload,git 跟踪;同一版本跨越拆多包,客户端按 get_path 列表全部下载)——赛瑞斯(129999)与史黛拉(139999)的全部客户端资产:16 表克隆数据、UI、像素动画、语音、技能 DSL、独有状态图标。打完模式链的客户端自动续上这层。服务端侧的角色表已在 `assets/*.json` 里随分支到手。
  - ④ **窗口/闭环/平衡层(1.4.103→1.4.106)**:横幅窗口包、资产闭环包、深渊武器最终平衡,依次自动续链(见 `assets/asset-patch/manifest.json` 各条说明)。
  - ⑤ **三角色终态层(1.4.106→1.4.107,2026-07-19)**:`pinball-1.4.106-1.4.107-*-threechar0719.zip`(10 个分包共 ~38MB、216 个 payload)——**白狼骑士·杰拉德(149999)全套客户端资产**(原图立绘/原创像素 v6/五段特效/强化弹射全链/语音,对应真机验收的 1.4.172 状态)+ **赛瑞斯五轮战斗修复终态**(官方 fixture 强化弹射树/特效容器/14 个官方光束容器/语音,对应真机验收的 1.4.182 状态)+ 随包史黛拉资产刷新。表为外科式合并,只带三角色认领行,不覆盖你的其它数据。此层到 **1.4.107**;其后接 backfill 两边(107→217→247),整链链尾以 manifest 为准。

### 3. 起服

按 [`docs/deployment.md`](deployment.md) 走(Node 20 + nginx + 域名 + Let's Encrypt + `.env` + TCP 联机口 8003)。

- **公网开服**:照 deployment.md 全套(nginx 反代 + HTTPS + 域名)。
- **本地/内网自己玩**:可简化——`.env` 里 `CN_LISTEN_HOST=0.0.0.0`,客户端直接重定向到 `<你的内网IP>:8001`(见步骤 4),省掉 nginx/域名/证书。

### 4. 打你自己的客户端(**五合一补丁**)

自建服要连**你自己的**服,客户端必须打五个补丁。拿官方 CN APK,用 FFDec 把主 SWF 导出为 AS3 目录(记为 `EXPORT_DIR`),依次应用:

```bash
# ① 免登录 + ② 重定向到你的服(改 DevConfig 两处)
bash client-patch/apply.sh <EXPORT_DIR> <你的host:port>     # 如 192.168.1.10:8001

# ③ 深渊装备战斗门控(否则武器装上不生效!)
python -X utf8 client-patch/abyss-mode-equipment/patch.py \
  --source <EXPORT_DIR>/pinball/common/data/character/BattleCharacterLogic.as \
  --output <EXPORT_DIR>/pinball/common/data/character/BattleCharacterLogic.as
```

①-③ 改完后用 FFDec 把 AS3 导回 SWF。接着打第四个补丁——它作用于 **P-code 层**(FFDec 的 pcode 导出,不是 AS3 源):

```bash
# ④ 赛瑞斯双形态 P-code(特殊演出预载/双形态动画/湿润雷伤终乘/退场充能/弱化延长)
#    不打的话:客户端播放赛瑞斯特殊演出会硬崩!
python -X utf8 client-patch/dual-form-v1/build_patch.py \
  --baseline-swf <上一步导回的主SWF> \
  --baseline-pcode-root <FFDec对该SWF的pcode导出目录> \
  --ffdec-jar <ffdec.jar> --output-dir <空输出目录> --profile-dir <FFDec配置目录> \
  --manifest client-patch/dual-form-v1/patch-manifest-seris-combat.json

# ⑤ 逐角色像素占屏(render-scale-v1):让渲染尊重 frame.scale
#    不打的话:杰拉德等大原生像素在角色页/战斗里恒定放大 1.79 倍(显著偏大但不崩)
#    站点1=PixelArtCharacterView.as 单行替换(AS3 层,同①-③一起导回);
#    站点2=MemberView P-code 补丁;完整流程见 client-patch/render-scale-v1/README.md
```

最后把产出的 SWF 替换进 APK、`zipalign` + `apksigner` 重签名、安装。
`client-patch/abyss-mode-equipment/build_apk.py` 提供了打包+回读验证的一体化脚本(参数见其 README)。

> ‼️ 已发布的 [`WorldFlipper-abyss.apk`](https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/releases) 是给"连某个固定服"用的,**自建服请自己重打**指向自己域名的客户端——那个现成包直接装对你没用。
>
> **但你不一定要走上面整条 FFDec 流水线**:`client-patch/repoint-apk/repoint_build.py` 拿已发布的
> **v2.0 五合一基座 APK**,只改 `DevConfig_gf_android` 里的 `host:port`(即②号补丁落点)再重签,
> ①③④⑤四个补丁的字节原样保留,构建内置回读校验(见其 [README](../client-patch/repoint-apk/README.md))。
> 需要自己改补丁内容时才走完整流水线。
> 签名选择的取舍:**沿用玩家旧包同一个 keystore** → 可覆盖安装,本地身份保留;**换签名** →
> 玩家必须卸载重装,本地身份被抹掉、下次登录开新号,存档还在服务端 DB,服主按 `device_id` 重绑。

### 5. 发放三位角色(服务端管理后台)

角色数据到位后玩家不会自动拥有,用管理后台邮件发放:打开 `http://<你的服>:8001/admin` → 邮件页 → 附件类型选「角色」,ID 填 `129999`(赛瑞斯)、`139999`(史黛拉)、`149999`(杰拉德)各发一封 → 玩家进游戏从邮箱领取。**前提①:发放前先重启服务端**——邮件附件白名单在启动时定格,刚装入的新角色/新装备不重启会被判「不存在于 CDN 数据中」;**前提②:客户端已实际更新到链尾**(以 manifest 为准,当前 1.4.247)——客户端缺资产时领取会崩,且该邮件删不掉、整个邮箱卡死,只能管理后台清空邮箱恢复。

### 6. 进游戏验证

- **模式**:Rush 活动 **700099「深渊连战」** → 打每轮 boss 掉武器/攒代币 → 兑换商店换 15 把深渊武器 → 装上进 700099 / 挑战 2001 / 练习关生效。
- **角色**:邮箱领取 129999/139999/149999 → 角色页查看面板(词条/队长技完整显示,立绘居中) → 赛瑞斯放技能进「龙王显形」(双形态动画+湿润上敌,需④号补丁;强化弹射人形=弹板光束/龙形=撞怪爆炸,**须赛瑞斯当队长**) → 史黛拉当队长打一场(能力攻击体系) → 杰拉德放「月耀一闪」+强化弹射三级演出,像素与官方角色等大(需⑤号补丁,没打⑤只是偏大不崩)。

---

## 已有部署如何升级(存量服)

已经跑着一个 WF CN 私服(上游 startpoint-cn 或旧版本)想加上两模式+三自制角色,不用从零来:

1. **换服务端代码**:`git remote add kuron https://github.com/kuronzzhan-droid/startpoint-cn.git && git fetch kuron && git checkout -b release/modes-20260714 kuron/release/modes-20260714`,然后 `npm install`、重新构建、重启。**数据库零迁移**——本分支不改表结构,原 `.database/` 和全部玩家存档直接沿用。
2. **数据自动下发**:服务端 masterdata 和客户端增量链都随分支到手(见步骤 2),重启后自动 serve。base CDN 须到 1.4.90;玩家客户端不论卡在哪个版本(含 1.4.101 撞车位),桥接包会把它推进到链尾,重启游戏即触发下载。
3. **重打客户端(唯一的人工大步)**:按步骤 4 打**五合一**,②重定向填你们**已有的**服务器地址。存量服的旧客户端只有①②——缺③=深渊武器装上不生效,缺④=赛瑞斯特殊演出必崩,缺⑤=杰拉德像素放大 1.79 倍(不崩)。
4. **换包与账号**:新 APK 签名与旧包不同时玩家须卸载重装,**本地客户端身份会被抹掉、下次登录开新号**;服主可在管理后台按 device_id 把老存档重绑,或重打时沿用旧包同一个 keystore(可覆盖安装,身份保留)。**免 FFDec 快路**:`client-patch/repoint-apk/repoint_build.py` 拿已发布的 v2.0 五合一整合包只换服务器指向并重签(基座 APK 在 [startpoint-cn-mod-tools Releases](https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/releases),双补丁齐全)。**全员换完包再发角色**——数据与客户端补丁必须配套。
5. **发角色 + 验证**:同步骤 5/6。

### 通用桥接:玩家客户端卡在任意版本 V(接不上增量链)

症状:服务端数据都在,但客户端开兑换商店/邮件领角色报"资源损坏"(C8601 换皮),
`get_path` 对该客户端版本返回空 diff——客户端经别的 CDN 血统到了链外版本(桥接包只救 1.4.101)。

修法按你的**血统**分两条路(2026-07-17 野外实证后修订):

**先判断**:你的基础 CDN/客户端表是不是**跟着本指南**走的(基线 ≤1.4.101 等价内容)?
还是来自**别的私服血统**(基础表内容比本链新,比如经别家更新链到了 1.4.1xx)?

**A. 基线血统 → 终态整合包救援(一跳直达链尾)**:

⚠ **旧版本的「cp 9 个 1.4.10x 包改名」写法在 2026-07-28/29 回填之后已经失效,别再照抄**:
那样只把客户端推到 1.4.102 时代的内容,而落点 `W` 之后**没有任何 `from ≥ W` 的边**
(回填两条边的 from 是 1.4.107 和 1.4.217,都排在 `W` 之前),客户端会缺 1.4.103→链尾的
全部内容并**第二次搁浅**。正确做法是先把整条链压成一个终态整合包,再改名成一跳:

```bash
V=1.4.123      # ← 玩家客户端实际卡住的版本
W=1.4.247      # ← 链尾,以 assets/asset-patch/manifest.json 为准;必须 > V

# 1) 先看一眼计划(不落盘):确认范围、分包数、被排除的平行边
python -X utf8 mod-tools/wf_pack_consolidate.py plan --from-ver 1.4.90 --to-ver "$W"

# 2) 生成终态整合包。产物落 mod-tools/work/pack_consolidate/rescue/,
#    **按 CDN 目录结构摆放**(archive-common-diff / archive-medium-diff / archive-android-diff)
python -X utf8 mod-tools/wf_pack_consolidate.py build \
  --from-ver 1.4.90 --to-ver "$W" --tag rescue

# 3) 逐 root 拷进 CDN 对应目录,只把文件名里的 from 换成 V(to/序号/tag 原样保留)
OUT=mod-tools/work/pack_consolidate/rescue
for d in archive-common-diff archive-medium-diff archive-android-diff; do
  for f in "$OUT/$d"/pinball-1.4.90-"$W"-*.zip; do
    [ -e "$f" ] || continue
    cp "$f" ".cdn/cn/$d/$(basename "$f" | sed "s/^pinball-1\.4\.90-/pinball-$V-/")"
  done
done
```

服务端自动感知目录变化(重启更稳妥);`get_path` 带 `res_ver: V` 应返回这一跳的全部 zip,
**落点直接是链尾**——日后上游再发 `from=链尾` 的新边,这批玩家自动续得上,不用再救第二次。

- ⚠ **必须按 root 分目录放,别全丢进一个目录**:三个 root 的分包序号各自从 1 开始,
  文件名会撞(`…-1-rescue.zip` 有三份)。`assets/asset-patch/active/` 是**扁平**的单 root 目录
  (`src/lib/cn-asset-graph.ts` 按 `patch` root 扫描),只适合放单 root 的小桥接包,不适合整合包。
- ⚠ 落点 `W` 必须 **大于** `V`:`findReleasePath` 只在比起点高的版本里选目标
  (`src/lib/cn-asset-graph.ts:135`)。玩家卡住的版本号反而高于链尾时,只能把 `W` 设成
  `V` 的下一号,代价是上游下次发新内容还得再桥一次。
- ⚠ 整合包放进 CDN 后**不要删除被它整合掉的旧包**——还停在中间版本的客户端要走原来那些边,
  删了就永久搁浅(见 `wf_pack_consolidate.py` 文件头的安全红线)。
- ⚠ 此路对基线血统外的部署是**破坏性**的:桥接 6 表/角色 16 表是整表替换,会抹掉你血统
  自己的活动/商店/角色行(实测:外血统换上后活动页/领主战直接「数据不足」瘫痪)。外血统走 B。

**B. 外血统 → 行级合并,禁止整表替换**:

> ⚠ **前提 -1:服务端逻辑**。下面 0-4 步全是**数据**层的活。深渊连战/兑换商店/连战塔要真能跑,
> 你的**服务端代码**还必须带模式逻辑,两个来源二选一:
> - **本分支 `release/modes-20260714`**:模式逻辑直接编译进服务端,装好就有,最省事;
> - **上游 `dev` + 装载缝**:基座零玩法逻辑,玩法以 `modes.d/*.mjs` 改造包形式手动安装,
>   见本节末尾的「dev 架构服务端(modes.d 装载缝)」。
>
> 只做完数据合并、服务端仍是**不带模式逻辑的 main/dev 基座** → 客户端能看到活动入口和商店,
> 但进本崩溃/结算不发奖。这一条与血统无关,A 路同样适用。

> ⚠ **前提 0(2026-07-17 野外事故后补明)**:mod-tools 的 **store(数据包)基线必须等于你目标
> 客户端的当前版本**。`wf_publish` 是整文件发布——store 里的表是什么状态,发出去客户端就被
> 覆盖成什么状态;用落后的 store(如 1.4.54)对 1.4.125 的客户端发布 = 把表滚回 71 个版本,
> 版本间隙里官方加的 key 全部丢失(实例:item 表缺 10000140 → 仓库 C8601)。
> store 落后时先刷新,两个办法任选:
> - **从你自己的 base CDN 重建**:把 `.cdn/cn/archive-common-full` 和 `archive-common-diff`
>   里的 zip **按版本升序**依次解压到同一目录(后解压覆盖先解压),得到的 `production/upload`
>   树就是链尾基线的 store(表数据全在 common 变体,跑数据工具足够;要编辑语音/立绘再按同法
>   叠 android 链),把 profiles/WF_TARGET_STORE 指过去;
> - **从设备拉**:任何一台跟着你的服更新到当前版本的设备/模拟器,
>   拉 `/sdcard/WorldFlipper/dummy/download/production/upload` 整目录。
> - **CDN 重建也追不上客户端时**(你的 CDN 链尾 < 客户端版本,差段来自别的链或自带数据的
>   重打包 APK):那段内容只存在于玩家设备上,但**不用拉全量——工具要写的只有表**。
>   表的存储路径 = `sha1(逻辑路径+SALT)`(`wf_mod_tool.sha1_path`,模式 7 表的现成对照表见
>   工具仓 docs),从一台完整更新到当前版本的设备把这几个表文件拉下来**覆盖进重建树**即可;
>   APK 若自带数据也可以直接解 APK 取表。覆盖后先确认间隙 key 已在(如 item 10000140)再发布。

0. **先试现成的「7 表救援包」(免工具,适用于与本链同源的血统)**:
   `archive/pinball-1.4.103-1.4.125-1-tables125mod07171232.zip` = 七张核心表
   (item/equipment/equipment_status/ability_soul/rush_event/event_item_shop/floor)在本链
   **1.4.125 窗口的状态**,已含全部模式行、该窗口的官方键(如 item 10000140)和真机验证的
   连战塔 floor。适用判据:你玩家客户端的 1.4.10x-12x 版本段是经本链(或其打包产物)到达的
   ——你缺的间隙键这套表里有,就是同源。用法(V=你玩家当前 res_ver):
   ```bash
   cd assets/asset-patch/active
   cp ../archive/pinball-1.4.103-1.4.125-1-tables125mod07171232.zip "pinball-V-W-1-tables125mod07171232.zip"
   cp ../archive/pinball-1.4.90-1.4.101-9-modassets07170102.zip    "pinball-V-W-2-modassets07170102.zip"
   ```
   重启服务端,玩家清缓存/重启游戏即到位。**表键仍缺(血统真不同源)再走下面 1-4。**
   另外把两个资产闭环包也带上(修兑换商店『数据不足』死循环——横幅在 1.4.104-125 窗口、
   武器图标与角色特效在 1.4.126+ 才发布,都不在早期链里):
   ```bash
   cp pinball-1.4.103-1.4.104-1-windowmod07171640.zip      "pinball-V-W-3-windowmod07171640.zip"
   cp pinball-1.4.104-1.4.105-1-afterchainassets07171830.zip "pinball-V-W-4-afterchainassets07171830.zip"
   ```
   ⚠ `windowquests`(连战塔任务表+event_list)是给**跟链血统**的:`event_list` 会整表替换
   活动页列表,外血统换上会把你自己的活动滤没,只有连战塔内 UI 出问题时再单独考虑前三张。

   ⚠ **这套救援包的连战塔部分已经过期**。tables125 里的 `master/battle/floor`、windowquests 里的
   `rush_event_quest`/`rush_event_quest_folder`,是本链 **1.4.125 / 1.4.104 时代的塔布局**,
   早于 2026-07-28、07-29 两次连战塔随机重做;而本分支现在的服务端 masterdata
   (`assets/rush_event_quest*.json`)是 **1.4.247 配套态**。直接混用 = server/client 两半不同步
   (楼层/boss 对不上、结算异常)。其余六张表(item / equipment / equipment_status /
   ability_soul / rush_event / event_item_shop)不受影响,照用即可;**塔表必须在你自己的
   store 上重新生成**:

   ```bash
   python -X utf8 mod-tools/wf_rogue_build.py --write --publish
   ```

   `--write` 同时写客户端表和服务端 `assets/rush_event_quest*.json`,`--publish` 发成你自己血统
   的增量——**服务端 JSON 与客户端表出自同一次构建**,只有这样两半才配套(单独换一半必错)。
   服务端 JSON 是静态 import,写完**必须重启服务端**。
1. **纯资产补充包对任何血统都安全**(`archive/pinball-1.4.90-1.4.101-9-modassets07170102.zip`,
   30 个全新路径文件:武器图/横幅/商店图,不含任何表),重命名成你的一跳直接发;
2. 深渊行数据用 [mod-tools](https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools) 在
   **你自己的数据包**上生成(全部行级写入,不动你的存量行):
   `wf_rogue_rewards / wf_rogue_build / wf_rogue_shop / wf_rogue_banner`(武器/掉落/兑换商店/横幅)
   + `wf_chain_build`(700099 楼层写进你的 floor 表);
3. 自制角色不要照抄 charpkg 整表,用角色包工作流(`wf_release` / `wf_character_flow`,
   见工具仓 docs/角色包工作流.md)把 129999/139999/149999 装进你的表;
4. `wf_publish --from-ver <你的当前版本>` 把以上发布成**你自己血统**的增量。

通用备注:救援后你的玩家停在自己的号位,**日后上游再发新内容链时需重做对应步骤**;
修完仍有「数据不足」→ 复现一次,把服务端 `logs/http404.log` 新增的 404 路径发给上游定位。

### dev 架构服务端(modes.d 装载缝)

上游 `dev` 走的是**内容编译**架构(`content:sync` + Content Release),和本分支的
"masterdata 直读 + CDN 增量"不是一回事。想在 dev 上跑模式类玩法,走**装载缝**:

**基座已在上游**——玩法模块装载缝已随 PR #19 合并进 `dev`(`df3ad91`,`src/modes/` +
`docs/systems/mode-seam.md`),**你不需要再 fork 服务端**。基座本身零玩法逻辑:没装模块时
所有挂点是空操作,行为与不带本机制的基座逐字节一致。

分发模型是三件产物,别混:

| 产物 | 是什么 | 谁来装 |
|---|---|---|
| **基座** | 上游 dev 构建的服务端,只含激活入口 | 正常部署 |
| **玩法改造包** | `rogue.mjs` + manifest,**代码** | 运营者手动放进 `modes.d/` 并登记哈希 |
| **内容包** | CDN 增量(资源 + 激活表),**数据** | 照常下发 |

> 红线:**内容包永不携带可自动加载的代码**。装模块 = 以服务器权限运行第三方代码,
> 与"安装服务端本身"同级别的信任决定,所以没有自动发现、没有热加载。

装载是**双重显式**的:文件要在 `modes.d/`,**且**其 sha256 要登记在
`modes.d/modes-allowlist.json`(形如 `{"rogue.mjs": "<sha256>"}`)。缺一或哈希不符都会跳过
并打日志,不会静默加载。装卸模块都要重启。总开关 `MODES_ENABLED=0`,目录可用 `MODES_DIR` 覆盖。

安装(rogue 改造包目前在 fork 的 `fork/dev-base` 分支 `modes-src/rogue/`,不参与基座构建):

```bash
cp modes-src/rogue/rogue.mjs modes.d/rogue.mjs
# sha256 不用自己算:mode-manifest.json 里带了(连同 install 三步、activationTable 一起),
# 照抄成 {"rogue.mjs": "<sha256>"} 写进 modes.d/modes-allowlist.json
CDN_DIR=<cdn父目录> npm run content:sync && node --env-file=.env out/cn-server.js
```

启动日志出现 `[modes] loaded rogue-rush (rogue-settlement@1) sha256=…` 才算装上;
没有这行 = 没装成(哈希没登记/不符,或激活表缺失)。三个挂点、事务边界与失败模型见
上游 `docs/systems/mode-seam.md`——要点是 `onRushFinish` 跑在结算事务**内部**,模块抛错
**整次结算回滚**(不吞异常是为了不留撕裂存档);`onQuestStart` 抛错则拒绝进本,消息回传客户端。

激活语义是**内容键控**:模块第一步读自己的激活表,表缺失或未启用就直接返回。所以
"装了模块但没下发内容"与"完全没装模块"表现一致,可以先装模块再按需下发内容。

⚠ 已验证到服务端级(结算发奖/防跳关/惰性/CDN 下发,2026-07-26),**客户端真机验收
(进本、掉落到账、轮次锁)尚未在 dev 架构上完成**。要稳,用本分支。

---

## 内容速览

- **深渊连战(Rush 700099)**:自制无尽/roguelike 活动,每轮不同 boss,通关掉落。
- **15 把深渊武器(`8000101`–`8000115`)**:每属性 2 把 + 通用 3 把,故意超模;代币 `2370099`,兑换商店。
- 门控白名单:武器/能力魂只在 `Rush 700099` · `挑战 2001` · `练习 1–97` 内生效,其余关卡与官方一致。
- **苍海龙王·赛瑞斯(129999,水,★5)**:双形态龙王。技能「苍海雷狱」双属性全屏+麻痹/气绝/湿润+进入「龙王显形」42 秒(全队攻/能伤+300%、技/直伤+300%、充能+50%、贯穿、弱化免疫、速度固定);与雷系互协力时视为雷系。双形态强化弹射(人形=官方弹板光束系,龙形=光环+撞怪爆炸,仅队长位生效)。
- **夏日女神·史黛拉(139999,光,★5)**:能力攻击辅助。全队按能力攻击次数滚雪球叠攻/能伤,开幕全队满槽,主位光属性能力伤害引擎。
- **白狼骑士·杰拉德(149999,光,★5)**:海崖王国的白狼骑士,v2 全套重制(原图立绘/原创像素/五段特效)。技能「月耀一闪」,月耀强化弹射三级演出(月牙→双弧时钟→零时环交叉斩),队长技联动强化弹射套路。

## 常见坑

- 客户端**只打了免登录+重定向、漏了深渊门控** → 能进服、能拿到武器,但装上在战斗里不生效。
- 客户端**漏了④双形态补丁**但服务端有角色数据 → 领赛瑞斯没事,但他的特殊演出播放即崩;湿润雷伤加成也不生效。五个补丁都要打(⑤例外:漏了只是杰拉德像素偏大,不崩)。
- **客户端没更到链尾就邮件发 149999** → 领取后下载/进战崩溃(客户端缺杰拉德资产),邮箱可能整体卡死。先确认玩家客户端已拉到链尾再发角色。
- **没放 CDN 或版本不全** → 客户端卡加载/报错。CDN 是必需的,不是可选。
- **活动页/领主战页空白且零报错** → 服务器时间在活动排期窗外(时间过滤是静默的)。表里的
  活动排期集中在 2023-11~2025-10(最近一批到 2025-10-14),而服务器时间是**存你库里的运行时
  设置,不随 git 分支到手**。起服后在管理后台(`/admin` 首页时间卡片)把服务器时间设到
  **2025-08-04 前后**并保持。深渊连战 700099 排期为 2000→2099 永续,不受此影响——
  Rush 页能看到 700099 而活动页空白,就是时间问题的实锤。
- 客户端读到自制数据但**没打对应补丁**(如深渊/随机塔/双形态)可能崩 → 数据与客户端补丁要配套,全员换包后再发数据。
