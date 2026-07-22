# WF One-Click Import M1A: `.wfpack` Toolchain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended in the current session) or `superpowers:executing-plans` to implement this plan task by task. Use `superpowers:test-driven-development` for every production-code task and `superpowers:verification-before-completion` before claiming completion.

**Goal:** Build the author-side, fail-closed `.wfpack` v1 toolchain: strict canonical JSON, a concrete manifest contract, Ed25519 signing, deterministic Zip64 construction and verification, a crash-order reference install model, golden vectors, and a no-prompt command-line workflow.

**Architecture:** Keep the format contract independent from both Android and the patched game client. The author-side builder scans a prepared cumulative payload, derives every payload hash/count/size, canonicalizes the manifest, signs only the domain-separated canonical manifest bytes, writes a deterministic stored Zip64 archive, and then reopens that archive through the public verifier. A separate pure reference transaction model defines persistent-ID and commit ordering for the future Android importer without installing anything into a real `WorldFlipper` directory.

**Tech Stack:** Python 3.11+ standard library, `cryptography` 49.x Ed25519 primitives, `unittest`, deterministic `zipfile`/Zip64 records, JSON Schema as a checked-in interoperability artifact, Windows batch wrapper.

**Approved design:** `docs/superpowers/specs/2026-07-22-wf-one-click-mod-center-design.md`

---

## Scope and safety boundary

M1A creates and validates the package contract. It does **not**:

- build, patch, sign, install, or launch an APK;
- read or mutate `弹国服/`, `D:\WF\wf-decrypted`, a device, an emulator, or a live `WorldFlipper` tree;
- publish a release, push a branch, or modify the active CDN/store graph;
- assemble the real three-character/two-mode payload yet;
- implement the Android Storage Access Framework or the in-game Mod Center.

All integration fixtures are tiny synthetic files under `mod-tools/tests/fixtures/wfpack/`, and every install-model test uses a temporary or in-memory root. Existing user WIP in `assets/`, `work/`, reverse-engineering directories, and the currently modified `mod-tools` files must remain untouched.

Before Task 1, use `superpowers:using-git-worktrees` to create the ignored isolated worktree `D:\WF\startpoint-cn\.worktrees\wfpack-m1a` on branch `codex/wfpack-m1a`, based on the commit containing this plan. Require a clean `git status --short` there before editing. Run every task, test, and commit from that worktree; stage only the exact owned paths listed by the task. Never run the final full-suite acceptance against the user's dirty primary checkout.

The Android importer is M1B and must consume M1A's golden vectors rather than reinterpreting the format. The game APK/Mod Center work is a separate client plan and must retain its real-device canary gate.

## Fixed v1 contract decisions

### Archive tree

The only legal archive members are regular files with these names:

```text
WFModPack/manifest.json
WFModPack/manifest.sig
WFModPack/payload/production/upload/<2 lowercase hex>/<38 lowercase hex>
WFModPack/payload/production/medium_upload/<2 lowercase hex>/<38 lowercase hex>
WFModPack/payload/production/android_upload/<2 lowercase hex>/<38 lowercase hex>
WFModPack/payload/dummy-overlay.json
WFModPack/payload/mode-variants.json
```

There are no directory entries. Paths containing an absolute prefix, `..`, `.`, an empty segment, a backslash, a NUL, a non-ASCII character, a symbolic link/reparse point, a duplicate normalized path, or a case-fold collision are rejected. Common, medium, and Android members remain separate namespaces even when their hashed tails match.

All entries use `ZIP_STORED`, DOS timestamp `1980-01-01 00:00:00`, Unix regular-file mode `0644`, no comments or extra application metadata, a deterministic lexical member order, per-member Zip64 local headers, and a Zip64 end-of-central-directory record. Two builds from identical bytes and metadata must be byte-for-byte equal.

Installation uses one exact, non-configurable member mapping:

| Archive member | Release-relative target |
|---|---|
| `WFModPack/manifest.json` | `manifest.json` |
| `WFModPack/manifest.sig` | `manifest.sig` |
| `WFModPack/payload/production/<relative>` | `production/<relative>` |
| `WFModPack/payload/dummy-overlay.json` | `dummy-overlay.json` |
| `WFModPack/payload/mode-variants.json` | `mode-variants.json` |

No other prefix stripping is allowed. The mapping is injective and may never produce `.wfpack-importer.json`, `transaction.json`, `complete.json`, `active.json`, or `required-persistent-ids.json`. `wfpack_contract.release_relative_path(member_path)` is shared by the archive verifier and install model; the golden install vector records every mapped fixture path and collision rejection.

M1A fixes only the two runtime documents' container envelopes: `dummy-overlay.json` has exactly `{"operations":[<canonical JSON objects>],"schema_version":1}` and `mode-variants.json` has exactly `{"modes":[<canonical JSON objects>],"schema_version":1}` at the top level. Both must themselves be strict canonical JSON, and their top-level arrays preserve declared order. M1A does not claim that non-empty operation/mode entries are game-valid. The later client/content plan must add versioned allowlist schemas with `additionalProperties: false` and their real semantic validators before a real pack can be marked runtime-ready; M1B merely verifies and installs their signed bytes.

### Canonical JSON subset

`manifest.json`, `manifest.sig`, trusted-key documents, active pointers, persistent-ID locks, and complete seals use the same strict subset:

- UTF-8 without BOM or trailing newline;
- RFC 8785 string escaping and UTF-16 code-unit key ordering;
- objects, arrays, strings, booleans, null, and integers only;
- integers restricted to `[-9007199254740991, 9007199254740991]`;
- every key and string already in Unicode NFC;
- duplicate keys, lone surrogates, floats, exponent notation, `NaN`, and infinities rejected;
- a parser accepts a document only when its input bytes exactly equal its canonical reserialization.

### Manifest shape

`mod-tools/schemas/wfpack-v1.schema.json` documents this exact top-level shape; `wfpack_contract.py` is the normative validator:

```json
{
  "schema_version": 1,
  "release": {
    "id": "three-characters-two-modes",
    "version": 1,
    "created_at_utc": "2026-07-22T00:00:00Z"
  },
  "base": {
    "contract_id": "wf-cn-1.4.54-clean-v1",
    "resource_version": "1.4.54",
    "asset_size_kind": "fulfill",
    "info_json_sha256": "<64 lowercase hex>",
    "key_path_set_sha256": "<64 lowercase hex>",
    "root_member_counts": {"common": 1, "medium": 1, "android": 1},
    "required_files": [
      {
        "root": "common",
        "logical_path": "<non-empty normalized logical path>",
        "hashed_path": "<2hex>/<38hex>",
        "size": 1,
        "sha256": "<64 lowercase hex>"
      }
    ]
  },
  "client": {
    "contract_id": "wf-offline-mod-center-v1",
    "master_schema": 1,
    "save_schema": 1,
    "min_version_code": 1,
    "max_version_code": 1,
    "certificate_sha256": ["<64 lowercase hex>"],
    "required_capabilities": ["mod_overlay_roots_v1"]
  },
  "content": {
    "character_ids": [129999, 139999, 149999],
    "mode_ids": [2001, 700099],
    "equipment_ids": [8000101],
    "provides_capabilities": ["three_characters_v1", "two_modes_v1"],
    "retains_persistent_ids": [],
    "provides_persistent_ids": ["character:129999", "character:139999", "character:149999", "equipment:8000101", "mail:990000001", "mode:2001", "mode:700099"],
    "tables": [
      {
        "root": "common",
        "logical_path": "<logical path>",
        "member_path": "WFModPack/payload/production/upload/<2hex>/<38hex>",
        "baseline_sha256": "<64 lowercase hex>",
        "output_sha256": "<64 lowercase hex>",
        "changed_keys": ["129999"]
      }
    ],
    "assets": [
      {
        "root": "common",
        "logical_path": "<logical path>",
        "member_path": "WFModPack/payload/production/upload/<2hex>/<38hex>",
        "size": 1,
        "sha256": "<64 lowercase hex>"
      }
    ],
    "mails": [
      {
        "mail_key": "grant.character.129999",
        "reserved_mail_id": 990000001,
        "reward_type": 1,
        "type_id": 129999,
        "amount": 1
      }
    ]
  },
  "payload": {
    "members": [
      {
        "path": "WFModPack/payload/dummy-overlay.json",
        "size": 1,
        "sha256": "<64 lowercase hex>"
      }
    ],
    "member_count": 1,
    "total_uncompressed_bytes": 1,
    "required_temporary_bytes": 13647873,
    "required_final_bytes": 5259265
  }
}
```

Arrays that represent sets are sorted and unique. `content.tables[*].output_sha256` and `content.assets[*].sha256` must equal the derived member entry. Every semantic member reference must exist in `payload.members`; every payload member must be represented exactly once as a table, asset, `dummy-overlay.json`, or `mode-variants.json`. The builder refuses a template that already contains `payload`, because those fields are derived from the source bytes.

`release.id` is a globally unique immutable release identifier, not a product-line name: any different canonical manifest must use a new release ID. `release.version` is the cumulative monotonic sequence used with `--previous-archive`; a successor has the prior version plus one even though its unique release ID changes.

`CN_PATH_SALT` is the literal ASCII string `K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy`. For every `base.required_files`, table, and asset entry, compute `hex = SHA1(UTF8(logical_path + CN_PATH_SALT))`; the only valid hashed tail is `hex[0:2] + "/" + hex[2:40]`, under the directory selected by `root`. Logical paths already use `/`, have no leading slash, empty/`.`/`..` segment, backslash, NUL, or Unicode normalization drift; the validator never silently rewrites them. Tests must assert this helper matches `wf_mod_tool.sha1_path` on fixed CN vectors.

`base.required_files` is sorted by root rank `common`, `medium`, `android`, then by UTF-8 logical path. `key_path_set_sha256` is `SHA256(canonical_json_bytes(base.required_files))`, including each entry's root, logical path, hashed path, size, and content SHA-256. `root_member_counts` describes the complete clean baseline roots rather than only the required subset and has exactly the three non-negative integer fields shown above.

`retains_persistent_ids` must be a subset of `provides_persistent_ids`; for a version after v1 it must equal the previous cumulative manifest's `provides_persistent_ids`. Every character, equipment item, mode, and reserved mail ID has the corresponding `character:<id>`, `equipment:<id>`, `mode:<id>`, or `mail:<reserved_mail_id>` entry in `provides_persistent_ids`. Every mail reward that references a character/equipment ID also requires that content ID and persistent ID. Extra persistent IDs are allowed for shops/quests declared by a release-specific recipe, but no declared content may be omitted. `provides_capabilities` is a sorted unique set of content capabilities supplied by this release; it is distinct from the client capabilities required to consume the pack.

`payload.member_count` and `payload.total_uncompressed_bytes` count only files below `WFModPack/payload/`; they exclude `manifest.json`, `manifest.sig`, ZIP records, and importer-created marker/journal/seal/state files. Manifest space values are target-independent logical lower bounds with exact constants: `MAX_MANIFEST_BYTES = 4 * 1024 * 1024`, `MAX_SIGNATURE_BYTES = 16 * 1024`, `GENERATED_METADATA_RESERVE = 1 * 1024 * 1024`, `TEMP_WORKING_RESERVE = 8 * 1024 * 1024`, `required_final_bytes = total_uncompressed_bytes + MAX_MANIFEST_BYTES + MAX_SIGNATURE_BYTES + GENERATED_METADATA_RESERVE`, and `required_temporary_bytes = required_final_bytes + TEMP_WORKING_RESERVE`. The already-downloaded `.wfpack` is not counted.

M1B must also recompute a target-volume bound after reading Android `StatFs`: for every actual mapped payload/manifest/signature file and bounded generated marker/journal/seal file, add `round_up(file_size, allocation_unit)`; add one allocation unit for every distinct release directory; then add `max(TEMP_WORKING_RESERVE, 4 * allocation_unit)` for transient metadata replacements. Available bytes before staging must be at least the maximum of this volume-specific temporary bound and manifest `required_temporary_bytes`. The final installed allocation is recomputed the same way without the transient reserve and compared with manifest `required_final_bytes`. Tests cover 4 KiB and 16 KiB allocation units plus 200,000 one-byte members, so directory/allocation overhead cannot hide behind the logical byte total.

The builder accepts arbitrary valid cumulative content IDs; release-specific assertions for exactly 3 characters, 2 modes, 15 equipment items, and 18 mails belong to the later real-release recipe, not the reusable container library.

### Signature envelope and key ID

The signed message is exactly:

```text
ASCII("WFMP1\0") || canonical_manifest_bytes
```

The key ID is `ed25519:` followed by lowercase SHA-256 of the raw 32-byte Ed25519 public key. `manifest.sig` is canonical JSON with exactly:

```json
{
  "format_version": 1,
  "algorithm": "Ed25519",
  "key_id": "ed25519:<64 lowercase hex>",
  "signature_base64": "<canonical padded standard Base64 of 64 bytes>"
}
```

Trusted public-key files add `public_key_base64` to the same version/algorithm/key-ID tuple. Unknown fields, unknown algorithms, non-canonical Base64, a key-ID/public-key mismatch, and an invalid signature all fail closed.

`init-signer` creates a raw 32-byte author key outside the repository and a public trusted-key JSON next to it. The requested signer directory must not exist: initialization creates an owned sibling staging directory, writes/fsyncs both files, syncs the staging directory, then renames it to the requested directory without replacement and syncs the parent. A failure removes only the staging directory identity created by that invocation. It never prompts for or stores a password. The build command receives the private-key path only through `WF_WFPACK_SIGNING_KEY_FILE`, so it is not placed in command history or JSON reports. The private key is never included in a fixture or archive; tests use the public RFC 8032 test seed only inside test code.

### Resource limits

`WfPackLimits` defaults are fixed at:

- 18 GiB complete archive bytes;
- 200,000 total archive members;
- 64 MiB complete central-directory bytes;
- 256 bytes per UTF-8 member name;
- 128 bytes per local or central extra field;
- zero archive/member comment bytes;
- 4 MiB `manifest.json`;
- 16 KiB `manifest.sig`;
- 2 GiB per payload member;
- 16 GiB total uncompressed payload;
- compression method must be stored, so any compressed/uncompressed size mismatch is rejected;
- no member is opened and no unbounded `zipfile` object list is constructed until a hand-parsed EOCD/Zip64 locator/Zip64 EOCD and streaming central-directory pass has bounded names, extras, counts, flags, sizes, offsets, overlaps, and all limits.

### Reference install commit order

The reference model installs only under an explicitly supplied synthetic root:

```text
WorldFlipper/dummy/modpacks/
├── active.json
├── required-persistent-ids.json
├── staging/<transaction-id>/
│   ├── .wfpack-importer.json
│   └── transaction.json
├── quarantine/<manifest-sha256>-<transaction-id>/
└── releases/<manifest-sha256>/
    ├── .wfpack-importer.json
    └── transaction.json
```

The canonical state documents are fixed as follows:

```json
{"schema_version":1,"release_id":"three-characters-two-modes","manifest_sha256":"<64 lowercase hex>","generation":1}
```

for `active.json`;

```json
{"schema_version":1,"persistent_ids":["character:129999","character:139999","character:149999","equipment:8000101","mail:990000001","mode:2001","mode:700099"]}
```

for `required-persistent-ids.json`; and

```json
{"schema_version":1,"manifest_sha256":"<64 lowercase hex>","payload_member_count":1,"payload_total_bytes":1,"payload_set_sha256":"<SHA-256 of canonical payload.members>","transaction_id":"<32 lowercase hex>"}
```

for `complete.json`. Its `payload_set_sha256` preimage is exactly the canonical UTF-8 JSON bytes of the signed manifest's already-sorted `payload.members` array; its count and byte total use the payload-only scope defined above. Transaction IDs are 128 random bits rendered as 32 lowercase hex characters. `active.generation` increments from the last valid active pointer; it is not security-sensitive and does not replace digest or signature validation.

Importer ownership and recovery are bound by these two canonical files:

```json
{"schema_version":1,"owner":"io.starpoint.wfmod.importer","transaction_id":"<32 lowercase hex>","manifest_sha256":"<64 lowercase hex>"}
```

for `.wfpack-importer.json`; and

```json
{"schema_version":1,"owner":"io.starpoint.wfmod.importer","transaction_id":"<32 lowercase hex>","manifest_sha256":"<64 lowercase hex>","phase":"staging","quarantined_release":null}
```

for `transaction.json`. Legal phases are `staging`, `staged`, `quarantine_intent`, `target_quarantined`, `promotion_intent`, `promoted`, and `lock_committed`. `quarantined_release` is either null or the exact normalized relative path `quarantine/<manifest-sha256>-<transaction-id>`. Every phase transition is temp-write → file `fsync` → atomic replace → parent-directory `fsync`. Recovery may move/delete a staging object only when its directory name, marker transaction ID, journal transaction ID, owner, and manifest digest all agree; fuzzy cleanup is forbidden.

It enforces this order:

1. Parse/verify the complete pack, lock, active pointer, active manifest, and all installed release ID/digest pairs before creating staging. A missing lock is equivalent to empty only when there is no active pointer, release, quarantine, staging, or transaction history; otherwise return `repair_required`. A release ID already bound to a different manifest digest is rejected as equivocation.
2. Require `active manifest IDs ⊆ locked IDs`; a smaller/corrupt lock fails closed for controlled repair. Then require `(locked IDs ∪ active manifest IDs) ⊆ candidate manifest provides_persistent_ids`.
3. Create an exclusive staging directory, write/fsync the exact marker and `staging` journal, then copy each verified member.
4. `fsync` every new file and its containing directory.
5. Re-read all staged hashes, write/fsync canonical `complete.json`, and advance the journal to `staged`.
6. Require the game process to be stopped before any release rename. If the target digest already names the same valid complete release, reuse it idempotently. If the exact target is incomplete/corrupt, persist `quarantine_intent`, move only that verified identity to `quarantine/<digest>-<transaction-id>`, sync both parents, then persist `target_quarantined`. Persist `promotion_intent`, rename staging to `releases/<manifest-sha256>` without replacement, sync both source and target parents, and persist `promoted` in the promoted release. If promotion fails after quarantine, recovery restores that exact prior directory and syncs both parents before doing anything else.
7. Atomically advance/fsync `required-persistent-ids.json` to the union. Never shrink it. Persist/fsync `lock_committed` before the content commit.
8. Reassert that the game process is stopped, then atomically replace/fsync `active.json` last; this is the only content-selection commit and no later file is mutated.
9. Re-read the lock, active pointer, target manifest, seal, and startup-critical members before reporting success.

A crash before step 6 leaves only importer-marked staging or an exact quarantined target that recovery can identify. A crash after step 6 leaves an inactive complete release that a retry may reuse. A crash after the lock advances but before `active.json` changes remains retryable because the candidate is cumulative. No failure path mutates an unrelated or valid old release or points active state at an incomplete release. A missing/corrupt lock with prior history is never rebuilt from the candidate; controlled repair may only union IDs from still-valid installed manifests or a separately parsed save ledger.

---

## Task 1: Strict canonical JSON

**Files:**

- Create: `mod-tools/wfpack_json.py`
- Create: `mod-tools/tests/test_wfpack_json.py`

- [ ] **1.1 Write failing unit tests**

Cover exact bytes for objects/arrays/control-character escaping, UTF-16 ordering (`U+1F600` sorts before `U+E000`), UTF-8 non-ASCII output, the safe-integer endpoints, and stable round trips. Cover rejection of BOM, trailing LF/whitespace, duplicate keys, floats/exponents, JSON constants, unsafe integers, non-NFC keys/values, lone surrogates, non-string keys, and non-canonical key order.

- [ ] **1.2 Prove the tests fail for the missing module**

Run:

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_json.py" -v
```

Expected: import failure because `wfpack_json.py` does not exist.

- [ ] **1.3 Implement the narrow API**

Expose:

```python
class CanonicalJsonError(ValueError): ...
def canonical_json_bytes(value: object) -> bytes: ...
def load_canonical_json(raw: bytes, *, label: str = "JSON") -> object: ...
```

Implement escaping directly; do not call the existing offline bundle/character-pack serializers because they allow values or bytes outside this contract. Reject instead of silently normalizing Unicode.

- [ ] **1.4 Run the focused test and hygiene check**

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_json.py" -v
git diff --check
```

- [ ] **1.5 Commit only Task 1 files**

```powershell
git add -- mod-tools/wfpack_json.py mod-tools/tests/test_wfpack_json.py
git commit -m "feat(wfpack): add strict canonical JSON"
```

## Task 2: Manifest and signature document contract

**Files:**

- Create: `mod-tools/wfpack_contract.py`
- Create: `mod-tools/schemas/wfpack-v1.schema.json`
- Create: `mod-tools/schemas/wfpack-signature-v1.schema.json`
- Create: `mod-tools/tests/test_wfpack_contract.py`

- [ ] **2.1 Write failing contract tests**

Build a minimal valid manifest in test helpers. Test every top-level object, exact-field rejection, identifier/UTC/hash/path syntax, sorted-unique sets, exact CN salted logical-path hashing, `key_path_set_sha256`, three complete root counts, the exact archive-to-release mapping and reserved-name collision rejection, three-root non-deduplication, payload-only totals and fixed space formulas, semantic-reference coverage, output hash agreement, provided/retained capabilities, content/mail/persistent-ID closure, mail-key/mail-ID uniqueness, and persistent-ID syntax/uniqueness. Include rejection of `active.json`, locks, save data, staging markers, and out-of-root members.

- [ ] **2.2 Run the red test**

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_contract.py" -v
```

Expected: import failure for `wfpack_contract`.

- [ ] **2.3 Implement the contract API and schemas**

Expose immutable dataclasses for member/signature metadata plus:

```python
class WfPackContractError(ValueError): ...
def parse_manifest(raw: bytes) -> Mapping[str, object]: ...
def validate_manifest(value: Mapping[str, object]) -> tuple[str, ...]: ...
def manifest_sha256(raw: bytes) -> str: ...
def hash_logical_path(logical_path: str) -> str: ...
def classify_payload_path(path: str) -> Literal["common", "medium", "android", "dummy", "modes"]: ...
def release_relative_path(member_path: str) -> PurePosixPath: ...
def parse_signature_document(raw: bytes) -> SignatureDocument: ...
```

`validate_manifest` returns all deterministic validation issues for author diagnostics; `parse_manifest` raises one `WfPackContractError` when any issue exists. Keep JSON Schema and Python semantics aligned, with Python remaining normative for rules JSON Schema cannot express.

- [ ] **2.4 Run focused validation**

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_contract.py" -v
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_json.py" -v
git diff --check
```

- [ ] **2.5 Commit only Task 2 files**

```powershell
git add -- mod-tools/wfpack_contract.py mod-tools/schemas/wfpack-v1.schema.json mod-tools/schemas/wfpack-signature-v1.schema.json mod-tools/tests/test_wfpack_contract.py
git commit -m "feat(wfpack): define the v1 manifest contract"
```

## Task 3: Ed25519 signing, public trust files, and golden signature vector

**Files:**

- Create: `mod-tools/wfpack_signing.py`
- Create: `mod-tools/tests/test_wfpack_signing.py`
- Create: `mod-tools/tests/fixtures/wfpack/v1/manifest.json`
- Create: `mod-tools/tests/fixtures/wfpack/v1/manifest.sig`
- Create: `mod-tools/tests/fixtures/wfpack/v1/trusted-key.json`
- Create: `mod-tools/tests/fixtures/wfpack/v1/signing-vector.json`
- Modify: `mod-tools/requirements.txt`

- [ ] **3.1 Add failing signing and key-lifecycle tests**

Use RFC 8032 test vector 1's seed only inside the Python test. Assert the exact raw public key, key ID, canonical manifest bytes, manifest SHA-256, domain-separated 64-byte signature, canonical signature document, and trusted-key document against `signing-vector.json`. Test wrong domain, key, key ID, signature, algorithm, length, Base64 alphabet/padding, extra fields, reparse/symlink key paths, existing destinations, key paths inside the repository, and private-key path leakage in reports.

- [ ] **3.2 Run the red test**

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_signing.py" -v
```

Expected: import failure for `wfpack_signing`.

- [ ] **3.3 Declare and implement the signing dependency**

Update the requirements comment and add `cryptography>=49,<50`, the currently validated stable line. Expose:

```python
SIGNATURE_DOMAIN = b"WFMP1\0"
def key_id(public_key_raw: bytes) -> str: ...
def create_signer(directory: Path, *, forbidden_roots: Sequence[Path]) -> PublicKeyInfo: ...
def load_private_key(path: Path, *, forbidden_roots: Sequence[Path]) -> Ed25519PrivateKey: ...
def sign_manifest(canonical_manifest: bytes, private_key: Ed25519PrivateKey) -> bytes: ...
def load_trusted_key(raw: bytes) -> TrustedKey: ...
def verify_manifest_signature(canonical_manifest: bytes, signature_raw: bytes, trusted_keys: Mapping[str, TrustedKey]) -> SignatureInfo: ...
```

Private-key creation uses an exclusive regular-file handle, rejects reparse/symlink paths, writes exactly 32 raw bytes, flushes and `fsync`s before publishing the public document, and never overwrites an existing signer. On POSIX set/check mode `0600`; on Windows reject reparse points and document that the signer directory must remain inside the author's ACL-protected profile. Do not print or serialize the key bytes or private path.

- [ ] **3.4 Run signing, dependency, and canonical tests**

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_signing.py" -v
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_json.py" -v
python -m pip check
git diff --check
```

- [ ] **3.5 Commit Task 3**

```powershell
git add -- mod-tools/wfpack_signing.py mod-tools/tests/test_wfpack_signing.py mod-tools/tests/fixtures/wfpack/v1/manifest.json mod-tools/tests/fixtures/wfpack/v1/manifest.sig mod-tools/tests/fixtures/wfpack/v1/trusted-key.json mod-tools/tests/fixtures/wfpack/v1/signing-vector.json mod-tools/requirements.txt
git commit -m "feat(wfpack): add Ed25519 signing and golden vectors"
```

## Task 4: Deterministic Zip64 writer and public verifier

**Files:**

- Create: `mod-tools/wfpack_archive.py`
- Create: `mod-tools/tests/test_wfpack_archive.py`
- Create: `mod-tools/tests/fixtures/wfpack/v1/payload/production/upload/fb/da3504e1e5ed8fba45b9fa15b0cb224321b624`
- Create: `mod-tools/tests/fixtures/wfpack/v1/payload/production/medium_upload/b1/5ee70da5386dbd6ff3f0463c1e848d04fc82ee`
- Create: `mod-tools/tests/fixtures/wfpack/v1/payload/production/android_upload/62/2f4f4bdcae972fa231e39cd13faf6d696fdb85`
- Create: `mod-tools/tests/fixtures/wfpack/v1/payload/dummy-overlay.json`
- Create: `mod-tools/tests/fixtures/wfpack/v1/payload/mode-variants.json`
- Create: `mod-tools/tests/fixtures/wfpack/v1/golden-v1.json`

- [ ] **4.1 Write failing archive tests**

Fixture bytes are exact and contain no trailing newline. Logical paths `fixture/common.bin`, `fixture/medium.bin`, and `fixture/android.bin` map through the fixed CN salt to the three file paths above; their bytes are ASCII `wfpack-common-fixture-v1`, `wfpack-medium-fixture-v1`, and `wfpack-android-fixture-v1`. `dummy-overlay.json` is `{"operations":[],"schema_version":1}`; `mode-variants.json` is `{"modes":[],"schema_version":1}`. Assert two archives are byte-identical. Inspect local and central records with an independent raw-record parser to prove stored compression, fixed timestamp/mode/flags/order, per-entry Zip64 sizes, and Zip64 EOCD. Test truncation, overlap, trailing bytes, comments, data descriptors, encryption flags, extra/missing/duplicate/case-colliding members, path traversal/backslashes, directory/symlink records, non-stored methods, non-canonical or malformed runtime envelopes, metadata drift, size/hash drift, untrusted signature, source mutation between scan and copy, output already existing, and every archive/central-directory/name/extra/member/total `WfPackLimits` boundary. After the independent parser passes, freeze the exact archive SHA-256 and record metadata into `golden-v1.json`, then add the permanent regression assertion.

- [ ] **4.2 Run the red archive test**

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_archive.py" -v
```

Expected: import failure for `wfpack_archive`.

- [ ] **4.3 Implement deterministic writing and fail-closed verification**

Expose:

```python
@dataclass(frozen=True)
class WfPackLimits: ...
@dataclass(frozen=True)
class PayloadSource: ...
@dataclass(frozen=True)
class VerifiedWfPack: ...
def write_wfpack(output: Path, *, manifest: bytes, signature: bytes, payload: Sequence[PayloadSource]) -> ArchiveReport: ...
def verify_wfpack(path: Path, *, trusted_keys: Mapping[str, TrustedKey], limits: WfPackLimits = WfPackLimits()) -> VerifiedWfPack: ...
```

Use a single bound archive handle for verification. Before constructing `zipfile.ZipFile`, hand-parse and bound EOCD, Zip64 locator/EOCD, the central-directory byte range, and every fixed/name/extra record. Validate the complete central directory and local-header layout before opening manifest/signature, verify canonical documents and Ed25519 before reading payload bodies, then stream-hash every declared payload. Writer inputs carry a pre-scan identity/size/hash and must match again while copied. Open output with exclusive create; on failure remove only the exact file identity owned by this invocation.

Reuse the proven ideas in `wf_offline_zip.py` (fixed metadata, Zip64 EOCD, one-handle verification, source identity checks) without changing its 10 GB archive API or production constants in this task.

- [ ] **4.4 Run focused and regression tests**

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_archive.py" -v
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_offline_zip.py" -v
git diff --check
```

- [ ] **4.5 Commit Task 4**

```powershell
git add -- mod-tools/wfpack_archive.py mod-tools/tests/test_wfpack_archive.py mod-tools/tests/fixtures/wfpack/v1/payload mod-tools/tests/fixtures/wfpack/v1/golden-v1.json
git commit -m "feat(wfpack): add deterministic Zip64 archives"
```

## Task 5: Payload-derived builder and no-prompt CLI

**Files:**

- Create: `mod-tools/wfpack_build.py`
- Create: `mod-tools/wfpack_cli.py`
- Create: `mod-tools/tests/test_wfpack_build.py`
- Create: `mod-tools/tests/test_wfpack_cli.py`
- Create: `mod-tools/tests/fixtures/wfpack/v1/manifest-template.json`

- [ ] **5.1 Write failing builder tests**

Test scan-to-manifest derivation, deterministic member order, three roots, required dummy/mode canonical envelopes, table/asset reference reconciliation, forbidden template-derived fields, excluded/backup files, symlinks/reparse points, source drift, output overlap, explicit credential fields in author metadata, signer-key/source identity overlap, pre-existing output, wrong/missing key environment, previous-archive/version/retained-ID continuity, and mandatory build-after-write verification. A v1 template requires empty `retains_persistent_ids`; version >1 requires a trusted verified previous archive, an incremented version, and exact prior `provides_persistent_ids`. Include opaque hashed binary bytes containing `password` and `-----BEGIN`, and a valid game field named `token`; all must remain legal because substring or generic-name scanning game data would create false positives. Patch the public verifier to fail and assert the builder removes only its owned incomplete output.

- [ ] **5.2 Write failing CLI tests**

Invoke `main(argv, environ=...)` without a subprocess for most cases and one subprocess smoke test for exit/output behavior. Cover `init-signer`, `build`, and `verify`; no-password/no-prompt behavior; stable last-line canonical JSON; exit codes `0` success, `2` contract/input, `3` signature/trust, and `4` I/O/source drift; stdout/stderr free of private-key bytes/path and unrelated environment secrets.

- [ ] **5.3 Run the red tests**

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_build.py" -v
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_cli.py" -v
```

Expected: import failures for the missing builder and CLI.

- [ ] **5.4 Implement builder orchestration**

Expose:

```python
def scan_payload(payload_root: Path) -> PayloadScan: ...
def build_manifest(template_raw: bytes, scan: PayloadScan) -> bytes: ...
def build_wfpack(payload_root: Path, template_path: Path, output: Path, *, private_key_path: Path, previous_archive_path: Path | None = None, previous_trusted_keys: Mapping[str, TrustedKey] | None = None, trusted_output: Path | None = None) -> BuildReport: ...
```

The scan must return `excluded == ()`; a known backup file is an error, not an ignored input. Compute all member size/hash/count/space fields from source bytes. The fixed path grammar admits no credential filename. Parse the template/author metadata with their exact schemas; parse `dummy-overlay.json` and `mode-variants.json` only with the canonical envelope contract explicitly fixed above. Reject explicit credential fields in author metadata (`password`, `private_key`, `private_key_pem`, `keystore_password`) and any payload file that is the same filesystem identity as the signing key. Do not blacklist the generic game term `token`. Treat hashed table/SWF/image/audio bytes and nested runtime entries as opaque signed content gated by exact semantic declaration, source identity, size, and SHA-256 rather than fallible secret substrings. After writing, call the public `verify_wfpack`, compare the resulting manifest digest/archive digest/member summary to the build report, and only then return success.

- [ ] **5.5 Implement the thin CLI**

Commands:

```powershell
python -X utf8 mod-tools/wfpack_cli.py init-signer --directory C:\Users\12101\.wfpack-signer
$env:WF_WFPACK_SIGNING_KEY_FILE = 'C:\Users\12101\.wfpack-signer\wfpack-ed25519.key'
python -X utf8 mod-tools/wfpack_cli.py build --payload-root mod-tools/tests/fixtures/wfpack/v1/payload --template mod-tools/tests/fixtures/wfpack/v1/manifest-template.json --output out/wfpack/golden.wfpack
python -X utf8 mod-tools/wfpack_cli.py verify --archive out/wfpack/golden.wfpack --trusted-key C:\Users\12101\.wfpack-signer\trusted-key.json
```

`build` has no private-key command-line option and never prompts. Cumulative versions after v1 additionally pass `--previous-archive out/wfpack/prior.wfpack --trusted-key C:\Users\12101\.wfpack-signer\trusted-key.json`; the builder calls the same public archive/signature verifier before using its manifest, and the first release rejects the previous-archive option. Every command emits a human-readable summary followed by one canonical JSON result line suitable for automation.

- [ ] **5.6 Run focused integration tests**

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_build.py" -v
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_cli.py" -v
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_*.py" -v
git diff --check
```

- [ ] **5.7 Commit Task 5**

```powershell
git add -- mod-tools/wfpack_build.py mod-tools/wfpack_cli.py mod-tools/tests/test_wfpack_build.py mod-tools/tests/test_wfpack_cli.py mod-tools/tests/fixtures/wfpack/v1/manifest-template.json
git commit -m "feat(wfpack): build and verify signed packages"
```

## Task 6: Persistent-ID and crash-order reference install model

**Files:**

- Create: `mod-tools/wfpack_install_model.py`
- Create: `mod-tools/tests/test_wfpack_install_model.py`
- Create: `mod-tools/tests/fixtures/wfpack/v1/install-events.json`

- [ ] **6.1 Write the state-machine tests first**

Use an in-memory durable-filesystem fake with an ordered event log. Assert the exact archive-to-release path vector, marker/journal schemas and phase barriers, happy-path sequence, game-stopped guards, active-last ordering, lock monotonicity, release digest naming, seal/digest preimages, 4 KiB/16 KiB allocation-aware space bounds, idempotent reinstall, inactive complete-release reuse, exact-target quarantine/restore, and post-commit reread. Inject a crash/failure before and after every durable event and verify recovery invariants after each prefix. Explicitly test a downgrade missing a locked ID, an illegally shrunken lock relative to the active manifest, missing/corrupt lock with and without prior history, lock-ahead-of-active recovery, same release ID bound to another digest, game-running refusal, corrupt existing release, marker/nonce disagreement, staging collision, path collision, insufficient logical/volume-specific space, pointer corruption, and replace/fsync failure.

- [ ] **6.2 Run the red model test**

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_install_model.py" -v
```

Expected: import failure for `wfpack_install_model`.

- [ ] **6.3 Implement only a reference model, not a live installer**

Expose:

```python
class DurableFileOps(Protocol): ...
@dataclass(frozen=True)
class InstalledState: ...
@dataclass(frozen=True)
class InstallPlan: ...
@dataclass(frozen=True)
class InstallResult: ...
def calculate_volume_space(verified: VerifiedWfPack, *, allocation_unit: int) -> SpaceRequirement: ...
def plan_install(verified: VerifiedWfPack, state: InstalledState) -> InstallPlan: ...
def execute_install(plan: InstallPlan, *, ops: DurableFileOps) -> InstallResult: ...
def recover_install(root: PurePosixPath, *, ops: DurableFileOps) -> RecoveryReport: ...
```

`DurableFileOps` includes an explicit `assert_game_stopped()` barrier plus exclusive directory creation, exact-identity marker checks, streaming verified writes, file/directory sync, no-replace rename, atomic file replacement, and bounded reread methods. There is deliberately no default OS-backed implementation and no CLI install command in M1A. M1B must implement Android-specific `fsync`/rename/SAF behavior and pass the same event/invariant vectors.

- [ ] **6.4 Run the exhaustive model tests**

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_install_model.py" -v
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_*.py" -v
git diff --check
```

- [ ] **6.5 Commit Task 6**

```powershell
git add -- mod-tools/wfpack_install_model.py mod-tools/tests/test_wfpack_install_model.py mod-tools/tests/fixtures/wfpack/v1/install-events.json
git commit -m "feat(wfpack): model crash-safe import transactions"
```

## Task 7: Operator documentation, wrapper, and final verification

**Files:**

- Create: `mod-tools/build-wfpack.bat`
- Create: `mod-tools/docs/WFPack构建与校验.md`
- Create: `mod-tools/tests/test_wfpack_wrapper.py`
- Modify: `mod-tools/README.md`

- [ ] **7.1 Add a failing wrapper smoke test**

Verify the batch file locates its own repository root, uses `python -X utf8`, forwards arguments without embedding a key/password, propagates the Python exit code, and works from a directory outside the repository.

- [ ] **7.2 Run the red wrapper test**

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_wrapper.py" -v
```

- [ ] **7.3 Add the wrapper and operator guide**

Document signer creation/backup, environment setup, prepared payload tree, template fields versus derived fields, build, independent verify, JSON result fields, recovery from every exit code, golden-vector purpose, key rotation policy, and the exact statement that M1A does not install into a phone. Update `mod-tools/README.md` to list `cryptography` as the package-signing dependency and link the guide.

- [ ] **7.4 Run the complete verification matrix**

```powershell
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_wfpack_*.py" -v
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_offline_zip.py" -v
python -X utf8 -m unittest discover -s mod-tools/tests -p "test_offline_store.py" -v
python -m pip check
npm run test:python
npm run verify
npm audit --audit-level=high
npm --prefix admin audit --audit-level=high
git diff --check
git status --short
```

Acceptance evidence must include:

- focused `.wfpack` test counts;
- the two-build byte-identical archive SHA-256;
- the golden manifest SHA-256, public key ID, and signature verification result (never the private seed/key);
- crash-prefix model case count and zero invariant failures;
- full repository verification result;
- a status listing proving no user WIP was staged or modified by this work.

- [ ] **7.5 Commit Task 7 only after all gates pass**

```powershell
git add -- mod-tools/build-wfpack.bat mod-tools/docs/WFPack构建与校验.md mod-tools/tests/test_wfpack_wrapper.py mod-tools/README.md
git commit -m "docs(wfpack): add the author build workflow"
```

## M1A completion and M1B handoff

M1A is complete only when every command above passes and the branch contains no real content pack, APK, private key, live-store mutation, or unrelated WIP.

The next written plan, M1B, will create `android/wfmod-importer/`, first importing these exact checked-in artifacts:

- canonical manifest bytes;
- manifest SHA-256;
- trusted public-key document and key ID;
- signature document and domain-separated verification result;
- deterministic archive SHA-256/member metadata;
- install event ordering and crash-prefix invariants.

Only after the Android implementation passes those shared vectors should it be allowed to touch a disposable emulator instance. Real three-character/two-mode content assembly and the patched game APK remain later, separately gated work.
