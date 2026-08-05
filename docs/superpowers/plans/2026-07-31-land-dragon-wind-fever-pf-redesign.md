# Wind Land Dragon Fever/PF Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a workspace-only `land_dragon_wind_poc` 1.1.0 candidate with the approved Fever loop, five equally weighted 60×→80× random boss skills, and a game-asset-only 6/12/24-hit custom power flip.

**Architecture:** Extend the existing isolated builder and its real-AMF3 contract tests. Master-data rows are composed from verified CN donor semantics, active-skill and PF programs are emitted as player-side ActionDsl, and all reused game effects are copied into character-owned paths with their complete PNG/atlas/parts/timeline dependencies. The build remains rooted below `work/character_packs/land_dragon_wind_poc` and is handed to `wf_character_flow.py preflight`; no live-store, save, emulator, CDN, or publish write is permitted.

**Tech Stack:** Python 3.14, `wf_mod_tool`, `wf_gui` composer, `wf_dsl`, AMF3 raw-deflate containers, Pillow, `wf_character_flow.py`.

## Global Constraints

- Source of truth: `docs/superpowers/specs/2026-07-31-land-dragon-wind-fever-pf-redesign.md`.
- Work only below `work/character_packs/land_dragon_wind_poc/` plus this plan and the existing design spec.
- Do not modify `assets/`, live `production/upload`, `.cdn/`, the current save, or emulator-private resources.
- Do not call `wf_character_flow.py publish`.
- Do not add hand-drawn or generated pixel art; use only game-original Wind Land Dragon Pixel and game-original effect assets.
- The five Fever variants have weights `20,20,20,20,20`, hit counts `8,10,16,20,32`, and totals `60×→80×`.
- The custom PF has `6,12,24` explicit attacks and preserves the corresponding official Fighter PF total damage.
- Ability 3 uses one main-position restriction source; ability 6 has none.
- Ability 3 skill-cast refund and Fever extension both use a 10-second (`600` frame) cooldown.
- ConditionFeverPoint rows retain the verified CN sentinel fields that prevent C7101.
- Every behavior change follows RED → GREEN; production code is not edited before its failing test is observed.
- `pytest` is not installed in the current Python runtimes. Run the existing plain-assert tests with:

```powershell
python -c "import runpy; ns=runpy.run_path(r'work\character_packs\land_dragon_wind_poc\test_package.py'); tests=[(n,v) for n,v in ns.items() if n.startswith('test_') and callable(v)]; [v() for n,v in sorted(tests)]; print(f'{len(tests)} passed')"
```

- Git commit steps are intentionally omitted because the character workspace is untracked user WIP and no Git authorization was given. Each task ends with an explicit test/evidence checkpoint instead.

---

## File Map

- Modify: `work/character_packs/land_dragon_wind_poc/test_package.py`
  - Executable contract for master rows, skill probability branches, effect ownership, PF programs, lifecycle, hit counts, and no-live-write evidence.
- Modify: `work/character_packs/land_dragon_wind_poc/build_workspace.py`
  - Sole builder for master rows, character data, active-skill/PF ActionDsl, copied effect families, manifest, and evidence.
- Modify: `work/character_packs/land_dragon_wind_poc/character-dossier.md`
  - Reader-facing final kit, random variants, PF behavior, preflight result, and deferred device gates.
- Generate: `work/character_packs/land_dragon_wind_poc/package/**`
  - Version `1.1.0` candidate only.
- Generate: `work/character_packs/land_dragon_wind_poc/evidence/**`
  - Build report, hash/readback records, visual QA, live-write proof, and preflight evidence.
- Create: `work/character_packs/land_dragon_wind_poc/device-canary/revision-1.1.0-checklist.md`
  - Non-executing checklist for the later explicitly authorized emulator canary.

---

### Task 1: Lock the revised master-data contract

**Files:**
- Modify: `work/character_packs/land_dragon_wind_poc/test_package.py:118-275`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py:68-105`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py:649-932`

**Interfaces:**
- Consumes: existing `_flat()`, `_row_semantic()`, `gui.wf_describe.layout()`.
- Produces: `_generated_ability_row(..., precondition_kind, cooldown_frames)` and the final 8-row leader/6-group ability contract used by all later package builds.

- [ ] **Step 1: Replace the old master-row test with exact approved semantics**

Add a richer semantic helper that exposes trigger threshold, cooldown, and start/max strengths:

```python
def _row_contract(row: list[str], kind: str) -> dict[str, Any]:
    blocks = gui.wf_describe.layout(kind)["blocks"]
    mode = row[blocks["precondition1"] - 1]
    trigger_base = (
        blocks["instant_trigger"] if mode == "0" else blocks["during_trigger"]
    )
    content_base = (
        blocks["instant_content"] if mode == "0" else blocks["during_content"]
    )
    return {
        "mode": mode,
        "unisonable": row[1] if kind == "ability" else "",
        "precondition": row[blocks["precondition1"]],
        "trigger": row[trigger_base],
        "threshold": row[trigger_base + 4],
        "limit": row[trigger_base + 7] if mode == "0" else "",
        "cooldown": row[trigger_base + 8] if mode == "0" else "",
        "effect": row[content_base],
        "target": row[content_base + 1],
        "groups": row[content_base + 2],
        "start": row[content_base + 4],
        "maximum": row[content_base + 5],
    }
```

Replace `test_leader_and_six_abilities_match_the_approved_skill_damage_kit`
with assertions for:

```python
assert len(leader_rows) == 8
assert {
    (c["mode"], c["trigger"], c["effect"], c["target"], c["groups"], c["maximum"])
    for c in map(lambda r: _row_contract(r, "leader_ability"), leader_rows)
} == {
    ("0", "0", "32", "5", "Green", "150000"),
    ("0", "0", "34", "5", "Green", "200000"),
    ("0", "0", "50", "5", "", "150000"),
    ("0", "0", "56", "0", "", "30000"),
    ("0", "8", "211", "5", "Green", "50000"),
    ("1", "4", "2", "5", "Green", "150000"),
    ("1", "4", "3", "5", "Green", "30000"),
    ("0", "0", "722", "", "", ""),
}
```

Assert these ability details:

```python
ability = _flat("master/ability/ability.orderedmap")

assert [gui.wf_describe.describe_line(r, "ability") for r in ability[f"{CID}1"]] == [
    "自身 技能伤害 50%→100%",
    "技能发动≥1 → 自身 状态Fever点 50%→100%(15秒)×1次",
]

a2 = [_row_contract(r, "ability") for r in ability[f"{CID}2"]]
assert [(r["precondition"], r["trigger"], r["threshold"], r["effect"], r["maximum"]) for r in a2] == [
    ("186", "12", "2000000", "213", "50000"),
    ("186", "12", "4000000", "213", "100000"),
    ("0", "12", "6000000", "211", "20000"),
]

a3 = [_row_contract(r, "ability") for r in ability[f"{CID}3"]]
assert all(r["unisonable"] == "false" for r in a3)
assert all("202" not in row for row in ability[f"{CID}3"])
assert {(r["trigger"], r["effect"], r["maximum"], r["cooldown"]) for r in a3} == {
    ("8", "211", "50000", "0"),
    ("4", "2", "150000", ""),
    ("4", "3", "50000", ""),
    ("23", "211", "30000", "600"),
    ("23", "213", "250000", "600"),
}

a6 = ability[f"{CID}6"]
assert all(row[1] == "true" and "202" not in row for row in a6)
```

Also assert the PF override payload:

```python
leader_layout = gui.wf_describe.layout("leader_ability")["blocks"]
override = next(
    row for row in leader_rows
    if row[leader_layout["instant_content"]] == "722"
)
cbase = leader_layout["instant_content"]
assert override[cbase + 35 : cbase + 38] == [
    "land_dragon_wind_pf",
    "1,2,3",
    "override_string_wind_spgirl_4anv",
]
```

- [ ] **Step 2: Run the new master-row test and verify RED**

Run:

```powershell
python -c "import runpy; ns=runpy.run_path(r'work\character_packs\land_dragon_wind_poc\test_package.py'); ns['test_leader_and_six_abilities_match_the_approved_fever_pf_kit']()"
```

Expected: FAIL because the package still has the old six-row leader, old ability groups, no 722 PF override, and old values.

- [ ] **Step 3: Extend the row generator minimally**

Change the helper signature to:

```python
def _generated_ability_row(
    dst_key: str,
    *,
    mode: str,
    trigger_kind: str,
    effect_kind: str,
    value: float,
    value_max: float,
    target: str = "0",
    groups: str = "",
    effect_unit: str = "pct",
    threshold: float | None = None,
    threshold_unit: str = "count",
    duration_frames: int | None = None,
    number: int | None = None,
    initial_multiply: int | None = None,
    main_only: bool = False,
    trigger_limit: int | None = None,
    precondition_kind: str = "0",
    cooldown_frames: int | None = None,
) -> list[str]:
```

Pass `precondition_kind` into `gui.composer_generate`. For instant rows, write
the verified cooldown column:

```python
if cooldown_frames is not None:
    if mode != "instant":
        raise ValueError("cooldown_frames is only valid for instant rows")
    row[blocks["instant_trigger"] + 8] = str(int(cooldown_frames))
```

Retain the existing ConditionFeverPoint sentinel block and change its duration
for ability 1 from `60000000` to `90000000` frames-as-100000-units (15 seconds).

- [ ] **Step 4: Implement the six approved ability groups**

Use these exact specs:

```python
ability_specs = {
    f"{NEW_ID}1": [
        dict(mode="instant", trigger_kind="0", effect_kind="34",
             value=50, value_max=100),
        dict(mode="instant", trigger_kind="23", threshold=1,
             effect_kind="21", value=50, value_max=100,
             duration_frames=90000000, number=100000, initial_multiply=1),
    ],
    f"{NEW_ID}2": [
        dict(mode="instant", trigger_kind="12", threshold=20,
             effect_kind="213", value=25, value_max=50,
             precondition_kind="186"),
        dict(mode="instant", trigger_kind="12", threshold=40,
             effect_kind="213", value=50, value_max=100,
             precondition_kind="186"),
        dict(mode="instant", trigger_kind="12", threshold=60,
             effect_kind="211", value=10, value_max=20),
    ],
    f"{NEW_ID}3": [
        dict(mode="instant", trigger_kind="8", threshold=1,
             effect_kind="211", value=25, value_max=50, main_only=True),
        dict(mode="during", trigger_kind="4", effect_kind="2",
             value=75, value_max=150, main_only=True),
        dict(mode="during", trigger_kind="4", effect_kind="3",
             value=25, value_max=50, main_only=True),
        dict(mode="instant", trigger_kind="23", threshold=1,
             effect_kind="211", value=15, value_max=30,
             precondition_kind="12", cooldown_frames=600, main_only=True),
        dict(mode="instant", trigger_kind="23", threshold=1,
             effect_kind="213", value=125, value_max=250,
             precondition_kind="12", cooldown_frames=600, main_only=True),
    ],
    f"{NEW_ID}4": [
        dict(mode="instant", trigger_kind="0", effect_kind="211",
             value=50, value_max=100),
        dict(mode="instant", trigger_kind="0", effect_kind="32",
             value=50, value_max=100),
        dict(mode="instant", trigger_kind="0", effect_kind="34",
             value=50, value_max=100),
    ],
    f"{NEW_ID}5": [
        dict(mode="instant", trigger_kind="0", effect_kind="34",
             value=50, value_max=100, target="5", groups="Green"),
        dict(mode="instant", trigger_kind="0", effect_kind="56",
             value=10, value_max=20),
        dict(mode="during", trigger_kind="4", effect_kind="0",
             value=50, value_max=100, target="5", groups="Green"),
    ],
    f"{NEW_ID}6": [
        dict(mode="instant", trigger_kind="23", threshold=1,
             effect_kind="34", value=15, value_max=30, trigger_limit=5),
        dict(mode="instant", trigger_kind="23", threshold=2,
             effect_kind="211", value=5, value_max=10),
        dict(mode="during", trigger_kind="4", effect_kind="411",
             value=15, value_max=30),
    ],
}
```

- [ ] **Step 5: Implement the final leader and PF override row**

Generate the first seven rows from these specs:

```python
specs = [
    dict(mode="instant", trigger_kind="0", effect_kind="32",
         value=100, value_max=150, target="5", groups="Green"),
    dict(mode="instant", trigger_kind="0", effect_kind="34",
         value=150, value_max=200, target="5", groups="Green"),
    dict(mode="instant", trigger_kind="0", effect_kind="50",
         value=100, value_max=150, target="5"),
    dict(mode="instant", trigger_kind="0", effect_kind="56",
         value=20, value_max=30),
    dict(mode="instant", trigger_kind="8", threshold=1, effect_kind="211",
         value=25, value_max=50, target="5", groups="Green"),
    dict(mode="during", trigger_kind="4", effect_kind="2",
         value=100, value_max=150, target="5", groups="Green"),
    dict(mode="during", trigger_kind="4", effect_kind="3",
         value=15, value_max=30, target="5", groups="Green"),
]
```

Clone the existing validated Gerald instant override row from active key
`149999`, select the row whose instant content kind is `722`, and change only:

```python
override[cbase + 35] = "land_dragon_wind_pf"
override[cbase + 36] = "1,2,3"
override[cbase + 37] = "override_string_wind_spgirl_4anv"
```

Append it as row 8. Run `_client_legality_problems` for every generated or
cloned row before writing.

- [ ] **Step 6: Build the package and verify GREEN**

Run:

```powershell
python work\character_packs\land_dragon_wind_poc\build_workspace.py build
python -c "import runpy; ns=runpy.run_path(r'work\character_packs\land_dragon_wind_poc\test_package.py'); ns['test_leader_and_six_abilities_match_the_approved_fever_pf_kit'](); ns['test_condition_fever_point_uses_cn_runtime_sentinels'](); print('master rows passed')"
```

Expected: both tests PASS and `evidence/live-write-verification.json` still
reports `writes_live=false`.

- [ ] **Step 7: Checkpoint**

Record the generated master descriptions and exact row counts in
`evidence/build-report.json`; do not commit.

---

### Task 2: Replace the fixed Fever sequence with five random boss skills

**Files:**
- Modify: `work/character_packs/land_dragon_wind_poc/test_package.py:276-371`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py:128-237`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py:1341-1684`

**Interfaces:**
- Consumes: `_block`, `_command`, `_event`, `_damage_beat`, `_one_shot_hit_area`, `locate_required`, `skin.remap_tree`.
- Produces: `FEVER_VARIANTS`, `_probability_branch()`, `_fever_probability_block()`, and the final two active-skill DSL files.

- [ ] **Step 1: Add a probability-branch parser to the tests**

```python
def _probability_branches(fever: Any) -> list[tuple[int, Any]]:
    conditional = _first_command(fever, "ConditionalsProbability")
    branch_nodes = conditional[1][1][1]
    result = []
    for branch in branch_nodes:
        assert branch[0] == "Block"
        weight_command, action_block = branch[1]
        assert weight_command[0] == "Command"
        assert weight_command[1][0] == "ProbabilityWeight"
        assert action_block[0] == "Block"
        result.append((int(weight_command[1][1]), action_block))
    return result
```

- [ ] **Step 2: Replace the fixed-34-hit test with the five-variant contract**

```python
expected = {
    "wind_breath_laser": (8, 80.0),
    "ground_craw_fang": (10, 80.0),
    "moving_slash_array": (16, 80.0),
    "targeted_hunt": (20, 80.0),
    "full_field_storm": (32, 80.0),
}
for level in (1, 2):
    tree = _dsl(level)
    normal = _branch(tree, False)
    fever = _branch(tree, True)
    assert _hit_area_audit(normal) == (8, 24.0)
    branches = _probability_branches(fever)
    assert [weight for weight, _branch_node in branches] == [20] * 5
    labels = {}
    for _weight, branch in branches:
        variant = next(
            command[1][1].split("/", 2)[1]
            for command in _nodes(branch, "Command", "ShowEffect")
            if command[1][1].startswith("Fever/")
        )
        labels[variant] = _hit_area_audit(branch)
        assert _resistance_down(branch) == (1200, -0.25)
        assert not list(_nodes(branch, "Command", "AddFeverPoint"))
        assert not list(_nodes(branch, "Command", "AddSkillPoint"))
        assert not list(_nodes(branch, "Command", "SpawnFunnel"))
        assert not list(_nodes(branch, "Command", "CreateTargetAttack"))
    assert labels == expected
```

Update the normal Fever-point assertion from `200` to `300`.

- [ ] **Step 3: Run the random-pool test and verify RED**

Run:

```powershell
python -c "import runpy; ns=runpy.run_path(r'work\character_packs\land_dragon_wind_poc\test_package.py'); ns['test_action_dsl_has_24x_normal_and_five_equal_80x_fever_variants']()"
```

Expected: FAIL because the current Fever block has no
`ConditionalsProbability`, still totals 34 fixed hits, and normal adds only
200 Fever.

- [ ] **Step 4: Replace `FEVER_GROUPS` with exact variant data**

```python
FEVER_VARIANTS = (
    dict(name="wind_breath_laser", hit_count=8,
         effects=("laser",), minimum=7.5, maximum=10.0,
         interval=8, radius=320, y=-80),
    dict(name="ground_craw_fang", hit_count=10,
         effects=("craw",), minimum=6.0, maximum=8.0,
         interval=7, radius=380, y=-120),
    dict(name="moving_slash_array", hit_count=16,
         effects=("slash",), minimum=3.75, maximum=5.0,
         interval=5, radius=440, y=-140),
    dict(name="targeted_hunt", hit_count=20,
         effects=("explosion", "wave_arc30"), prelude="target_sight",
         minimum=3.0, maximum=4.0,
         interval=4, radius=360, y=-100),
    dict(name="full_field_storm", hit_count=32,
         effects=("overall", "explosion", "wave_arc120_fast",
                  "wave_arc120_middle", "wave_arc120_slow"),
         minimum=1.875, maximum=2.5,
         interval=3, radius=620, y=-180),
)
```

- [ ] **Step 5: Build the official probability shape**

Use the verified player-skill structure:

```python
def _probability_branch(weight: int, actions: list[Any]) -> list[Any]:
    return _block([
        _command("ProbabilityWeight", weight),
        _block(actions),
    ])


def _fever_probability_block() -> list[Any]:
    branches = []
    for variant_index, variant in enumerate(FEVER_VARIANTS):
        actions = []
        if variant.get("prelude"):
            actions.append(_command(
                "ShowEffect",
                f"Fever/{variant['name']}/prelude",
                ["SpecifyEffectDirectly", _effect_path(variant["prelude"])],
                0,
                ["ForesideOfCharacter"],
                ["PlayOnlyFirstSequence"],
                ["AB"], 0, 0, 0, True, True,
                ["Some", _power(6, 6)],
            ))
        for hit_index in range(variant["hit_count"]):
            effects = variant["effects"]
            actions.append(_damage_beat(
                wait=hit_index * variant["interval"],
                label=f"Fever/{variant['name']}/{hit_index + 1}",
                effect=effects[hit_index % len(effects)],
                seed=2000 + variant_index * 200 + hit_index * 4,
                minimum=variant["minimum"],
                maximum=variant["maximum"],
                radius=variant["radius"],
                y=variant["y"] + ((hit_index % 3) - 1) * 30,
                resistance=(1200, -0.20, -0.25)
                if hit_index == 0 else None,
            ))
        branches.append(_probability_branch(20, actions))
    return _command("ConditionalsProbability", _block(branches))
```

Use this command as the Fever branch content. Change the normal
`AddFeverPoint` power to `_power(240, 300)`.

- [ ] **Step 6: Build and verify GREEN**

Run:

```powershell
python work\character_packs\land_dragon_wind_poc\build_workspace.py build
python -c "import runpy; ns=runpy.run_path(r'work\character_packs\land_dragon_wind_poc\test_package.py'); ns['test_action_dsl_has_24x_normal_and_five_equal_80x_fever_variants'](); print('random skill passed')"
```

Expected: PASS for both skill levels, with five branches and no enemy commands.

- [ ] **Step 7: Checkpoint**

Verify both ActionDsl files round-trip and record variant weights, hit counts,
and multipliers in `evidence/build-report.json`; do not commit.

---

### Task 3: Own every random-skill effect dependency

**Files:**
- Modify: `work/character_packs/land_dragon_wind_poc/test_package.py:345-371`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py:128-135`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py:1602-1653`

**Interfaces:**
- Consumes: `locate_required()`, `read_tree()`, `encode_tree()`, `skin.remap_tree()`, `write_root()`.
- Produces: `_copy_effect_family()` plus ten complete character-owned active-skill effect families.

- [ ] **Step 1: Expand the owned-effect test**

```python
expected = {
    "explosion", "wave_arc30", "wave_arc120_fast",
    "wave_arc120_middle", "wave_arc120_slow",
    "laser", "craw", "slash", "target_sight", "overall",
}
assert {path.parent.name for path in root.rglob("*.png")} == expected
for name in expected:
    names = {path.name for path in (root / name).iterdir()}
    assert names == {
        f"{name}.png",
        f"{name}.atlas.amf3.deflate",
        f"{name}.parts.amf3.deflate",
        f"{name}.timeline.amf3.deflate",
    }
```

For every ShowEffect path in every random branch, assert the corresponding
`.png`, `.atlas.amf3.deflate`, `.parts.amf3.deflate`, and
`.timeline.amf3.deflate` files exist.

- [ ] **Step 2: Run the effect test and verify RED**

Run:

```powershell
python -c "import runpy; ns=runpy.run_path(r'work\character_packs\land_dragon_wind_poc\test_package.py'); ns['test_owned_random_skill_effect_assets_are_complete']()"
```

Expected: FAIL because only the old five effect families exist.

- [ ] **Step 3: Generalize effect copying**

Implement:

```python
def _copy_effect_family(
    *,
    source_dir: str,
    source_stem: str,
    target_dir: str,
    target_stem: str,
    remaps: tuple[tuple[str, str], ...] = (),
) -> list[dict[str, Any]]:
    files = []
    for extension in (
        "png", "atlas.amf3.deflate",
        "parts.amf3.deflate", "timeline.amf3.deflate",
    ):
        source_path = locate_required(f"{source_stem}.{extension}")[1]
        if extension == "png":
            data = source_path.read_bytes()
        else:
            tree = read_tree(source_path)
            tree = skin.remap_tree(tree, source_dir, target_dir)
            for old, new in remaps:
                tree = skin.remap_tree(tree, old, new)
            data = encode_tree(tree)
        target = write_root("common", f"{target_stem}.{extension}", data)
        files.append({
            "logical_path": f"{target_stem}.{extension}",
            "size": target.stat().st_size,
            "sha256": sha256_file(target),
        })
    return files
```

Map these generic green sources:

```python
EFFECT_SOURCES = {
    "explosion": "enemy_shot_explosion_medium",
    "wave_arc30": "enemy_shot_wave_arc30_middle",
    "wave_arc120_fast": "enemy_shot_wave_arc120_fast",
    "wave_arc120_middle": "enemy_shot_wave_arc120_middle",
    "wave_arc120_slow": "enemy_shot_wave_arc120_slow",
    "laser": "enemy_shot_laser_ll",
    "craw": "enemy_shot_craw_large",
    "slash": "enemy_shot_slash_middle",
    "overall": "enemy_shot_overall_attack",
}
```

Handle `target_sight` separately because its source atlas/PNG stem is
`enemy_shot_discard_dragon_wind` while its parts/timeline stem is
`discard_dragon_target_sight`. Remap both source stems to the single owned
target stem:

```text
battle/effect/skill_unique/land_dragon_wind_playable/target_sight/target_sight
```

- [ ] **Step 4: Build and verify GREEN**

Run:

```powershell
python work\character_packs\land_dragon_wind_poc\build_workspace.py build
python -c "import runpy; ns=runpy.run_path(r'work\character_packs\land_dragon_wind_poc\test_package.py'); ns['test_owned_random_skill_effect_assets_are_complete'](); print('skill effects passed')"
```

Expected: PASS with ten complete owned effect families and zero unresolved
texture paths.

- [ ] **Step 5: Checkpoint**

Record every source/target stem and file hash in the build report; do not commit.

---

### Task 4: Build the game-asset-only 6/12/24-hit custom PF

**Files:**
- Modify: `work/character_packs/land_dragon_wind_poc/test_package.py`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py:239-258`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py:934-1139`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py:1341-1708`

**Interfaces:**
- Consumes: official Fighter PF logical programs, `_copy_effect_family()`, AMF3 helpers, and the leader 722 override from Task 1.
- Produces: `POWER_FLIP_KIND`, three PF ActionDsl files, `power_flip_action.orderedmap#land_dragon_wind_pf`, and three complete PF effect families.

- [ ] **Step 1: Add PF loading/audit helpers to the tests**

```python
PF_KIND = "land_dragon_wind_pf"
PF_COUNTS = {1: 6, 2: 12, 3: 24}
PF_TOTALS = {
    1: {6: 7.5, 13: 12.0, 14: 9.6},
    2: {6: 16.0, 13: 15.0, 14: 19.2},
    3: {6: 27.0, 13: 20.0, 14: 28.8},
}


def _pf_dsl(level: int) -> Any:
    path = (
        COMMON / "battle" / "action" / "power_flip" / "action" / "override"
        / f"{PF_KIND}${PF_KIND}_lv{level}.action.dsl.amf3.deflate"
    )
    return wf_dsl.parse_dsl(zlib.decompress(path.read_bytes(), -15))["tree"]


def _attack_total(tree: Any, field: int = 6) -> float:
    return sum(
        float(node[1][field][0]["max"])
        for node in _nodes(tree, "Command", "CreateNormalAttack")
    )
```

- [ ] **Step 2: Add the complete PF contract test**

```python
def test_custom_power_flip_has_owned_programs_lifecycle_and_real_hits() -> None:
    table = _flat("master/skill/power_flip_action.orderedmap")
    assert table[PF_KIND][0] == [
        f"battle/action/power_flip/action/override/{PF_KIND}${PF_KIND}_lv1",
        f"battle/action/power_flip/action/override/{PF_KIND}${PF_KIND}_lv2",
        f"battle/action/power_flip/action/override/{PF_KIND}${PF_KIND}_lv3",
    ]
    for level, expected_hits in PF_COUNTS.items():
        tree = _pf_dsl(level)
        assert len(list(_nodes(tree, "Command", "CreateHitArea"))) == expected_hits
        assert len(list(_nodes(tree, "Command", "CreateNormalAttack"))) == expected_hits
        for field, expected_total in PF_TOTALS[level].items():
            assert math.isclose(
                _attack_total(tree, field), expected_total,
                rel_tol=0, abs_tol=1e-6,
            )
        assert len(list(_nodes(tree, "Command", "SetPowerFilpSuppress"))) == 2
        assert len(list(_nodes(tree, "Command", "NotifyPowerflipEnd"))) == 2
        assert all(
            area[1][14] == ["CalculatedUsingMaxNumOfHits", 1]
            for area in _nodes(tree, "Command", "CreateHitArea")
        )
```

Add a resource assertion for:

```python
pf_root = COMMON / "battle/effect/powerflip/land_dragon_wind_powerflip"
assert {p.parent.name for p in pf_root.rglob("*.png")} == {
    "wind_fang", "wind_wing", "wind_storm",
}
```

- [ ] **Step 3: Run the PF test and verify RED**

Run:

```powershell
python -c "import runpy; ns=runpy.run_path(r'work\character_packs\land_dragon_wind_poc\test_package.py'); ns['test_custom_power_flip_has_owned_programs_lifecycle_and_real_hits']()"
```

Expected: FAIL because there is no PF table key, no override DSL, and no owned
PF effect directory.

- [ ] **Step 4: Register the PF table as a package-owned master**

Add:

```python
POWER_FLIP_KIND = "land_dragon_wind_pf"
POWER_FLIP_PROGRAMS = {
    level: (
        "battle/action/power_flip/action/override/"
        f"{POWER_FLIP_KIND}${POWER_FLIP_KIND}_lv{level}"
    )
    for level in (1, 2, 3)
}
```

Add `"master/skill/power_flip_action.orderedmap": "flat"` to `TABLE_CODECS`.
Write a new shadow row containing the three comma-separated program paths
before `export_data()` runs.

- [ ] **Step 5: Copy only game-original PF visuals**

Create three owned families:

```python
PF_EFFECT_SOURCES = {
    "wind_fang": "enemy_shot_wave_arc30_middle",
    "wind_wing": "enemy_shot_wave_arc120_middle",
    "wind_storm": "enemy_shot_overall_attack",
}
```

Copy their green variants through `_copy_effect_family()` into:

```text
battle/effect/powerflip/land_dragon_wind_powerflip/<name>/<name>
```

No generated or hand-drawn PNG is allowed.

- [ ] **Step 6: Preserve official Fighter PF lifecycle and replace only impacts**

For each level, load:

```text
battle/action/power_flip/action/fighter$fighter_lv<level>
```

Keep the template header and collision lifecycle, including both
`SetPowerFilpSuppress` and both `NotifyPowerflipEnd` commands. Within the
collision block, replace the old impact schedule with `6/12/24` cloned
one-shot impact events.

Compute official totals from the untouched template:

```python
PF_HITS = {1: 6, 2: 12, 3: 24}
expected_totals = {
    index: sum(
        float(attack[1][index][0]["max"])
        for attack in _nodes(template, "Command", "CreateNormalAttack")
    )
    for index in (6, 13, 14)
}
```

For each new hit, set the corresponding damage range to
`expected_totals[index] / PF_HITS[level]`. Cycle effects as:

```python
PF_EFFECT_CYCLES = {
    1: ("wind_fang",),
    2: ("wind_fang", "wind_wing"),
    3: ("wind_fang", "wind_wing", "wind_storm"),
}
```

Use unique hit-area IDs and `CalculatedUsingMaxNumOfHits(1)` for every hit.
Encode, decode, and compare each output tree before accepting it.

- [ ] **Step 7: Build and verify GREEN**

Run:

```powershell
python work\character_packs\land_dragon_wind_poc\build_workspace.py build
python -c "import runpy; ns=runpy.run_path(r'work\character_packs\land_dragon_wind_poc\test_package.py'); ns['test_custom_power_flip_has_owned_programs_lifecycle_and_real_hits'](); print('custom PF passed')"
```

Expected: PASS for table registration, lifecycle, owned effects, real hit
counts, and official total damage preservation.

- [ ] **Step 8: Checkpoint**

Record template paths, source total multipliers, output hit counts, output
totals, lifecycle command counts, and hashes in `evidence/build-report.json`;
do not commit.

---

### Task 5: Lock Pixel provenance and package metadata

**Files:**
- Modify: `work/character_packs/land_dragon_wind_poc/test_package.py`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py:63-105`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py:1257-1339`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py:1709-1780`

**Interfaces:**
- Consumes: existing `build_pixel_assets()`, source Pixel timeline, manifest writer.
- Produces: a 1.1.0 manifest and proof that no new Pixel artwork was authored.

- [ ] **Step 1: Add Pixel provenance and version tests**

```python
def test_custom_pf_reuses_the_complete_game_original_attack_pixel_chain() -> None:
    pixel_root = COMMON / "character" / CODE / "pixelart"
    normal = wf_dsl.parse_dsl(
        zlib.decompress((pixel_root / "pixelart.timeline.amf3.deflate").read_bytes(), -15)
    )["tree"]
    special = wf_dsl.parse_dsl(
        zlib.decompress((pixel_root / "special.timeline.amf3.deflate").read_bytes(), -15)
    )["tree"]
    sequences = {item["name"]: item for item in special["sequences"]}
    assert sequences["special_land"] == {
        "name": "special_land", "kind": "pass", "begin": 61, "end": 96,
    }
    assert sequences["special_pose"] == {
        "name": "special_pose", "kind": "once", "begin": 97, "end": 158,
    }
    assert normal["sequences"]
    assert not (pixel_root / "power_flip_sprite_sheet.png").exists()


def test_manifest_is_revision_1_1_0_and_workspace_only() -> None:
    manifest = json.loads((WORKSPACE / "package/manifest.json").read_text("utf-8"))
    assert manifest["package_version"] == "1.1.0"
    report = json.loads((WORKSPACE / "evidence/build-report.json").read_text("utf-8"))
    assert report["workspace_only"] is True
    assert report["published"] is False
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
python -c "import runpy; ns=runpy.run_path(r'work\character_packs\land_dragon_wind_poc\test_package.py'); ns['test_manifest_is_revision_1_1_0_and_workspace_only']()"
```

Expected: FAIL because the current candidate version is `1.0.2`.

- [ ] **Step 3: Update package identity and skill text**

Set:

```python
REVISION_VERSION = "1.1.0"
```

Update both skill descriptions to state:

```text
以完整荒岚攻势造成风属性伤害并降低风属性抗性／非Fever状态下增加Fever槽／
Fever状态下随机释放一种首领技，造成大幅风属性伤害
```

Set `leader_title` to `荒岚霸主＋`.

- [ ] **Step 4: Preserve the existing Pixel build unchanged**

Do not create any PF-specific character sprite sheet. Keep the original source
sheet/atlas remap and the exact special ranges `61-96` and `97-158`. Extend the
Pixel build report with:

```python
"power_flip_pixel_art": {
    "new_frames_authored": 0,
    "source": str(SOURCE_PIXEL),
    "uses_game_original_attack_chain": True,
}
```

- [ ] **Step 5: Build and verify GREEN**

Run:

```powershell
python work\character_packs\land_dragon_wind_poc\build_workspace.py build
python -c "import runpy; ns=runpy.run_path(r'work\character_packs\land_dragon_wind_poc\test_package.py'); ns['test_custom_pf_reuses_the_complete_game_original_attack_pixel_chain'](); ns['test_manifest_is_revision_1_1_0_and_workspace_only'](); print('pixel provenance passed')"
```

Expected: PASS and no new Pixel PNG beyond the existing character sheets.

- [ ] **Step 6: Checkpoint**

Save the Pixel provenance report in `evidence/build-report.json`; do not commit.

---

### Task 6: Refresh dossier, canary contract, and full workspace build

**Files:**
- Modify: `work/character_packs/land_dragon_wind_poc/character-dossier.md`
- Create: `work/character_packs/land_dragon_wind_poc/device-canary/revision-1.1.0-checklist.md`
- Generate: `work/character_packs/land_dragon_wind_poc/package/**`
- Generate: `work/character_packs/land_dragon_wind_poc/evidence/**`

**Interfaces:**
- Consumes: all Task 1-5 outputs.
- Produces: the sealed, workspace-only 1.1.0 candidate and a device test handoff that performs no install.

- [ ] **Step 1: Add the final evidence test**

```python
def test_build_report_describes_random_skill_and_custom_pf_without_live_writes() -> None:
    report = json.loads((WORKSPACE / "evidence/build-report.json").read_text("utf-8"))
    assert report["skill"]["variant_weights"] == {
        "wind_breath_laser": 20,
        "ground_craw_fang": 20,
        "moving_slash_array": 20,
        "targeted_hunt": 20,
        "full_field_storm": 20,
    }
    assert report["skill"]["variant_hits"] == {
        "wind_breath_laser": 8,
        "ground_craw_fang": 10,
        "moving_slash_array": 16,
        "targeted_hunt": 20,
        "full_field_storm": 32,
    }
    assert report["power_flip"]["hit_counts"] == {"1": 6, "2": 12, "3": 24}
    assert report["live_write_verification"] == {
        "writes_live": False,
        "unchanged": True,
    }
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
python -c "import runpy; ns=runpy.run_path(r'work\character_packs\land_dragon_wind_poc\test_package.py'); ns['test_build_report_describes_random_skill_and_custom_pf_without_live_writes']()"
```

Expected: FAIL until the build report contains the new random-skill and PF
sections.

- [ ] **Step 3: Complete the build report**

Add:

```python
"skill": {
    **skill_report,
    "variant_weights": {item["name"]: 20 for item in FEVER_VARIANTS},
    "variant_hits": {
        item["name"]: item["hit_count"] for item in FEVER_VARIANTS
    },
},
"power_flip": power_flip_report,
```

Keep `workspace_only=True`, `published=False`, and the existing live-state
before/after comparison.

- [ ] **Step 4: Rewrite the dossier**

Document exact max values for the leader and six abilities, the 300-point
normal skill, all five 80× variants, PF 6/12/24 hits, game-original Pixel
provenance, effect-source ownership, and all remaining device gates. Mark:

```text
1.1.0 workspace-only candidate; not published; not installed by this build.
```

- [ ] **Step 5: Create the non-executing device checklist**

The checklist must contain separate rows for:

```text
Battle entry/no C7101
PF Lv1 actual 6 hits
PF Lv2 actual 12 hits
PF Lv3 actual 24 hits
20/40 combo Fever triggers outside Fever only
Normal skill 8 hits/24x/+300 Fever
Each of five forced Fever branches and 80x total
Random distribution after restoring weights
Fever entry +100% self gauge total
Fever cast +30% gauge/+250 Fever/10s cooldown
Second-cast feasibility and no infinite loop
Effect direction/size/occlusion/beat sync
No G3000/F1009/Fatal/ANR
```

State explicitly that running the checklist requires separate authorization to
temporarily install the candidate into emulator-private storage.

- [ ] **Step 6: Rebuild and verify GREEN**

Run:

```powershell
python work\character_packs\land_dragon_wind_poc\build_workspace.py build
python -c "import runpy; ns=runpy.run_path(r'work\character_packs\land_dragon_wind_poc\test_package.py'); tests=[(n,v) for n,v in ns.items() if n.startswith('test_') and callable(v)]; [v() for n,v in sorted(tests)]; print(f'{len(tests)} passed')"
python work\character_packs\land_dragon_wind_poc\build_workspace.py verify-live
```

Expected: all tests PASS; `verify-live` reports no activity change.

- [ ] **Step 7: Checkpoint**

Capture the test count, build-report SHA-256, manifest SHA-256, and
`live-write-verification.json` hash; do not commit.

---

### Task 7: Run production preflight without publishing

**Files:**
- Read: `work/character_packs/land_dragon_wind_poc/package/**`
- Generate: `work/character_packs/land_dragon_wind_poc/evidence/**`

**Interfaces:**
- Consumes: sealed 1.1.0 workspace candidate from Task 6.
- Produces: production preflight result only; no publish side effects.

- [ ] **Step 1: Run character-flow preflight**

Run:

```powershell
python mod-tools\wf_character_flow.py preflight --workspace work\character_packs\land_dragon_wind_poc --installed-package-dir work\installed_character_packages\land_dragon_wind_poc\1.0.1\package
```

Expected:

```text
required assets 37/37
release_ready=true
can_prepare=true
conflicts=0
deletions=0
writes_live=false
```

- [ ] **Step 2: Re-run all character tests after preflight**

Run:

```powershell
python -c "import runpy; ns=runpy.run_path(r'work\character_packs\land_dragon_wind_poc\test_package.py'); tests=[(n,v) for n,v in ns.items() if n.startswith('test_') and callable(v)]; [v() for n,v in sorted(tests)]; print(f'{len(tests)} passed')"
```

Expected: all tests still PASS after manifest sealing.

- [ ] **Step 3: Verify active state remained unchanged**

Run:

```powershell
python work\character_packs\land_dragon_wind_poc\build_workspace.py verify-live
```

Expected: `writes_live=false`, active CDN/version/save/emulator untouched.

- [ ] **Step 4: Final workspace-only handoff**

Report:

- candidate package version;
- manifest and build-report SHA-256;
- test count;
- 37/37 and three-layer preflight status;
- five random branches and three PF levels encoded;
- known limitation that static checks do not prove device hit/effect behavior;
- exact statement that nothing was installed or published;
- request separate authorization for the emulator canary.

Do not publish, install, edit the save, stage, commit, or push.
