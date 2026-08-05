# Abyss Conqueror Team Survival Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one `8000113` ability source give each primary party member three non-dispellable Guts charges and three independent HP≤1% self-invincibility triggers.

**Architecture:** Keep the existing four-slot `WeaponSpec` and donor rows, changing only slot 1 target/count and slot 2 trigger-puller/target/limit. A static, producer-independent column oracle guards runtime-significant fields; a scoped store writer stages and atomically replaces only `ability_soul`, followed by a one-table CDN publish.

**Tech Stack:** Python 3, `unittest`, orderedmap builders in `wf_quest_lib`, `wf_publish.py`, decompiled ActionScript runtime evidence.

## Global Constraints

- Work in `D:\WF\startpoint-cn` on `release/modes-20260714`; preserve all pre-existing dirty and untracked WIP.
- Do not modify `web/pages/`, `src/routes/web/`, `web/public/`, `assets/`, `sync_pending.json`, `wf_rogue_build.py`, `wf_rogue_reroll.py`, weapon IDs, sorting, or APK/client code.
- The user's explicit 2026-08-05 instruction overrides the old numeric-only redline only for `8000113` slots 1 and 2.
- Do not change effect-slot count, 1% threshold, 10-second duration, non-dispellability, immunity, or +525% ability-damage slot.
- Keep `c48/c49=100000` for Guts probability and `c56/c57=100000` for each invincibility application; only Guts count becomes `300000` and invincibility trigger limit becomes `3`.
- Keep the existing target-test count at 49; extend an existing test method instead of adding a new `test_*` method.
- Do not commit this shared reverse-engineering workspace unless separately requested.
- Before any store write, prove the generated client-table diff is exactly `ability_soul[8000113]`; abort on any extra changed key or table.
- Store writes must be recoverable, staged in the same directory, atomically replaced, and followed by exact readback.
- Publish only `ability_soul`; never run `wf_rogue_rewards.py --publish` for this change.
- Device-side combat validation belongs to the user and is not implied by local green tests or successful publication.

---

### Task 1: Add an independent static oracle and prove RED

**Files:**
- Modify: `mod-tools/tests/test_rogue_rewards.py:200-225`
- Modify: `mod-tools/tests/test_rogue_rewards.py:1424-1468`

**Interfaces:**
- Consumes: `fake_templates()`, `rewards.build_soul_leaf()`, `rewards.WEAPONS`.
- Produces: `EXPECTED_CONQUEROR_SURVIVAL_COLUMNS`, a static two-row oracle that never reads `EffectSpec.overrides` or production resolver output.

- [x] **Step 1: Record the same-session pre-change baseline**

  Before editing either target file, run from `D:\WF\startpoint-cn\mod-tools`:

  ```powershell
  python -X utf8 -m unittest tests.test_rogue_rewards
  python -X utf8 -m unittest discover -s tests -p "test_rogue*.py"
  ```

  Record discovered counts and every failure/error identity. The last verified state was target `49 / OK` and aggregate `337 / 0 failures / 6 errors`; if the fresh result differs, the fresh result becomes the comparison baseline and must be explained before implementation.

- [x] **Step 2: Add the exact two-row oracle**

  Add beside `EXPECTED_5050022_OUTPUT_COLUMNS`:

  ```python
  EXPECTED_CONQUEROR_SURVIVAL_COLUMNS = (
      {
          44: "468", 45: "5", 46: "(None)",
          48: "100000", 49: "100000",
          56: "300000", 57: "300000",
          64: "1", 69: "false", 71: "1",
      },
      {
          24: "25", 25: "5", 26: "(None)",
          27: "1000", 28: "1000", 31: "3", 32: "0",
          44: "16", 45: "7", 46: "",
          56: "100000", 57: "100000",
          64: "1", 69: "false",
      },
  )
  ```

  Add a static donor-fixture map for the official non-duration fields inherited
  from `300001#5` and `300002#6` (`c56/c57`, `c64`, `c69`, and slot 1 `c71`).
  Keep `c54/c55` as the existing unique donor sentinels: the global duration
  preservation oracle must continue proving that slot 2 does not overwrite its
  donor's 10-second duration.

- [x] **Step 3: Extend the existing soul-generation test without increasing test count**

  Inside `test_each_effect_uses_its_templates_first_line_and_fixed_columns`, add the following `8000113` branch after the existing `8000112` structural assertion:

  ```python
  if spec.id == "8000113":
      actual = tuple(
          {column: row[column] for column in expected}
          for row, expected in zip(rows[:2], EXPECTED_CONQUEROR_SURVIVAL_COLUMNS)
      )
      self.assertEqual(EXPECTED_CONQUEROR_SURVIVAL_COLUMNS, actual)
  ```

  In `test_universal_effects_use_none_sentinel_for_unfiltered_party_target`, change only the first `8000113` group from `""` to `"(None)"`:

  ```python
  "8000113": ["(None)", "", "", "(None)"],
  ```

- [x] **Step 4: Run the focused test and capture RED**

  From `D:\WF\startpoint-cn\mod-tools`, run:

  ```powershell
  python -X utf8 -m unittest tests.test_rogue_rewards.TestSoulGeneration.test_each_effect_uses_its_templates_first_line_and_fixed_columns -v
  ```

  Expected: `FAIL`, with current slot 1 values such as `c45='0'` and `c56='100000'` differing from the static oracle. If it passes before implementation, stop and inspect concurrent edits.

---

### Task 2: Implement the minimal two-slot specification and reach GREEN

**Files:**
- Modify: `mod-tools/wf_rogue_rewards.py:373-377`
- Test: `mod-tools/tests/test_rogue_rewards.py`

**Interfaces:**
- Consumes: existing `_INIT`, `_trig()`, `EffectSpec`, donor rows `300001#5` and `300002#6`.
- Produces: the exact two-slot output defined by `EXPECTED_CONQUEROR_SURVIVAL_COLUMNS`.

- [x] **Step 1: Change only the two `8000113` effect declarations**

  Replace the current first two effects with:

  ```python
  EffectSpec("300001", "468", 100000, donor_line=5, target="5",
             target_groups="(None)",
             overrides=_INIT + (
                 (56, "300000"), (57, "300000"), (64, "1"),
             )),
  EffectSpec("300002", "16", "", donor_line=6, target="7",
             target_groups=None,
             overrides=_trig(
                 25, puller=5, groups="(None)", th="1000", limit="3",
             ) + ((64, "1"),)),
  ```

  Do not alter the third immunity effect or fourth +525% ability-damage effect.

- [x] **Step 2: Run focused GREEN**

  From `mod-tools/`, run the two affected existing tests:

  ```powershell
  python -X utf8 -m unittest `
    tests.test_rogue_rewards.TestSoulGeneration.test_each_effect_uses_its_templates_first_line_and_fixed_columns `
    tests.test_rogue_rewards.TestSoulGeneration.test_universal_effects_use_none_sentinel_for_unfiltered_party_target -v
  ```

  Expected: `Ran 2 tests` and `OK`.

- [x] **Step 3: Run the complete target module**

  From `mod-tools/`, run:

  ```powershell
  python -X utf8 -m unittest tests.test_rogue_rewards -v
  ```

  Expected: `Ran 49 tests` and `OK`. Any count change means the existing-test constraint was violated.

---

### Task 3: Validate description, legality, regression, and exact generated diff

**Files:**
- Read: `mod-tools/wf_rogue_rewards.py`
- Read: active CN orderedmaps resolved by `mod-tools/profiles.json` / `WF_TARGET_STORE`
- Do not write during this task.

**Interfaces:**
- Consumes: `rewards.build_master_changes()`, `wf_describe.describe_rows()`, active CN `MasterTables`.
- Produces: dry-run evidence and an exact table/key diff gate for Task 4.

- [x] **Step 1: Run the production dry-run**

  From repository root:

  ```powershell
  python -X utf8 mod-tools/wf_rogue_rewards.py
  ```

  Require exit code 0 and final `[DRY-RUN] 未写入任何文件`. In the `8000113` block require descriptions equivalent to:

  ```text
  赋予全队 状态Guts 100%×3次[不可驱散]
  HP≤1%(限3次) → 赋予触发者 状态无敌(10秒)×1次[不可驱散]
  ```

- [x] **Step 2: Run the full rogue regression against a fresh baseline**

  From repository root:

  ```powershell
  python -X utf8 -m unittest discover -s mod-tools/tests -p "test_rogue*.py"
  ```

  Expected from the last verified shared-tree baseline: `Ran 337 tests`, no failures, and six pre-existing `test_rogue_validate.py` fixture errors. Because the tree is shared and dirty, compare with a same-session pre-change result; accept only no new failures/errors and unchanged test discovery count.

- [x] **Step 3: Prove the generated client-table diff is exactly one key**

  From repository root, run this read-only check:

  ```powershell
  @'
  import sys
  from pathlib import Path

  root = Path.cwd()
  sys.path.insert(0, str(root / "mod-tools"))
  import wf_mod_tool as core
  import wf_quest_lib as q
  import wf_rogue_rewards as rewards

  rewards.require_cn_profile()
  tables = rewards.MasterTables(
      items=q.load_table(rewards.ITEM_T),
      equipment=q.load_table(rewards.EQUIP_T),
      equipment_status=q.load_table(rewards.EQUIP_STATUS_T),
      ability_soul=q.load_table(rewards.SOUL_T),
      rush_event=q.load_table(rewards.RUSH_EVENT_T),
  )
  changes = rewards.build_master_changes(tables)

  def changed_keys(before, after):
      return sorted(
          key for key in set(before) | set(after)
          if before.get(key) != after.get(key)
      )

  actual = {
      "items": changed_keys(tables.items, changes.items),
      "equipment": changed_keys(tables.equipment, changes.equipment),
      "equipment_status": changed_keys(
          tables.equipment_status, changes.equipment_status
      ),
      "ability_soul": changed_keys(tables.ability_soul, changes.ability_soul),
      "rush_event": changed_keys(tables.rush_event, changes.rush_event),
  }
  expected = {
      "items": [],
      "equipment": [],
      "equipment_status": [],
      "ability_soul": ["8000113"],
      "rush_event": [],
  }
  assert actual == expected, (actual, expected)

  old_rows = core.read_csv_lines(
      rewards._leaf_text(tables.ability_soul["8000113"])
  )
  new_rows = core.read_csv_lines(
      rewards._leaf_text(changes.ability_soul["8000113"])
  )
  assert len(old_rows) == len(new_rows) == 4
  assert [i for i, pair in enumerate(zip(old_rows, new_rows)) if pair[0] != pair[1]] == [0, 1]
  assert old_rows[2:] == new_rows[2:]
  print(actual)
  print("8000113 changed rows: [0, 1]")
  '@ | python -X utf8 -
  ```

  Require exactly:

  ```python
  {
      "items": [],
      "equipment": [],
      "equipment_status": [],
      "ability_soul": ["8000113"],
      "rush_event": [],
  }
  ```

  Then parse old and generated `ability_soul[8000113]`, require four rows total, require only row indexes `0` and `1` to differ, and require rows `2` and `3` byte-for-byte equal. Abort instead of widening scope if any other key/table/row differs.

- [x] **Step 4: Review scoped source diff**

  Run:

  ```powershell
  git diff --check -- mod-tools/wf_rogue_rewards.py mod-tools/tests/test_rogue_rewards.py
  git diff -- mod-tools/wf_rogue_rewards.py mod-tools/tests/test_rogue_rewards.py
  ```

  Confirm only the static oracle, one expected group, and the two `8000113` specs are attributable to this task. Preserve all earlier WIP already present in these files.

---

### Task 4: Atomically write and publish only `ability_soul`

**Files:**
- Modify at runtime: active CN store `master/ability/ability_soul.orderedmap`
- Create at runtime: timestamped adjacent backup from the scoped writer
- Publish at runtime: one CDN diff edge containing only `master/ability/ability_soul.orderedmap`

**Interfaces:**
- Consumes: Task 3's exact diff result and generated `changes.ability_soul`.
- Produces: atomically replaced active table, exact readback evidence, and a one-table client update; does not modify APK.

- [x] **Step 1: Recheck profile and snapshot pending state**

  Require `rewards.require_cn_profile()` to prove active and explicit CN stores resolve to the same absolute directory. Read `mod-tools/work/sync_pending.json` without modifying it and record its hash/content:

  ```powershell
  Get-FileHash -Algorithm SHA256 -LiteralPath 'mod-tools\work\sync_pending.json'
  Get-Content -LiteralPath 'mod-tools\work\sync_pending.json' -Encoding utf8 -Raw
  ```

  If the pending file does not exist, record that fact and require it still not to exist after explicit-table publication.

- [x] **Step 2: Stage, verify, back up, and atomically replace the table**

  From repository root, run this one-process scoped writer. It repeats the Task 3 diff gate, stages in the target directory, validates the full staged tree, makes one adjacent backup, atomically replaces, and reads back exact runtime columns:

  ```powershell
  @'
  import hashlib
  import os
  import shutil
  import sys
  import tempfile
  import time
  from pathlib import Path

  root = Path.cwd()
  sys.path.insert(0, str(root / "mod-tools"))
  import wf_mod_tool as core
  import wf_quest_lib as q
  import wf_rogue_rewards as rewards

  profile = rewards.require_cn_profile()
  active_store = profile.store.resolve()
  logicals = {
      "items": rewards.ITEM_T,
      "equipment": rewards.EQUIP_T,
      "equipment_status": rewards.EQUIP_STATUS_T,
      "ability_soul": rewards.SOUL_T,
      "rush_event": rewards.RUSH_EVENT_T,
  }
  paths = {name: q.store_path(logical).resolve() for name, logical in logicals.items()}
  for name, path in paths.items():
      assert path.is_relative_to(active_store), (name, path, active_store)

  before_hashes = {
      name: hashlib.sha256(path.read_bytes()).hexdigest()
      for name, path in paths.items()
  }
  tables = rewards.MasterTables(
      items=q.load_table(rewards.ITEM_T),
      equipment=q.load_table(rewards.EQUIP_T),
      equipment_status=q.load_table(rewards.EQUIP_STATUS_T),
      ability_soul=q.load_table(rewards.SOUL_T),
      rush_event=q.load_table(rewards.RUSH_EVENT_T),
  )
  changes = rewards.build_master_changes(tables)

  def changed_keys(before, after):
      return sorted(
          key for key in set(before) | set(after)
          if before.get(key) != after.get(key)
      )

  diff = {
      "items": changed_keys(tables.items, changes.items),
      "equipment": changed_keys(tables.equipment, changes.equipment),
      "equipment_status": changed_keys(
          tables.equipment_status, changes.equipment_status
      ),
      "ability_soul": changed_keys(tables.ability_soul, changes.ability_soul),
      "rush_event": changed_keys(tables.rush_event, changes.rush_event),
  }
  assert diff == {
      "items": [],
      "equipment": [],
      "equipment_status": [],
      "ability_soul": ["8000113"],
      "rush_event": [],
  }, diff

  old_rows = core.read_csv_lines(
      rewards._leaf_text(tables.ability_soul["8000113"])
  )
  new_rows = core.read_csv_lines(
      rewards._leaf_text(changes.ability_soul["8000113"])
  )
  assert len(old_rows) == len(new_rows) == 4
  assert [i for i, pair in enumerate(zip(old_rows, new_rows)) if pair[0] != pair[1]] == [0, 1]
  assert old_rows[2:] == new_rows[2:]

  expected_columns = (
      {
          44: "468", 45: "5", 46: "(None)",
          48: "100000", 49: "100000",
          56: "300000", 57: "300000",
          64: "1", 69: "false", 71: "1",
      },
      {
          24: "25", 25: "5", 26: "(None)",
          27: "1000", 28: "1000", 31: "3", 32: "0",
          44: "16", 45: "7", 46: "",
          54: "60000000", 55: "60000000",
          56: "100000", 57: "100000",
          64: "1", 69: "false",
      },
  )
  for row, expected in zip(new_rows[:2], expected_columns):
      assert {column: row[column] for column in expected} == expected

  target = paths["ability_soul"]
  fd, stage_name = tempfile.mkstemp(
      prefix=target.name + ".stage-", dir=target.parent
  )
  os.close(fd)
  stage = Path(stage_name).resolve()
  stage.unlink()
  assert stage.parent == target.parent
  backup = target.with_name(
      target.name + ".bak-conqueror-" + time.strftime("%Y%m%d-%H%M%S")
  )
  assert not backup.exists()

  try:
      q.save_table(
          rewards.SOUL_T,
          changes.ability_soul,
          path=stage,
          backup=False,
      )
      assert q.load_table(rewards.SOUL_T, path=stage) == changes.ability_soul
      shutil.copy2(target, backup)
      os.replace(stage, target)
      readback = q.load_table(rewards.SOUL_T)
      assert readback == changes.ability_soul
      readback_rows = core.read_csv_lines(
          rewards._leaf_text(readback["8000113"])
      )
      for row, expected in zip(readback_rows[:2], expected_columns):
          assert {column: row[column] for column in expected} == expected

      after_hashes = {
          name: hashlib.sha256(path.read_bytes()).hexdigest()
          for name, path in paths.items()
      }
      assert all(
          before_hashes[name] == after_hashes[name]
          for name in paths if name != "ability_soul"
      )
      assert before_hashes["ability_soul"] != after_hashes["ability_soul"]
      assert set(tables.ability_soul) == set(readback)
      print(f"backup={backup}")
      print(f"target={target}")
      print("readback=OK; changed key=8000113; changed rows=[0, 1]")
  finally:
      if stage.exists() and stage.parent == target.parent:
          stage.unlink()
  '@ | python -X utf8 -
  ```

  Preserve the printed adjacent backup after success. If an assertion fails after replacement, stop publishing and restore only from that exact printed backup after diagnosing the mismatch.

- [x] **Step 3: Verify post-write scope and pending preservation**

  Reload all five client tables. Require only active `ability_soul[8000113]` differs from the saved pre-write snapshot and require the table key set to be identical. Re-read `sync_pending.json` and require its hash/content unchanged.

- [x] **Step 4: Preview and publish the one-table edge**

  Preview the actual post-write payload first:

  ```powershell
  python -X utf8 mod-tools/wf_publish.py --tables ability_soul --list
  ```

  Require one prepared table, no key-deletion blocker, and no request for `--allow-key-deletion`. Then run:

  ```powershell
  python -X utf8 mod-tools/wf_publish.py --tables ability_soul
  ```

  Require exit code 0, exactly one non-placeholder payload table, successful key-deletion guard, an `[OK] 已发布` edge, and no `--allow-key-deletion`. Record `from_ver -> to_ver`, archive path, size, and dev-catalog status. Because `--tables` is explicit, verify `sync_pending.json` remains unchanged.

- [x] **Step 5: Final readback and handoff**

  Re-run the exact active-row oracle, target module tests, `git diff --check`, and a read-only CDN chain/catalog check available in the current workspace. Report clearly:

  - source/test files changed;
  - exact store backup path and recovery method;
  - published version edge and archive;
  - no APK rebuild required or produced;
  - local verification is complete but runtime behavior remains yellow until the user confirms on a real device;
  - device check should verify three main units each show/consume three Guts charges, each unit's low-HP counter is independent, invincibility lasts 10 seconds, and remaining below 1% does not auto-refresh.
  - when both weapon and same-key soul sources are present, duplicate handlers should consume synchronously rather than extending the result to 6/9 sequential cycles.

## Execution Result

- Completed on 2026-08-05 in the existing dirty `release/modes-20260714` checkout; no unrelated WIP was reverted, staged, or committed.
- TDD RED caught the old self/one-charge structure. Focused GREEN was `2/2`; the target module remained `49/49 OK`.
- The same-session full rogue result was unchanged before and after: `337 / 1 failure / 6 errors`. The failure is the unrelated tower WIP's `领域保底完成 22/22` assertion; all six errors are existing `test_rogue_validate` class fixtures.
- Generated client-table diff was exactly `ability_soul[8000113]`, rows 0 and 1 only. The active store was atomically replaced after a verified same-directory stage and adjacent backup.
- Published only `ability_soul` on `1.4.306 -> 1.4.307`; key gate stayed `451 -> 451`, common ZIP contains only the hashed ability-soul table, and quality/platform ZIPs contain only `.empty`.
- Post-publish readback, archive CRC/scope, pending preservation, and dev-catalog edge hashes passed. Full dev audit still reports 771 historical repository issues; none names the new edge.
- No APK was built or changed. Real-device combat behavior remains the user's acceptance step.
