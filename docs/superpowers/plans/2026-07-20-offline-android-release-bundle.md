# World Flipper 国服离线 Android 整合包 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从既有离线 `base.apk.1` 和“弹国服”当前三层资源 store 构建一个可在飞行模式运行、接收者只需安装 APK 并解压一次数据 ZIP 的 1.4.196 五文件发行包。

**Architecture:** 构建分成四条可独立验收、最后汇合的流水线：只读冻结三层 store 并生成 Player 1000 最小覆盖；在同一份 base SWF 上按固定顺序合并深渊、赛瑞斯、三处缩放和资源版本补丁；使用专用稳定签名只重打包/对齐/签名一次；最后以设备验收收据绑定候选哈希，生成 manifest/checksums 并原子提升为最终五文件目录。所有输入均以基线哈希和严格成员白名单锁定，任一漂移都 fail closed。

**Tech Stack:** Python 3.14 `unittest`、标准库 `zipfile/hashlib/json/pathlib/shutil/subprocess`、FFDec 26.2.1、Java 8、Android `aapt/zipalign/apksigner`、ADB/MuMu、现有 `wf_*` master/character/rogue 工具链。

**Approved Spec:** `docs/superpowers/specs/2026-07-20-offline-android-release-bundle-design.md`

## Global Constraints

- 输入 APK 固定为用户提供的 `C:\Users\12101\Downloads\base.apk.1`；正式构建要求 SHA-256 为 `4f6884f33641788108c0522c7c70036c63ba530e1fdb183105b3cd395bdd66f6`，内置 `assets/worldflipper_android_release.swf` SHA-256 为 `08187f538703aecadce264b7bd5e085411f8e3aedb5f48adf2cf035a100f550d`。
- 输出根固定为 `out/wf-offline-android/1.4.196/`，最终目录固定为 `WF离线整合版/`，且最终只允许五个文件：`WorldFlipper-离线整合版.apk`、`WorldFlipper-数据-1.4.196.zip`、`导入说明.txt`、`build-manifest.json`、`SHA256SUMS.txt`。
- APK 必须继续使用 `DevConfig_individual`、`DummyRemote`、`socket=0`、`sdkDummy=true`、`DummyPayment`、`isFullPackage=true`、`WorldFlipper/dummy/download` 和 `WorldFlipper/save_haxe` 读写链路；不得调用 `client-patch/repoint-apk/`、v2 RealRemote/LAN 或任何伴随服务。
- APK 只允许主 SWF、ZIP 容器布局、对齐结果和顶层签名条目变化；package/version/label、AndroidManifest、DEX、native libraries、AIR wrapper 以及所有非目标 APK member 的内容字节必须保持基线一致。
- SWF 补丁顺序固定为 `abyss gate → Seris Phase 4 九站点 → PixelArt/MemberView/CharacterCellView 三处缩放 → fullResourceVersion 1.4.54→1.4.196`；每站点必须精确匹配一次并在 FFDec reopen 后复验。
- 数据 ZIP 根必须恰好为 `WorldFlipper/`；common/medium/android 分别映射到 `production/upload/`、`production/medium_upload/`、`production/android_upload/`。严格 hashed member 数固定为 `138,289`，加 `info.json` 和 `.empty` 后 ZIP member 数固定为 `138,291`；旧离线包 `137,820` 个 hashed 路径必须零遗漏，新增必须恰好 `469`。
- `info.json.version` 和内容快照版本固定为 `1.4.196`；`.empty` 固定为单字节 ASCII `0`；外置 ZIP 不重复携带 `bundle.zip`，不携带 `save_haxe`、`dummy_save.json`、账号数据、服务端、Node、构建日志或秘密材料。
- Player 1000 初始角色表只保留原 `"1":"2"` 并追加 `129999/139999/149999` 各 `"1"`；不得改队伍、mana node、物品、装备、货币、进度或购买记录，不预发 `8000101..8000115`。
- 三名角色都必须通过 identity、37/37 required assets、三层映射、master 引用以及逐文件 size/SHA 绑定。规划时 `work/character_packs/seris_dragon_king/workspace.json` 实际身份是 `139999/stella_summer_goddess`，所以该证据必须被拒绝；129999 只能由身份正确的 sealed workspace 或本计划定义的等价 1.4.196 已发布快照证据放行。
- 专用签名默认位于 `%USERPROFILE%\.wf-offline-release\wf-offline-release.jks`，alias 为 `wf-offline-release`；密码只允许交互输入或环境变量 `WF_OFFLINE_KEYSTORE_PASSWORD`，私钥、密码、绝对私钥路径不得进入仓库、`work/`、`out/`、命令行、日志、manifest 或说明书。不得复用或删除历史 `work/` keystore/password。
- 构建器绝不修改源 APK、弹国服 live store、旧 ZIP、历史 edge、`work/` 或用户 WIP；不调用 live publish/rebase；不覆盖已有成功 final；候选与 final 必须同卷并通过目录级原子 rename 提升。
- 当前 dirty 的 `mod-tools/wf_gui.html`、`mod-tools/wf_gui.py`、`mod-tools/wf_rogue_build.py`、`mod-tools/wf_rogue_reroll.py`，所有未跟踪 Seris/rogue 文件以及 `work/` 一律不编辑、不暂存、不还原。
- 实施必须能读取当前 checkout 中被忽略的“弹国服”和 `work/` 证据；不要把执行迁到缺少这些本地输入的新 worktree。若后续确需隔离，先用 `superpowers:using-git-worktrees` 并把输入作为显式只读外部路径传入，绝不复制秘密或 WIP 到 Git 跟踪区。
- `web/pages/`、`src/routes/web/`、`web/public/` 在 M4 前零改动；不提交 `web/dist`、`admin/node_modules`。Node.js 最低版本仍为 `20.19.0`；本计划不改依赖或 lockfile。
- 所有正式静态门禁和飞行模式设备门禁都通过后才能生成最终 manifest/SHA 并标记可交付；设备清档、卸载、覆盖安装或改共享存储前必须使用精确确认口令，不得按端口或进程名结束陌生进程。

---

## File Structure

### Existing files to modify

- `mod-tools/build_three_char_release_patch.py` — 为 common/medium/android 成员保留 root-qualified key，修复新生成 edge 的三根映射；不重写历史 ZIP。
- `mod-tools/wf_character_workspace.py` — 增加完全不落盘的 workspace inspect 路径，默认行为保持兼容。
- `mod-tools/tests/test_character_workspace.py` — 证明 `persist=False` 不改 evidence/status/hash-cache 或任何 workspace 字节。
- `mod-tools/wf_mod_tool.py` — 增加 orderedmap raw-row 的纯 bytes 读取接口，供 staging overlay 使用。
- `mod-tools/wf_rogue_validate.py` — 抽出不依赖 live publish 的纯数据验证接口，同时保留原 CLI/API。
- `client-patch/abyss-mode-equipment/build_apk.py` — 抽出“只输入/输出 SWF、不签 APK”的 abyss gate stage；原 APK builder 继续可用。

### New production files

- `mod-tools/wf_offline_store.py` — 三层 store 解析、严格枚举、旧 ZIP/tail 比较、源漂移检测、真实 copy snapshot、1.4.196 markers。
- `mod-tools/wf_offline_player.py` — Player 1000 初始角色最小覆盖及写回后重解析报告。
- `mod-tools/wf_offline_content.py` — 深渊/武器/商店/三角色 identity、37/37、master/asset/三层 SHA 绑定和等价 published-snapshot seal。
- `mod-tools/wf_offline_zip.py` — 确定性 `ZIP_STORED` Zip64 写入和逐 member 复验。
- `mod-tools/wf_offline_toolchain.py` — Java/FFDec/Android tools/ADB/MuMu 发现、专用 signer public config 和安全 bootstrap。
- `mod-tools/wf_offline_bundle.py` — canonical manifest、四行 SHA256SUMS、五文件布局、秘密扫描、设备收据绑定和原子 finalize。
- `mod-tools/wf_offline_device.py` — 只读设备 probe、显式破坏性准备、飞行模式检查和人工验收收据。
- `mod-tools/wf_offline_release.py` — `preflight/build-candidate/device-probe/device-accept/finalize/verify/init-signer` 总 CLI。
- `mod-tools/build-offline-android.bat` — Windows 操作者入口，只转交参数和错误码，不保存密码。
- `mod-tools/templates/offline-import-guide.zh-CN.txt` — 最终 `导入说明.txt` 的固定用户文案模板。
- `mod-tools/docs/离线Android整合包.md` — 构建者说明、密钥生命周期、候选/设备/finalize 流程与故障恢复。
- `client-patch/offline-android/base-lock.json` — 已审核的 base APK/SWF/manifest/DEX/native/offline/save/method/stage locks；不含本机路径或秘密。
- `client-patch/offline-android/apk_baseline.py` — APK 基线检查、允许差异比较和离线 wrapper 方法复验。
- `client-patch/offline-android/seris_phase4_pcode.py` — 从用户 WIP 提升后的九站点纯 P-code 补丁和语义验证。
- `client-patch/offline-android/render_scale_pcode.py` — PixelArt、MemberView ctor、CharacterCellView 三个 base-specific 定点缩放补丁。
- `client-patch/offline-android/resource_version_pcode.py` — 唯一 `fullResourceVersion` 定点替换和 `isFullPackage` 保持验证。
- `client-patch/offline-android/lock_discovery.py` — 仅供受控基线发现/接受使用；正式 build 路径无 refresh-locks 能力。
- `client-patch/offline-android/build_offline_apk.py` — 单次提取、顺序 patch、单次回写、zipalign、单次签名、最终复验。
- `client-patch/offline-android/README.md` — patch 顺序、锁格式和禁止 RealRemote/repoint 的维护说明。

### New tests

- `mod-tools/tests/test_build_three_char_release_patch.py`
- `mod-tools/tests/test_offline_store.py`
- `mod-tools/tests/test_offline_player.py`
- `mod-tools/tests/test_offline_content.py`
- `mod-tools/tests/test_offline_zip.py`
- `mod-tools/tests/test_offline_toolchain.py`
- `mod-tools/tests/test_offline_apk_baseline.py`
- `mod-tools/tests/test_offline_apk_abyss_merge.py`
- `mod-tools/tests/test_offline_apk_seris.py`
- `mod-tools/tests/test_offline_apk_render_scale.py`
- `mod-tools/tests/test_offline_apk_resource_version.py`
- `mod-tools/tests/test_offline_apk_builder.py`
- `mod-tools/tests/test_offline_bundle.py`
- `mod-tools/tests/test_offline_device.py`
- `mod-tools/tests/test_offline_release.py`

## Shared Interfaces

All paths in reports are release-relative POSIX paths. These public types are defined once and reused verbatim by later tasks:

```python
RootName = Literal["common", "medium", "android"]
RootedKey = tuple[RootName, str]

@dataclass(frozen=True, slots=True)
class StoreRoots:
    common: Path
    medium: Path
    android: Path

@dataclass(frozen=True, slots=True)
class StoreMember:
    root: RootName
    relative: str
    source_path: Path
    size: int
    sha256: str

    @property
    def archive_name(self) -> str:
        prefix = {
            "common": "WorldFlipper/dummy/download/production/upload/",
            "medium": "WorldFlipper/dummy/download/production/medium_upload/",
            "android": "WorldFlipper/dummy/download/production/android_upload/",
        }[self.root]
        return prefix + self.relative

@dataclass(frozen=True, slots=True)
class ManifestEntry:
    path: str
    size: int
    sha256: str
    source: Literal["common", "medium", "android", "generated-marker"]

@dataclass(frozen=True, slots=True)
class CandidateIdentity:
    build_id: str
    apk_sha256: str
    data_zip_sha256: str
    guide_sha256: str
```

---

### Task 1: Preserve all three archive roots in the three-character builder

**Files:**
- Modify: `mod-tools/build_three_char_release_patch.py:106-256`
- Create: `mod-tools/tests/test_build_three_char_release_patch.py`
- Preserve unchanged: `mod-tools/tests/test_three_char_release_patch.py`

**Interfaces:**
- Consumes: `wf_character_pack.ARCHIVE_PREFIXES`.
- Produces: `parse_archive_member(name: str) -> RootedKey`, `repo_tail_state() -> dict[RootedKey, bytes]`, `collect() -> tuple[dict[RootedKey, tuple[bytes, str]], list[str]]`, and root-aware `build_parts(...)`.

- [ ] **Step 1: Write the synthetic failing root-preservation test**

```python
def test_build_parts_preserves_common_medium_android_roots(self):
    rel_a = "aa/" + "1" * 38
    rel_b = "bb/" + "2" * 38
    rel_c = "cc/" + "3" * 38
    members = {
        ("common", rel_a): (b"common", "fixture"),
        ("medium", rel_b): (b"medium", "fixture"),
        ("android", rel_c): (b"android", "fixture"),
    }
    names = {name for name, _raw in module.build_parts(members, max_part_bytes=1024)[0]}
    self.assertEqual(names, {
        f"production/upload/{rel_a}",
        f"production/medium_upload/{rel_b}",
        f"production/android_upload/{rel_c}",
    })
```

Add separate tests that reject an unknown prefix, preserve two identical relative hashes in different roots, and parse all three legal prefixes.

- [ ] **Step 2: Run the focused test and confirm the current flattening bug**

Run: `python -X utf8 -m unittest mod-tools/tests/test_build_three_char_release_patch.py -v`

Expected: FAIL because medium/android are emitted under `production/upload/` or because the builder still keys by bare relative path.

- [ ] **Step 3: Refactor collection and output keys without touching historical archives**

```python
RootName = Literal["common", "medium", "android"]
RootedKey = tuple[RootName, str]
PREFIX_TO_ROOT = {value.rstrip("/"): key for key, value in ARCHIVE_PREFIXES.items()}

def parse_archive_member(name: str) -> RootedKey:
    normalized = name.replace("\\", "/").strip("/")
    for prefix, root in PREFIX_TO_ROOT.items():
        marker = prefix + "/"
        if normalized.startswith(marker):
            relative = normalized[len(marker):]
            if not re.fullmatch(r"[0-9a-f]{2}/[0-9a-f]{38}", relative):
                raise ValueError(f"invalid hashed member: {name}")
            return root, relative
    raise ValueError(f"unknown archive root: {name}")

def archive_member_name(key: RootedKey) -> str:
    root, relative = key
    return f"{ARCHIVE_PREFIXES[root]}{relative}"
```

Change every map/set comparison in `repo_tail_state`, `collect`, part sizing and ZIP writing to use `RootedKey`; table files are `("common", relative)`.

- [ ] **Step 4: Run focused and historical regression tests**

Run:

```powershell
python -X utf8 -m unittest mod-tools/tests/test_build_three_char_release_patch.py -v
python -X utf8 -m unittest mod-tools/tests/test_three_char_release_patch.py -v
```

Expected: both suites PASS; `git status --short assets/asset-patch .cdn` shows no new or modified historical ZIP.

- [ ] **Step 5: Commit the root-preservation fix**

```powershell
git add mod-tools/build_three_char_release_patch.py mod-tools/tests/test_build_three_char_release_patch.py
git commit -m "fix(mod-tools): preserve three-character asset roots"
```

---

### Task 2: Add a truly read-only character workspace inspector

**Files:**
- Modify: `mod-tools/wf_character_workspace.py:410-548`
- Modify: `mod-tools/tests/test_character_workspace.py`

**Interfaces:**
- Consumes: existing workspace manifest/hash/requirements functions.
- Produces: `workspace_status(workspace: Path, *, persist: bool = True) -> dict[str, Any]` and `inspect_workspace(workspace: Path) -> dict[str, Any]`.

- [ ] **Step 1: Add tests that snapshot every file before a no-persist inspection**

```python
def test_inspect_workspace_does_not_write_status_or_hash_cache(self):
    workspace = self.make_release_ready_workspace()
    before = self.tree_bytes(workspace)
    report = module.inspect_workspace(workspace)
    after = self.tree_bytes(workspace)
    self.assertTrue(report["release_ready"])
    self.assertEqual(before, after)

def test_inspect_workspace_rejects_identity_mismatch_without_writing(self):
    workspace = self.make_release_ready_workspace(character_id=139999, code_name="stella_summer_goddess")
    before = self.tree_bytes(workspace)
    report = module.inspect_workspace(workspace)
    self.assertEqual(report["identity"], {"character_id": 139999, "code_name": "stella_summer_goddess"})
    self.assertEqual(before, self.tree_bytes(workspace))
```

- [ ] **Step 2: Run the focused tests and confirm writes are currently observable**

Run: `python -X utf8 -m unittest mod-tools/tests/test_character_workspace.py -v`

Expected: the new no-write test FAILS because current `workspace_status()` updates `evidence/status.json` and/or hash cache.

- [ ] **Step 3: Thread an explicit persist flag through status calculation**

```python
def workspace_status(workspace: Path, *, persist: bool = True) -> dict[str, Any]:
    report = _compute_workspace_status(workspace, use_disk_hash_cache=persist)
    if persist:
        _write_status_and_hash_cache(workspace, report)
    return report

def inspect_workspace(workspace: Path) -> dict[str, Any]:
    return workspace_status(workspace, persist=False)
```

Keep `persist=True` as the compatibility default. Ensure `_compute_workspace_status` uses an in-memory cache when false and that neither access-denied nor invalid-manifest paths attempt a repair/seal/write.

- [ ] **Step 4: Run workspace and character-flow regression suites**

Run:

```powershell
python -X utf8 -m unittest mod-tools/tests/test_character_workspace.py -v
python -X utf8 -m unittest mod-tools/tests/test_character_flow.py -v
```

Expected: PASS; existing callers still persist, `inspect_workspace` leaves byte-for-byte identical trees.

- [ ] **Step 5: Commit the read-only inspector**

```powershell
git add mod-tools/wf_character_workspace.py mod-tools/tests/test_character_workspace.py
git commit -m "refactor(mod-tools): add read-only character inspection"
```

---

### Task 3: Freeze the 1.4.196 three-layer store without mutating live data

**Files:**
- Create: `mod-tools/wf_offline_store.py`
- Create: `mod-tools/tests/test_offline_store.py`

**Interfaces:**
- Consumes: `profiles.json`, `wf_assets.roots()`, `wf_asset_inventory.sha256_file()`, `ARCHIVE_PREFIXES`, old `弹国服/单机版数据包.zip`, and tail `.cdn/cn/archive-common-diff/pinball-1.4.195-1.4.196-1-mod07200253.zip`.
- Produces: `resolve_store_roots`, `enumerate_hashed_members`, `inspect_legacy_zip_paths`, `compare_path_sets`, `verify_tail_edge`, `required_free_bytes`, and `materialize_snapshot`.

- [ ] **Step 1: Write strict scanner, count, exclusion and source-drift tests**

```python
def test_enumerate_uses_root_qualified_keys_and_rejects_unknown_files(self):
    roots = self.make_roots(common={"aa/" + "1" * 38: b"x"}, medium={"aa/" + "1" * 38: b"y"})
    report = module.enumerate_hashed_members(roots)
    self.assertEqual([(m.root, m.relative) for m in report.members], [
        ("common", "aa/" + "1" * 38),
        ("medium", "aa/" + "1" * 38),
    ])
    (roots.android / "unexpected.txt").write_bytes(b"bad")
    with self.assertRaisesRegex(module.StoreError, "unknown non-hashed member"):
        module.enumerate_hashed_members(roots)

def test_snapshot_is_a_real_copy_and_writes_generated_markers(self):
    report = module.materialize_snapshot(
        self.scan_fixture(), self.stage / "WorldFlipper", snapshot_version="1.4.196"
    )
    self.assertEqual((report.worldflipper_root / "dummy/download/.empty").read_bytes(), b"0")
    self.assertEqual(json.loads((report.worldflipper_root / "dummy/info.json").read_text("utf-8"))["version"], "1.4.196")
    self.assertNotEqual(os.stat(self.source_member).st_ino, os.stat(report.copied_members[0]).st_ino)
```

Add tests for lowercase `2hex/38hex`, reparse/symlink rejection, documented `.bak/.tmp/.part/partial_downloaded.json` exclusion, secret/save/bundle fatal rejection, stat-before/stat-after drift, legacy root parsing, `137820 → 138289 (+469, omissions 0)`, tail member count `12`, and disk-space formula.

- [ ] **Step 2: Run tests and verify the module is absent**

Run: `python -X utf8 -m unittest mod-tools/tests/test_offline_store.py -v`

Expected: FAIL with import/file-not-found for `wf_offline_store`.

- [ ] **Step 3: Implement immutable reports and strict enumeration**

```python
HASHED_RELATIVE_RE = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{38}$")
KNOWN_BACKUP_RE = re.compile(r"(?:^|/)(?:\.bak|.*\.bak(?:-.*)?|.*\.tmp|.*\.part|partial_downloaded\.json)$")

@dataclass(frozen=True, slots=True)
class StoreScanReport:
    roots: StoreRoots
    members: tuple[StoreMember, ...]
    excluded: tuple[str, ...]
    counts: Mapping[RootName, int]
    total_bytes: int
    tree_sha256: str

@dataclass(frozen=True, slots=True)
class SnapshotDiff:
    current_count: int
    legacy_count: int
    added: tuple[RootedKey, ...]
    missing: tuple[RootedKey, ...]

def compare_path_sets(current: Collection[RootedKey], legacy: Collection[RootedKey]) -> SnapshotDiff:
    diff = SnapshotDiff(len(current), len(legacy), tuple(sorted(set(current) - set(legacy))), tuple(sorted(set(legacy) - set(current))))
    if (diff.current_count, diff.legacy_count, len(diff.added), len(diff.missing)) != (138_289, 137_820, 469, 0):
        raise StoreError(f"snapshot count mismatch: {diff}")
    return diff
```

Use `lstat`, Windows reparse attribute checks, 8 MiB streaming SHA, sorted root-qualified keys, and stat-before/stat-after equality. Never recurse through unknown directories or follow links.

- [ ] **Step 4: Implement copy snapshot, markers, tail and space gates**

```python
def required_free_bytes(total_store_bytes: int, source_apk_bytes: int) -> int:
    safety = 2 * 1024**3
    return total_store_bytes * 2 + source_apk_bytes * 3 + safety

def marker_entries(total_store_bytes: int) -> tuple[ManifestEntry, ManifestEntry]:
    info = (json.dumps({
        "version": "1.4.196",
        "assetRecoveryInfo": [],
        "totalSize": total_store_bytes,
        "assetSizeKind": "fulfill",
        "baseUrl": "https://xiaozhiche/",
        "latestModifiedTimeOfArchive": "",
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    return (
        ManifestEntry("WorldFlipper/dummy/info.json", len(info), sha256(info).hexdigest(), "generated-marker"),
        ManifestEntry("WorldFlipper/dummy/download/.empty", 1, sha256(b"0").hexdigest(), "generated-marker"),
    )
```

`materialize_snapshot` uses `open(source, "rb")` → `open(dest, "xb")`, hashes while copying, `flush/fsync`, then checks copied SHA/size against the scan and source stat/tree hash again. It must create only a new caller-owned staging directory.

- [ ] **Step 5: Run focused tests and a metadata-only real preflight**

Run:

```powershell
python -X utf8 -m unittest mod-tools/tests/test_offline_store.py -v
python -X utf8 mod-tools/wf_offline_store.py preflight --profile cn --snapshot-version 1.4.196 --legacy-zip "弹国服/单机版数据包.zip" --tail-zip ".cdn/cn/archive-common-diff/pinball-1.4.195-1.4.196-1-mod07200253.zip" --no-copy
```

Expected: tests PASS; final JSON reports common `113822`, medium `23458`, android `1009`, total `138289`, legacy `137820`, added `469`, missing `0`, tail verified `12`, and does not create a staging tree.

- [ ] **Step 6: Commit store freezing**

```powershell
git add mod-tools/wf_offline_store.py mod-tools/tests/test_offline_store.py
git commit -m "feat(mod-tools): freeze offline resource snapshot"
```

---

### Task 4: Apply and prove the minimal Player 1000 overlay

**Files:**
- Modify: `mod-tools/wf_mod_tool.py:416-490`
- Create: `mod-tools/wf_offline_player.py`
- Create: `mod-tools/tests/test_offline_player.py`

**Interfaces:**
- Consumes: staged common root and logical `master/player/player_character.orderedmap` at `51/b73a9401c1fae38366ee79f4274942254d389c`.
- Produces: `read_orderedmap_raw_rows_from_bytes`, `add_initial_characters_to_bytes`, and `apply_initial_player_overlay`.

- [ ] **Step 1: Write pure-bytes and staged-write tests**

```python
def test_overlay_preserves_existing_row_and_adds_only_three_level_one_rows(self):
    raw = self.player_character_bytes({"1000": {"1": "2"}})
    output, report = module.add_initial_characters_to_bytes(raw)
    self.assertEqual(self.parse(output), {"1000": {
        "1": "2", "129999": "1", "139999": "1", "149999": "1",
    }})
    self.assertEqual(report.added_character_ids, ("129999", "139999", "149999"))
    self.assertEqual(report.character_level, 1)

def test_overlay_rejects_missing_player_and_non_idempotent_conflict(self):
    with self.assertRaisesRegex(module.PlayerOverlayError, "player 1000"):
        module.add_initial_characters_to_bytes(self.player_character_bytes({"999": {"1": "2"}}))
    with self.assertRaisesRegex(module.PlayerOverlayError, "conflicting character level"):
        module.add_initial_characters_to_bytes(self.player_character_bytes({"1000": {"129999": "80"}}))
```

Add a test that snapshots the staged tree and proves exactly one root-qualified member changes, the source fixture stays unchanged, output reparses, and no `8000101..8000115` appears in any player possession table.

- [ ] **Step 2: Run tests and observe missing bytes API/module**

Run: `python -X utf8 -m unittest mod-tools/tests/test_offline_player.py -v`

Expected: FAIL because `read_orderedmap_raw_rows_from_bytes` and `wf_offline_player` do not exist.

- [ ] **Step 3: Add the bytes reader and immutable overlay report**

```python
def read_orderedmap_raw_rows_from_bytes(raw: bytes, logical_path: str = "[memory-bytes]") -> OrderedMap:
    node = parse_node(raw)
    return _orderedmap_raw_rows_from_node(node, logical_path)

@dataclass(frozen=True, slots=True)
class PlayerOverlayReport:
    logical_path: str
    relative_path: str
    before_sha256: str
    after_sha256: str
    before_character_ids: tuple[str, ...]
    after_character_ids: tuple[str, ...]
    added_character_ids: tuple[str, ...]
    character_level: int
```

`add_initial_characters_to_bytes` copies the parsed mapping, preserves every original key/value byte semantics, inserts the three sorted ID rows with string value `"1"`, serializes with the existing raw-row builder, immediately reparses, and rejects any before-row drift.

- [ ] **Step 4: Implement atomic staged replacement without writing through a link**

```python
def apply_initial_player_overlay(staged_common_root: Path) -> PlayerOverlayReport:
    target = staged_common_root / "51" / "b73a9401c1fae38366ee79f4274942254d389c"
    output, report = add_initial_characters_to_bytes(target.read_bytes())
    temp = target.with_name(target.name + ".wf-offline-new")
    with temp.open("xb") as stream:
        stream.write(output)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, target)
    return report
```

Reject symlink/reparse targets and ensure cleanup removes only the exact temporary file on failure.

- [ ] **Step 5: Run focused and master-codec regressions**

Run:

```powershell
python -X utf8 -m unittest mod-tools/tests/test_offline_player.py -v
python -X utf8 -m unittest mod-tools/tests/test_wf_mod_tool.py -v
```

Expected: PASS; output report contains only three added IDs and one changed common member.

- [ ] **Step 6: Commit the Player overlay**

```powershell
git add mod-tools/wf_mod_tool.py mod-tools/wf_offline_player.py mod-tools/tests/test_offline_player.py
git commit -m "feat(mod-tools): add offline initial character overlay"
```

---

### Task 5: Gate all new content and replace the invalid Seris workspace claim with equivalent snapshot evidence

**Files:**
- Modify: `mod-tools/wf_rogue_validate.py:95-210`
- Create: `mod-tools/wf_offline_content.py`
- Create: `mod-tools/tests/test_offline_content.py`

**Interfaces:**
- Consumes: `StoreRoots`, `ManifestEntry`, staged common/medium/android roots, `inspect_workspace`, `char_asset_requirements`, `build_requirement_report`, `wf_rogue_rewards.EVENT_ID/TOKEN_ID/WEAPONS`, Phase 4 patch asset literals, and final APK client report.
- Produces: `CharacterReleaseSpec`, `CharacterEvidenceReport`, `OfflineContentReport`, `validate_rogue_data`, `verify_character_release`, `build_published_snapshot_evidence`, and `validate_offline_content(staged_roots, *, workspace_sources, phase4_asset_logicals, assets_dir, client_report=None)`.

- [ ] **Step 1: Write identity, 37/37, three-layer and rogue-content tests**

```python
def test_seris_workspace_with_stella_identity_is_rejected(self):
    spec = module.CharacterReleaseSpec(129999, "seris_dragon_king")
    report = self.workspace_report(character_id=139999, code_name="stella_summer_goddess", ready=True)
    with self.assertRaisesRegex(module.ContentGateError, "identity mismatch"):
        module.verify_character_workspace_report(spec, report, self.snapshot)

def test_equivalent_seris_snapshot_evidence_binds_every_required_byte(self):
    report = module.build_published_snapshot_evidence(
        module.CharacterReleaseSpec(129999, "seris_dragon_king"),
        self.snapshot, phase4_asset_logicals=self.phase4_asset_logicals,
    )
    self.assertEqual(report.identity, {"character_id": 129999, "code_name": "seris_dragon_king"})
    self.assertEqual((report.required_present, report.required_total), (37, 37))
    self.assertTrue(report.three_layer_consistent)
    self.assertEqual(len(report.missing), 0)
    self.assertEqual(report.seal_sha256, module.sha256_canonical_report(report))
```

Add tests for one missing or wrong-hash medium/android file, workspace manifest seal drift, unreadable package, master outer-key absence, Phase 4 asset literal absence, all 15 weapons, event `700099`, 15 rounds, token `2370099`, shop/mirror/reward/icon mapping, and no weapons in Player 1000 possession.

- [ ] **Step 2: Run the content tests and confirm the current Seris evidence fails**

Run: `python -X utf8 -m unittest mod-tools/tests/test_offline_content.py -v`

Expected: FAIL because the content module does not exist; the real-fixture identity test must later report `expected 129999/seris_dragon_king, got 139999/stella_summer_goddess`.

- [ ] **Step 3: Extract a pure rogue-data validator**

```python
@dataclass(frozen=True, slots=True)
class RogueDataReport:
    event_id: int
    round_count: int
    token_id: int
    weapon_ids: tuple[int, ...]
    missing_logicals: tuple[str, ...]
    ready: bool

@dataclass(frozen=True, slots=True)
class CharacterEvidenceReport:
    identity: Mapping[str, int | str]
    evidence_mode: Literal["sealed-workspace", "published-snapshot"]
    required_present: int
    required_total: int
    three_layer_consistent: bool
    bound_files: tuple[ManifestEntry, ...]
    missing: tuple[str, ...]
    seal_sha256: str

@dataclass(frozen=True, slots=True)
class OfflineContentReport:
    rogue: RogueDataReport
    characters: tuple[CharacterEvidenceReport, ...]
    client_gate_ready: bool | None
    ready: bool

def validate_rogue_data(store: Path, assets_dir: Path) -> RogueDataReport:
    report = validate_release_data_only(store, assets_dir)
    if report.event_id != 700099 or report.round_count != 15:
        raise RogueValidationError("rush event 700099 must have exactly 15 rounds")
    if report.token_id != 2370099 or report.weapon_ids != tuple(range(8000101, 8000116)):
        raise RogueValidationError("rogue token or weapon set mismatch")
    return report
```

Implement `validate_release_data_only(store, assets_dir) -> RogueDataReport` by moving the existing table/PNG/reward/shop checks currently inside `validate_release` without changing their predicates. Keep existing `validate_release` and `require_release_ready` behavior by making them call this pure function plus their current client-report checks.

- [ ] **Step 4: Implement strict character identity and workspace binding**

```python
@dataclass(frozen=True, slots=True)
class CharacterReleaseSpec:
    character_id: int
    code_name: str

CHARACTERS = (
    CharacterReleaseSpec(129999, "seris_dragon_king"),
    CharacterReleaseSpec(139999, "stella_summer_goddess"),
    CharacterReleaseSpec(149999, "white_wolf_gerald"),
)

def verify_character_workspace_report(spec: CharacterReleaseSpec, report: Mapping[str, Any], snapshot: StoreRoots) -> CharacterEvidenceReport:
    actual = (int(report["identity"]["character_id"]), str(report["identity"]["code_name"]))
    if actual != (spec.character_id, spec.code_name):
        raise ContentGateError(f"identity mismatch: expected {spec.character_id}/{spec.code_name}, got {actual[0]}/{actual[1]}")
    if not report["release_ready"] or report["requirement_report"]["required_present"] != 37:
        raise ContentGateError(f"character {spec.character_id} is not 37/37 release-ready")
    return _bind_claimed_files_to_snapshot(spec, report, snapshot)
```

The binder must load and canonical-hash the package manifest, validate workspace input digest/seal, and compare every non-master client-root entry by root, relative path, size and SHA against the frozen snapshot. Access denied is a fatal, named gate failure, never a reason to trust stale status.

- [ ] **Step 5: Implement equivalent published-snapshot evidence for 129999**

`build_published_snapshot_evidence` must not read/write the invalid workspace. It derives the exact 37 required logicals from `char_asset_requirements("seris_dragon_king")`, extracts every `character/`, `battle/`, `sound_effect/` and voice asset literal from the tracked Phase 4 `PATCHES`, resolves each logical through the current asset mapping into one of the three frozen roots, verifies every byte, and checks ID/action/ability/skill/master references in staged common. It emits a canonical report containing every logical/root/hash and a `seal_sha256` computed over the report without that field.

```python
def build_published_snapshot_evidence(
    spec: CharacterReleaseSpec,
    snapshot: StoreRoots,
    *,
    phase4_asset_logicals: Collection[str],
) -> CharacterEvidenceReport:
    required = tuple(sorted(_required_37_logicals(spec.code_name) | set(phase4_asset_logicals)))
    bound = tuple(_resolve_and_hash_logical(snapshot, logical) for logical in required)
    _assert_character_master_identity(snapshot.common, spec)
    unsigned = CharacterEvidenceReport(
        identity={"character_id": spec.character_id, "code_name": spec.code_name},
        evidence_mode="published-snapshot", required_present=37, required_total=37,
        three_layer_consistent=True, bound_files=bound, missing=(), seal_sha256="",
    )
    return replace(unsigned, seal_sha256=sha256_canonical_report(unsigned))
```

The real 129999 gate accepts only this equivalent report or a future identity-correct sealed workspace. It records why the stale/misidentified workspace was rejected.

- [ ] **Step 6: Run focused, rogue and character regressions**

Run:

```powershell
python -X utf8 -m unittest mod-tools/tests/test_offline_content.py -v
python -X utf8 -m unittest mod-tools/tests/test_rogue_validate.py -v
python -X utf8 -m unittest mod-tools/tests/test_character_requirements.py -v
python -X utf8 -m unittest mod-tools/tests/test_character_workspace.py -v
```

Expected: PASS; the invalid Seris workspace fixture is rejected and the byte-bound equivalent 1.4.196 snapshot fixture is accepted.

- [ ] **Step 7: Commit the content gates**

```powershell
git add mod-tools/wf_rogue_validate.py mod-tools/wf_offline_content.py mod-tools/tests/test_offline_content.py
git commit -m "feat(mod-tools): gate offline release content"
```

---

### Task 6: Build and fully re-read a deterministic Zip64 data archive

**Files:**
- Create: `mod-tools/wf_offline_zip.py`
- Create: `mod-tools/tests/test_offline_zip.py`

**Interfaces:**
- Consumes: a complete staged `WorldFlipper/` tree and sorted `ManifestEntry` records from Tasks 3–5.
- Produces: `write_data_zip(...) -> ZipBuildReport` and `verify_data_zip(...) -> ZipVerificationReport`.

- [ ] **Step 1: Write deterministic layout and forced-Zip64 tests**

```python
def test_zip_has_one_root_no_directories_and_fixed_metadata(self):
    report = module.write_data_zip(self.stage, self.output, self.entries)
    with zipfile.ZipFile(self.output) as archive:
        infos = archive.infolist()
    self.assertEqual([info.filename for info in infos], sorted(entry.path for entry in self.entries))
    self.assertTrue(all(info.filename.startswith("WorldFlipper/") for info in infos))
    self.assertTrue(all(not info.is_dir() for info in infos))
    self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos))
    self.assertTrue(all(info.compress_type == zipfile.ZIP_STORED for info in infos))
    self.assertEqual(report.member_count, len(self.entries))

def test_zip64_eocd_is_written_when_file_count_crosses_limit(self):
    with mock.patch.object(zipfile, "ZIP_FILECOUNT_LIMIT", 2):
        module.write_data_zip(self.stage, self.output, self.entries[:3])
    self.assertIn(b"PK\x06\x06", self.output.read_bytes())
```

Add tests for duplicate/casefold-colliding names, absolute/drive/backslash/`..` paths, wrong `.empty`, double `WorldFlipper/WorldFlipper`, no explicit directories, tampered payload, manifest/hash mismatch, and exclusive output creation.

- [ ] **Step 2: Run tests and confirm the module is absent**

Run: `python -X utf8 -m unittest mod-tools/tests/test_offline_zip.py -v`

Expected: FAIL with missing `wf_offline_zip`.

- [ ] **Step 3: Implement stable streaming Zip64 output**

```python
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
FIXED_EXTERNAL_ATTR = 0o100644 << 16

@dataclass(frozen=True, slots=True)
class ZipVerificationReport:
    archive_sha256: str
    member_count: int
    counts: Mapping[str, int]
    total_uncompressed_bytes: int
    zip64: bool

ZipBuildReport = ZipVerificationReport

def _zip_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = FIXED_EXTERNAL_ATTR
    info.extra = b""
    info.comment = b""
    return info

def write_data_zip(staged_worldflipper: Path, output: Path, entries: Sequence[ManifestEntry]) -> ZipBuildReport:
    _validate_entry_names(entries)
    with zipfile.ZipFile(output, "x", allowZip64=True) as archive:
        for entry in sorted(entries, key=lambda item: item.path):
            with archive.open(_zip_info(entry.path), "w", force_zip64=True) as destination:
                _copy_and_verify(staged_worldflipper.parent / entry.path, destination, entry)
    return verify_data_zip(output, {entry.path: entry for entry in entries}, expected_members=len(entries))
```

The verifier reopens the final ZIP, rejects duplicates/casefold collisions/path escape, streams every member, recomputes size/SHA, checks `138291` for production, validates counts `113822/23458/1009 + 2`, and requires a Zip64 EOCD.

- [ ] **Step 4: Run focused tests twice and compare archive hashes**

Run:

```powershell
python -X utf8 -m unittest mod-tools/tests/test_offline_zip.py -v
python -X utf8 -m unittest mod-tools/tests/test_offline_zip.py -v
```

Expected: both runs PASS and the deterministic fixture ZIP SHA-256 is identical across runs.

- [ ] **Step 5: Commit the Zip64 builder**

```powershell
git add mod-tools/wf_offline_zip.py mod-tools/tests/test_offline_zip.py
git commit -m "feat(mod-tools): build deterministic offline Zip64 data"
```

---

### Task 7: Discover tools and manage a stable signer without leaking secrets

**Files:**
- Create: `mod-tools/wf_offline_toolchain.py`
- Create: `mod-tools/tests/test_offline_toolchain.py`

**Interfaces:**
- Produces: `Toolchain`, `SigningConfig`, `discover_toolchain`, `load_signing_config`, `init_signer_interactive`, `parse_apksigner_verify`, and `redact_process_error`.
- Consumed by: Tasks 8–15.

- [ ] **Step 1: Write discovery, signer and redaction tests**

```python
def test_signing_config_requires_keystore_public_fingerprint_and_password_env(self):
    home = self.path / ".wf-offline-release"
    with self.assertRaisesRegex(module.ToolchainError, "missing stable keystore"):
        module.load_signing_config(home, env={})
    (home / "wf-offline-release.jks").write_bytes(b"fixture")
    (home / "signer-public.json").write_text(json.dumps({
        "schema_version": 1,
        "alias": "wf-offline-release",
        "certificate_sha256": "ab" * 32,
    }), encoding="utf-8")
    with self.assertRaisesRegex(module.ToolchainError, "WF_OFFLINE_KEYSTORE_PASSWORD"):
        module.load_signing_config(home, env={})

def test_errors_reports_and_commands_never_contain_password(self):
    secret = "p@ss-fixture-123"
    runner = self.fake_runner_failure(stderr=f"bad password {secret}")
    with self.assertRaises(module.ToolchainError) as raised:
        module.run_apksigner(self.config(secret), runner=runner)
    self.assertNotIn(secret, str(raised.exception))
    self.assertTrue(all(secret not in " ".join(call.argv) for call in runner.calls))
```

Add tests for discovery priority `explicit → WF_OFFLINE_* / Android SDK env → PATH → repo FFDec`, ambiguous/missing tools, version capture, signer fingerprint drift, v1/v2/v3 parsing, password UTF-8/UTF-16 redaction, and bootstrap commands containing no `-storepass/-keypass` values.

- [ ] **Step 2: Run tests and confirm the module is absent**

Run: `python -X utf8 -m unittest mod-tools/tests/test_offline_toolchain.py -v`

Expected: FAIL with missing `wf_offline_toolchain`.

- [ ] **Step 3: Implement tool and signer contracts**

```python
@dataclass(frozen=True, slots=True)
class Toolchain:
    java: Path
    ffdec: Path
    aapt: Path
    zipalign: Path
    apksigner: Path
    adb: Path | None
    mumu_manager: Path | None
    versions: Mapping[str, str]

@dataclass(frozen=True, slots=True)
class SigningConfig:
    keystore: Path
    alias: str
    password_env: str
    expected_certificate_sha256: str

def load_signing_config(release_home: Path, *, env: Mapping[str, str]) -> SigningConfig:
    public = json.loads((release_home / "signer-public.json").read_text("utf-8"))
    password = env.get("WF_OFFLINE_KEYSTORE_PASSWORD", "")
    if not password:
        raise ToolchainError("WF_OFFLINE_KEYSTORE_PASSWORD is not set")
    return SigningConfig(
        release_home / "wf-offline-release.jks",
        "wf-offline-release",
        "WF_OFFLINE_KEYSTORE_PASSWORD",
        _normalize_fingerprint(public["certificate_sha256"]),
    )
```

Reports expose only tool basename/version and certificate fingerprint. They never serialize local executable, keystore or release-home absolute paths.

- [ ] **Step 4: Implement explicit interactive signer bootstrap**

`init_signer_interactive` requires the exact confirmation `CREATE_WF_OFFLINE_RELEASE_SIGNER`, refuses an existing keystore/public config, creates the release-home directory outside the repo, invokes Java 8 `keytool -genkeypair` with alias/RSA-4096/validity/DN but no password arguments, inherits a real console for password prompts, exports only a public certificate, calculates its SHA-256, writes `signer-public.json` atomically, and deletes the temporary public certificate. The ordinary build command never calls this function automatically.

```python
KEYTOOL_ARGS = (
    "-genkeypair", "-alias", "wf-offline-release", "-keyalg", "RSA",
    "-keysize", "4096", "-validity", "9125",
    "-dname", "CN=WF Offline Release, OU=Offline Build, O=Local, C=CN",
)
```

- [ ] **Step 5: Run tests and a read-only real tool discovery**

Run:

```powershell
python -X utf8 -m unittest mod-tools/tests/test_offline_toolchain.py -v
python -X utf8 mod-tools/wf_offline_toolchain.py discover --json
```

Expected: tests PASS; discovery reports Java, FFDec 26.2.1, aapt, zipalign, apksigner and optional ADB/MuMu without embedding personal absolute paths in persisted output. It may report `signer_ready=false`; it must not create a key.

- [ ] **Step 6: Commit toolchain and signer management**

```powershell
git add mod-tools/wf_offline_toolchain.py mod-tools/tests/test_offline_toolchain.py
git commit -m "feat(mod-tools): add offline Android toolchain gates"
```

---

### Task 8: Extract the abyss gate as a composable SWF stage

**Files:**
- Modify: `client-patch/abyss-mode-equipment/build_apk.py`
- Create: `mod-tools/tests/test_offline_apk_abyss_merge.py`
- Regression: `mod-tools/tests/test_abyss_mode_patch.py`
- Regression: `mod-tools/tests/test_abyss_apk_builder.py`

**Interfaces:**
- Consumes: existing `patch.py` exact gate semantics, Java/FFDec toolchain and an extracted base SWF.
- Produces: `PatchStageReport` and `apply_gate_to_swf(source_swf, output_swf, *, ffdec, java, profile_dir, work_dir) -> PatchStageReport`.

- [ ] **Step 1: Write a fake-toolchain test for SWF-only composition**

```python
def test_apply_gate_to_swf_exports_base_class_patches_reopens_and_never_signs(self):
    runner = FakeFfdecRunner(self.base_class, self.post_patch_class)
    report = module.apply_gate_to_swf(
        self.source_swf, self.output_swf,
        ffdec=self.ffdec, java=self.java, profile_dir=self.profile, work_dir=self.work,
        runner=runner,
    )
    self.assertEqual(report.stage, "abyss-mode-equipment")
    self.assertEqual(report.match_count, 1)
    self.assertEqual(report.output_sha256, sha256_file(self.output_swf))
    self.assertFalse(any("apksigner" in call.program or "zipalign" in call.program for call in runner.calls))
    self.assertEqual([call.kind for call in runner.calls], ["export", "import", "reopen-export"])
```

Add tests for source/output alias rejection, source hash drift during run, exact class export, patch match count other than one, reopen verification failure, isolated APPDATA/profile, exclusive output creation and temporary cleanup.

- [ ] **Step 2: Run the focused test and observe the missing SWF-stage interface**

Run: `python -X utf8 -m unittest mod-tools/tests/test_offline_apk_abyss_merge.py -v`

Expected: FAIL because `apply_gate_to_swf` is not defined.

- [ ] **Step 3: Extract the existing verified flow without changing patch semantics**

```python
@dataclass(frozen=True, slots=True)
class PatchStageReport:
    stage: str
    output_path: Path
    input_sha256: str
    output_sha256: str
    target_class: str
    before_method_sha256: str
    after_method_sha256: str
    match_count: int

def apply_gate_to_swf(source_swf: Path, output_swf: Path, *, ffdec: Path, java: Path,
                      profile_dir: Path, work_dir: Path, runner: Runner = subprocess_runner) -> PatchStageReport:
    _require_distinct_new_output(source_swf, output_swf)
    exported = export_verified_class(source_swf, "BattleCharacterLogic", ffdec=ffdec, java=java,
                                     profile_dir=profile_dir, work_dir=work_dir, runner=runner)
    before = sha256_file(exported)
    patch_file(exported)
    verify_file(exported)
    _import_class_into_copy(source_swf, output_swf, exported, runner=runner)
    reopened = export_verified_class(output_swf, "BattleCharacterLogic", ffdec=ffdec, java=java,
                                     profile_dir=profile_dir, work_dir=work_dir, runner=runner)
    verify_file(reopened)
    return PatchStageReport("abyss-mode-equipment", output_swf, sha256_file(source_swf), sha256_file(output_swf),
                            "BattleCharacterLogic", before, sha256_file(reopened), 1)
```

The existing APK builder may call this function, but its public behavior and current tests must remain compatible.

- [ ] **Step 4: Run focused and abyss regression suites**

Run:

```powershell
python -X utf8 -m unittest mod-tools/tests/test_offline_apk_abyss_merge.py -v
python -X utf8 -m unittest mod-tools/tests/test_abyss_mode_patch.py -v
python -X utf8 -m unittest mod-tools/tests/test_abyss_apk_builder.py -v
```

Expected: PASS; the composable stage produces no APK/signing command.

- [ ] **Step 5: Commit the composable abyss stage**

```powershell
git add client-patch/abyss-mode-equipment/build_apk.py mod-tools/tests/test_offline_apk_abyss_merge.py
git commit -m "refactor(client-patch): expose abyss SWF stage"
```

---

### Task 9: Promote and re-anchor the nine-site Seris Phase 4 patch

**Files:**
- Create: `client-patch/offline-android/seris_phase4_pcode.py`
- Create: `client-patch/offline-android/lock_discovery.py`
- Create/update during this task: `client-patch/offline-android/base-lock.json`
- Create: `mod-tools/tests/test_offline_apk_seris.py`
- Read-only source: `work/seris_v2/phase4_client/phase4_pcode.py`
- Read-only source: `work/seris_v2/phase4_client/patch-manifest-phase4.json`

**Interfaces:**
- Consumes: the post-abyss SWF from Task 8, `dual-form-v1/abc_methods.py`, `dual-form-v1/pcode_tools.py`, and existing WIP Phase 4 semantics.
- Produces: immutable `PATCHES`, `extract_asset_logicals`, `apply_seris_phase4`, `verify_seris_phase4`, `discover_lock_candidate`, and `accept_lock_candidate`.

- [ ] **Step 1: Write nine-site schema, exact-match and semantic tests before copying production code**

```python
EXPECTED_SITES = {
    "preload_seris_dual_form_assets",
    "switch_special_pixel_slot_preserve_frame_scale",
    "default_seris_human_power_flip",
    "dynamic_seris_skill_cutin",
    "dynamic_seris_member_status_path",
    "refresh_seris_member_status_texture",
    "dynamic_seris_control_board_path",
    "refresh_seris_control_board_texture",
    "route_seris_skill_voice_by_form",
}

def test_patch_schema_has_exact_nine_sites_and_no_lock_refresh(self):
    self.assertEqual({patch.site_id for patch in module.PATCHES}, EXPECTED_SITES)
    self.assertFalse(hasattr(module, "refresh_locks"))

def test_each_patch_rejects_zero_or_multiple_anchors(self):
    for patch in module.PATCHES:
        with self.subTest(patch=patch.site_id):
            with self.assertRaises(module.SerisPatchError):
                patch.apply("")
            with self.assertRaises(module.SerisPatchError):
                patch.apply(patch.before_anchor + patch.before_anchor)
```

Add fixture tests for all nine before→after method blocks, idempotence rejection, asset-literal extraction, schema-4 report, and native compatibility checks for `MemberImpl/startPowerFlip`, `MemberImpl/resolveConditionalKind`, `PixelArtCharacterView/spriteSheetLoadCompleted`, and `MemberView/MemberView`.

- [ ] **Step 2: Run tests and confirm tracked production code is absent**

Run: `python -X utf8 -m unittest mod-tools/tests/test_offline_apk_seris.py -v`

Expected: FAIL because `client-patch/offline-android/seris_phase4_pcode.py` is absent.

- [ ] **Step 3: Promote the WIP patch logic without modifying or importing from work/**

Copy the nine patch definitions and semantic verifiers into the tracked module, replace every hard-coded old body/method index with name-based `SwfMethodIndex.require_ref`, and keep before/after code hashes in the external lock file.

```python
@dataclass(frozen=True, slots=True)
class SerisPatch:
    site_id: str
    class_name: str
    method_name: str
    apply: Callable[[str], str]
    verify: Callable[[str], None]

@dataclass(frozen=True, slots=True)
class SerisPatchReport:
    output_path: Path
    input_sha256: str
    output_sha256: str
    site_ids: tuple[str, ...]
    before_hashes: Mapping[str, str]
    after_hashes: Mapping[str, str]
    asset_logicals: tuple[str, ...]
    verified: bool

def apply_seris_phase4(source_swf: Path, output_swf: Path, lock: Mapping[str, Any],
                       *, ffdec: Path, java: Path, profile_dir: Path, work_dir: Path) -> SerisPatchReport:
    current = source_swf
    for patch in PATCHES:
        current = _replace_one_method_and_reopen(current, patch, lock[patch.site_id], ffdec, java, profile_dir, work_dir)
    _copy_exclusive(current, output_swf)
    return verify_seris_phase4(output_swf, lock, ffdec=ffdec, java=java, profile_dir=profile_dir)
```

The implementation stages each replacement into a new SWF, reopens it, verifies the patched method and all already-applied sites, then deletes only that stage's temporary predecessor.

- [ ] **Step 4: Build a controlled post-abyss lock candidate**

Run:

```powershell
python -X utf8 client-patch/offline-android/lock_discovery.py discover --source-apk "C:\Users\12101\Downloads\base.apk.1" --expected-apk-sha256 4f6884f33641788108c0522c7c70036c63ba530e1fdb183105b3cd395bdd66f6 --after-stage abyss --output work/offline-lock-review-1.4.196.json
```

Expected: stable JSON with `status="candidate"`, `stage="post-abyss"`, `site_count=9`, exact base hashes, seven unchanged semantic sites, and two base-specific candidates for `BattleCharacterLogic/resolvePathCollection` and `getPowerFlipAction`. It must not edit `base-lock.json`.

The candidate must identify the unpatched base methods as:

```text
BattleCharacterLogic/resolvePathCollection  4c17b898e702b11092ee4d8ec148b18b3550900475f3b0e14a1ef725062f84fd
BattleCharacterLogic/getPowerFlipAction     fe609f8079a69de8b6276a10f166676e232a917aedf03c1702314dbcd96ac4c9
```

- [ ] **Step 5: Verify the two three-way merges and accept the immutable lock**

The lock verifier must prove:

```text
resolvePathCollection: base offline path behavior + abyss gate behavior + Seris dual-form preload behavior
getPowerFlipAction: base offline behavior + Seris human/dragon power-flip selection
all nine sites: exact class/method identity, one anchor, post-patch semantic verifier passes
```

Then run:

```powershell
python -X utf8 client-patch/offline-android/lock_discovery.py accept --candidate work/offline-lock-review-1.4.196.json --output client-patch/offline-android/base-lock.json --confirm ACCEPT_OFFLINE_BASE_4F6884F3
```

Expected: `base-lock.json` is canonical UTF-8 JSON containing the known APK/SWF/manifest/DEX/native/offline/save hashes and all post-abyss Seris before/after locks, with no absolute path, timestamp, password or refresh command.

- [ ] **Step 6: Run Seris tests against the accepted lock**

Run:

```powershell
python -X utf8 -m unittest mod-tools/tests/test_offline_apk_seris.py -v
python -X utf8 client-patch/offline-android/seris_phase4_pcode.py verify-lock --lock client-patch/offline-android/base-lock.json
```

Expected: PASS and stable JSON `site_count=9`, `verified=true`, `asset_logicals` non-empty.

- [ ] **Step 7: Commit tracked Phase 4 code and immutable locks**

```powershell
git add client-patch/offline-android/seris_phase4_pcode.py client-patch/offline-android/lock_discovery.py client-patch/offline-android/base-lock.json mod-tools/tests/test_offline_apk_seris.py
git commit -m "feat(client-patch): merge Seris Phase 4 into offline base"
```

---

### Task 10: Implement all three render-scale sites and the exact resource-version patch

**Files:**
- Create: `client-patch/offline-android/render_scale_pcode.py`
- Create: `client-patch/offline-android/resource_version_pcode.py`
- Update: `client-patch/offline-android/base-lock.json`
- Create: `mod-tools/tests/test_offline_apk_render_scale.py`
- Create: `mod-tools/tests/test_offline_apk_resource_version.py`
- Read-only references: `client-patch/render-scale-v1/build_render_scale_apk.py`, `client-patch/render-scale-v1/patch_memberview_site2.py`

**Interfaces:**
- Consumes: post-Seris SWF and the accepted base lock.
- Produces: `apply_render_scale`, `verify_render_scale`, `patch_pixel_art`, `patch_member_view_ctor`, `patch_character_cell`, `apply_resource_version`, and `verify_resource_version`.

- [ ] **Step 1: Write P-code fixture tests for PixelArt, MemberView and CharacterCellView**

```python
def test_member_view_removes_only_character_scale_renderer_and_keeps_shadow_scale(self):
    output = module.patch_member_view_ctor(self.member_view_before)
    self.assertNotIn(self.character_scale_anchor, output)
    self.assertIn(self.shadow_scale_anchor, output)
    module.verify_member_view_ctor(output)

def test_character_cell_view_scales_after_matrix_without_overwriting_base_logic(self):
    output = module.patch_character_cell(self.character_cell_before)
    self.assertIn(self.base_transformation_matrix_anchor, output)
    self.assertEqual(output.count(self.default_scale_getter), 2)
    self.assertEqual(output.count(self.inserted_scale_anchor), 1)
    module.verify_character_cell(output)
```

Add PixelArt tests, zero/multiple-anchor rejection for all three functions, pre/post method hashes, and a full stage test that checks the three base identities:

```text
PixelArtCharacterView/spriteSheetLoadCompleted  body 88088 / method 96450  9475368c4dd326f0d8230ba724d96a60af5d30dba37ac5d43d5bdd04a85b038b
MemberView/MemberView                           body 61075 / method 66123  0ca2af059a85e432c9c6dc991126d0eeba57acaa5ecc152aee83e36ed19a9d77
CharacterCellView/drawWithAdvanceFlag          body 66257 / method 72109  cc64eafcb0bbaeb4f1ae705944da569cc1d59bf9dc7636b1bbfe64342175e3a7
```

Real base inspection showed that `CharacterCell/CharacterCell` only initializes
timeline, pedestal and playhead state; it has no character id, scale or render
matrix and therefore cannot implement the list/party scale fix.  The reviewed
third site is the post-matrix block in `CharacterCellView/drawWithAdvanceFlag`.
It multiplies both axes by `defaultScale / 6`, which is a no-op for official
`defaultScale=6` assets while preserving custom frame scale.

- [ ] **Step 2: Write the exact 1.4.54→1.4.196 resource-version tests**

```python
def test_resource_version_replaces_one_expected_value_and_preserves_full_package(self):
    output = module.patch_resource_version(self.before_block, source="1.4.54", target="1.4.196")
    self.assertEqual(output.count('PushString "1.4.196"'), 1)
    self.assertNotIn('PushString "1.4.54"', output)
    self.assertIn(self.is_full_package_true_anchor, output)
    module.verify_resource_version(output, expected="1.4.196")
```

Add zero/two source occurrence rejection, existing-target rejection, wrong method hash and DummyRemote/isFullPackage drift tests.

- [ ] **Step 3: Run both suites and confirm missing implementations**

Run:

```powershell
python -X utf8 -m unittest mod-tools/tests/test_offline_apk_render_scale.py -v
python -X utf8 -m unittest mod-tools/tests/test_offline_apk_resource_version.py -v
```

Expected: FAIL because the new modules are absent; CharacterCellView must not be silently skipped.

- [ ] **Step 4: Implement three base-specific P-code patches**

```python
@dataclass(frozen=True, slots=True)
class RenderSite:
    site_id: str
    class_name: str
    method_name: str
    patch: Callable[[str], str]
    verify: Callable[[str], None]

RENDER_SITES = (
    RenderSite("pixel-art", "PixelArtCharacterView", "spriteSheetLoadCompleted", patch_pixel_art, verify_pixel_art),
    RenderSite("member-view", "MemberView", "MemberView", patch_member_view_ctor, verify_member_view_ctor),
    RenderSite("character-cell", "CharacterCellView", "drawWithAdvanceFlag", patch_character_cell, verify_character_cell),
)

@dataclass(frozen=True, slots=True)
class RenderPatchReport:
    output_path: Path
    input_sha256: str
    output_sha256: str
    site_ids: tuple[str, ...]
    before_hashes: Mapping[str, str]
    after_hashes: Mapping[str, str]
    verified: bool

@dataclass(frozen=True, slots=True)
class ResourceVersionReport:
    output_path: Path
    input_sha256: str
    output_sha256: str
    source_version: str
    output_version: str
    is_full_package: bool
    verified: bool

def apply_render_scale(source_swf: Path, output_swf: Path, lock: Mapping[str, Any], **tools: Any) -> RenderPatchReport:
    current = source_swf
    for site in RENDER_SITES:
        current = _replace_one_method_and_reopen(current, site, lock[site.site_id], **tools)
    _copy_exclusive(current, output_swf)
    return verify_render_scale(output_swf, lock, **tools)
```

Port only the exact P-code behavior needed from the old render builder; do not import old full-class ActionScript or overwrite base variants.

- [ ] **Step 5: Implement resource-version stage and append reviewed locks**

```python
def patch_resource_version(block: str, *, source: str = "1.4.54", target: str = "1.4.196") -> str:
    source_anchor = f'PushString "{source}"'
    target_anchor = f'PushString "{target}"'
    if block.count(source_anchor) != 1 or block.count(target_anchor) != 0:
        raise ResourceVersionError("resource-version anchor count mismatch")
    output = block.replace(source_anchor, target_anchor, 1)
    verify_resource_version(output, expected=target)
    return output
```

Use controlled discovery/acceptance from Task 9 to append the three post-Seris render locks and the `boot_ffc6#$script364/$init` resource-version lock to `base-lock.json`; acceptance requires `ACCEPT_OFFLINE_BASE_4F6884F3` and preserves canonical key order.

- [ ] **Step 6: Run focused and legacy render tests**

Run:

```powershell
python -X utf8 -m unittest mod-tools/tests/test_offline_apk_render_scale.py -v
python -X utf8 -m unittest mod-tools/tests/test_offline_apk_resource_version.py -v
python -X utf8 client-patch/render-scale-v1/test_build_render_scale_apk.py -v
```

Expected: PASS; reports show exactly three render sites and source/output versions `1.4.54/1.4.196`.

- [ ] **Step 7: Commit render, version and final locks**

```powershell
git add client-patch/offline-android/render_scale_pcode.py client-patch/offline-android/resource_version_pcode.py client-patch/offline-android/base-lock.json mod-tools/tests/test_offline_apk_render_scale.py mod-tools/tests/test_offline_apk_resource_version.py
git commit -m "feat(client-patch): add offline render and version patches"
```

---

### Task 11: Assemble, align, sign and verify the APK exactly once

**Files:**
- Create: `client-patch/offline-android/apk_baseline.py`
- Create: `client-patch/offline-android/build_offline_apk.py`
- Create: `client-patch/offline-android/README.md`
- Create: `mod-tools/tests/test_offline_apk_baseline.py`
- Create: `mod-tools/tests/test_offline_apk_builder.py`

**Interfaces:**
- Consumes: Tasks 7–10 toolchain, signer config, base lock and patch stages.
- Produces: `ApkBaselineReport`, `OfflineApkBuildConfig`, `ApkBuildReport`, `inspect_apk`, `assert_locked_baseline`, `assert_allowed_member_diff`, and `build_offline_apk`.

- [ ] **Step 1: Write base-contract tests with the known real hashes**

```python
def test_known_base_contract_is_locked(self):
    lock = module.load_base_lock(self.lock_path)
    self.assertEqual(lock.source_apk_sha256, "4f6884f33641788108c0522c7c70036c63ba530e1fdb183105b3cd395bdd66f6")
    self.assertEqual(lock.source_swf_sha256, "08187f538703aecadce264b7bd5e085411f8e3aedb5f48adf2cf035a100f550d")
    self.assertEqual(lock.manifest_sha256, "2823fbfad46bfcdc34c8df77b3f2ed2acf9f5812b8b61644304cc6d11109d6f9")
    self.assertEqual(lock.dex_sha256, {
        "classes.dex": "c12d119d425f0e8f35623dbac07296e00a8b9e60620c4f371b307121b389c043",
        "classes2.dex": "b310c77febb7da0d2908b32274391ae39226a9df334e0d7d7f51b5a081bc539b",
    })
    self.assertEqual(lock.native_aggregate_sha256, "a42f92e417199a9ac99ca4f63efa0db487019bdf1220a86301fcfa0a4118f995")
    self.assertEqual(lock.offline_method_sha256, {
        "DevConfig_individual/DevConfig_individual": "ac87a4744507d4fa47fa46af99290a1aec0c230a5338e317cbeeb7c80badc139",
        "boot_ffc6#$script364/$init": "afcb8c8602158db0a64ba1560f36875166004283bfe6a04ad9eeaf49ee3714b2",
        "InitializeDummyRemote/logicAssetLoadedHandler": "d17591dc3c793faaa02c1080968b0bb30384b968f70dbe9363d8860fa30fcd3c",
        "DummyRemote/debugUnlinkTwitter": "45bc87da473d018f700f349fda2c743a6d11509cc236390584dccf2ac7d75a38",
    })
```

Add tests for package `com.leiting.wf`, versionCode `1008001`, versionName `1.8.1`, exactly one `MANAGE_EXTERNAL_STORAGE`, main SWF count one, and the four offline method hashes from the base lock. Test that dormant RealRemote strings do not cause a false rejection while the active DevConfig hash does.

- [ ] **Step 2: Write fake-toolchain build-order, allowed-diff and signer tests**

```python
def test_builder_patches_once_rewrites_once_aligns_once_and_signs_once(self):
    report = module.build_offline_apk(self.config, runner=self.runner)
    self.assertEqual(report.patch_order, (
        "abyss-mode-equipment", "seris-phase4", "render-scale", "resource-version",
    ))
    self.assertEqual(self.runner.count("apk-rewrite"), 1)
    self.assertEqual(self.runner.count("zipalign-build"), 1)
    self.assertEqual(self.runner.count("apksigner-sign"), 1)
    self.assertEqual(self.runner.count("zipalign-check"), 1)
    self.assertEqual(self.runner.count("apksigner-verify"), 1)

def test_member_diff_allows_only_main_swf_and_top_level_signatures(self):
    with self.assertRaisesRegex(module.ApkBuildError, "unexpected member drift: classes.dex"):
        module.assert_allowed_member_diff(self.base_apk, self.apk_with_changed_dex)
    module.assert_allowed_member_diff(self.base_apk, self.apk_with_changed_swf_and_signatures)
```

Add tests for `META-INF/AIR/**` preservation, signature stripping limited to top-level signer files, output signer equals dedicated configured fingerprint rather than input fingerprint, v1/v2/v3 true, post-sign zipalign check, password redaction, Chinese final name handled via ASCII work path, failure/cancel cleanup, no overwrite and report path sanitization.

- [ ] **Step 3: Run baseline and builder tests and confirm missing modules**

Run:

```powershell
python -X utf8 -m unittest mod-tools/tests/test_offline_apk_baseline.py -v
python -X utf8 -m unittest mod-tools/tests/test_offline_apk_builder.py -v
```

Expected: FAIL because the offline APK modules are absent.

- [ ] **Step 4: Implement baseline inspection and byte-level member comparison**

```python
TARGET_SWF = "assets/worldflipper_android_release.swf"

def allowed_to_change(name: str) -> bool:
    return name == TARGET_SWF or is_signature_member(name)

def assert_allowed_member_diff(base_apk: Path, output_apk: Path) -> None:
    base = _member_content_hashes(base_apk, exclude=is_signature_member)
    output = _member_content_hashes(output_apk, exclude=is_signature_member)
    if set(base) != set(output):
        raise ApkBuildError("non-signature APK member set changed")
    drift = [name for name in base if name != TARGET_SWF and base[name] != output[name]]
    if drift:
        raise ApkBuildError(f"unexpected member drift: {drift[0]}")
```

`inspect_apk` also exports and hashes the active offline/save/resource methods by class+method identity. It records but does not require the input signer fingerprint `a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc` for output.

- [ ] **Step 5: Implement the single-pass transactional build**

```python
@dataclass(frozen=True, slots=True)
class OfflineApkBuildConfig:
    source_apk: Path
    baseline_lock: Path
    output_apk: Path
    report_path: Path
    work_dir: Path
    toolchain: Toolchain
    signing: SigningConfig

@dataclass(frozen=True, slots=True)
class ApkBaselineReport:
    apk_sha256: str
    swf_sha256: str
    package_name: str
    version_code: str
    version_name: str
    manifest_sha256: str
    dex_sha256: Mapping[str, str]
    native_aggregate_sha256: str
    offline_method_sha256: Mapping[str, str]

@dataclass(frozen=True, slots=True)
class ApkBuildReport:
    output_sha256: str
    certificate_sha256: str
    patch_order: tuple[str, ...]
    stage_reports: tuple[Mapping[str, Any], ...]
    full_resource_version: str
    aligned: bool
    signature_schemes: Mapping[str, bool]
    verified: bool

def build_offline_apk(config: OfflineApkBuildConfig, *, runner: Runner = subprocess_runner) -> ApkBuildReport:
    baseline = assert_locked_baseline(inspect_apk(config.source_apk, config.toolchain), config.baseline_lock)
    swf0 = _extract_exactly_one_swf(config.source_apk, config.work_dir)
    swf1 = apply_gate_to_swf(swf0, _next_stage(config.work_dir, 1), **_ffdec_args(config))
    swf2 = apply_seris_phase4(swf1.output_path, _next_stage(config.work_dir, 2), _lock(config), **_ffdec_args(config))
    swf3 = apply_render_scale(swf2.output_path, _next_stage(config.work_dir, 3), _lock(config), **_ffdec_args(config))
    swf4 = apply_resource_version(swf3.output_path, _next_stage(config.work_dir, 4), _lock(config), **_ffdec_args(config))
    unsigned = rewrite_apk_once(config.source_apk, swf4.output_path, config.work_dir / "unsigned.apk")
    assert_allowed_member_diff(config.source_apk, unsigned)
    aligned = zipalign_once(unsigned, config.work_dir / "aligned.apk", config.toolchain, runner)
    signed = sign_once(aligned, config.work_dir / "signed.apk", config.toolchain, config.signing, runner)
    verify_signed_apk(signed, config, baseline, runner)
    _copy_exclusive(signed, config.output_apk)
    return _write_sanitized_report(config, signed, baseline)
```

Actual code uses `try/finally`, fsync and exact work-owned paths; it never removes a pre-existing output/report. Signing commands use `--ks-pass env:WF_OFFLINE_KEYSTORE_PASSWORD --key-pass env:WF_OFFLINE_KEYSTORE_PASSWORD --v4-signing-enabled false`; after signing run `zipalign -c -p -v 4` and `apksigner verify --verbose --print-certs` and require v1/v2/v3 plus configured fingerprint.

- [ ] **Step 6: Verify final SWF and offline invariants after signing**

Re-extract the signed APK's SWF and rerun all stage verifiers. Require `fullResourceVersion=1.4.196`, `isFullPackage=true`, the locked active DummyRemote/save_haxe method hashes, 9 Seris sites, 3 render sites, abyss client gate report, unchanged manifest/DEX/native hashes, and sanitized report values.

- [ ] **Step 7: Run focused and inherited builder suites**

Run:

```powershell
python -X utf8 -m unittest mod-tools/tests/test_offline_apk_baseline.py -v
python -X utf8 -m unittest mod-tools/tests/test_offline_apk_builder.py -v
python -X utf8 -m unittest mod-tools/tests/test_abyss_apk_builder.py -v
```

Expected: PASS; fault-injection tests leave no final APK/report and never alter an older successful output.

- [ ] **Step 8: Commit the APK builder**

```powershell
git add client-patch/offline-android/apk_baseline.py client-patch/offline-android/build_offline_apk.py client-patch/offline-android/README.md mod-tools/tests/test_offline_apk_baseline.py mod-tools/tests/test_offline_apk_builder.py
git commit -m "feat(client-patch): build signed offline Android APK"
```

---

### Task 12: Freeze candidate artifacts, scan secrets and atomically finalize exactly five files

**Files:**
- Create: `mod-tools/wf_offline_bundle.py`
- Create: `mod-tools/templates/offline-import-guide.zh-CN.txt`
- Create: `mod-tools/tests/test_offline_bundle.py`

**Interfaces:**
- Consumes: APK/data/content/player/ZIP reports and a later device acceptance receipt.
- Produces: `canonical_json_bytes`, `render_import_guide`, `freeze_candidate`, `build_sha256sums`, `scan_release_for_secrets`, `validate_release_layout`, `finalize_candidate`, and `verify_final_bundle`.

- [ ] **Step 1: Write exact five-file, manifest and checksum tests**

```python
FINAL_FILES = (
    "WorldFlipper-离线整合版.apk",
    "WorldFlipper-数据-1.4.196.zip",
    "导入说明.txt",
    "build-manifest.json",
    "SHA256SUMS.txt",
)

@dataclass(frozen=True, slots=True)
class SecretFinding:
    relative_path: str
    container_member: str | None
    rule_id: str
    summary: str

def test_finalize_creates_exactly_five_files_and_four_checksum_lines(self):
    final = module.finalize_candidate(self.candidate, self.receipt, self.final_dir)
    self.assertEqual(tuple(sorted(path.name for path in final.iterdir())), tuple(sorted(FINAL_FILES)))
    lines = (final / "SHA256SUMS.txt").read_text("utf-8").splitlines()
    self.assertEqual(len(lines), 4)
    self.assertTrue(all(" *" in line for line in lines))
    self.assertFalse(any("SHA256SUMS.txt" in line for line in lines))
```

Add tests that manifest lists all `138291` data entries, distinguishes the three resource-version fields, omits absolute paths/private-key paths/passwords/self-hash, records dirty-worktree state, content/player/APK/device gates, and has stable UTF-8 LF JSON ordering.

- [ ] **Step 2: Write secret-scanning and atomic-promotion failure tests**

```python
def test_secret_scan_finds_password_in_utf8_utf16_and_nested_archives_without_echoing_it(self):
    secret = "fixture-Pass-2468"
    self.make_nested_archive(self.candidate, secret)
    findings = module.scan_release_for_secrets(self.candidate, secret_values=(secret,))
    self.assertGreaterEqual(len(findings), 2)
    self.assertTrue(all(secret not in finding.summary for finding in findings))

def test_existing_final_and_cross_volume_are_never_overwritten(self):
    self.final_dir.mkdir(parents=True)
    sentinel = self.final_dir / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with self.assertRaises(module.BundleError):
        module.finalize_candidate(self.candidate, self.receipt, self.final_dir)
    self.assertEqual(sentinel.read_text("utf-8"), "keep")
```

Add tests for `.jks/.keystore/.p12/.pfx/.pem/.key/keystore-pass.txt`, PEM/private-key markers, unreadable/reparse members, actual password bytes in UTF-8/UTF-16LE, APK/ZIP nested member names, `secret_observer` non-match, candidate hash drift after device QA, and failure summary redaction.

- [ ] **Step 3: Run tests and confirm the module/template are absent**

Run: `python -X utf8 -m unittest mod-tools/tests/test_offline_bundle.py -v`

Expected: FAIL with missing `wf_offline_bundle`.

- [ ] **Step 4: Implement two-phase candidate freeze and final manifest ordering**

`freeze_candidate` copies the immutable APK/data ZIP/guide into a same-volume candidate directory with `mode="x"`, hashes them, writes internal evidence outside the future five-file root, and returns `CandidateIdentity`. It does not yet write final manifest/SHA because device status is not known.

After the receipt is validated against `build_id/apk_sha256/data_zip_sha256`, `finalize_candidate` creates a new sibling temp directory, writes/copies in this order:

```text
1. WorldFlipper-离线整合版.apk
2. WorldFlipper-数据-1.4.196.zip
3. 导入说明.txt
4. build-manifest.json (includes device receipt status, not its local path)
5. SHA256SUMS.txt (hashes the preceding four files)
```

`build-manifest.json` records the source APK basename/size/hash, patch before/after hashes, signer certificate fingerprint, source/output/snapshot versions, three-root counts/bytes/mapping, all data entries, Player 1000 ID diff, every static/device gate, git commit and dirty flag. It records no absolute input, tool, key or receipt path.

- [ ] **Step 5: Implement the fixed Chinese import guide**

The template must render these exact operational points:

```text
- 可先按 SHA256SUMS.txt 校验四个文件。
- 备份共享存储根目录下的 WorldFlipper/save_haxe；新用户可跳过。
- 安装 WorldFlipper-离线整合版.apk；若签名冲突，确认已备份后再卸载旧 APK。
- 授予“所有文件访问权限”。
- 把 WorldFlipper-数据-1.4.196.zip 直接解压到 /storage/emulated/0/。
- 最终路径必须是 /storage/emulated/0/WorldFlipper/dummy/download/production/，不能放在 Download 下，不能多套一层 WorldFlipper。
- 开启飞行模式后首次启动；游戏后在菜单点击“保存”，退出本身不会替代保存。
- 干净首次启动会有 129999/139999/149999；已有 save_haxe 继续以原存档为准，ZIP 不覆盖个人进度。
```

- [ ] **Step 6: Implement fail-closed secret scanning and atomic rename**

```python
def finalize_candidate(candidate_dir: Path, receipt_path: Path, final_dir: Path) -> Path:
    if final_dir.exists():
        raise BundleError(f"final already exists: {final_dir.name}")
    _require_same_volume(candidate_dir, final_dir.parent)
    identity = _rehash_frozen_candidate(candidate_dir)
    receipt = validate_acceptance_receipt(receipt_path, identity)
    temp = final_dir.parent / f".{final_dir.name}.finalizing-{uuid.uuid4().hex}"
    temp.mkdir(mode=0o700)
    try:
        _write_five_files(temp, candidate_dir, receipt)
        _require_no_findings(scan_release_for_secrets(temp, secret_values=_configured_secret_values()))
        verify_final_bundle(temp)
        os.replace(temp, final_dir)
    except BaseException:
        _remove_owned_temp_tree(temp)
        raise
    return final_dir
```

The scanner reports only relative container/member path and rule ID. It never echoes matching bytes or generic “secret” text.

- [ ] **Step 7: Run bundle tests twice**

Run: `python -X utf8 -m unittest mod-tools/tests/test_offline_bundle.py -v`

Expected: PASS; a second finalize against the same final path fails without changing the first directory.

- [ ] **Step 8: Commit bundle finalization and guide**

```powershell
git add mod-tools/wf_offline_bundle.py mod-tools/templates/offline-import-guide.zh-CN.txt mod-tools/tests/test_offline_bundle.py
git commit -m "feat(mod-tools): finalize five-file offline bundle"
```

---

### Task 13: Bind a real airplane-mode device acceptance receipt to the candidate

**Files:**
- Create: `mod-tools/wf_offline_device.py`
- Create: `mod-tools/tests/test_offline_device.py`

**Interfaces:**
- Consumes: immutable `CandidateIdentity`, explicit ADB serial and optional MuMu instance.
- Produces: `DeviceTarget`, `DeviceProbeReport`, `DeviceAcceptanceReceipt`, `probe_device`, `prepare_device`, `record_manual_acceptance`, and `validate_acceptance_receipt`.

- [ ] **Step 1: Write fake-ADB tests for unique targeting and offline state**

```python
def test_probe_requires_explicit_online_serial_and_airplane_mode(self):
    target = module.DeviceTarget(self.adb, "127.0.0.1:16384")
    report = module.probe_device(target, runner=self.runner(
        devices=[("127.0.0.1:16384", "device")], airplane_mode="1", wifi="disabled",
        mobile="disabled", default_route="", active_network="null",
    ))
    self.assertTrue(report.airplane_mode)
    self.assertTrue(report.no_active_network)

def test_prepare_rejects_destructive_action_without_serial_bound_confirmation(self):
    with self.assertRaisesRegex(module.DeviceError, "confirmation"):
        module.prepare_device(self.target, self.candidate_dir, self.identity, confirm="WRONG", runner=self.runner())
```

Add tests for multiple/no devices, unauthorized/offline target, package mismatch, pre-existing `WorldFlipper/save_haxe` or dummy data refusal, receipt hash/build-id drift, missing manual check, network/default route present, companion ports observed as dependency, logcat fatal/crash detection, and no implicit `pm clear/uninstall/rm` in probe.

- [ ] **Step 2: Run tests and confirm the module is absent**

Run: `python -X utf8 -m unittest mod-tools/tests/test_offline_device.py -v`

Expected: FAIL with missing `wf_offline_device`.

- [ ] **Step 3: Implement a read-only probe and explicit destructive preparation**

```python
@dataclass(frozen=True, slots=True)
class DeviceTarget:
    adb: Path
    serial: str
    package: str = "com.leiting.wf"
    mumu_manager: Path | None = None
    instance: str | None = None

@dataclass(frozen=True, slots=True)
class DeviceProbeReport:
    serial_digest: str
    package_name: str
    airplane_mode: bool
    wifi_disabled: bool
    mobile_disabled: bool
    no_default_route: bool
    no_active_network: bool
    companion_ports_unused: bool
    save_haxe_present_before: bool
    dummy_data_present_before: bool
    fatal_log_lines: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class DeviceAcceptanceReceipt:
    schema_version: int
    build_id: str
    apk_sha256: str
    data_zip_sha256: str
    serial_digest: str
    probe: DeviceProbeReport
    checks: Mapping[str, bool]
    accepted_at_utc: str

PREPARE_CONFIRM_PREFIX = "RESET_AND_REINSTALL_COM_LEITING_WF_ON_"

def prepare_device(target: DeviceTarget, candidate_dir: Path, identity: CandidateIdentity,
                   *, confirm: str, runner: AdbRunner) -> DeviceProbeReport:
    expected = PREPARE_CONFIRM_PREFIX + target.serial
    if confirm != expected:
        raise DeviceError(f"confirmation must be {expected}")
    _require_exact_device(target, runner)
    apk = candidate_dir / "WorldFlipper-离线整合版.apk"
    if sha256_file(apk) != identity.apk_sha256:
        raise DeviceError("candidate APK hash drift before install")
    before = probe_device(target, runner=runner)
    if before.save_haxe_present_before or before.dummy_data_present_before:
        raise DeviceError("clean QA requires a dedicated empty instance or a manual backup of existing WorldFlipper shared data")
    if _package_is_installed(target, runner):
        runner.adb(target.serial, "shell", "pm", "clear", target.package)
        runner.adb(target.serial, "uninstall", target.package)
    runner.adb(target.serial, "install", str(apk))
    return probe_device(target, runner=runner)
```

Keep shared-data backup/removal and data-ZIP extraction as separately confirmed operator/manual steps; never delete or rename the broad shared `WorldFlipper` root automatically. `probe_device` reads `WorldFlipper/save_haxe` and `WorldFlipper/dummy` presence, airplane mode, Wi-Fi/mobile state, routes, active network, package activity and logcat only. If either shared-data path already exists, stop and require a dedicated clean MuMu instance or a user-performed backup before rerunning prepare.

- [ ] **Step 4: Implement the complete manual acceptance schema**

```python
REQUIRED_MANUAL_CHECKS = (
    "home_party_character_list_open",
    "original_character_1_and_129999_139999_149999_owned",
    "all_three_characters_enter_battle_and_use_skill",
    "seris_dual_form_skill_powerflip_results_stable",
    "gerald_scale_list_party_battle_correct",
    "rush_700099_round_reward_token_confirmed",
    "all_15_weapons_visible_one_obtained_and_equipped",
    "weapon_effect_whitelist_and_non_whitelist_confirmed",
    "save_button_force_stop_restart_restores_progress",
    "airplane_mode_held_no_companion_service",
)

def record_manual_acceptance(identity: CandidateIdentity, probe: DeviceProbeReport,
                             checks: Mapping[str, bool], output: Path) -> DeviceAcceptanceReceipt:
    if tuple(checks) != REQUIRED_MANUAL_CHECKS or not all(checks.values()):
        raise DeviceError("all manual acceptance checks must be present and true")
    if not probe.airplane_mode or not probe.no_active_network:
        raise DeviceError("device is not proven offline")
    return _write_receipt_bound_to_identity(identity, probe, checks, output)
```

The receipt stores a salted serial digest rather than a personal device label, includes candidate hashes/build ID/probe facts/check booleans/UTC time, and sits outside the final five files.

- [ ] **Step 5: Run device tests**

Run: `python -X utf8 -m unittest mod-tools/tests/test_offline_device.py -v`

Expected: PASS; fake ADB proves no destructive command occurs without the exact serial-bound token.

- [ ] **Step 6: Commit device acceptance**

```powershell
git add mod-tools/wf_offline_device.py mod-tools/tests/test_offline_device.py
git commit -m "feat(mod-tools): gate offline device acceptance"
```

---

### Task 14: Orchestrate the whole workflow behind one operator-facing CLI and batch entry

**Files:**
- Create: `mod-tools/wf_offline_release.py`
- Create: `mod-tools/build-offline-android.bat`
- Create: `mod-tools/docs/离线Android整合包.md`
- Create: `mod-tools/tests/test_offline_release.py`

**Interfaces:**
- Consumes: every interface from Tasks 3–13.
- Produces CLI subcommands `preflight`, `build-candidate`, `device-probe`, `prepare-device`, `device-accept`, `finalize`, `verify`, `init-signer`; every command emits one final stable JSON line and a nonzero exit code on failure.

- [ ] **Step 1: Write small-fixture end-to-end and phase-resume tests**

```python
def test_build_candidate_runs_stages_in_fixed_order_and_stops_before_final(self):
    result = module.build_candidate(self.config, services=self.fake_services)
    self.assertEqual(self.fake_services.calls, [
        "preflight", "scan-store", "legacy-tail-gates", "copy-snapshot", "player-overlay",
        "content-data-gates", "build-apk", "content-client-gate", "build-zip",
        "verify-zip", "render-guide", "freeze-candidate", "secret-scan",
    ])
    self.assertEqual(result.status, "awaiting_device_acceptance")
    self.assertFalse(self.final_dir.exists())

def test_source_tree_hashes_are_rechecked_after_build(self):
    self.fake_services.mutate_source_after_zip = True
    with self.assertRaisesRegex(module.ReleaseError, "source store drift"):
        module.build_candidate(self.config, services=self.fake_services)
```

Add tests for signer-not-ready preflight, disk space, source APK hash, existing candidate/final, stage report schema, sanitized error receipt, Ctrl-C cleanup, no live publish calls, no user-WIP paths staged, device receipt binding, final verify, and exact five-file output.

- [ ] **Step 2: Run tests and confirm the orchestrator is absent**

Run: `python -X utf8 -m unittest mod-tools/tests/test_offline_release.py -v`

Expected: FAIL with missing `wf_offline_release`.

- [ ] **Step 3: Implement typed release configuration and commands**

```python
@dataclass(frozen=True, slots=True)
class OfflineReleaseConfig:
    source_apk: Path
    snapshot_version: str
    output_root: Path
    profile_id: str
    legacy_zip: Path
    tail_zip: Path
    toolchain: Toolchain
    signing: SigningConfig

@dataclass(frozen=True, slots=True)
class ReleaseResult:
    status: Literal["awaiting_device_acceptance", "finalized", "verified"]
    build_id: str
    candidate_dir: Path | None
    final_dir: Path | None
    identity: CandidateIdentity

COMMANDS = (
    "preflight", "build-candidate", "device-probe", "prepare-device", "device-accept",
    "finalize", "verify", "init-signer",
)
```

`build-candidate` creates `out/wf-offline-android/1.4.196/.staging-<uuid>` with an ownership marker, then calls the exact sequence asserted by the test. It hashes source APK/store before and after; errors write a redacted summary under `out/wf-offline-android/1.4.196/failures/`, never a success manifest. Cleanup is limited to a path with the matching ownership marker inside the resolved output root.

- [ ] **Step 4: Add the one-command Windows wrapper with CRLF**

```bat
@echo off
setlocal
set "WF_OFFLINE_SOURCE_APK=%~1"
if not defined WF_OFFLINE_SOURCE_APK set "WF_OFFLINE_SOURCE_APK=%USERPROFILE%\Downloads\base.apk.1"
python -X utf8 "%~dp0wf_offline_release.py" build-candidate --source-apk "%WF_OFFLINE_SOURCE_APK%" --snapshot-version 1.4.196
exit /b %ERRORLEVEL%
```

The wrapper does not print, prompt for, set or save `WF_OFFLINE_KEYSTORE_PASSWORD`. Normalize only this `.bat` to CRLF after patching.

- [ ] **Step 5: Write operator documentation with exact lifecycle commands**

Document:

```powershell
python -X utf8 mod-tools/wf_offline_release.py init-signer --confirm CREATE_WF_OFFLINE_RELEASE_SIGNER
$signingSecret = Read-Host "Offline signer password" -AsSecureString
$secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($signingSecret)
try { $env:WF_OFFLINE_KEYSTORE_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer) }
python -X utf8 mod-tools/wf_offline_release.py preflight --source-apk "$env:USERPROFILE\Downloads\base.apk.1" --snapshot-version 1.4.196
mod-tools\build-offline-android.bat "$env:USERPROFILE\Downloads\base.apk.1"
$candidateId = Read-Host "Candidate ID printed by build-candidate"
$adbSerial = Read-Host "Exact ADB serial selected from adb devices"
$prepareConfirm = "RESET_AND_REINSTALL_COM_LEITING_WF_ON_" + $adbSerial
python -X utf8 mod-tools/wf_offline_release.py device-probe --candidate $candidateId --serial $adbSerial
python -X utf8 mod-tools/wf_offline_release.py prepare-device --candidate $candidateId --serial $adbSerial --confirm $prepareConfirm
python -X utf8 mod-tools/wf_offline_release.py device-accept --candidate $candidateId --serial $adbSerial --receipt-out out/wf-offline-android/1.4.196/device-acceptance.json
python -X utf8 mod-tools/wf_offline_release.py finalize --candidate $candidateId --receipt out/wf-offline-android/1.4.196/device-acceptance.json
python -X utf8 mod-tools/wf_offline_release.py verify --bundle "out/wf-offline-android/1.4.196/WF离线整合版"
Remove-Item Env:\WF_OFFLINE_KEYSTORE_PASSWORD -ErrorAction SilentlyContinue
Remove-Variable signingSecret -ErrorAction SilentlyContinue
```

Explain that `$candidateId` is copied from the final JSON line emitted by `build-candidate` and `$adbSerial` is selected from `adb devices`; neither value is hard-coded. Include recovery: old final is never overwritten, stop using failed candidate, preserve source/live/WIP, and never delete historical keys without separate authorization.

- [ ] **Step 6: Run orchestrator and all focused offline suites**

Run:

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_offline_*.py" -v
python -X utf8 -m unittest mod-tools/tests/test_build_three_char_release_patch.py -v
```

Expected: PASS; fixture output is exact five-file layout only after a valid fake receipt.

- [ ] **Step 7: Commit orchestration and docs**

```powershell
git add mod-tools/wf_offline_release.py mod-tools/build-offline-android.bat mod-tools/docs/离线Android整合包.md mod-tools/tests/test_offline_release.py
git commit -m "feat(mod-tools): orchestrate offline Android release"
```

---

### Task 15: Build the real 1.4.196 candidate, complete airplane-mode QA, and finalize

**Files generated outside Git:**
- `%USERPROFILE%\.wf-offline-release\wf-offline-release.jks`
- `%USERPROFILE%\.wf-offline-release\signer-public.json`
- `out/wf-offline-android/1.4.196/.candidate-<build-id>/...`
- `out/wf-offline-android/1.4.196/device-acceptance.json`
- `out/wf-offline-android/1.4.196/WF离线整合版/` with exactly five files

**Interfaces:**
- Consumes: the finished CLI and real base/store/toolchain/MuMu inputs.
- Produces: the user-requested deliverable and its independently verifiable evidence.

- [ ] **Step 1: Run the full repository gate before touching real output**

Run:

```powershell
npm run verify
npm run test:launcher
npm run test:hygiene
npm run check:hygiene
```

Expected: all commands exit `0`; Python offline tests are included by `npm run test:python`. If any unrelated pre-existing WIP test fails, record the exact failing test and determine ownership before changing any file.

- [ ] **Step 2: Bootstrap the dedicated signer only if it is still absent**

Run in a visible local terminal, never paste the password into chat:

```powershell
python -X utf8 mod-tools/wf_offline_release.py init-signer --confirm CREATE_WF_OFFLINE_RELEASE_SIGNER
$signingSecret = Read-Host "Offline signer password" -AsSecureString
$secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($signingSecret)
try { $env:WF_OFFLINE_KEYSTORE_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer) }
```

Expected: if absent, keytool prompts interactively and creates only the two release-home files; if already present, the command refuses to rotate/overwrite. Verify `git status --short` and `Get-ChildItem out -Recurse -File` contain no keystore/password file.

- [ ] **Step 3: Run real preflight and build candidate without blocking the conversation**

Run:

```powershell
python -X utf8 mod-tools/wf_offline_release.py preflight --source-apk "$env:USERPROFILE\Downloads\base.apk.1" --snapshot-version 1.4.196
mod-tools\build-offline-android.bat "$env:USERPROFILE\Downloads\base.apk.1"
```

Expected preflight JSON includes the exact base hash, store counts `113822/23458/1009`, legacy `137820`, added `469`, missing `0`, tail `12`, signer fingerprint match and enough free space. The long build is launched/polled in intervals no longer than 60 seconds. Completion status is `awaiting_device_acceptance`, not `complete`; no final directory exists yet.

Capture the emitted identifier in the same PowerShell session:

```powershell
$candidateId = Read-Host "Candidate ID from the build-candidate JSON result"
```

- [ ] **Step 4: Independently verify the immutable candidate before device mutation**

Run:

```powershell
python -X utf8 mod-tools/wf_offline_release.py verify --candidate $candidateId
```

Expected: APK signature/alignment/offline/SWF/content gates pass; data ZIP has `138291` members, correct root counts and hashes; secret findings `0`; source APK/store post-hashes equal pre-hashes. Substitute the actual candidate ID printed by Step 3.

- [ ] **Step 5: Probe the exact MuMu/ADB target, then request destructive confirmation**

Run:

```powershell
& "D:\WF\MuMuPlayer\nx_main\adb.exe" devices -l
$adbSerial = Read-Host "Exact online ADB serial to test"
python -X utf8 mod-tools/wf_offline_release.py device-probe --candidate $candidateId --serial $adbSerial
```

Expected: exactly the chosen serial is online and the clean-QA probe reports no pre-existing `save_haxe` or dummy data. Before `prepare-device`, show the user the exact target serial and required token produced by `"RESET_AND_REINSTALL_COM_LEITING_WF_ON_$adbSerial"` because `pm clear/uninstall/install` changes emulator state. Never clear a different serial or delete the broad shared `WorldFlipper` directory; use a dedicated empty instance or manually back up existing shared data first.

- [ ] **Step 6: Install/extract and complete every flight-mode check**

After the user explicitly repeats the serial-bound confirmation token, run only against that target:

```powershell
$prepareConfirm = "RESET_AND_REINSTALL_COM_LEITING_WF_ON_" + $adbSerial
python -X utf8 mod-tools/wf_offline_release.py prepare-device --candidate $candidateId --serial $adbSerial --confirm $prepareConfirm
```

Then extract `WorldFlipper-数据-1.4.196.zip` so the final shared-storage path is `/storage/emulated/0/WorldFlipper/dummy/download/production/`, enable airplane mode, disable Wi-Fi/mobile and cold start. Complete all ten `REQUIRED_MANUAL_CHECKS` from Task 13, including:

```text
original character 1 remains owned; 129999/139999/149999 are owned and each enters battle
129999 dual form, skill, enhanced projectile and results stable
139999 normal display and skill assets load correctly
149999 proportions correct in list/party/battle
700099 at least one round, 15-round structure/reward/token 2370099
all 15 weapons displayed; acquire/equip one; whitelist-only special effect
menu Save → force-stop → restart restores characters/rewards/weapons/progress
airplane mode remains on; no server/localhost/LAN/companion port dependency
```

Expected: no crash/fatal log and every check is true. Any failure leaves the candidate unfinalized and writes only a redacted failed receipt outside final.

- [ ] **Step 7: Record the bound receipt and atomically finalize**

Run:

```powershell
python -X utf8 mod-tools/wf_offline_release.py device-accept --candidate $candidateId --serial $adbSerial --receipt-out out/wf-offline-android/1.4.196/device-acceptance.json
python -X utf8 mod-tools/wf_offline_release.py finalize --candidate $candidateId --receipt out/wf-offline-android/1.4.196/device-acceptance.json
```

Expected: receipt hashes exactly match the frozen candidate; finalizer rehashes again, creates manifest then four-line SHA file, secret-scans, verifies, and atomically creates `out/wf-offline-android/1.4.196/WF离线整合版/` without overwriting anything.

- [ ] **Step 8: Run final independent verification and record evidence**

Run:

```powershell
python -X utf8 mod-tools/wf_offline_release.py verify --bundle "out/wf-offline-android/1.4.196/WF离线整合版"
npm run verify
npm run test:launcher
npm run test:hygiene
npm run check:hygiene
git status --short
Remove-Item Env:\WF_OFFLINE_KEYSTORE_PASSWORD -ErrorAction SilentlyContinue
Remove-Variable signingSecret -ErrorAction SilentlyContinue
```

Expected: final verify status `deliverable=true`, exact five files, four matching SHA lines, all static/device gates true, secret findings `0`; repository suites exit `0`; `git status` contains no staged output and the known user-WIP paths have exactly their pre-execution state rather than new edits from this implementation.

- [ ] **Step 9: Commit only any verification-doc correction made during the real run**

If the real run proves the tracked operator document needs a factual command/output correction, stage only that exact tracked document and commit:

```powershell
git add mod-tools/docs/离线Android整合包.md
git commit -m "docs(mod-tools): record offline release verification"
```

If no tracked documentation changed, do not create an empty commit. Never commit APK, ZIP, receipt, key, candidate, final output, `work/`, live store or user WIP.

---

## Final Verification Matrix

| Gate | Command/evidence | Required result |
|---|---|---|
| Three-root regression | `test_build_three_char_release_patch.py` | common/medium/android preserved; historical ZIP untouched |
| Store snapshot | `wf_offline_store.py preflight --no-copy` | 113822/23458/1009, total 138289, old 137820, +469, missing 0, tail 12 |
| Player overlay | `test_offline_player.py` + manifest report | only 129999/139999/149999 added at level 1; one common member changed |
| Character gates | `test_offline_content.py` + candidate evidence | three identities correct, 37/37, three roots and every claimed SHA bound; invalid Seris workspace rejected |
| Rogue content | `validate_rogue_data` | 700099, 15 rounds, 2370099, 8000101..8000115, shop/reward/icon mapping |
| APK baseline | `test_offline_apk_baseline.py` + final inspect | exact input hashes; package/manifest/DEX/native/offline/save invariants unchanged |
| SWF patches | patch reports and reopen verification | order fixed; abyss 1 site, Seris 9 sites, render 3 sites, version 1.4.196 |
| APK signing | `zipalign -c` + `apksigner verify --print-certs` | aligned, v1/v2/v3 true, dedicated signer fingerprint match |
| Data ZIP | `verify_data_zip` | Zip64, 138291 members, one WorldFlipper root, every size/SHA matches |
| Security | `scan_release_for_secrets` | 0 findings, including nested APK/ZIP and actual password byte variants |
| Device | bound receipt | all 10 checks true in airplane mode, no companion service |
| Final layout | `verify --bundle` | exact five files and four valid SHA256SUMS lines |
| Repository | `npm run verify/test:launcher/test:hygiene/check:hygiene` | all exit 0 |
