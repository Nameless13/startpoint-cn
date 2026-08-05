# Land Dragon Wind 1.1.1 Canary Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a workspace-only `1.1.1` wind-dragon candidate that exposes special PF, uses real Fever-point units, applies the approved ability rebalance, and replaces per-hit effect restarts with coherent skill/PF presentations.

**Architecture:** Keep the package generator as the only source of generated assets. Extend its existing table writers for the data corrections, then split visual presentation creation from hit-event creation in the ActionDsl builders. Validate consumer-visible generated tables and decoded ActionDsl with literal assertions before running the character-flow production preflight.

**Tech Stack:** Python 3, `wf_mod_tool`, `wf_gui`, `wf_dsl`, AMF3 raw-deflate assets, `wf_character_flow.py`.

## Global Constraints

- Work only inside `work/character_packs/land_dragon_wind_poc`, its generated package/evidence, and the two approved design/plan documents.
- Do not write `assets/`, `.cdn/`, current saves, emulator/device storage, or live release graphs.
- Do not publish or install the candidate.
- Do not perform Git actions.
- Candidate version is exactly `1.1.1`.
- Character ID is `149998`; code is `land_dragon_wind_playable`.
- Normal skill is 8 real hits and 24× total at max level.
- Fever variants are 8／10／16／20／32 real hits and 80× total at max level.
- PF levels are 6／12／24 real hits and preserve their current total damage.
- Ability-table `AddFeverPoint` values use `count` units; ActionDsl `AddFeverPoint` remains raw point units.
- Static verification is not device acceptance.

---

### Task 1: Data-table regression contracts

**Files:**
- Modify: `work/character_packs/land_dragon_wind_poc/test_package.py`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py`

**Interfaces:**
- Consumes: generated package under `work/character_packs/land_dragon_wind_poc/package`
- Produces: `1.1.1` table rows with special PF, valid all-party sentinel, and approved ability values

- [ ] **Step 1: Write failing generated-package tests**

Update the existing literal contracts so they assert:

```python
assert row[6] == "4"
assert server_row[6] == "4"

("0", "0", "50", "5", "(None)", "150000")

assert [
    (row["precondition"], row["trigger"], row["threshold"],
     row["effect"], row["maximum"])
    for row in a2
] == [
    ("186", "12", "1000000", "213", "15000000"),
    ("186", "12", "1500000", "213", "30000000"),
    ("0", "12", "2500000", "211", "20000"),
]

assert ("23", "213", "45000000", "600") in {
    (row["trigger"], row["effect"], row["maximum"], row["cooldown"])
    for row in a3
}

assert exact_groups[f"{CID}4"] == {
    ("0", "0", "211", "0", "", "100000"),
}
assert exact_groups[f"{CID}5"] == {
    ("0", "0", "34", "5", "Green", "50000"),
    ("0", "0", "56", "0", "", "10000"),
    ("1", "4", "0", "5", "Green", "50000"),
}
```

Change the expected ability-4 row count from 3 to 1 and the manifest version expectation from `1.1.0` to `1.1.1`.

The production mutations caught are: retained fighter type, missing all-party sentinel, percentage-scaled Fever points, old combo thresholds, extra ability-4 rows, and unhalved ability-5 values.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python work\character_packs\land_dragon_wind_poc\test_package.py
```

Expected: the identity/ability/version tests fail against the existing `1.1.0` package with literal mismatches, while unrelated tests continue to run.

- [ ] **Step 3: Implement the table changes**

In `build_workspace.py`:

```python
REVISION_VERSION = "1.1.1"
```

Call the existing shadow-store PF writer after `load_shadowed_gui()`:

```python
speciality = gui.powerflip_set_spec(NEW_ID, 4, False)
```

Return the result in `customize_character_data()` evidence.

Change the leader Fever-rate spec to:

```python
dict(
    mode="instant",
    trigger_kind="0",
    effect_kind="50",
    value=100,
    value_max=150,
    target="5",
    groups="(None)",
)
```

Replace ability 2 with:

```python
dict(mode="instant", trigger_kind="12", threshold=10,
     effect_kind="213", value=75, value_max=150,
     effect_unit="count", precondition_kind="186"),
dict(mode="instant", trigger_kind="12", threshold=15,
     effect_kind="213", value=150, value_max=300,
     effect_unit="count", precondition_kind="186"),
dict(mode="instant", trigger_kind="12", threshold=25,
     effect_kind="211", value=10, value_max=20),
```

Replace ability 3's Fever-point row with:

```python
dict(mode="instant", trigger_kind="23", threshold=1,
     effect_kind="213", value=225, value_max=450,
     effect_unit="count", precondition_kind="12",
     cooldown_frames=600, main_only=True),
```

Reduce ability 4 to the existing `effect_kind="211"` start-gauge row only. Set ability 5 max values to `50`, `10`, and `50`.

- [ ] **Step 4: Rebuild and verify GREEN for data contracts**

Run:

```powershell
python work\character_packs\land_dragon_wind_poc\build_workspace.py build
python work\character_packs\land_dragon_wind_poc\test_package.py
```

Expected: Task 1 assertions pass. Animation assertions added in Task 2 may still fail.

---

### Task 2: Skill presentation lifecycle regression contracts

**Files:**
- Modify: `work/character_packs/land_dragon_wind_poc/test_package.py`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py`

**Interfaces:**
- Consumes: decoded ActionDsl trees and copied owned effect timelines
- Produces: `_show_effect_event(...)`, `_hit_event(...)`, and presentation schedules with visual creation separated from hit creation

- [ ] **Step 1: Add failing lifecycle and placement tests**

Add a helper that extracts `ShowEffect` parameter arrays from a branch and asserts real decoded output. Test these observable contracts:

```python
expected_shows = {
    "wind_breath_laser": {"laser": 1},
    "ground_craw_fang": {"craw": 1},
    "moving_slash_array": {"slash": 2},
    "targeted_hunt": {"target_sight": 1, "explosion": 1, "wave_arc30": 1},
    "full_field_storm": {
        "overall": 1,
        "explosion": 1,
        "wave_arc120_fast": 1,
        "wave_arc120_middle": 1,
        "wave_arc120_slow": 1,
    },
}
```

For every owned skill effect `ShowEffect`:

```python
assert show[5][0] == "SpecifyEffectLifetimeDirectly"
assert int(show[5][1]) > 0
assert show[5] != ["PlayOnlyFirstSequence"]
```

Also assert:

- normal branch has exactly one owned `wave_arc30` presentation and still has eight hit areas;
- laser hit areas share one forward axis;
- crawl hit-area forward offsets are strictly increasing;
- slash hit-area horizontal offsets contain both negative and positive values;
- target-hunt hit areas share the target reference anchor/point used by its sight effect;
- full-field hit events are distributed across more than one wait frame;
- none of the skill branches contains `SpawnFunnel` or `CreateTargetAttack`.

The production mutations caught are: restoring `_damage_beat` effect creation, reinstating `PlayOnlyFirstSequence`, collapsing positions, or moving all storm hits onto one frame.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python work\character_packs\land_dragon_wind_poc\test_package.py
```

Expected: lifecycle/count/placement assertions fail because `1.1.0` restarts effects for every hit and truncates them to the first sequence.

- [ ] **Step 3: Split visual and damage builders**

Replace `_damage_beat(...)` with two focused helpers:

```python
def _show_effect_event(
    *, wait: int, label: str, effect: str, lifetime: int,
    anchor: list[Any] | None = None, x: int = 0, y: int = 0,
    rotation: int | float = 0, track_position: bool = True,
    track_direction: bool = True,
) -> list[Any]:
    return _event("Wait", wait, "*", _block([
        _command(
            "ShowEffect",
            label,
            ["SpecifyEffectDirectly", _effect_path(effect)],
            0,
            ["ForesideOfCharacter"],
            ["SpecifyEffectLifetimeDirectly", lifetime],
            anchor or ["AB"],
            x,
            y,
            rotation,
            track_position,
            track_direction,
            ["Some", _power(6, 6)],
        )
    ]))


def _hit_event(
    *, wait: int, seed: int, minimum: float, maximum: float,
    radius: int, x: int, y: int, rotation: int | float = 0,
    resistance: tuple[int, float, float] | None = None,
) -> list[Any]:
    return _event("Wait", wait, "*", _block([
        _one_shot_hit_area(
            seed=seed,
            minimum=minimum,
            maximum=maximum,
            radius=radius,
            x=x,
            y=y,
            rotation=rotation,
            resistance=resistance,
        )
    ]))
```

Extend `_one_shot_hit_area(...)` with explicit `x` and `rotation` parameters and place them in the `CreateHitArea` command next to `y`.

- [ ] **Step 4: Build literal visual and hit schedules**

Represent presentation cues and hit offsets as literal per-variant data so tests do not infer expected behavior from the builder:

- laser: one `laser` cue; eight hits on one forward axis;
- crawl: one `craw` cue; ten hits with monotonically advancing forward offsets;
- slash: two `slash` cues with opposite horizontal offsets/rotations; sixteen alternating left/right hits;
- target hunt: one sight cue followed by one explosion and one arc cue, all bound to the same target reference point; twenty hits around that point;
- full-field storm: one cue per owned storm family; thirty-two hits split across its configured wait frames and battlefield positions.

Use direct lifetimes at least as long as each copied timeline's required visible range. Keep the existing first-hit wind-resistance debuff and literal hit multipliers.

Create the normal branch with one coherent `wave_arc30` cue plus eight `_hit_event(...)` calls, followed by the unchanged ActionDsl `AddFeverPoint(_power(240, 300))`.

- [ ] **Step 5: Rebuild and verify GREEN for the skill tree**

Run:

```powershell
python work\character_packs\land_dragon_wind_poc\build_workspace.py build
python work\character_packs\land_dragon_wind_poc\test_package.py
```

Expected: the decoded DSL preserves 8 normal hits, five 80× variants, correct resistance-down rows, direct lifetimes, planned effect counts, and placement contracts.

---

### Task 3: PF presentation lifecycle regression contracts

**Files:**
- Modify: `work/character_packs/land_dragon_wind_poc/test_package.py`
- Modify after RED: `work/character_packs/land_dragon_wind_poc/build_workspace.py`

**Interfaces:**
- Consumes: official Fighter PF lifecycle templates and owned `wind_fang`／`wind_wing`／`wind_storm` effects
- Produces: special-PF decoded trees with unchanged damage/lifecycle and non-repeating visual cues

- [ ] **Step 1: Add failing PF presentation tests**

For each PF level, assert literal owned-effect counts:

```python
expected_pf_effects = {
    1: {"wind_fang": 1},
    2: {"wind_fang": 1, "wind_wing": 1},
    3: {"wind_fang": 1, "wind_wing": 1, "wind_storm": 1},
}
```

Assert every owned PF effect uses `SpecifyEffectLifetimeDirectly`, none uses `PlayOnlyFirstSequence`, the three levels still have 6／12／24 `CreateHitArea` and `CreateNormalAttack` nodes, and source/output attack totals remain equal.

The production mutation caught is returning the `ShowEffect` clone to every hit event.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python work\character_packs\land_dragon_wind_poc\test_package.py
```

Expected: PF effect-count assertions fail because `1.1.0` creates a visual for every hit.

- [ ] **Step 3: Separate PF cues from PF hit events**

In `_power_flip_tree(level)`:

- keep the copied official collision prefix and lifecycle commands;
- build one cue event per entry in `POWER_FLIP_EFFECT_CYCLES[level]`;
- set each cue's owned path, unique label, explicit positive lifetime, and planned offset/rotation;
- build each hit event with only its cloned `CreateHitArea`;
- keep per-field attack power equal to `source_total / hit_count`;
- keep the existing delayed `NotifyPowerflipEnd`.

Do not change the official `SetPowerFilpSuppress` or `NotifyPowerflipEnd` counts.

- [ ] **Step 4: Rebuild and verify GREEN for PF**

Run:

```powershell
python work\character_packs\land_dragon_wind_poc\build_workspace.py build
python work\character_packs\land_dragon_wind_poc\test_package.py
```

Expected: all PF visual, hit-count, total-damage, and lifecycle assertions pass.

---

### Task 4: Full workspace build, evidence, and production preflight

**Files:**
- Regenerate: `work/character_packs/land_dragon_wind_poc/package/**`
- Regenerate: `work/character_packs/land_dragon_wind_poc/evidence/**`
- Modify: `work/character_packs/land_dragon_wind_poc/character-dossier.md`

**Interfaces:**
- Consumes: green package builder and character-flow validator
- Produces: sealed workspace-only `1.1.1` candidate and a preflight report for user review

- [ ] **Step 1: Run complete character tests**

```powershell
python work\character_packs\land_dragon_wind_poc\build_workspace.py build
python work\character_packs\land_dragon_wind_poc\test_package.py
python work\character_packs\land_dragon_wind_poc\build_workspace.py verify-live
```

Expected: all character tests pass and live-write verification reports `writes_live=false`, `unchanged=true`.

- [ ] **Step 2: Run character-flow status and preflight**

```powershell
python mod-tools\wf_character_flow.py status --workspace work\character_packs\land_dragon_wind_poc
python mod-tools\wf_character_flow.py preflight --workspace work\character_packs\land_dragon_wind_poc --installed-package-dir work\installed_character_packages\land_dragon_wind_poc\1.0.1\package
```

Expected: production assets 37/37, manifest/hash/seal complete, no drift/conflicts/deletions, `release_ready=true`, `can_prepare=true`, `writes_live=false`.

- [ ] **Step 3: Update the dossier with verified facts only**

Record:

- candidate version and manifest SHA-256;
- exact automated test and preflight results;
- the fixed table values and decoded DSL structure;
- that no install/device validation has occurred for `1.1.1`;
- the remaining device checks for PF type, Fever gains, random skills, directions, positions, flicker, and hit counts.

- [ ] **Step 4: Stop before install or publication**

Report the candidate and preflight evidence to the user. Wait for explicit installation confirmation. Do not publish, mutate the save, or change the release graph.
