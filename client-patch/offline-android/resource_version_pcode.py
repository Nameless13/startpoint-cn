#!/usr/bin/env python3
"""Patch the locked offline SWF full resource version with pure P-code.

The release stage is deliberately independent from the ignored ``work`` tree.
It resolves the target and the active DummyRemote method by name, checks both
canonical P-code and raw ABC locks, performs one FFDec replacement, reopens the
result, and publishes only after the owned transaction has been removed.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
CLIENT_PATCH = HERE.parent
DUAL_FORM = CLIENT_PATCH / "dual-form-v1"
ABYSS_BUILD_PATH = CLIENT_PATCH / "abyss-mode-equipment" / "build_apk.py"

RESOURCE_SITE_ID = "full-resource-version"
RESOURCE_CLASS = "pinball.config.core.DevConfig"
RESOURCE_METHOD = "boot_ffc6#$script364/$init"
SOURCE_VERSION = "1.4.54"
TARGET_VERSION = "1.4.196"
DUMMY_REMOTE_METHOD = (
    "pinball.context.remote.dummy:DummyRemote/debugUnlinkTwitter"
)
DUMMY_REMOTE_LOCK_KEY = "DummyRemote/debugUnlinkTwitter"

LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")
OFFSET_LABEL = re.compile(r"\bofs[0-9A-Fa-f]+\b")
PUSHSTRING_LINE = re.compile(
    r'(?mi)^(?P<indent>[ \t]*)(?P<opcode>pushstring)'
    r'[ \t]+"(?P<value>[^"\r\n]*)"[ \t]*$'
)

RESOURCE_LOCK_FIELDS = frozenset(
    {
        "site_id",
        "class_name",
        "method_name",
        "source_version",
        "target_version",
        "before_pcode_sha256",
        "after_pcode_sha256",
        "before_abc_sha256",
        "after_abc_sha256",
    }
)


class ResourceVersionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ResourceVersionReport:
    output_path: Path
    input_sha256: str
    output_sha256: str
    source_version: str
    output_version: str
    is_full_package: bool
    verified: bool


def _load_helper(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ResourceVersionError(f"cannot load tracked helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ABC_METHODS = _load_helper(
    "offline_resource_version_abc_methods", DUAL_FORM / "abc_methods.py"
)
PUBLISH_TOOLS = _load_helper(
    "offline_resource_version_publish_tools", ABYSS_BUILD_PATH
)


def canonical_pcode(text: str) -> str:
    """Normalize only FFDec offset-label renumbering, preserving topology."""
    value = str(text)
    definitions = re.findall(
        r"(?m)^[ \t]*(ofs[0-9A-Fa-f]+):[ \t]*$", value
    )
    normalized = [label.lower() for label in definitions]
    if len(normalized) != len(set(normalized)):
        raise ResourceVersionError(
            "P-code contains duplicate offset label definitions"
        )
    labels = {label: f"L{index}" for index, label in enumerate(normalized)}
    referenced = {
        match.group(0).lower() for match in OFFSET_LABEL.finditer(value)
    }
    undefined = sorted(referenced - set(labels))
    if undefined:
        raise ResourceVersionError(
            f"P-code contains undefined offset label references: {undefined}"
        )
    return OFFSET_LABEL.sub(
        lambda match: labels[match.group(0).lower()], value
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_pcode(text: str) -> str:
    return hashlib.sha256(canonical_pcode(text).encode("utf-8")).hexdigest()


def _sha256_abc(code: bytes) -> str:
    return hashlib.sha256(bytes(code)).hexdigest()


def _property_line(name: str) -> str:
    return f'initproperty QName(PackageNamespace(""),"{name}")'


def _dev_config_line() -> str:
    return (
        'getlex QName(PackageNamespace("pinball.config.core"),'
        '"DevConfig")'
    )


def _pushstring_matches(block: str, value: str) -> list[re.Match[str]]:
    return [
        match
        for match in PUSHSTRING_LINE.finditer(str(block))
        if match.group("value") == value
    ]


def _resource_version_value(block: str) -> str:
    lines = [line.strip() for line in str(block).splitlines()]
    full_property = _property_line("fullResourceVersion")
    full_indexes = [
        index for index, line in enumerate(lines) if line == full_property
    ]
    if len(full_indexes) != 1:
        raise ResourceVersionError(
            "fullResourceVersion property count mismatch"
        )
    full_index = full_indexes[0]
    if full_index < 2 or lines[full_index - 2] != _dev_config_line():
        raise ResourceVersionError(
            "fullResourceVersion owner sequence mismatch"
        )
    version_line = PUSHSTRING_LINE.fullmatch(lines[full_index - 1])
    if version_line is None:
        raise ResourceVersionError(
            "fullResourceVersion assignment is not a direct PushString"
        )

    full_package_property = _property_line("isFullPackage")
    full_package_indexes = [
        index
        for index, line in enumerate(lines)
        if line == full_package_property
    ]
    if len(full_package_indexes) != 1:
        raise ResourceVersionError("isFullPackage property count mismatch")
    full_package_index = full_package_indexes[0]
    if (
        full_package_index < 2
        or lines[full_package_index - 2] != _dev_config_line()
        or lines[full_package_index - 1].lower() != "pushtrue"
        or full_package_index >= full_index
    ):
        raise ResourceVersionError("isFullPackage=true semantics changed")
    return version_line.group("value")


def _verify_resource_block(block: str, *, expected: str) -> None:
    if expected not in (SOURCE_VERSION, TARGET_VERSION):
        raise ResourceVersionError("unsupported release resource version")
    actual = _resource_version_value(block)
    matches = _pushstring_matches(block, expected)
    if actual != expected or len(matches) != 1:
        raise ResourceVersionError(
            f"fullResourceVersion mismatch: expected {expected!r}"
        )


def patch_resource_version(
    block: str,
    *,
    source: str = SOURCE_VERSION,
    target: str = TARGET_VERSION,
) -> str:
    """Replace exactly one locked fullResourceVersion P-code literal."""
    if source != SOURCE_VERSION or target != TARGET_VERSION:
        raise ResourceVersionError(
            "resource-version stage only supports 1.4.54 -> 1.4.196"
        )
    text = str(block)
    _verify_resource_block(text, expected=source)
    source_matches = _pushstring_matches(text, source)
    target_matches = _pushstring_matches(text, target)
    if len(source_matches) != 1 or target_matches:
        raise ResourceVersionError("resource-version anchor count mismatch")
    match = source_matches[0]
    output = text[: match.start("value")] + target + text[match.end("value") :]
    _verify_resource_block(output, expected=target)
    return output


def _method_blocks(text: str) -> tuple[str, ...]:
    lines = str(text).splitlines()
    result: list[str] = []
    for start, line in enumerate(lines):
        if line.strip() != "method":
            continue
        indent = line[: len(line) - len(line.lstrip())]
        terminator = f"{indent}end ; method"
        for end in range(start + 1, len(lines)):
            if lines[end] == terminator:
                result.append(
                    textwrap.dedent("\n".join(lines[start : end + 1]))
                    + "\n"
                )
                break
    return tuple(result)


def _extract_resource_initializer(exported_pcode: str) -> str:
    """Extract the unique DevConfig script initializer by semantics."""
    candidates = [
        block
        for block in _method_blocks(exported_pcode)
        if '"isFullPackage"' in block
        and '"fullResourceVersion"' in block
    ]
    if len(candidates) != 1:
        raise ResourceVersionError(
            "expected exactly one DevConfig resource initializer, "
            f"found {len(candidates)}"
        )
    block = candidates[0]
    _resource_version_value(block)
    return block


def _resource_lock(
    lock: Mapping[str, Any],
) -> tuple[Mapping[str, str], str]:
    if not isinstance(lock, Mapping):
        raise ResourceVersionError("resource-version lock must be a mapping")
    if lock.get("schema_version") != 4 or lock.get("status") != "accepted":
        raise ResourceVersionError(
            "resource-version lock must be accepted schema 4"
        )
    entry = lock.get("resource_version")
    if not isinstance(entry, Mapping) or set(entry) != RESOURCE_LOCK_FIELDS:
        raise ResourceVersionError("resource_version lock schema mismatch")
    expected_values = {
        "site_id": RESOURCE_SITE_ID,
        "class_name": RESOURCE_CLASS,
        "method_name": RESOURCE_METHOD,
        "source_version": SOURCE_VERSION,
        "target_version": TARGET_VERSION,
    }
    for field, expected in expected_values.items():
        if entry.get(field) != expected:
            raise ResourceVersionError(
                f"resource_version lock identity mismatch at {field}"
            )
    for field in (
        "before_pcode_sha256",
        "after_pcode_sha256",
        "before_abc_sha256",
        "after_abc_sha256",
    ):
        if LOWER_SHA256.fullmatch(str(entry.get(field, ""))) is None:
            raise ResourceVersionError(f"invalid resource_version {field}")
    if hmac.compare_digest(
        str(entry["before_pcode_sha256"]),
        str(entry["after_pcode_sha256"]),
    ):
        raise ResourceVersionError("resource-version P-code lock is unchanged")
    if hmac.compare_digest(
        str(entry["before_abc_sha256"]),
        str(entry["after_abc_sha256"]),
    ):
        raise ResourceVersionError("resource-version ABC lock is unchanged")

    offline = lock.get("offline_method_sha256")
    if not isinstance(offline, Mapping):
        raise ResourceVersionError("offline method lock is missing")
    baseline_resource = str(offline.get(RESOURCE_METHOD, ""))
    dummy_hash = str(offline.get(DUMMY_REMOTE_LOCK_KEY, ""))
    if LOWER_SHA256.fullmatch(baseline_resource) is None:
        raise ResourceVersionError("baseline resource method lock is missing")
    if not hmac.compare_digest(
        baseline_resource, str(entry["before_abc_sha256"])
    ):
        raise ResourceVersionError(
            "resource before ABC lock disagrees with offline baseline"
        )
    if LOWER_SHA256.fullmatch(dummy_hash) is None:
        raise ResourceVersionError("DummyRemote method lock is missing")
    return MappingProxyType(dict(entry)), dummy_hash


def _subprocess_runner(
    command,
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: int,
):
    completed = subprocess.run(
        [str(part) for part in command],
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise ResourceVersionError(
            f"FFDec command failed ({completed.returncode}): "
            f"{completed.stderr[-1000:]}"
        )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _run(
    command,
    *,
    cwd: Path,
    profile_dir: Path,
    runner,
    timeout: int,
) -> None:
    environment = os.environ.copy()
    environment["APPDATA"] = str(profile_dir.resolve())
    result = runner(
        command, cwd=cwd, env=environment, timeout=timeout
    )
    if isinstance(result, Mapping) and int(result.get("returncode", 0)) != 0:
        raise ResourceVersionError(
            f"FFDec command failed: {result.get('returncode')}"
        )


def _export_resource_class(
    swf: Path,
    export_root: Path,
    *,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    cwd: Path,
    runner,
    timeout: int,
) -> None:
    _run(
        [
            str(java),
            "-Xmx4g",
            "-jar",
            str(ffdec),
            "-air",
            "-format",
            "script:pcode",
            "-selectclass",
            RESOURCE_CLASS,
            "-export",
            "script",
            str(export_root),
            str(swf),
        ],
        cwd=cwd,
        profile_dir=profile_dir,
        runner=runner,
        timeout=timeout,
    )


def _read_exported_resource(export_root: Path) -> str:
    source = (
        Path(export_root)
        / "scripts"
        / Path(*RESOURCE_CLASS.split(".")).with_suffix(".pcode")
    )
    if not source.is_file():
        raise ResourceVersionError(
            f"missing exported P-code for {RESOURCE_CLASS}"
        )
    try:
        return _extract_resource_initializer(
            source.read_text(encoding="utf-8")
        )
    except OSError as exc:
        raise ResourceVersionError(str(exc)) from exc


def _replace_one(
    source: Path,
    destination: Path,
    replacement: Path,
    body_index: int,
    *,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    cwd: Path,
    runner,
    timeout: int,
) -> None:
    _run(
        [
            str(java),
            "-Xmx4g",
            "-jar",
            str(ffdec),
            "-air",
            "-onerror",
            "abort",
            "-replace",
            str(source),
            str(destination),
            RESOURCE_CLASS,
            str(replacement),
            str(body_index),
        ],
        cwd=cwd,
        profile_dir=profile_dir,
        runner=runner,
        timeout=timeout,
    )
    if not destination.is_file():
        raise ResourceVersionError(
            "FFDec did not create the resource-version stage"
        )


def _method_refs(swf: Path):
    try:
        index = ABC_METHODS.index_swf_methods(swf)
        resource = index.require_ref(RESOURCE_METHOD)
        dummy = index.require_ref(DUMMY_REMOTE_METHOD)
    except Exception as exc:
        raise ResourceVersionError(
            "resource-version method identity resolution failed"
        ) from exc
    return resource, dummy


def _require_raw_hash(actual_code: bytes, expected: str, label: str) -> None:
    if not hmac.compare_digest(_sha256_abc(actual_code), expected):
        raise ResourceVersionError(f"{label} raw ABC hash mismatch")


def _verify_reopened_swf(
    swf: Path,
    entry: Mapping[str, str],
    dummy_hash: str,
    *,
    export_root: Path,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    cwd: Path,
    runner,
    timeout: int,
) -> None:
    resource_ref, dummy_ref = _method_refs(swf)
    _require_raw_hash(
        resource_ref.code,
        str(entry["after_abc_sha256"]),
        "resource-version reopen",
    )
    _require_raw_hash(
        dummy_ref.code, dummy_hash, "DummyRemote reopen"
    )
    _export_resource_class(
        swf,
        export_root,
        ffdec=ffdec,
        java=java,
        profile_dir=profile_dir,
        cwd=cwd,
        runner=runner,
        timeout=timeout,
    )
    block = _read_exported_resource(export_root)
    _verify_resource_block(block, expected=TARGET_VERSION)
    if not hmac.compare_digest(
        _sha256_pcode(block), str(entry["after_pcode_sha256"])
    ):
        raise ResourceVersionError(
            "resource-version reopen canonical P-code hash mismatch"
        )


def _validate_stage_paths(
    source_swf: Path,
    output_swf: Path,
    ffdec: Path,
    java: Path,
    work_dir: Path,
    profile_dir: Path,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    source = Path(source_swf).resolve()
    output = Path(output_swf).resolve()
    ffdec_path = Path(ffdec).resolve()
    java_path = Path(java).resolve()
    work = Path(work_dir).resolve()
    profile = Path(profile_dir).resolve()
    if os.path.normcase(str(source)) == os.path.normcase(str(output)):
        raise ResourceVersionError("source and output SWF must differ")
    if not source.is_file():
        raise ResourceVersionError(f"source SWF is missing: {source}")
    if os.path.lexists(output):
        try:
            if os.path.samefile(source, output):
                raise ResourceVersionError(
                    "source and output SWF are filesystem aliases"
                )
        except OSError:
            pass
        raise ResourceVersionError(f"output SWF already exists: {output}")
    for label, directory in (("work", work), ("profile", profile)):
        try:
            directory.relative_to(output)
        except ValueError:
            continue
        raise ResourceVersionError(
            f"output SWF cannot equal or contain the {label} directory"
        )
    for label, path in (("FFDec", ffdec_path), ("Java", java_path)):
        if not path.is_file():
            raise ResourceVersionError(f"{label} tool is missing: {path}")
    for label, directory in (("work", work), ("profile", profile)):
        if directory.exists() and not directory.is_dir():
            raise ResourceVersionError(
                f"{label} path is not a directory: {directory}"
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    profile.mkdir(parents=True, exist_ok=True)
    return source, output, ffdec_path, java_path, work, profile


def _copy_snapshot(source: Path, destination: Path) -> None:
    with source.open("rb") as input_handle, destination.open(
        "xb"
    ) as output_handle:
        shutil.copyfileobj(input_handle, output_handle, 1024 * 1024)
        output_handle.flush()
        os.fsync(output_handle.fileno())


def _assert_source_hash(source: Path, expected: str) -> None:
    try:
        actual = _sha256_file(source)
    except OSError as exc:
        raise ResourceVersionError(
            "source SWF became unreadable during resource-version stage"
        ) from exc
    if not hmac.compare_digest(actual, expected):
        raise ResourceVersionError(
            "source SWF changed during resource-version stage"
        )


def _require_handle_bound_publish_support() -> None:
    try:
        PUBLISH_TOOLS._require_handle_bound_publish_support()
    except PUBLISH_TOOLS.BuildError as exc:
        raise ResourceVersionError(str(exc)) from exc


def _stage_output_sibling(
    source: Path, destination: Path, expected_hash: str
):
    try:
        return PUBLISH_TOOLS._stage_output_sibling(
            source, destination, expected_hash
        )
    except PUBLISH_TOOLS.BuildError as exc:
        raise ResourceVersionError(str(exc)) from exc


def _publish_staged_exclusive(
    staging, destination: Path, expected_hash: str
) -> None:
    try:
        PUBLISH_TOOLS._publish_staged_exclusive(
            staging, destination, expected_hash
        )
    except PUBLISH_TOOLS.BuildError as exc:
        raise ResourceVersionError(str(exc)) from exc


def _cleanup_owned_staging(staging) -> None:
    try:
        PUBLISH_TOOLS._cleanup_owned_staging(staging)
    except PUBLISH_TOOLS.BuildError as exc:
        raise ResourceVersionError(str(exc)) from exc


def _clean_transaction_before_publish(transaction: Path) -> None:
    try:
        PUBLISH_TOOLS._clean_transaction_before_publish(transaction)
    except PUBLISH_TOOLS.BuildError as exc:
        raise ResourceVersionError(str(exc)) from exc


def apply_resource_version(
    source_swf: Path,
    output_swf: Path,
    lock: Mapping[str, Any],
    *,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    work_dir: Path,
    runner=_subprocess_runner,
    timeout: int = 240,
) -> ResourceVersionReport:
    """Apply the one locked replacement and publish a new SWF exclusively."""
    _require_handle_bound_publish_support()
    entry, dummy_hash = _resource_lock(lock)
    source, output, ffdec_path, java_path, work, profile = (
        _validate_stage_paths(
            source_swf, output_swf, ffdec, java, work_dir, profile_dir
        )
    )
    source_sha = _sha256_file(source)
    transaction: Path | None = None
    staged_output = None
    original_error: BaseException | None = None
    try:
        transaction = Path(
            tempfile.mkdtemp(prefix=".resource-version-", dir=work)
        ).resolve()
        snapshot = transaction / "source.swf"
        _copy_snapshot(source, snapshot)
        if not hmac.compare_digest(_sha256_file(snapshot), source_sha):
            raise ResourceVersionError(
                "source SWF changed while creating stage snapshot"
            )
        _assert_source_hash(source, source_sha)

        resource_ref, dummy_ref = _method_refs(snapshot)
        _require_raw_hash(
            resource_ref.code,
            str(entry["before_abc_sha256"]),
            "resource-version input",
        )
        _require_raw_hash(
            dummy_ref.code, dummy_hash, "DummyRemote input"
        )

        before_export = transaction / "before-export"
        _export_resource_class(
            snapshot,
            before_export,
            ffdec=ffdec_path,
            java=java_path,
            profile_dir=profile,
            cwd=transaction,
            runner=runner,
            timeout=timeout,
        )
        _assert_source_hash(source, source_sha)
        before = _read_exported_resource(before_export)
        if not hmac.compare_digest(
            _sha256_pcode(before), str(entry["before_pcode_sha256"])
        ):
            raise ResourceVersionError(
                "resource-version input canonical P-code hash mismatch"
            )
        after = patch_resource_version(before)
        if not hmac.compare_digest(
            _sha256_pcode(after), str(entry["after_pcode_sha256"])
        ):
            raise ResourceVersionError(
                "resource-version output canonical P-code hash mismatch"
            )
        replacement = transaction / "resource-version.pcode"
        replacement.write_text(after, encoding="utf-8", newline="\n")
        staged = transaction / "resource-version.swf"
        _replace_one(
            snapshot,
            staged,
            replacement,
            resource_ref.body_index,
            ffdec=ffdec_path,
            java=java_path,
            profile_dir=profile,
            cwd=transaction,
            runner=runner,
            timeout=timeout,
        )
        _assert_source_hash(source, source_sha)
        _verify_reopened_swf(
            staged,
            entry,
            dummy_hash,
            export_root=transaction / "reopen-export",
            ffdec=ffdec_path,
            java=java_path,
            profile_dir=profile,
            cwd=transaction,
            runner=runner,
            timeout=timeout,
        )
        _assert_source_hash(source, source_sha)

        output_sha = _sha256_file(staged)
        staged_output = _stage_output_sibling(staged, output, output_sha)
        report = ResourceVersionReport(
            output_path=output,
            input_sha256=source_sha,
            output_sha256=output_sha,
            source_version=SOURCE_VERSION,
            output_version=TARGET_VERSION,
            is_full_package=True,
            verified=True,
        )
        cleanup_target = transaction
        _clean_transaction_before_publish(cleanup_target)
        transaction = None
        _assert_source_hash(source, source_sha)
        _publish_staged_exclusive(staged_output, output, output_sha)
        staged_output = None
        return report
    except BaseException as error:
        original_error = error
        raise
    finally:
        if transaction is not None:
            try:
                shutil.rmtree(transaction)
            except BaseException as cleanup_error:
                if original_error is None:
                    raise ResourceVersionError(
                        "failed to clean resource-version transaction"
                    ) from cleanup_error
                original_error.add_note(
                    "failed to clean resource-version transaction: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )
        if staged_output is not None:
            try:
                _cleanup_owned_staging(staged_output)
            except BaseException as cleanup_error:
                if original_error is None:
                    if isinstance(cleanup_error, ResourceVersionError):
                        raise
                    raise ResourceVersionError(
                        "failed to clean staged resource-version output"
                    ) from cleanup_error
                original_error.add_note(
                    "failed to clean staged resource-version output: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )


def _verify_resource_swf(
    output_swf: Path,
    lock: Mapping[str, Any],
    *,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    work_dir: Path,
    runner,
    timeout: int,
) -> ResourceVersionReport:
    entry, dummy_hash = _resource_lock(lock)
    output = Path(output_swf).resolve()
    ffdec_path = Path(ffdec).resolve()
    java_path = Path(java).resolve()
    work = Path(work_dir).resolve()
    profile = Path(profile_dir).resolve()
    if not output.is_file() or not ffdec_path.is_file() or not java_path.is_file():
        raise ResourceVersionError(
            "resource-version verification input or tool is missing"
        )
    if work.exists() and not work.is_dir():
        raise ResourceVersionError("verification work path is not a directory")
    if profile.exists() and not profile.is_dir():
        raise ResourceVersionError(
            "verification profile path is not a directory"
        )
    work.mkdir(parents=True, exist_ok=True)
    profile.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".resource-version-verify-", dir=work
    ) as temporary:
        root = Path(temporary)
        _verify_reopened_swf(
            output,
            entry,
            dummy_hash,
            export_root=root / "reopen-export",
            ffdec=ffdec_path,
            java=java_path,
            profile_dir=profile,
            cwd=root,
            runner=runner,
            timeout=timeout,
        )
    digest = _sha256_file(output)
    return ResourceVersionReport(
        output_path=output,
        input_sha256=digest,
        output_sha256=digest,
        source_version=SOURCE_VERSION,
        output_version=TARGET_VERSION,
        is_full_package=True,
        verified=True,
    )


def verify_resource_version(
    subject,
    lock: Mapping[str, Any] | None = None,
    *,
    expected: str = TARGET_VERSION,
    ffdec: Path | None = None,
    java: Path | None = None,
    profile_dir: Path | None = None,
    work_dir: Path | None = None,
    runner=_subprocess_runner,
    timeout: int = 240,
):
    """Verify either one P-code block or a reopened SWF stage.

    ``str`` input is the small pure-P-code verifier used by unit fixtures and
    lock discovery.  Path-like input requires the accepted lock and toolchain
    arguments and returns :class:`ResourceVersionReport`.
    """
    if isinstance(subject, str):
        if lock is not None:
            raise ResourceVersionError(
                "P-code verification does not accept an SWF lock"
            )
        _verify_resource_block(subject, expected=expected)
        return None
    if lock is None:
        raise ResourceVersionError("SWF verification requires a lock")
    if None in (ffdec, java, profile_dir, work_dir):
        raise ResourceVersionError(
            "SWF verification requires FFDec, Java, profile and work paths"
        )
    return _verify_resource_swf(
        Path(subject),
        lock,
        ffdec=Path(ffdec),
        java=Path(java),
        profile_dir=Path(profile_dir),
        work_dir=Path(work_dir),
        runner=runner,
        timeout=timeout,
    )


__all__ = [
    "DUMMY_REMOTE_METHOD",
    "RESOURCE_CLASS",
    "RESOURCE_METHOD",
    "RESOURCE_SITE_ID",
    "SOURCE_VERSION",
    "TARGET_VERSION",
    "ResourceVersionError",
    "ResourceVersionReport",
    "apply_resource_version",
    "canonical_pcode",
    "patch_resource_version",
    "verify_resource_version",
]
