# World Flipper 剧本导出器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个纯只读 CLI，从当前 CN CDN store 导出全部剧情为 Markdown 与 JSONL，并用 1708 个官方 scenario 做全量解码门禁。

**Architecture:** `wf_story_export.py` 分为五层：AS3 核实后的 opcode schema、嵌套 orderedmap 解码、角色/quest 索引、Markdown/JSONL 渲染、CLI/validate。二进制寻址和 orderedmap 构建/读取复用 `wf_mod_tool`，任意深度 quest 表只读解析复用 `wf_quest_lib.parse_node`；所有测试使用临时目录与合成字节，不访问真实 store。

**Tech Stack:** Python 3 stdlib、仓内 `wf_mod_tool.py`、仓内 `wf_quest_lib.py`、`unittest`。

## Global Constraints

- 工作目录固定为 `D:\WF\startpoint-cn`，Python 命令使用 `python`。
- 不修改 `wf_mod_tool.py`、`wf_quest_lib.py`、store、`sync_pending.json` 或任何发布链文件。
- 真实输出只允许写到显式 `--out` 或默认忽略目录 `mod-tools/work/story_export/`。
- 数据清单以 `mod-tools/WF_PATHLIST_recovered.txt` 的 1708 个 scenario 为准；关联表额外引用的文件不得擅自扩入 `--all`。
- 不新增第三方依赖；测试命令使用 `unittest`。
- 保留当前脏工作区与用户 WIP；不执行 `git clean`、还原或批量暂存。
- 当前任务不提交 commit；若用户后续要求发布，再只暂存本任务交付文件。

---

### Task 1: 嵌套 scenario 解码与 opcode schema

**Files:**
- Create: `mod-tools/wf_story_export.py`
- Create: `mod-tools/tests/test_story_export.py`

**Interfaces:**
- Produces: `OpcodeSpec`, `ScenarioCommand`, `OPCODES`, `normalize_story_text(value: str) -> str`, `decode_scenario_bytes(raw: bytes, logical_path: str) -> tuple[str, list[ScenarioCommand]]`。
- Consumes: `wf_mod_tool.read_orderedmap_raw_rows_from_bytes`；外层/内层索引与每条 zlib 行另做 `eof/unused_data/unconsumed_tail` 严格校验，避免宽松 dict reader 覆盖重复键或忽略尾随字节。

- [ ] **Step 1: 写合成嵌套 orderedmap fixture 和首批失败测试**

  用 `build_orderedmap(OrderedMap(...))` 构造 zlib 行的内层，用 `build_orderedmap_raw_rows(OrderedMap(...))` 构造外层；覆盖外层单键、数字行号、引号 CSV、真实换行、字面 `\\n`、`(None)`、未知 kind。测试先因 `wf_story_export` 或公开接口不存在而失败。

- [ ] **Step 2: 运行 RED**

  Run: `python -m unittest discover -s mod-tools/tests -p "test_story_export.py" -v`
  Expected: FAIL，失败原因是导出模块/接口尚未实现，而非 fixture 构造错误。

- [ ] **Step 3: 实现最小解码层**

  `decode_scenario_bytes` 校验外层恰好一个键、外层 row 覆盖完整 blob、内层键为连续的 `1..N`；每行用 `csv.reader(io.StringIO(row_text))` 解析。`OPCODES` 使用 `ScenarioCommandKind.as` 与 `ScenarioCommandValues.as` 核实的 kind 0..24、字段名、列号和类型；未知 kind 保留非空列为 `col_<n>`，`raw` 永远保留原始字符串列。

- [ ] **Step 4: 运行 GREEN 并做 mutation check**

  Run: `python -m unittest discover -s mod-tools/tests -p "test_story_export.py" -v`
  Expected: 解码相关测试 PASS；将 fixture 外层误改为 zlib 行或删除 `\\n` 归一逻辑时至少一项测试会失败。

- [ ] **Step 5: 检查 scoped diff**

  Run: `git status --short -- mod-tools/wf_story_export.py mod-tools/tests/test_story_export.py`，并直接审阅未跟踪文件内容。
  Expected: 仅新增解码层和对应离线测试，无 store 路径写入调用；不依赖普通 `git diff` 显示未跟踪文件。

### Task 2: 说话人解析与双格式渲染

**Files:**
- Modify: `mod-tools/wf_story_export.py`
- Modify: `mod-tools/tests/test_story_export.py`

**Interfaces:**
- Consumes: `ScenarioCommand`, `StoryEntry`, `dict[str, Speaker]`。
- Produces: `load_speakers(store: Path) -> dict[str, Speaker]`, `render_markdown(entry, commands, speakers) -> str`, `render_jsonl(commands, speakers) -> str`。

- [ ] **Step 1: 写失败测试**

  覆盖 `_known` 直接取权威显示名、空代号渲染为旁白、语音 🔊 条件、多行 Markdown 硬换行和缩进、CharacterIn/CharacterOut/CharacterFace/MovieSequence/BGM 注记、unknown HTML 注释、JSONL 每条命令都有 `line/kind/op/args/raw` 且对白有四个扩展字段。

- [ ] **Step 2: 运行 RED**

  Run: `python -m unittest discover -s mod-tools/tests -p "test_story_export.py" -v`
  Expected: FAIL，缺失渲染接口或输出与手写字面量不符。

- [ ] **Step 3: 实现渲染层**

  说话人只读 `master/story/story_character.orderedmap` 的 col0；不折叠 `_known`。Markdown 对任务书要求的对白、BGM、movie section、角色入退场、表情和静态背景给出简短斜体注记；其他已知命令完整保留在 JSONL，对未知命令输出 `<!-- kind=N cols={...} -->`。JSONL 使用 UTF-8 中文、每指令一行、typed args 与完整 raw 并存。

- [ ] **Step 4: 运行 GREEN**

  Run: `python -m unittest discover -s mod-tools/tests -p "test_story_export.py" -v`
  Expected: 渲染测试 PASS，输出末尾换行稳定。

### Task 3: 剧情目录、quest 关联与角色家族选择

**Files:**
- Modify: `mod-tools/wf_story_export.py`
- Modify: `mod-tools/tests/test_story_export.py`

**Interfaces:**
- Produces: `CharacterInfo`, `StoryEntry`, `StoryCatalog(store: Path, pathlist: Path)`, `StoryCatalog.select_quest(query)`, `StoryCatalog.select_character(query)`, `StoryCatalog.select_category(category)`。
- Consumes: `wf_mod_tool.table_path/read_orderedmap_file/read_csv_lines` 与 `wf_quest_lib.parse_node`。

- [ ] **Step 1: 写临时 store 的失败测试**

  用 `table_path` 将合成 character、character_text、story_character、character_quest 与 scenario 写入临时 store。覆盖：quest scenario 路径是权威关联；角色 col27 `identity_character_id` 将 base/周年/圣诞变体归为一族；同名但 identity 不同的 NPC 不误收；episode 用 col50；同 basename 的 quest 查询报歧义而不猜。

- [ ] **Step 2: 运行 RED**

  Run: `python -m unittest discover -s mod-tools/tests -p "test_story_export.py" -v`
  Expected: FAIL，缺少目录/选择器实现。

- [ ] **Step 3: 实现索引层**

  清单仅收 `master/story/<category>/.../scenario.orderedmap`。quest source 固定为：character col126/title3/character49/episode50；main col124/title1；story event col126 与 world story event col125/title2；advent col130/title2；triggered tutorial col26。关联值转为 `master/<value>.orderedmap` 后与 pathlist 精确匹配；系统标题缺失时回退目录名。角色查询支持 id/code/CN 名，命中后按 col27 identity 家族扩展并只保留有个人剧情的成员。

- [ ] **Step 4: 运行 GREEN**

  Run: `python -m unittest discover -s mod-tools/tests -p "test_story_export.py" -v`
  Expected: 索引/选择测试 PASS。

### Task 4: CLI、输出边界与 validate 稳定摘要

**Files:**
- Modify: `mod-tools/wf_story_export.py`
- Modify: `mod-tools/tests/test_story_export.py`

**Interfaces:**
- Produces: `ValidationReport`, `validate_catalog(catalog, speakers)`, `export_entries(...)`, `main(argv: list[str] | None = None) -> int`。
- Consumes: Tasks 1-3 的解码、索引与渲染接口。

- [ ] **Step 1: 写 CLI 失败测试**

  覆盖 `--list [category]` 不落盘、`--quest`/`--character`/`--category`/`--all` 的互斥、默认 both、显式格式、输出路径 `<category>/<relative>/scenario.md|jsonl`、缺 store 清晰退出、`--validate` 不创建 out、末行 `sort_keys=True` 的稳定 JSON 摘要、decode failure/unknown speaker/unknown opcode/title missing 的统计。

- [ ] **Step 2: 运行 RED**

  Run: `python -m unittest discover -s mod-tools/tests -p "test_story_export.py" -v`
  Expected: FAIL，缺失 CLI 或文件边界行为。

- [ ] **Step 3: 实现 CLI 与 validate**

  `argparse` 用互斥 selector；`--store` 不存在立即报错且不找其他 profile。只有导出 selector 会在完成全部解码/渲染和路径预检后，以同目录临时文件 + `os.replace` 写目标；拒绝 store 重叠、父目录穿越及链接/reparse 叶子，list/validate 全程只读。validate 逐文件独立捕获异常并输出失败清单、unknown 分布、未解析说话人、标题缺失，并对默认 pathlist 强制 1708 及分类计数，最后输出单行 JSON 摘要；解码失败或清单契约不符时返回非零，unknown/标题回退不丢数据。

- [ ] **Step 4: 运行 GREEN 与完整 Python 回归**

  Run: `python -m unittest discover -s mod-tools/tests -p "test_story_export.py" -v`
  Expected: 本文件测试 PASS。

  Run: `npm run test:python`
  Expected: 全部 Python 测试 PASS。

### Task 5: 使用说明与真实数据验收

**Files:**
- Create: `mod-tools/docs/剧本导出器使用说明.md`
- Modify only if evidence requires: `mod-tools/wf_story_export.py`
- Modify only if a regression is found first: `mod-tools/tests/test_story_export.py`

**Interfaces:**
- Documents: CLI 命令、目录布局、完整 opcode 表、AS3 证据、任务书经验表与反编译差异、限制。

- [ ] **Step 1: 写使用说明并自审**

  opcode 表必须覆盖 0..24，指出当前 1708 文件实际出现 0..15、18..20、22..24；明确 movie/timeline、语音抽取、GUI 均不在本期。检查文档无占位符、无把 kind 4/7/11/22 的旧经验语义继续写错。

- [ ] **Step 2: 跑真实金样导出**

  Run: `python mod-tools/wf_story_export.py --quest white_tiger_001 --out mod-tools/work/story_export`

  Run: `python mod-tools/wf_story_export.py --quest white_tiger_002 --out mod-tools/work/story_export`

  Run: `python mod-tools/wf_story_export.py --quest white_tiger_003 --out mod-tools/work/story_export`

  Run: `python mod-tools/wf_story_export.py --quest main_chapter_01_01 --out mod-tools/work/story_export`

  Expected: 白三话对白 44/44/56；第一话首段 BGM→scene0→阿尔克入场→“久等了。”；主线 51 指令且首句“这里就是外面的世界？”。

- [ ] **Step 3: 跑角色家族与全量门禁**

  Run: `python mod-tools/wf_story_export.py --character 白 --out mod-tools/work/story_export`
  Expected: 只导出 white_tiger、white_tiger_2anv、white_tiger_xm20 各三话，共 9 话。

  Run: `python mod-tools/wf_story_export.py --validate`
  Expected: pathlist scenario_total=1708、decoded=1708、decode_failures=0；unknown opcode 只统计不丢 raw。

- [ ] **Step 4: 跑仓库规定门禁并检查只读边界**

  Run: `npm run verify`

  Run: `npm run test:launcher`

  Run: `npm run test:hygiene`

  Run: `npm run check:hygiene`

  Run: `git status --short --branch`

  Expected: 门禁均成功；除本计划、三个交付文件和忽略的 `mod-tools/work/story_export/` 外，没有本任务造成的变化，store 文件时间/内容未被修改。
