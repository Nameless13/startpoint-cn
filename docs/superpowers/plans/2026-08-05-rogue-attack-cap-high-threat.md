# Rogue Attack Cap and High-Threat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every generated floor's final enemy attack multiplier auditable, normally near 1.1 and never above 1.5, while replacing the old mobility-only list with the approved high-threat policy.

**Architecture:** `solve_atk()` becomes a calculation-only function. `enforce_atk_band()` owns an explicit downgrade state machine that mutates curse tiers or the recorded source/normalization component, logs every change, and fails loudly if it cannot converge. Threat classification is loaded once from structured JSON and reused by initial selection, HP rearrangement, and curse finalization.

**Tech Stack:** Python 3, `unittest`, ordered-map dry-run builder, JSON policy file.

## Global Constraints

- Work on `release/modes-20260714` and preserve all pre-existing dirty WIP.
- Do not write store data, publish, modify `assets/`, touch `sync_pending.json`, touch `wf_dev_catalog.py`, or push to a device.
- Do not commit this local reverse-engineering workspace unless the user separately asks.
- Keep dry-run's “next candidate tower, not current store tower” message.
- Before implementation, change existing tests so the focused run is RED; after implementation make it GREEN.
- Do not increase the suite count: full regression must remain exactly `337 tests / failures=7 / errors=30`.
- On completion immediately write `mod-tools/work/codex_out/REPORT-attack-cap-high-threat.md` with RED/GREEN and full-suite evidence.

---

### Task 1: Explicit attack downgrade gate and high-threat policy

**Files:**
- Modify: `mod-tools/wf_rogue_build.py`
- Modify: `mod-tools/rogue_special_bosses.json`
- Modify: `mod-tools/tests/test_rogue_chain_gate.py`
- Create: `mod-tools/work/codex_out/REPORT-attack-cap-high-threat.md`

**Interfaces:**
- Consumes: `apply_picks(out, picks, combo)`, `downgrade_atk_curse(curse)`, `hp_curve_fit_pick(...)`, `tower_pick(r)`.
- Produces: `load_high_threat_rules(path) -> tuple[tuple[str, ...], frozenset[str]]`, `is_high_threat_bosses(bosses, prefixes, exact) -> bool`, calculation-only `solve_atk(...)`, and explicit `enforce_atk_band(...)` logs.

- [ ] **Step 1: Rewrite existing tests to the approved numbers and behavior**

  In existing test methods (no net-new test count), assert:

  ```python
  self.assertEqual(rb.DIFF_PRESETS["hell"][2:4], (1.1, 1.1))
  self.assertEqual(rb.ATK_CURSE_TIERS["嗜血狂潮"], (1.05, 1.10, 1.15))
  self.assertEqual(rb.ATK_CURSE_TIERS["深渊逆鳞"], (1.10, 1.20, 1.30))
  self.assertEqual(rb.ATK_CURSE_TIERS["玻璃深渊"], (1.20, 1.30, 1.40))
  self.assertEqual(rb.BAND_TARGET, {"median": 1.1, "p90": 1.35, "max": 1.5})
  ```

  Extend the existing convergence test to enumerate rounds `1..31` and all three attack-card tier choices, then assert every `rec["atk"] <= 1.5` and that no log contains `单层夹到`.

  Rewrite the existing mobility-config test for `high_threat.prefixes/exact`, including exact-match negative coverage and malformed-data failures. Extend an existing HP-pick/tower-selection test to prove shallow candidates prefer a non-threat carrier.

- [ ] **Step 2: Run the focused tests and capture RED evidence**

  Run:

  ```powershell
  python -m unittest tests.test_rogue_chain_gate.AtkCurseTierCase tests.test_rogue_chain_gate.SolveAtkCase tests.test_rogue_chain_gate.AtkBandCase tests.test_rogue_chain_gate.HighMobilityCase
  ```

  Expected: failures on old `1.7/1.8/2.6`, old `6.6/2/3/6` gates, old `high_mobility` schema, and silent clamp behavior.

- [ ] **Step 3: Implement the minimal explicit downgrade state machine**

  Update constants exactly as specified in the design. Remove all result-clamping `min()` calls from `solve_atk()`. In `enforce_atk_band()`:

  ```python
  if rec["atk"] > limit + 1e-9:
      note = downgrade_atk_curse(rec["curse"])
      if note is None:
          old_ba = rec["ba"]
          rec["ba"] *= limit / rec["atk"]
          log.append(f"...攻击来源×{old_ba:g}→×{rec['ba']:g}...")
  ```

  Recalculate after every mutation. Validate all factors are finite and positive, raise on non-convergence, and post-assert every floor against the hard ceiling. Do not assign a `hard_cap` return-value clamp.

- [ ] **Step 4: Implement and wire structured high-threat rules**

  Replace `load_high_mobility_prefixes` / `is_high_mobility_bosses` and their call sites with the new structured policy. Add the approved prefix/exact values to JSON. Filter high-threat candidates in the first 20% of rounds in both `tower_pick()` and `hp_curve_fit_pick()` when a non-threat candidate remains. Rename runtime/log fields from mobility to threat so reports say `[高威胁]`.

- [ ] **Step 5: Run focused GREEN tests**

  Run the command from Step 2 plus the existing HP-rearrangement test classes touched by the shallow filter. Expected: all focused cases pass with no new unittest failures/errors.

- [ ] **Step 6: Run full regression and write the batch report**

  Run from `mod-tools/`:

  ```powershell
  python -m unittest discover -s tests -p "test_rogue*.py"
  ```

  Required final line: `Ran 337 tests`; required status: `FAILED (failures=7, errors=30)`. Record the exact command, RED output, GREEN output, constant values, downgrade logs, changed functions, uncertainties, and forbidden-path audit in `REPORT-attack-cap-high-threat.md`.

