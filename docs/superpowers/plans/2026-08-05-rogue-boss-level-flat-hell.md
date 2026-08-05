# Rogue Boss-Level Scaling and Flat Hell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development while implementing each task. The tasks are tightly coupled in `wf_rogue_build.py`, so implementation stays serial; independent agents may perform read-only audits and final review.

**Goal:** Make every boss floor except the round-1 minion warmup target 21,940,625–30,716,875 DPS by default, scaling general bosses through cloned `boss_level.c2`; preserve the old 600,000→25,000,000 geometry only behind `--ramp`.

**Architecture:** Treat HP profile and difficulty preset as separate inputs. Pure helpers validate the runtime-selected `general_boss` row and rebuild Hit-HP `boss_level` CSV leaves; the builder clones every distinct general code on a floor, applies one uniform c2 scale (including HP curses), swaps all runtime boss slots, and holds quest c86 at 1.0. Pure-standard floors may remain only when their required baseline c86 is within 0.9–1.1; mixed-family, Fix-HP, or otherwise unscalable floors are rejected and redrawn. Flat and ramp profiles use distinct acceptance gates. HP replacement uses the same actual-level carrier/c36 gate as the curse stage: a pinned element-immunity curse requires an eligible replacement, and ordinary HP replacement prefers eligible candidates before explicitly falling back.

**Tech Stack:** Python 3, `unittest`, nested orderedmap helpers in `wf_quest_lib`, CSV `cells()`/`join()`, existing dry-run chain validators.

## Global Constraints

- Work on `D:\WF\startpoint-cn`, branch `release/modes-20260714`, preserving all unrelated dirty-worktree changes.
- Do not write to store, do not publish, do not run `wf_publish`, and do not change anything under `assets/`.
- Do not modify `mod-tools/wf_dev_catalog.py`.
- The full rogue suite may not exceed the established `failures=7, errors=30` baseline.
- Final producer evidence must include a 30-floor in-memory dry-run reporting 31/31 complete chains. Because this task may not write store, standalone `--check` must report the complete chain count of whatever build is already installed and the report must distinguish that count.
- `assets/rogue_event.json` remains untouched; the report records the eventual restore value `{ "rounds": 30, "difficulty": "hell", "mix": true }`.
- Current parsed `boss_level` shape is `code -> CSV leaf`, not a nested level map. `general_boss` alone uses getSurjectivity (`first key >= enemy_level`); clone validation must prove that selected general row is unchanged and that the matching clone owns the rebuilt boss-level leaf.

---

### Task 1: Lock the HP-profile and boss-level contracts with failing tests

**Files:**
- Modify: `mod-tools/tests/test_rogue_chain_gate.py`

**Interfaces:**
- Consumes existing `cells`, `join`, `floor_native_hp`, `hp_curve_errors`, and CLI dry-run helpers.
- Defines expected public helpers: `select_surjective_level`, `clone_hit_boss_level_c2`, `general_hp_scale_plan`, `target_dps`, and mode-aware `hp_curve_errors(..., ramp=...)`.

- [ ] Add a literal-table test proving `select_surjective_level({"79": ..., "100": ...}, 80) == 100`, 79 selects 79, and 101 returns `None`.
- [ ] Add a CSV round-trip test whose Hit row has c2=10/c3=2; scaling by 3 must create c2=30, preserve c3/c4 and source text, and reject Fix (`c0=1`), malformed, nonfinite, or nonpositive input.
- [ ] Add a pure-general plan test with two distinct codes and hand-derived native HP. The uniform baseline factor must hit `target_dps * 900`; the final factor must additionally include `curse_hp`; output c86 must be 1.0.
- [ ] Add mixed general/standard and Fix-HP rejection tests so half-scaled floors cannot pass.
- [ ] Replace the old default-geometric test: flat profile returns 25,000,000 on every boss round; ramp profile retains 600,000 and 25,000,000 endpoints.
- [ ] Split curve-gate tests: flat mode ignores the explicitly marked round-1 warmup and requires every remaining row within 21,940,625–30,716,875; ramp mode alone checks 15% downward jitter, last band, and 35–50x endpoint ratio.
- [ ] Run only the added tests and confirm they fail for missing/new behavior, not setup errors.

### Task 2: Implement validated c2 cloning and family-aware HP planning

**Files:**
- Modify: `mod-tools/wf_rogue_build.py`
- Test: `mod-tools/tests/test_rogue_chain_gate.py`

**Interfaces:**
- `select_surjective_level(node: dict, enemy_level: int) -> int | None`
- `clone_hit_boss_level_c2(source_leaf: str | bytes, scale: float) -> str | bytes`
- `general_hp_scale_plan(bosses: list[str], native: dict, general_boss: dict, boss_level: dict, enemy_level: int, target_hp: float, curse_hp: float) -> dict`
- `floor_native_hp(..., boss_level: dict | None = None) -> dict` must bypass `_BASE_STATS` when a build-time table is supplied.

- [ ] Extract the getSurjectivity selector and reuse it in `general_boss_element_immunity_block`.
- [ ] Implement strict Hit-row c2 rebuilding through `cells()`/`join()`; never mutate/reuse a mutable leaf and never scale c3/c4.
- [ ] Make `boss_base_stats`, `true_stat`, and `floor_native_hp` accept a build-time `boss_level` table so final clone audits do not read stale `_BASE_STATS`.
- [ ] Implement a pure-general scaling plan that requires every distinct runtime code to be present in `general_boss` and `boss_level`, requires a selectable general row, rejects Fix/mixed families, scales every distinct general code uniformly, and exposes baseline/final rounded c2 leaves plus exact HP evidence.
- [ ] Run the focused helper tests and confirm green.

### Task 3: Move the build pipeline from c86 solving to clone c2 scaling

**Files:**
- Modify: `mod-tools/wf_rogue_build.py`
- Test: `mod-tools/tests/test_rogue_chain_gate.py`

**Interfaces:**
- `make_caster_boss` gains explicit clone code/suffix and a prebuilt boss-level leaf.
- `gimmick_field` accepts all `(source_code, clone_code)` swaps for a floor.
- HP audit records retain `baseline_true_hp`, `true_hp`, `baseline_dps`, `realized_dps`, `curse_hp`, `c86`, and add c2 scale evidence.

- [ ] Change candidate feasibility: pure scalable general floors are feasible without a c86 ceiling; pure standard floors require baseline c86 0.9–1.1; deep floors reject standard; mixed/Fix/unverifiable floors redraw.
- [ ] Pass HP-channel information into curse conflict checks. General floors keep c86=1 and place HP curse multiplication in c2; standard floors retain the only available c86 channel and must remain within 0.9–1.1 after all HP curses.
- [ ] Clone every distinct general source code on each general floor, attaching action/pre-action only to the designated carrier clone and copying `general_boss_variable`/self-watch as before.
- [ ] Apply all swaps to the cloned zone even when no field/gimmick curse exists; re-read final single-player boss slots and audit them against build-time `bl_t`.
- [ ] Write `row[86:89] = 1` for general floors. Keep only bounded c86 for standard floors and the existing visible proxy on the no-boss warmup.
- [ ] Add integration assertions for same-code multi-instance swaps, multiple distinct general codes, clone selected-level parity, c2 evidence, and Task A HP invariance after attack curse removal.
- [ ] Run the focused HP/clone tests and a canonical 30-floor dry-run.

### Task 4: Make flat hell default and retain ramp explicitly

**Files:**
- Modify: `mod-tools/wf_rogue_build.py`
- Modify: `mod-tools/wf_rogue_reroll.py`
- Test: `mod-tools/tests/test_rogue_chain_gate.py`

**Interfaces:**
- CLI `--ramp` selects the old DPS geometry; it is unrelated to `--enemy-level ramp`.
- `hp_profile_target_dps(r, n, ramp=False)` returns 25,000,000 by default and 600,000→25,000,000 geometrically when ramped.
- `wf_rogue_reroll.py --ramp` forwards exactly one `--ramp` to the builder.

- [ ] Add `--ramp` help text that distinguishes DPS profile from enemy-level ramp.
- [ ] Keep `--difficulty` responsible for curse/ATK preset behavior; default hell remains canonical. Preserve explicit difficulty/HP overrides as explicit noncanonical scaling, while canonical flat-hell targets stay inside the decision band.
- [ ] Mark round 1 as the sole warmup exemption in HP audit; flat `hp_curve_errors` validates every boss row, while ramp keeps the old trend/ratio gates.
- [ ] Update end-to-end assertions: default log reports flat profile and every round 2–30 baseline DPS in band; `--ramp` reports the old endpoints and passes ramp gates.
- [ ] Forward `--ramp` through `wf_rogue_reroll.py`; do not alter server code or asset configuration in this task.
- [ ] Run focused CLI/dry-run tests and confirm green.

### Task 5: Preserve element-immunity carriers during HP replacement

**Files:**
- Modify: `mod-tools/wf_rogue_build.py`
- Test: `mod-tools/tests/test_rogue_chain_gate.py`

**Interfaces:**
- `element_immunity_requested(forced)` recognizes all three element curse names.
- HP candidate metrics carry `element_immunity_block`; `None` means carrier references, actual `general_boss` level row, and c36 all pass.

- [ ] When a workshop floor pins an element curse, an HP-valid but ineligible current boss must search the eligible pool instead of silently losing the curse.
- [ ] Ordinary HP replacement searches the eligible pool first so shallow random curses have a real carrier path.
- [ ] Run the complete mix/quota fallback pipeline for eligible candidates before falling back to the ordinary HP pool.
- [ ] If a pinned curse has no eligible replacement and its current HP is already valid, keep the current boss, log the downgrade, and let the existing curse gate redraw without consuming replacement RNG/quota. If the user also pinned an ineligible boss, reject that contradictory pair explicitly instead of silently changing either pin.
- [ ] A pinned terrain still runs the same donor replacement path and must retain its cloned terrain; it does not lock an ineligible donor in place.
- [ ] Add seed-locked round-12 and pinned-terrain integrations proving HP replacement retains `元素禁壁`; add an ineligible pinned-boss regression proving the conflict fails loudly.

### Task 6: Full verification, review, and report

**Files:**
- Create: `mod-tools/work/codex_out/2026-08-05-rogue-boss-level-flat-hell.md`

**Interfaces:**
- Report names changed functions, target/profile constants, c2/c86 policy, standard fallbacks, tests, 31-chain evidence, mix result, asset restore value, and uncertainties.

- [ ] Run `python -m unittest discover -s tests -p "test_rogue*.py"`; require exactly or fewer than 7 failures and 30 errors.
- [ ] Run canonical 30-floor default and `--ramp` dry-runs without `--write`/`--publish`; inspect all HP and clone evidence.
- [ ] Run `python mod-tools/wf_rogue_build.py --check` read-only; if store still contains the user's short prior build, report its actual count separately from the canonical dry-run's 31/31.
- [ ] Run `git diff --check` and review only the scoped files against the pre-task diff.
- [ ] Request an independent final code review, resolve load-bearing findings, then write the concise report.
