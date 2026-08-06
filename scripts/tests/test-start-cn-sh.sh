#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LAUNCHER="$ROOT/scripts/start-cn.sh"
LOCK_RESOLVER="$ROOT/scripts/resolve-local-cdn-publish-lock.mjs"
passed=0

pass() {
    passed=$((passed + 1))
    printf '[PASS] %s\n' "$1"
}

assert_not_contains() {
    local pattern="$1"
    local message="$2"
    if grep -Eq -- "$pattern" "$LAUNCHER"; then
        printf '[FAIL] %s\n' "$message" >&2
        exit 1
    fi
    pass "$message"
}

assert_contains() {
    local pattern="$1"
    local message="$2"
    if ! grep -Eq -- "$pattern" "$LAUNCHER"; then
        printf '[FAIL] %s\n' "$message" >&2
        exit 1
    fi
    pass "$message"
}

assert_not_contains '(^|[[:space:]])pkill([[:space:]]|$)' 'launcher never uses process-name-wide pkill'
assert_not_contains '(^|[[:space:]])nohup([[:space:]]|$)' 'launcher does not detach an unowned background process'
assert_not_contains '(^|[[:space:]])pgrep([[:space:]]|$)' 'launcher does not infer ownership from a broad process match'
assert_contains 'exec[[:space:]]+node' 'launcher keeps the CN server in the supervised foreground'
assert_contains '--check-only' 'launcher exposes a read-only preflight mode'
assert_contains 'CN_LISTEN_PORT' 'launcher derives the checked port from environment configuration'
assert_contains '20\.19\.0' 'launcher enforces the supported Node baseline'
assert_contains '\.cn-server-build-stamp' 'launcher uses an explicit successful-build stamp'
assert_contains 'resolve-local-cdn-publish-lock\.mjs' 'launcher resolves the publication lock through shared CDN_DIR semantics'
if ! grep -Eq '\.wf-local-1\.4\.312\.lock' "$LOCK_RESOLVER"; then
    printf '[FAIL] lock resolver does not name the fixed local publication lock\n' >&2
    exit 1
fi
pass 'launcher refuses the fixed local publication lock'

lock_checks="$(grep -Ec '^[[:space:]]*assert_no_local_cdn_publish_lock([[:space:]]|$)' "$LAUNCHER")"
if ((lock_checks < 2)); then
    printf '[FAIL] launcher must check the publication lock before preflight and immediately before exec\n' >&2
    exit 1
fi
pass 'launcher checks the publication lock twice'

ENV_FIXTURE="$(mktemp)"
trap 'rm -f "$ENV_FIXTURE"' EXIT

assert_resolved_lock() {
    local configured="$1"
    local actual="$2"
    if ! node - "$actual" "$ROOT" "$configured" <<'NODE'
const path = require('node:path')
const [, , actual, root, configured] = process.argv
const cdn = path.isAbsolute(configured)
  ? path.normalize(configured)
  : path.resolve(root, configured)
const expected = path.join(cdn, 'cn', '.wf-local-1.4.312.lock')
if (path.normalize(actual) !== expected) {
  console.error(`resolved lock mismatch: ${actual} != ${expected}`)
  process.exit(1)
}
NODE
    then
        printf '[FAIL] CDN_DIR=%s did not resolve the expected publication lock\n' "$configured" >&2
        exit 1
    fi
    pass "CDN_DIR=$configured resolves the expected publication lock"
}

: >"$ENV_FIXTURE"
default_lock="$(env -u CDN_DIR node --env-file="$ENV_FIXTURE" "$LOCK_RESOLVER" "$ROOT")"
assert_resolved_lock '.cdn' "$default_lock"

printf 'CDN_DIR="launcher-fixture-cdn"\n' >"$ENV_FIXTURE"
custom_lock="$(env -u CDN_DIR node --env-file="$ENV_FIXTURE" "$LOCK_RESOLVER" "$ROOT")"
assert_resolved_lock 'launcher-fixture-cdn' "$custom_lock"

printf '[PASS] Linux launcher safety suite (%d assertions)\n' "$passed"
