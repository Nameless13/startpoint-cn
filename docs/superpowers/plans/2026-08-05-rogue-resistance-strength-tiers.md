# Rogue Resistance Strength Tiers Implementation Plan

> **For agentic workers:** Use test-driven development. Keep implementation serial in `wf_rogue_build.py`; independent agents may perform read-only source and review audits.

**Goal:** Correct the element-resistance strength model to `damage / (1 + r)`, add four truthful depth-scheduled element curse tiers, and count only `r >= 99` as an element-path lock while preserving the four damage-type resistances' verified `damage * (1 - r)` semantics.

**Architecture:** Keep element and damage-type resistance as distinct axes with distinct label/lock helpers. Build all four element entries in the shared curse catalog, then apply depth eligibility only to random selection; explicit workshop pins remain eligible subject to the existing carrier/c36 and solvability gates. Emit the selected resistance value unchanged into `ACToleranceOfElement`.

**Constraints:** Work only in the dirty `release/modes-20260714` checkout. Do not write store, publish, or modify `assets/`. Preserve the established rogue-suite baseline (`failures=7`, `errors=30`).

## Task 1: Lock corrected semantics with failing tests

**Files:**
- Modify: `mod-tools/tests/test_rogue_chain_gate.py`

- Add literal tests for `resistance_label(1/9/99/999)` and the four element-curse specs.
- Prove `r=1` and `r=9` do not consume an element exit, while merged `r>=99` entries do.
- Prove the four damage axes still use `r=1` as a complete lock.
- Prove the DSL preserves arbitrary finite positive element strengths and rejects invalid strengths.
- Prove shallow/middle/deep random eligibility rises from low to high strength while explicit forced names survive scheduling.

## Task 2: Implement separate element and damage resistance contracts

**Files:**
- Modify: `mod-tools/wf_rogue_build.py`

- Add `元素滞钝` and central element tier specifications.
- Generate player-facing element text from `1 / (1 + r)` rather than hard-coded immunity text.
- Retain damage-type text and lock semantics derived from `1 - r`; do not raise their values above 1.
- Change `immunity_axes` so the element lock threshold is 99 and the damage lock threshold remains 1.
- Document that fixed/ratio damage bypasses element resistance, so this gate protects ordinary element-damage routes rather than claiming an absolute combat softlock.
- Emit the exact element resistance value into the CreateCondition DSL.

## Task 3: Apply depth scheduling without weakening workshop pins

**Files:**
- Modify: `mod-tools/wf_rogue_build.py`
- Test: `mod-tools/tests/test_rogue_chain_gate.py`

- Random schedule: rounds 1-6 use `元素滞钝`; 7-15 allow `元素滞钝/三相封界`; 16-24 allow `三相封界/元素禁壁`; final 20% allow `元素禁壁/五相绝域` (ratios generalized for non-30-floor towers).
- Apply schedule after runtime capability filtering and only to random/refill selection.
- Resolve forced curse names against the full capability-eligible catalog so existing shallow pins remain authoritative.
- Keep cross-curse high-resistance rejection explicit and logged; never silently truncate.

## Task 4: Verify and report

**Files:**
- Create: `mod-tools/work/codex_out/2026-08-05-rogue-resistance-strength-tiers.md`

- Run focused tests, the complete rogue unittest suite, canonical dry-run(s), current-store `--check`, and `git diff --check`.
- Inspect generated DSL trees for all four strengths.
- Record the true-device validation, corrected formulas, depth schedule, fixed/ratio escape route, tests, and any remaining uncertainty.
- Do not commit, publish, or write store.
