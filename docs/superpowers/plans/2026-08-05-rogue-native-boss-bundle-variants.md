# Rogue Native Boss Bundle Variants Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace string-only boss selection with active-layer, BossKind-aware native bundles; select family → variant → bundle without multiplicity weighting; make mix/HP reorder/final cloning share compatibility and refs+HP+c36 revalidation; and report truthful post-gate coverage.

**Architecture:** Add a read-only `wf_rogue_bundle.py` domain layer for immutable bundle metadata, terrain/action analysis, deterministic grouping, selection, portability, and validation results. Keep table mutation, HP plans, special parent cloning, quest assembly, writes, and publication in `wf_rogue_build.py`. Native eligibility uses active/kind/level/ref/HP/special gates; incomplete action closure marks a bundle `native_only` and blocks only transplantation. All mutation paths produce a `RealizedBundle` and pass one revalidator.

**Tech Stack:** Python 3, `dataclasses`, `hashlib`, `unittest`, raw-deflate AMF3 via `wf_dsl`, existing orderedmap helpers in `wf_quest_lib`.

## Global Constraints

- Work on `release/modes-20260714`; preserve all existing dirty WIP and stage only explicit files if a later instruction authorizes staging.
- Do not write store data, publish, modify `assets/`, touch `sync_pending.json`, call a device, or run `--write` / `--publish` while implementing and testing this plan.
- Do not commit this local reverse-engineering workspace unless separately requested. Each task still records its proposed small commit command; execute it only after that authorization.
- Keep discovery fixed at exactly `337 tests / failures=7 / errors=30`. Rewrite or extend existing methods with `subTest`; do not add a net-new `test_*` method.
- Native reuse does not require proven action closure. `ACTION_CLOSURE_UNAUDITED` is a `native_only_reason`, not a native rejection; it disables `--mix` portability and forces native fallback.
- A bundle becomes natively ineligible only through active-layer, `(BossKind, code)`, level, reference, HP, explicit special/C8016, or final c36 gates.
- Random transplant incompatibility falls back to the selected boss's native bundle with a structured log. Explicit boss + terrain pin incompatibility fails loudly without redraw or silently consuming a pin.
- Run refs + HP + c36 revalidation after selection, mix realization, HP reorder, and final clone.
- After every task, append commands, RED/GREEN output, current post-gate counts, uncertainties, and forbidden-path audit to `mod-tools/work/codex_out/REPORT-native-boss-bundle-variants.md`.

---

### Task 1: Immutable bundle model, active layers, and exact BossKind resolution

**Files:**
- Create: `mod-tools/wf_rogue_bundle.py`
- Modify: `mod-tools/wf_rogue_build.py`
- Modify: `mod-tools/tests/test_rogue_chain_gate.py`
- Create: `mod-tools/work/codex_out/REPORT-native-boss-bundle-variants.md`

**Interfaces:**
- Produces: `BossRef`, `ActiveBossSlot`, `TerrainLayerCaps`, `NativeBossBundle`, `RealizedBundle` frozen dataclasses.
- Produces: `load_terrain_layer_caps(field_id, field_data, zone, terrain_loader) -> tuple[TerrainLayerCaps, ...]`.
- Produces: `active_boss_slots(field_id, field_data, zone, terrain_loader) -> tuple[ActiveBossSlot, ...]`.
- Produces: `validate_boss_ref(ref, enemy_level, tables) -> GateResult`.
- Preserves: `_zone_pick(field)` as a temporary adapter derived only from active single refs.

- [ ] **Step 1: Capture the untouched baseline and exact discovery count**

  From `mod-tools/` run:

  ```powershell
  python -X utf8 -m unittest discover -s tests -p "test_rogue*.py"
  ```

  Record `Ran 337 tests` and `FAILED (failures=7, errors=30)` in the report. Also record `git status --short` without altering unrelated paths.

- [ ] **Step 2: Rewrite existing active-slot tests and run RED**

  Extend these existing methods without adding a test method:

  - `StandardBossHpCase.test_zone_pick_uses_single_battle_side_of_each_boss_slot`
  - `ZoneBossSlotsCase.test_single_multi_variants_are_one_entity`
  - `SpecialBossTableCase.test_special_table_boss_not_dangling`

  Add table-driven assertions equivalent to:

  ```python
  with self.subTest("inactive zone layer is ignored"):
      slots = rbb.active_boss_slots(
          "f", {"f": "f,terrain/path,z"},
          {"z": {"0": wave_kind(1, "active"),
                 "1": wave_kind(0, "inactive")}},
          terrain_loader=lambda _logical: terrain_tree("0"))
      self.assertEqual([(s.single.kind, s.single.code) for s in slots],
                       [(1, "active")])

  with self.subTest("wrong constructor table fails"):
      result = rbb.validate_boss_ref(
          rbb.BossRef(0, "general_only"), 100,
          synthetic_tables(general={"general_only": {"100": "row"}}))
      self.assertEqual(result.reason, "KIND_CODE_MISMATCH")
  ```

  Run:

  ```powershell
  python -X utf8 -m unittest discover -s tests -p "test_rogue_chain_gate.py" -k "zone_pick_uses_single_battle_side or single_multi_variants or special_table_boss_not_dangling"
  ```

  Expected RED: missing `wf_rogue_bundle`, active-layer API, or wrong-kind rejection.

- [ ] **Step 3: Implement terrain parsing and active-layer intersection**

  In `wf_rogue_bundle.py`, decode `field_data.c1 + ".amf3.deflate"` with raw-deflate and parse via `wf_dsl.parse_dsl`. Every `objectgroup.name` must be a unique non-negative integer and must have a same-key zone row, because the client TerrainParser iterates every terrain objectgroup and dereferences that key; an extra terrain layer therefore fails closed. Extra zone rows are inactive and ignored. Preserve duplicate `CUSTOM_POSITION` names as `(name, count)`. Return `TERRAIN_PARSE` / `NO_ACTIVE_LAYER` on failure; never scan all zone rows as fallback.

  Parse c22 and the complete slot pairs:

  ```python
  SLOT_COLUMNS = ((23, 24, 25, 26),
                  (27, 28, 29, 30),
                  (31, 32, 33, 34))
  ```

  The single event view uses c23/24, c27/28, c31/32, while the dataclass retains both sides.

- [ ] **Step 4: Implement the BossKind source map and level adapter**

  Encode audited kinds 0–13 exactly, but reject active kind 5 as `SPECIAL_TABLE_UNAUDITED` because `ZoneSource.as:387-389` throws for that constructor path. Kind 8 validates against its proven general source path. Kinds 14/15 reject because they take numeric constructor values, not code strings. Kinds 0/1/8 require injected level and funnel callbacks; missing callbacks fail closed. The builder's single table-bundle factory injects `boss_funnel_ok()` and a resolver that returns the selected level through `boss_level_ok()`/`select_surjective_level()`; do not duplicate their floor/ceil rules.

- [ ] **Step 5: Make legacy readers derive from the new source**

  Change `_zone_pick()` and `zone_boss_slots()` adapters to call `active_boss_slots()`. Return bare strings only at legacy boundaries; attach the originating `NativeBossBundle` to quest/tower entries for subsequent tasks.

- [ ] **Step 6: Run focused GREEN, fixed discovery, and report**

  Run the focused command from Step 2, then full `test_rogue*.py`. Require exact discovery `337`; classify the known 7/30 failures separately from touched-test regressions. Append active-layer samples, `treasure_cave_area` proof, wrong-kind proof, and changed interfaces to the report.

- [ ] **Step 7: Record the proposed small commit**

  Proposed commit, only if separately authorized:

  ```powershell
  git add -- mod-tools/wf_rogue_bundle.py mod-tools/wf_rogue_build.py mod-tools/tests/test_rogue_chain_gate.py mod-tools/work/codex_out/REPORT-native-boss-bundle-variants.md
  git commit -m "refactor(rogue): model active native boss bundles"
  ```

---

### Task 2: Post-gate catalog and unweighted family → variant → bundle selection

**Files:**
- Modify: `mod-tools/wf_rogue_bundle.py`
- Modify: `mod-tools/wf_rogue_build.py`
- Modify: `mod-tools/tests/test_rogue_chain_gate.py`
- Modify: `mod-tools/work/codex_out/REPORT-native-boss-bundle-variants.md`

**Interfaces:**
- Produces: `BundleRejection`, `BundleCatalog`, `BundleSelection`.
- Produces: `build_native_bundle_catalog(...) -> BundleCatalog`.
- Produces: `choose_family_variant_bundle(catalog, rng, policy) -> BundleSelection`.
- Produces: deterministic `family_id` / `variant_id` from canonical JSON + SHA-256.
- Produces: `audit_bundle_coverage(catalog) -> dict`.

- [x] **Step 1: Rewrite existing grouping tests and run RED**

  Extend:

  - `CollapseGradesCase.test_keeps_highest_grade_only`
  - `BossSeriesCase.test_orochi_heads_untouched`
  - `SpecialBossTableCase.test_special_table_boss_not_dangling`

  Use a fake RNG that records each `randrange(n)` and assert the first draw sees two families even when family A owns nine bundles and family B owns one:

  ```python
  selection = rbb.choose_family_variant_bundle(catalog, rng, policy)
  self.assertEqual(rng.ranges[0], 2)
  self.assertEqual(rng.ranges[1], len(catalog.variants[selection.family_id]))
  self.assertNotIn("#", selection.family_id)
  self.assertEqual(selection.family_id, selection_again.family_id)
  ```

  Also assert one Orochi family has exactly `single`, `multi`, `multi_plus` variants and no head alias tickets.

  Run the three classes with `-k "keeps_highest_grade_only or orochi_heads_untouched or special_table_boss_not_dangling"`; expect RED on flattened selection and absent reason records.

- [x] **Step 2: Build catalog from all active official fields**

  Scan official `field_data` entries and attach floor/BGM/quest metadata afterward. Do not use `cb.build_pool()`'s legacy `bosses` list as a source of truth. Native eligibility gates are exactly: active layer, kind/code, level, refs, HP, explicit special policy, and C8016.

- [x] **Step 3: Implement stable family and variant grouping**

  Use the NFC/trimmed complete localized display name from `wf_boss.boss_names()` as the family identity; only missing names fall back to exact `(BossKind, code)`. Model and selected-level action metadata belong to the variant identity, never the family identity, or one visible boss is split back into multiple family tickets. Variant identity is a sorted, multiplicity-preserving mechanism multiset of `(kind, code, model, selected-level roots)`; exclude layer/slot/c22/field/zone/terrain because those are bundle placement. Serialize canonical payloads with sorted keys and full SHA-256. Apply featured weights, history and series quotas at family level. Collapse duplicate grades only inside one variant and only for proved numeric-grade schemas or advent quest-metadata groups with identical terrain and active zone shape; unknown suffixes never collapse.

- [x] **Step 4: Encode explicit exclusions from evidence**

  Assert and report:

  ```python
  MULTI_ONLY = {
      "alter_sheep_materia_multi", "alter_sheep_materia_multi_80",
      "devil_commander_evil_envy_80", "discarded_dragon_wind",
      "mechanic_dragon_eater_multi", "mechanic_dragon_eater_multi_80",
  }
  ```

  Derive `NO_SINGLE_FIELD` from absence in active single refs, not the suffix. Keep `arch_evil* → C8016`; keep `orochi_ex → SPECIAL_PHASE_HP_UNSCALABLE` or earlier `SPECIAL_TABLE_UNAUDITED`.

- [x] **Step 5: Separate native eligibility from portability**

  Store action-analysis failure on otherwise valid entries as:

  ```python
  native_eligible = True
  portable = False
  native_only_reason = "ACTION_CLOSURE_UNAUDITED"
  ```

  Do not place these entries in catalog rejections and do count them in native post-gate coverage. Only `--mix` donor/target searches consult `portable`.

- [x] **Step 6: Run focused GREEN, full discovery, and report real counts**

  Record scanned, eligible and rejected code/family/variant/bundle counts, rejection reasons, and native-only reasons. Label the audit snapshot `114/60` as pre-gate theory only. Run full discovery and require 337.

- [ ] **Step 7: Record the proposed small commit**

  Proposed commit, only if authorized: `feat(rogue): select boss families and variants without field weighting`.

---

### Task 3: Action closure and per-active-layer transplant compatibility

**Files:**
- Modify: `mod-tools/wf_rogue_bundle.py`
- Modify: `mod-tools/wf_rogue_build.py`
- Modify: `mod-tools/tests/test_rogue_chain_gate.py`
- Modify: `mod-tools/work/codex_out/REPORT-native-boss-bundle-variants.md`

**Interfaces:**
- Produces: `BossTerrainRequirements`.
- Produces: `boss_terrain_requirements(bundle, enemy_level, loaders) -> RequirementResult`.
- Produces: `terrain_compatibility(source, target, requirements) -> CompatibilityResult`.
- Consumes: c41/c42 roots, active c49/c50 state paths, c109 pre-action unconditionally
  (c110 is rerun behavior only), c111–c160, nested action references, and standard
  `.esdl.amf3.deflate` resources.

- [x] **Step 1: Rewrite existing mix/slot tests and run RED**

  Extend `SwapZoneBossesCase.test_single_slot_mix_reports_only_the_realized_donor_entity`, `SwapZoneBossesCase.test_boss_slots_swapped_zakos_kept`, and `ZoneBossSlotsCase.test_counts_entities_not_columns` with synthetic cases for:

  - equal slot total but different per-layer shapes;
  - missing `CUSTOM_POSITION`;
  - c22-derived BossGroup topology mismatch (there is no terrain `BOSS_GROUP` object);
  - wrong FUNNEL group;
  - count mismatch using `min(max_command_count, anchor_count)`;
  - unknown/ambiguous closure producing native-only, not native rejection.

  Run those method filters and expect RED on missing compatibility APIs.

- [x] **Step 2: Traverse the finite proved action closure and fail closed elsewhere**

  Parse selected-level roots, recursively follow known action references, and extract
  `SpawnFunnel`, `SpawnAlterEgo`, `CUSTOM_POSITION`, and reference requirements. The known
  proved edge set includes `CreateBombMultiball` param5 × literal param0,
  `CreateTornado` param6 × `floor(param4/param5)`, `CreateTargetAttack` param4 ×1,
  `SpawnFunnel`, and `SpawnAlterEgo`. Client review proved `CreateSummonsMultiball`
  param8 is an event ID while the real child comes from `MultiballTable`; v1 therefore
  marks that command unaudited rather than following param8.
  Sum sequential blocks/sibling events, take the maximum of mutually exclusive conditions,
  multiply literal `Repeat`, and count `Wait` once. If a finite maximum cannot be proved,
  return `ACTION_CLOSURE_UNAUDITED`; this is native-only, never a native rejection.

- [x] **Step 3: Compare every active layer conservatively**

  Require slot-shape equality, c22 compatibility, named custom positions, and per-group
  FUNNEL count equivalence. BossGroup is derived from zone c22 plus active slots: c22=0 means
  all active boss slots share one group, c22=1 means one group per slot. Never require a
  synthetic terrain `BOSS_GROUP` object; the official terrain corpus has none.

  ```python
  min(req.max_commands, target.count) == \
      min(req.max_commands, source.count)
  ```

  Keep existing `transplant_safe` as an additional v1 portability gate. Native realization ignores portability but still passes refs/level/HP/special gates.

- [x] **Step 4: Run focused GREEN, fixed discovery, and append evidence**

  Report each synthetic incompatibility's reason, native-only behavior, and at least one real safe transplant. Run the full suite and require discovery 337.

- [ ] **Step 5: Record the proposed small commit**

  Proposed commit, only if authorized: `feat(rogue): validate boss terrain action compatibility`.

---

### Task 4: Orochi parent bundles, parent + eight-head HP, and clone channel

**Files:**
- Modify: `mod-tools/wf_rogue_bundle.py`
- Modify: `mod-tools/wf_rogue_build.py`
- Modify: `mod-tools/wf_gui.py`
- Modify: `mod-tools/tests/test_rogue_chain_gate.py`
- Modify: `mod-tools/work/codex_out/REPORT-native-boss-bundle-variants.md`

**Interfaces:**
- Produces: `expand_bundle_hp_members(bundle, enemy_level, tables) -> HpExpansionResult`, where
  `HpExpansionResult = (ok, members, total_hp, selected_parent_level, reason, detail)` and
  `total_hp` is raw HP before K/c86.
- Produces: `clone_orochi_parent_bundle(bundle, round_no, scale, tables) -> OrochiCloneResult`.
- Extends catalog with optional `bundle_hp_gate(bundle, level)` for complete special bundles;
  keeps the existing `hp_gate(slots, level)` contract for kind 0/1/8.
- Produces: `SPECIAL_HP_CHANNEL_UNSUPPORTED` when complete nine-entity cloning cannot be proved.
- May write later: `master/battle/boss/orochi.orderedmap` through the existing staged `written` list only.

- [x] **Step 1: Rewrite existing Orochi and HP tests and run RED**

  Extend:

  - `BossSeriesCase.test_orochi_heads_untouched`
  - `StandardBossHpCase.test_floor_native_hp_keeps_two_real_instances_with_the_same_code`
  - `BossLevelHpScalingCase.test_hit_hp_clone_changes_only_c2_and_preserves_the_source`

  Pin the three parent/field mappings and these lv100 totals:

  ```python
  expected = {
      "single": 60_780.72,
      "multi": 164_107.944,
      "multi_plus": 321_719.94855,
  }
  self.assertEqual(len(expanded.members), 9)
  self.assertAlmostEqual(expanded.total_hp, expected[variant], places=5)
  ```

  Add a subcase where one head is Fix/malformed and assert `SPECIAL_HP_CHANNEL_UNSUPPORTED`, not parent-only scaling. Run RED.

  Also pin the six official active fields (single 3 / multi 2 / multi_plus 1), first-`>=`
  level behavior for 79/80/90/99/100 versus rejecting 101, duplicate-head instance
  accumulation, and zero partial mutation when the final head fails.

  Separately assert `discovered fields == 6` and post-grade selector bundles `== 5`; the two
  multi fields are one variant/terrain grade chain and must not be reported as six tickets.
  Assert all three parents become native eligible but remain
  `portable=False/native_only_reason=ACTION_CLOSURE_UNAUDITED`; `orochi_ex` remains
  `SPECIAL_PHASE_HP_UNSCALABLE`.

- [x] **Step 2: Implement parent discovery and HP expansion**

  Read parent c24 head ids from the first `orochi` level row `>= enemy_level`. Preserve one
  parent instance plus eight head instances in source order; never de-duplicate by code. Treat
  the three parents as one family with three variants. Keep `orochi_ex` on its separate
  phase-HP rejection and do not generalize this level rule to other historical special adapters.
  Route only complete kind 3 bundles through `bundle_hp_gate`; do not change Task 2's ordinary
  slot gate or invent portability for kind 3.

- [x] **Step 3: Implement all-or-nothing per-round cloning**

  Clone the kind=3 parent special row and boss_level leaf. Clone all eight general heads plus
  `general_boss_variable`, `boss_level`, and `general_enemy_watch` self data; rewrite parent c24
  to ordered per-round ids. Sanitize stale clone prefixes first, then build and validate all rows
  in an off-table overlay; only after overlay readback succeeds may additions be committed to the
  in-memory tables. Apply one Hit-HP c2
  scale to all nine members and preserve relative HP. Raw HP is multiplied by K and c86 exactly
  once; never feed an already-K-scaled target back into c2. Keep zone kind 3 and purge stale
  `mod_rogue_orochi*` rows from every cloned table.

  Reject target-key conflicts, incomplete c24, missing/short/Fix/non-finite Hit leaves, missing
  head gb/gv, and degraded/hard code-reference scans before commit. A failed candidate leaves all
  five sanitized input tables unchanged. Do not apply the ordinary general “gv only 100” rule to
  reachable multi_plus heads; prove and clone their parent-selected level instead.

- [x] **Step 4: Add write/publication coverage without writing**

  Make `orochi.orderedmap` enter `written` whenever `orochi_dirty = produced or purged`; a purge-only
  build still changed the table. Add the same logical to `wf_gui.py::ROGUE_BATTLE_LOGICALS`; make
  GUI publication text derive table count from the actual list. Split save conditions so an
  Orochi-only build writes gb/bl/gv/optional ew dependencies without rewriting general_zako or
  zako_level. Unit tests remain in-memory/dry-run.

- [x] **Step 5: Re-expand and read back final HP**

  From mutated in-memory tables, expand the final parent + heads and compare total HP with the plan using `math.isclose(rel_tol=1e-9, abs_tol=1.0)`. Any missing dependency, code reference, level row, or non-Hit leaf rejects the variant honestly.
  Extend `check_field_chain()` / `validate_built_rows()` with injected actual special tables and
  exact `(BossKind, code)` validation. Prove an in-memory-only clone passes at lv79 and fails at
  lv101 even when global `_SPECIAL_LV` lacks that code; never use the enemies union as a bypass.

- [x] **Step 6: Run focused GREEN, fixed discovery, and report**

  Record the three parent/head/total values, clone ids, table coverage, six discovered fields versus
  five post-grade selector bundles, and whether each variant is eligible. Full discovery remains 337.

- [ ] **Step 7: Record the proposed small commit**

  Proposed commit, only if authorized: `feat(rogue): realize complete orochi parent bundles`.

---

### Task 5: Unified realization, native fallback, and hard pin semantics

**Files:**
- Modify: `mod-tools/wf_rogue_bundle.py`
- Modify: `mod-tools/wf_rogue_build.py`
- Modify: `mod-tools/tests/test_rogue_chain_gate.py`
- Modify: `mod-tools/work/codex_out/REPORT-native-boss-bundle-variants.md`

**Interfaces:**
- Produces: `realize_bundle(source, target, *, round_no, enemy_level, pinned_boss, pinned_terrain) -> RealizationResult`.
- Produces frozen `NativeFallbackRecord`, `RealizationPlan`, and `RealizationResult`; the
  realized value retains source/attempted-target/actual-terrain bundles, full kind+code slots,
  selected levels, typed clone map, and condition carrier.
- Replaces internal direct mutation by `swap_zone_bosses()` in `mix_pick()`.
- Produces structured `NATIVE_FALLBACK` records.

- [ ] **Step 1: Rewrite existing swap and CLI tests and run RED**

  Extend:

  - `SwapZoneBossesCase.test_boss_slots_swapped_zakos_kept`
  - `SwapZoneBossesCase.test_single_slot_mix_reports_only_the_realized_donor_entity`
  - `TaskCDryRunCase.test_flat_hell_mix_build_has_at_least_one_real_safe_transplant`

  Assert donor single/multi kind+code pairs are copied together, zakos remain unchanged, a random incompatibility yields the source native field plus a structured reason, and dual pin incompatibility returns nonzero with both field and boss named.

- [ ] **Step 2: Implement immutable realization plans before mutation**

  Build a complete kind+code slot rewrite plan, validate it, then clone field/zone in a local
  overlay. Re-read actual active slots before commit. Do not partially modify zone or consume
  pools/quotas/pins before compatibility and readback pass. Preserve source bundle metadata and
  return actual slots read from the new field.

- [ ] **Step 3: Implement fallback/pin decision table exactly**

  Random/random → source native fallback; boss-only pin → compatible target or boss native; terrain-only pin → compatible source redraw or terrain native; dual pin incompatibility → loud failure. Do not silently alter boss, terrain, or explicit curse pins.

- [ ] **Step 4: Wire `tower_pick`, `src_pick`, `mix_pick`, and `quest_pool`**

  All pickers carry `NativeBossBundle` and selection IDs. Build the catalog from the current
  in-memory tables before the old flat pool; bind it to the actual per-floor enemy level and
  re-gate if `resolve_level()` changes the tier. Remove flattened entry weighting. Keep
  labels/BGM/thumbnail from the realized native or target bundle as defined by the design.

- [ ] **Step 5: Run focused GREEN, a multi-seed dry-run sample, and full discovery**

  Run at least seeds `20260805`, `20260806`, `20260807` without `--write`; report transplanted rounds, native fallbacks and dual-pin failure evidence. Require discovery 337.

- [ ] **Step 6: Record the proposed small commit**

  Proposed commit, only if authorized: `refactor(rogue): realize boss bundles through one path`.

---

### Task 6: Bundle-fingerprint HP reorder and refs + HP + c36 revalidation

**Files:**
- Modify: `mod-tools/wf_rogue_bundle.py`
- Modify: `mod-tools/wf_rogue_build.py`
- Modify: `mod-tools/tests/test_rogue_chain_gate.py`
- Modify: `mod-tools/work/codex_out/REPORT-native-boss-bundle-variants.md`

**Interfaces:**
- Produces: `bundle_fingerprint(realized, tables, enemy_level) -> str`.
- Produces: `revalidate_selected_bundle(realized, *, stage, enemy_level, requires_element_resistance, tables) -> BundleValidation`.
- Changes: `floor_native_hp()` consumes realized entity paths, including special expansion.
- Changes: `hp_curve_fit_pick()` selects a bundle and calls `realize_bundle()`; it never edits raw boss strings.
- Requires: `RealizedBundle.condition_carrier` identifies the one runtime c109 carrier for c36.

- [ ] **Step 1: Rewrite HP reorder/revalidation tests and run RED**

  Extend:

  - `TaskCDryRunCase.test_pinned_terrain_does_not_bypass_immunity_aware_hp_reorder`
  - `StandardBossHpCase.test_floor_native_hp_keeps_two_real_instances_with_the_same_code`
  - `GeneralBossElementResistanceCase`'s existing actual-row c36 method

  Add subcases proving: donor swap changes the fingerprint and invalidates HP cache; duplicate instances remain duplicated; post-reorder actual c36 is checked at the selected level; failed final clone HP/readback stops output.

- [ ] **Step 2: Replace `_hp_fit_cache` key**

  Use canonical realized fingerprint + round + exact `float(target).hex()`. Re-read current
  injected tables and include active slots, selected levels, boss/source rows, boss_level rows,
  special parent c24, terrain caps, action requirements, Standard ESDL/HP evidence, and curve/K.
  Never cache by field alone or reuse live-store `_BASE_STATS/_SPECIAL_LV` for clone validation.

- [ ] **Step 3: Make HP reorder return and realize bundles**

  Candidate ranking may remain, but every candidate is a native bundle. On selection, call `realize_bundle()` on the current terrain, then recompute native HP. If portability fails, obey native fallback; if dual pinned, fail.

- [ ] **Step 4: Implement the common three-part validator**

  At stages `selected`, `mixed`, `hp_reordered`, `final_clone`, and write-time `final_gate`,
  re-read the realized field and run:

  ```text
  refs: active slot pairs + correct source/level + spawned dependencies
  HP: all actual reachable instances, including Orochi parent + eight heads
  c36: actual `condition_carrier` selected/clone row when element resistance is requested
  ```

  Keep final `validate_built_rows()` as an extra whole-table gate.

- [ ] **Step 5: Run focused GREEN, full dry-run, fixed discovery, and report**

  Require logs to show each revalidation stage and zero stale-cache reuse. Run the 30-floor flat hell dry-run and `--mix`, then the full 337-test discovery. Append refs/HP/c36 counts and any rejection details.

- [ ] **Step 6: Record the proposed small commit**

  Proposed commit, only if authorized: `fix(rogue): revalidate boss bundles after every mutation`.

---

### Task 7: Remove the endless-reroll bypass

**Files:**
- Modify: `mod-tools/wf_rogue_build.py`
- Modify: `mod-tools/wf_rogue_save.py`
- Modify: `mod-tools/tests/test_rogue_chain_gate.py`
- Modify: `mod-tools/work/codex_out/REPORT-native-boss-bundle-variants.md`

**Interfaces:**
- Produces: `choose_endless_native_bundle(rng, enemy_level=100) -> NativeBossBundle`.
- Changes: `reroll_endless_field()` consumes that API and never imports/calls `wf_chain_build.build_pool()`.
- Changes CLI defaults to event `700099`, quest `99`, and derives enemy level from the target c95.

- [ ] **Step 1: Extend an existing test method and run RED**

  In `StandardBossHpCase.test_zone_pick_uses_single_battle_side_of_each_boss_slot`, add a `subTest` that patches `wf_rogue_build.choose_endless_native_bundle`, invokes `wf_rogue_save.reroll_endless_field(..., apply=False)`, and asserts the shared selector was called while a patched `wf_chain_build.build_pool` was not.

- [ ] **Step 2: Export a read-only native selector**

  Build the same post-gate catalog from a fresh snapshot, choose a native bundle through
  family → variant → bundle, and run `revalidate_selected_bundle(stage="selected")` before
  returning it. Return source field and BGM from that bundle. Do not add a stale enemy-level-only
  cache key.

- [ ] **Step 3: Rewire reroll while preserving apply semantics**

  `apply=False` only prints the candidate. `apply=True` alone edits rush quest and invokes
  `wf_publish.py`; publish failure propagates. Missing/short target rows and empty-BGM policy fail
  before writes. Preserve existing server/device behavior; do not add implicit writes.
  Thumbnail/recommended-element synchronization is explicitly outside this first task and must
  not be inferred from the removed legacy pool.

- [ ] **Step 4: Run focused GREEN, fixed discovery, and report**

  Report the patched call proof and one real dry-run candidate. Run full discovery and require 337.

- [ ] **Step 5: Record the proposed small commit**

  Proposed commit, only if authorized: `fix(rogue): use screened bundles for endless rerolls`.

---

### Task 8: Truthful coverage, multi-seed rotation, and final acceptance report

**Files:**
- Modify: `mod-tools/wf_rogue_bundle.py`
- Modify: `mod-tools/wf_rogue_build.py`
- Modify: `mod-tools/tests/test_rogue_chain_gate.py`
- Modify: `mod-tools/work/codex_out/REPORT-native-boss-bundle-variants.md`

**Interfaces:**
- Produces: JSON-serializable `audit_bundle_coverage()` output.
- Produces: multi-seed rotation records keyed by family, variant, native bundle, fallback reason, and validation stage.
- Prints exactly: `这是下一座候选塔，不是当前 store 塔` for every multi-seed dry-run candidate.

- [ ] **Step 1: Rewrite existing coverage/CLI assertions and run RED**

  Extend `TaskCDryRunCase.test_flat_hell_build_matches_the_absolute_hp_contract` and `CollapseGradesCase.test_keeps_highest_grade_only` to assert report schema, post-gate counts, family rotation records, native-only counts, and the exact candidate-tower disclaimer. Do not create a new test method.

- [ ] **Step 2: Render real post-gate coverage**

  Report scanned/eligible counts for code, family, variant and bundle; reason distributions with representative codes; native-only reason counts; Orochi variant status; the six `NO_SINGLE_FIELD` codes; `arch_evil*`; and `orochi_ex`. Never copy the 114/60 pre-gate ceiling into eligible fields.

- [ ] **Step 3: Run deterministic multi-seed rotation**

  Use at least ten recorded seeds including `20260805`–`20260814`, 30 rounds, flat hell, with and without `--mix`. Show representative families rotating and verify family selection is unchanged when duplicate bundle fixtures are added under one family.

- [ ] **Step 4: Run final focused and full verification**

  From `mod-tools/` run:

  ```powershell
  python -X utf8 -m unittest discover -s tests -p "test_rogue_chain_gate.py"
  python -X utf8 -m unittest discover -s tests -p "test_rogue*.py"
  python -X utf8 wf_rogue_build.py --rounds 30 --seed 20260805 --difficulty hell --ignore-plan
  python -X utf8 wf_rogue_build.py --rounds 30 --seed 20260805 --difficulty hell --ignore-plan --mix
  ```

  Required: touched tests green, full discovery `Ran 337 tests`, known baseline exactly `failures=7, errors=30`, both builds end in `[DRY-RUN] 未写入`, and no forbidden path changed.

- [ ] **Step 5: Finish the report**

  Include RED/GREEN evidence for every task, exact post-gate coverage, native-only counts, family/variant rotation, native fallback and dual-pin evidence, Orochi parent+head HP/readback, refs+HP+c36 stage counts, reroll shared-selector proof, changed interfaces, uncertainties, `git diff --check`, and a path audit proving no store/CDN/device/assets/sync write.

- [ ] **Step 6: Record the proposed final commit**

  Proposed commit, only if authorized: `test(rogue): report native boss bundle coverage`.
