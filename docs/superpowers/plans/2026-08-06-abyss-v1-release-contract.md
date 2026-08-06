# Abyss Weapon v1 Release Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the published abyss-weapon v1 archive reproducible from an immutable historical contract while keeping the current v3.3 generator explicitly pending and completely outside the historical builder.

**Architecture:** Store the 15 published equipment and ability-soul leaves plus order-sensitive full-table digests in an immutable v1 JSON contract. The historical builder reconstructs from that contract, the pinned bridge, and official baselines without importing `wf_rogue_rewards`; a separate status JSON binds the pending v3.3 generator to a deterministic three-table semantic digest.

**Tech Stack:** Python 3.13 standard library, `unittest`, ordered dictionaries through Python `dict`, existing `wf_quest_lib` orderedmap codec, JSON release contracts, GitHub Actions.

## Global Constraints

- Work only in `D:\WF\startpoint-cn\.worktrees\pr2-abyss-release-contract` on `codex/pr2-abyss-release-contract`.
- Do not modify `mod-tools/wf_rogue_rewards.py`, gameplay values, `assets/asset-patch/manifest.json`, or `assets/asset-patch/active/*.zip`.
- Do not write to a live store, `.cdn/`, player saves, or server routes; do not invoke any publish command.
- Keep the existing archive size, SHA-256, member order, ZIP metadata, version, and manifest registration unchanged.
- Historical rebuilding must work when `wf_rogue_rewards` is unavailable and when the committed historical archive is unavailable.
- Cross-zlib rebuild acceptance is ordered semantic equality, not byte-identical rebuilt ZIP SHA.
- Use `apply_patch` for repository file edits and keep the implementation in one `fix(mod-tools):` commit after the documentation commit.

---

## File Structure

- `mod-tools/release-contracts/abyss_weapon_balance_v1.json`: immutable v1 metadata, 15 published equipment leaves, 15 published ability-soul leaves, and full-table ordered digests.
- `mod-tools/release-contracts/abyss_weapon_current.json`: mutable status marker for the current v3.3 source revision and semantic digest; never consumed by the v1 builder.
- `mod-tools/build_abyss_weapon_balance_patch.py`: historical contract loader, digest helpers, and v1 reconstruction; no current-generator import.
- `mod-tools/tests/test_abyss_weapon_release_patch.py`: RED/GREEN regression, contract corruption gates, archive-to-contract repository checks, and current pending semantic check.

---

### Task 1: Prove the historical builder is coupled to the current generator

**Files:**
- Modify: `mod-tools/tests/test_abyss_weapon_release_patch.py:1-203`
- Test: `mod-tools/tests/test_abyss_weapon_release_patch.py`

**Interfaces:**
- Consumes: existing `builder.build_payloads_from_soul_table(bridge_bytes, soul_baseline, wab_baseline_bytes)`.
- Produces: three regression tests that fail until the builder ignores current generator data and module availability while rebuilding without reading the committed output archive.

- [ ] **Step 1: Add a shared historical-input helper**

Add `subprocess` to the imports and add this method to `AbyssWeaponReleasePatchTests`:

```python
    def historical_inputs(self) -> tuple[bytes, dict[str, object], bytes]:
        soul_bytes = self.member_bytes[builder.SOUL_MEMBER]
        official_soul = builder.parse_table(
            builder.strip_custom_soul_rows(soul_bytes), builder.SOUL_LOGICAL
        )
        return (
            builder.checked_bridge(builder.BRIDGE_ARCHIVE),
            official_soul,
            self.member_bytes[builder.WAB_MEMBER],
        )
```

- [ ] **Step 2: Add the mutable-inventory regression test**

```python
    def test_historical_rebuild_ignores_current_weapon_inventory(self) -> None:
        bridge, official_soul, wab = self.historical_inputs()
        original = rewards.WEAPONS
        try:
            rewards.WEAPONS = ()
            rebuilt = builder.build_payloads_from_soul_table(
                bridge, official_soul, wab
            )
        finally:
            rewards.WEAPONS = original

        for payload, member, logical in (
            (rebuilt[0], builder.EQUIPMENT_MEMBER, builder.EQUIPMENT_LOGICAL),
            (rebuilt[1], builder.SOUL_MEMBER, builder.SOUL_LOGICAL),
        ):
            expected = builder.parse_table(self.member_bytes[member], logical)
            actual = builder.parse_table(payload, logical)
            self.assertEqual(list(expected), list(actual))
            self.assertEqual(
                builder.canonical_node_sha256(expected),
                builder.canonical_node_sha256(actual),
            )
```

- [ ] **Step 3: Add the import-isolation regression test**

Run the real historical rebuild in a fresh interpreter after making `wf_rogue_rewards` unavailable:

```python
    def test_historical_builder_rebuilds_without_current_generator_module(self) -> None:
        script = f"""
import sys
import zipfile
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'mod-tools'))
sys.modules['wf_rogue_rewards'] = None
import build_abyss_weapon_balance_patch as historical
with zipfile.ZipFile(historical.OUTPUT_ARCHIVE) as archive:
    soul_bytes = archive.read(historical.SOUL_MEMBER)
    wab_bytes = archive.read(historical.WAB_MEMBER)
official = historical.parse_table(
    historical.strip_custom_soul_rows(soul_bytes), historical.SOUL_LOGICAL
)
payloads = historical.build_payloads_from_soul_table(
    historical.checked_bridge(historical.BRIDGE_ARCHIVE), official, wab_bytes
)
assert len(payloads) == 3
"""
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
```

- [ ] **Step 4: Add the missing-archive reconstruction regression**

Load the official baseline and WAB before replacing the output path, then prove reconstruction itself does not read the committed archive:

```python
    def test_historical_rebuild_does_not_read_committed_archive(self) -> None:
        bridge, official_soul, wab = self.historical_inputs()
        original = builder.OUTPUT_ARCHIVE
        builder.OUTPUT_ARCHIVE = ROOT / "missing-historical-archive.zip"
        try:
            rebuilt = builder.build_payloads_from_soul_table(
                bridge, official_soul, wab
            )
        finally:
            builder.OUTPUT_ARCHIVE = original

        rebuilt_equipment = builder.parse_table(
            rebuilt[0], builder.EQUIPMENT_LOGICAL
        )
        archived_equipment = builder.parse_table(
            self.member_bytes[builder.EQUIPMENT_MEMBER], builder.EQUIPMENT_LOGICAL
        )
        self.assertEqual(
            builder.canonical_node_sha256(archived_equipment),
            builder.canonical_node_sha256(rebuilt_equipment),
        )
```

- [ ] **Step 5: Run RED and record the expected failures**

Run:

```powershell
python -m unittest mod-tools/tests/test_abyss_weapon_release_patch.py
```

Expected: the existing current-generator comparison fails, both reconstruction regressions fail on historical content, and the child process fails because the builder imports `wf_rogue_rewards`.

---

### Task 2: Add the immutable v1 contract and decouple reconstruction

**Files:**
- Create: `mod-tools/release-contracts/abyss_weapon_balance_v1.json`
- Modify: `mod-tools/build_abyss_weapon_balance_patch.py:1-265`
- Modify: `mod-tools/tests/test_abyss_weapon_release_patch.py:15-203`

**Interfaces:**
- Produces: `HistoricalReleaseContract`, `load_v1_contract(path: Path = RELEASE_CONTRACT_PATH)`, `key_sequence_sha256(keys: Iterable[str])`, and module constant `V1_CONTRACT`.
- Consumes later: Task 3 validates loader rejection paths; Task 4 uses `V1_CONTRACT.custom_ids` for current semantic framing.

- [ ] **Step 1: Extract the immutable rows and exact ordered digests read-only**

Run the following script only to stdout. It first verifies the committed archive SHA and then emits the complete JSON that must be pasted with `apply_patch`:

```powershell
@'
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path

root = Path.cwd()
sys.path.insert(0, str(root / "mod-tools"))
import build_abyss_weapon_balance_patch as builder

archive_bytes = builder.OUTPUT_ARCHIVE.read_bytes()
expected_archive_sha = "e9ec4451ac5b3101f060c74278fd8901b7c207c57f19e313084ff9f9639f7272"
assert hashlib.sha256(archive_bytes).hexdigest() == expected_archive_sha

def key_sequence_sha256(keys):
    digest = hashlib.sha256()
    for key in keys:
        raw = key.encode("utf-8")
        digest.update(struct.pack("<Q", len(raw)))
        digest.update(raw)
    return digest.hexdigest()

with zipfile.ZipFile(builder.OUTPUT_ARCHIVE) as archive:
    equipment = builder.parse_table(
        archive.read(builder.EQUIPMENT_MEMBER), builder.EQUIPMENT_LOGICAL
    )
    ability_soul = builder.parse_table(
        archive.read(builder.SOUL_MEMBER), builder.SOUL_LOGICAL
    )

custom_ids = [str(value) for value in range(8000101, 8000116)]
document = {
    "schema_version": 1,
    "published": {
        "id": "abyss-weapon-balance-v1",
        "status": "published",
        "depends_on": "1.4.105",
        "version": "1.4.106",
        "archive": "pinball-1.4.105-1.4.106-1-abyssbalance0718.zip",
        "archive_sha256": expected_archive_sha,
        "equipment_canonical_sha256": builder.canonical_node_sha256(equipment),
        "equipment_key_sequence_sha256": key_sequence_sha256(equipment),
        "ability_soul_canonical_sha256": builder.canonical_node_sha256(ability_soul),
        "ability_soul_key_sequence_sha256": key_sequence_sha256(ability_soul),
    },
    "custom_ids": custom_ids,
    "payload_rows": {
        "equipment": {key: equipment[key] for key in custom_ids},
        "ability_soul": {key: ability_soul[key] for key in custom_ids},
    },
}
print(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
'@ | python -
```

The four expected digest values are:

```text
equipment_canonical_sha256=2ba3e56399301192ab324044426c36bfd4653a8a0f5a594217e81512d7cefd59
equipment_key_sequence_sha256=1d4ddf8296d35e323a318c9978caa711caec05cd08ea48ca5abf5fee79ed5eb9
ability_soul_canonical_sha256=7060106f492dc980ddfbb0be4e3550f1837f08fc336db981fade2bcbd038c000
ability_soul_key_sequence_sha256=23782ad8cb1a9d7412b720dc583fc46c3c062077b0e0e311343bbd9df84bdeba
```

- [ ] **Step 2: Replace mutable logical-path dependencies with frozen constants**

In the historical builder, remove `import wf_rogue_rewards as rewards` and define:

```python
EQUIPMENT_LOGICAL = "master/item/equipment.orderedmap"
SOUL_LOGICAL = "master/ability/ability_soul.orderedmap"
WAB_LOGICAL = "master/equipment_enhancement/equipment_enhancement_ability.orderedmap"
ARCHIVE_SHA256 = "e9ec4451ac5b3101f060c74278fd8901b7c207c57f19e313084ff9f9639f7272"
RELEASE_CONTRACT_PATH = (
    MOD_TOOLS / "release-contracts" / "abyss_weapon_balance_v1.json"
)
EXPECTED_CUSTOM_IDS = tuple(str(value) for value in range(8000101, 8000116))
```

Delete unused item/status/rush logical constants because historical v1 reconstruction no longer calls `build_master_changes`.

- [ ] **Step 3: Add immutable contract and key-sequence interfaces**

Add standard-library imports `csv`, `json`, `re`, `dataclass`, `Iterable`, `Mapping`, and `MappingProxyType`. Define:

```python
@dataclass(frozen=True)
class HistoricalReleaseContract:
    custom_ids: tuple[str, ...]
    equipment_rows: Mapping[str, str]
    ability_soul_rows: Mapping[str, str]
    equipment_canonical_sha256: str
    equipment_key_sequence_sha256: str
    ability_soul_canonical_sha256: str
    ability_soul_key_sequence_sha256: str


def key_sequence_sha256(keys: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for key in keys:
        raw = key.encode("utf-8")
        digest.update(struct.pack("<Q", len(raw)))
        digest.update(raw)
    return digest.hexdigest()
```

For this first GREEN, implement `load_v1_contract()` only to parse the known-good JSON, read the named fields, convert `custom_ids` to a tuple, and return `MappingProxyType` wrappers. Bind `V1_CONTRACT = load_v1_contract()` once at import. Do not add the fail-closed schema/metadata/CSV/digest validation yet; Task 3 writes those RED cases first.

- [ ] **Step 4: Rebuild only from frozen rows**

Change `strip_custom_soul_rows()` to use `V1_CONTRACT.custom_ids`. Replace the `MasterTables`/`build_master_changes` section with:

```python
    bridge_equipment_bytes = read_bridge_member(bridge_bytes, EQUIPMENT_LOGICAL)
    equipment = parse_table(bridge_equipment_bytes, EQUIPMENT_LOGICAL)
    for custom_id in V1_CONTRACT.custom_ids:
        if custom_id not in equipment:
            raise ValueError(f"bridge equipment is missing historical id {custom_id}")
        equipment[custom_id] = V1_CONTRACT.equipment_rows[custom_id]

    ability_soul = dict(soul_baseline)
    for custom_id in V1_CONTRACT.custom_ids:
        ability_soul[custom_id] = V1_CONTRACT.ability_soul_rows[custom_id]

    if key_sequence_sha256(equipment) != V1_CONTRACT.equipment_key_sequence_sha256:
        raise RuntimeError("historical equipment key order does not match v1 contract")
    if canonical_node_sha256(equipment) != V1_CONTRACT.equipment_canonical_sha256:
        raise RuntimeError("historical equipment content does not match v1 contract")
    if key_sequence_sha256(ability_soul) != V1_CONTRACT.ability_soul_key_sequence_sha256:
        raise RuntimeError("historical ability_soul key order does not match v1 contract")
    if canonical_node_sha256(ability_soul) != V1_CONTRACT.ability_soul_canonical_sha256:
        raise RuntimeError("historical ability_soul content does not match v1 contract")

    equipment_bytes = quest.build_node(equipment)
    soul_bytes = build_official_orderedmap(ability_soul)
```

Keep the existing noncustom-equipment and stripped-soul restoration checks, replacing current generator IDs with `V1_CONTRACT.custom_ids`.

- [ ] **Step 5: Convert the old current-generator test into an archive-to-contract test**

Rename it to `test_payloads_match_frozen_v1_contract_and_official_baselines`. Remove the loop over current `rewards.WEAPONS`; instead assert:

```python
        equipment = builder.parse_table(equipment_bytes, builder.EQUIPMENT_LOGICAL)
        souls = builder.parse_table(soul_bytes, builder.SOUL_LOGICAL)
        for custom_id in builder.V1_CONTRACT.custom_ids:
            self.assertEqual(
                builder.V1_CONTRACT.equipment_rows[custom_id],
                equipment[custom_id],
            )
            self.assertEqual(
                builder.V1_CONTRACT.ability_soul_rows[custom_id],
                souls[custom_id],
            )
```

For rebuilt versus committed tables, assert `list(expected) == list(actual)`, each `key_sequence_sha256`, and each `canonical_node_sha256`; do not use plain dict equality as the only proof.

- [ ] **Step 6: Run GREEN for the historical boundary**

Run:

```powershell
python -m unittest mod-tools/tests/test_abyss_weapon_release_patch.py
```

Expected: all historical tests pass; no archive, manifest, store, or `.cdn` file changes.

---

### Task 3: Prove the v1 loader fails closed

**Files:**
- Modify: `mod-tools/tests/test_abyss_weapon_release_patch.py`
- Modify: `mod-tools/build_abyss_weapon_balance_patch.py`

**Interfaces:**
- Consumes: `load_v1_contract(path)` from Task 2.
- Produces: deterministic `ValueError` rejection for malformed schema, metadata, ordered keys, CSV leaves, and digest syntax.

- [ ] **Step 1: Add table-driven corrupted-contract tests**

Load the valid JSON, deep-copy it, and write each mutation to a `TemporaryDirectory`. Cover these exact cases and expected error fields:

```python
mutations = {
    "schema": (
        "schema_version",
        lambda doc: doc.__setitem__("schema_version", 2),
    ),
    "archive_sha": (
        "archive_sha256",
        lambda doc: doc["published"].__setitem__("archive_sha256", "0" * 64),
    ),
    "missing_equipment": (
        "payload_rows.equipment",
        lambda doc: doc["payload_rows"]["equipment"].pop("8000101"),
    ),
    "reordered_soul": (
        "payload_rows.ability_soul",
        lambda doc: doc["payload_rows"].__setitem__(
            "ability_soul",
            dict(reversed(doc["payload_rows"]["ability_soul"].items())),
        ),
    ),
    "empty_leaf": (
        "payload_rows.equipment.8000101",
        lambda doc: doc["payload_rows"]["equipment"].__setitem__(
            "8000101", ""
        ),
    ),
    "bad_digest": (
        "equipment_canonical_sha256",
        lambda doc: doc["published"].__setitem__(
            "equipment_canonical_sha256", "ABC"
        ),
    ),
}
```

For every mutation, apply the callable and assert `with self.assertRaisesRegex(ValueError, re.escape(expected_field))` around `builder.load_v1_contract(path)`.

- [ ] **Step 2: Run RED against any validation gaps**

Run the target test file. Expected: at least one mutation is accepted by the minimal loader and produces a failing assertion.

- [ ] **Step 3: Implement the smallest explicit validators**

Add helpers `_require_mapping`, `_require_exact_keys`, `_require_sha256`, and `_require_csv_leaf`. Error messages must include the rejected field name used by the table-driven assertions. Do not read the committed archive from `load_v1_contract()`.

- [ ] **Step 4: Run GREEN**

Run the target test file and confirm every corruption case fails closed while valid v1 reconstruction still passes.

---

### Task 4: Bind the pending v3.3 status to current three-table semantics

**Files:**
- Create: `mod-tools/release-contracts/abyss_weapon_current.json`
- Modify: `mod-tools/tests/test_abyss_weapon_release_patch.py`

**Interfaces:**
- Consumes: current `rewards.build_master_changes`, `builder.V1_CONTRACT.custom_ids`, and `builder.canonical_node_sha256`.
- Produces: pending status with semantic SHA-256 `fe00411013e578151c44e81d93c9d2faf81f1d9bfa59a399ed34150596d5f07d`.

- [ ] **Step 1: Add the missing-status RED test**

Define `CURRENT_STATUS = ROOT / "mod-tools" / "release-contracts" / "abyss_weapon_current.json"`. The test must first assert `CURRENT_STATUS.is_file()`, which fails before the file exists.

Then parse it and assert exact metadata:

```python
self.assertEqual(1, status["schema_version"])
self.assertEqual("abyss-weapons-v3.3", status["id"])
self.assertEqual("pending", status["status"])
self.assertEqual("mod-tools/wf_rogue_rewards.py", status["source"])
self.assertEqual(
    "3e5ae0d532ce5179f5e8254afb900e5b61c55869",
    status["source_revision"],
)
self.assertIsNone(status["artifact"])
```

- [ ] **Step 2: Compute the real current semantic node in the test**

Use the pinned bridge and official soul baseline to call `rewards.build_master_changes`. Frame the digest with this exact insertion order:

```python
semantic_node = {
    "equipment": {
        key: changes.equipment[key] for key in builder.V1_CONTRACT.custom_ids
    },
    "equipment_status": {
        key: changes.equipment_status[key]
        for key in builder.V1_CONTRACT.custom_ids
    },
    "ability_soul": {
        key: changes.ability_soul[key]
        for key in builder.V1_CONTRACT.custom_ids
    },
}
self.assertEqual(
    status["semantic_sha256"],
    builder.canonical_node_sha256(semantic_node),
)
```

- [ ] **Step 3: Run RED**

Run the target test file. Expected: failure at `CURRENT_STATUS.is_file()`.

- [ ] **Step 4: Add the exact current status file**

Create:

```json
{
  "schema_version": 1,
  "id": "abyss-weapons-v3.3",
  "status": "pending",
  "source": "mod-tools/wf_rogue_rewards.py",
  "source_revision": "3e5ae0d532ce5179f5e8254afb900e5b61c55869",
  "semantic_sha256": "fe00411013e578151c44e81d93c9d2faf81f1d9bfa59a399ed34150596d5f07d",
  "artifact": null
}
```

- [ ] **Step 5: Run GREEN**

Run the target test file and `python -m unittest mod-tools/tests/test_rogue_rewards.py`. Expected: both pass, with the latter still reporting 49 tests.

---

### Task 5: Verify scope, regressions, hygiene, and commit

**Files:**
- Verify only; no additional production files.

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: local verification evidence and one implementation commit ready to update PR #2.

- [ ] **Step 1: Verify no protected output changed**

Before the implementation commit, run `git status --short` and `git diff --name-only HEAD`. The implementation working diff may contain only:

```text
mod-tools/release-contracts/abyss_weapon_balance_v1.json
mod-tools/release-contracts/abyss_weapon_current.json
mod-tools/build_abyss_weapon_balance_patch.py
mod-tools/tests/test_abyss_weapon_release_patch.py
```

Explicitly verify no path under `assets/`, `.cdn/`, or a live store appears.

- [ ] **Step 2: Run focused verification**

```powershell
python -m unittest mod-tools/tests/test_abyss_weapon_release_patch.py
python -m unittest mod-tools/tests/test_rogue_rewards.py
python -m py_compile mod-tools/build_abyss_weapon_balance_patch.py mod-tools/tests/test_abyss_weapon_release_patch.py
```

- [ ] **Step 3: Run repository verification**

```powershell
python -m unittest discover -s mod-tools/tests -p "test_*.py"
npm run verify
npm run test:launcher
npm run test:hygiene
npm run check:hygiene
git diff --check
```

The two local long-path `test_offline_release` WinError 3 errors are baseline-only and must be reported separately if repeated. The target abyss test must not fail, and GitHub Actions must not gain a new failure.

- [ ] **Step 4: Review contract provenance and leakage**

Confirm the v1 rows were extracted only from the pinned committed archive, the status file contains no local paths or credentials, and `git diff --stat` shows no binary changes.

- [ ] **Step 5: Commit the implementation**

```powershell
git add -- mod-tools/release-contracts/abyss_weapon_balance_v1.json mod-tools/release-contracts/abyss_weapon_current.json mod-tools/build_abyss_weapon_balance_patch.py mod-tools/tests/test_abyss_weapon_release_patch.py
git diff --cached --check
git commit -m "fix(mod-tools): decouple abyss v1 release from current generator"
```

- [ ] **Step 6: Recheck the exact commit**

Run the focused tests again after commit, inspect `git show --stat --oneline HEAD`, and confirm the worktree is clean. Updating or pushing PR #2 is a separate final action after local evidence is reviewed.
