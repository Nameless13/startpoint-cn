# Rogue Mixed Immunity and Dragon Heart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-element mixed resistance strengths with truthful copy and controlled dispellability, while making Dragon Heart always arrive with a visible non-boon mechanic.

**Architecture:** Resistance tuples are normalized into atoms that include cancelability; merging and solvability operate on normalized atoms, while the DSL builder groups atoms by the command-wide cancelable flag. A single `finalize()` companion step handles Dragon Heart for random, combo, and forced paths.

**Tech Stack:** Python 3, `unittest`, action DSL AMF3/raw-deflate round-trip validation.

## Global Constraints

- Work on `release/modes-20260714` and preserve all pre-existing dirty WIP.
- Do not write store data, publish, modify `assets/`, touch `sync_pending.json`, touch `wf_dev_catalog.py`, or push to a device.
- Do not commit this local reverse-engineering workspace unless separately requested.
- Keep the test count fixed: full regression must be exactly `337 tests / failures=7 / errors=30`.
- Use TDD by rewriting existing relevant test methods before implementation; do not add net-new `test_*` methods.
- Keep element data codes 1-based; retain the autoHighLevel event-quest guard and c36 actual-row gate.
- Text never exposes cancelability and always derives numeric claims from actual strength.
- Immediately write `mod-tools/work/codex_out/REPORT-mixed-immunity-dragon-heart.md` after the batch passes.

---

### Task 1: Mixed resistance atoms, DSL split, and Dragon Heart companion

**Files:**
- Modify: `mod-tools/wf_rogue_build.py`
- Modify: `mod-tools/tests/test_rogue_chain_gate.py`
- Create: `mod-tools/work/codex_out/REPORT-mixed-immunity-dragon-heart.md`

**Interfaces:**
- Produces: `mixed_element_entry(rng, strengths, forced=None, name="混相禁域") -> dict`.
- Produces: normalized resistance atoms `(target, strength, cancelable)` accepted by `_merged_resistance`, `build_immunity_dsl_tree`, and `immunity_program`.
- Produces: `ensure_dragon_heart_companion(picks, rng, can_carry, menu) -> list[dict]`.
- Preserves: old 2-tuple resistance and 3-tuple stacked callers as non-dispellable compatibility input.

- [ ] **Step 1: Rewrite existing tests for the new contract and run RED**

  Without increasing discovered test count, update existing methods in `CurseConflictCase`, `StackedResistanceCase`, `ElementImmunityDslCase`, `GeneralBossElementResistanceCase`, and `HellEverywhereCase` to cover:

  ```python
  forced = [
      {"element": 1, "strength": 1.0},
      {"element": 2, "strength": 999.0},
      {"element": 3, "strength": 999.0},
      {"element": 6, "strength": 999.0},
  ]
  entry = mixed_element_entry(Random(1), strengths=(1, 9, 99, 999), forced=forced)
  self.assertEqual(entry["element_resistance"],
                   [(1, 1.0, False), (2, 999.0, False),
                    (3, 999.0, False), (6, 999.0, False)])
  ```

  Also assert: any positive resistance on all six attributes is a conflict; false/true atoms become separate `CreateCondition` commands; bool-only differences produce different program IDs; Dragon Heart text contains 20/50/90 and no `百分点`; forced shallow Dragon Heart has exactly one non-boon companion if none existed and does not add a third field when replacing a boon.

  Run focused classes and record expected missing-interface/old-copy/old-tree failures.

- [ ] **Step 2: Implement mixed element generation and depth schedule**

  Add `混相禁域` to the element family and carrier requests. Random generation chooses 1～5 unique elements and independently chooses strengths from the depth-specific set. Forced entries validate exact types/ranges/uniqueness and do not perform the random atom draws. Generate text by sorting element codes and joining `ELEMENT_DATA_CN[e] + resistance_label(r)`.

- [ ] **Step 3: Normalize cancelability and split the DSL**

  Accept legacy tuples as `cancelable=False`. Merge element strengths by `(element, cancelable)` while solvability sums both groups. Hard atoms override any requested true value to false. Group one-shot AC entries into false then true `CreateCondition` commands. Keep stacked commands per visible layer and false. Include bools in `immunity_program()`'s JSON signature and verify build→parse equality.

- [ ] **Step 4: Strengthen merged solvability and all three runtime gates**

  In `curse_conflict()`, reject if positive-strength affected elements equal `{1,2,3,4,5,6}`, independently of the existing `r>=99` high-lock check. Keep the four-damage-type exit check. Ensure dynamic mixed cards pass the same `ELEMENT_CURSE_NAMES`, general-boss carrier, c36, high-threat, and `assert_element_immunity_runtime_safe()` paths as presets. Log rejected combinations before redraw.

- [ ] **Step 5: Pair Dragon Heart in finalize**

  Detect `ACToleranceOfDebuff` in stacked specs. Before the first final conflict check, reuse an existing non-`加成` field, replace one boon field if all fields are boons, or append one unused non-boon field. Fail loudly without a carrier/candidate. Keep 20/50/90 layers and replace the old percentage-points copy with `普通减益几乎无法命中；强制赋予除外`.

- [ ] **Step 6: Focused GREEN, full regression, and report**

  Run focused touched classes, then from `mod-tools/` run:

  ```powershell
  python -m unittest discover -s tests -p "test_rogue*.py"
  ```

  Required: `Ran 337 tests` and `FAILED (failures=7, errors=30)`. Report RED/GREEN, forced author example, random depth distribution, merged exit gates, false/true DSL dump, c36/autoHighLevel evidence, Dragon Heart companion evidence, exact suite result, changed functions, uncertainties, and forbidden-path audit.

