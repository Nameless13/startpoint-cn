#!/usr/bin/env python3
"""Fail-closed baseline inspection for the offline Android release APK.

The inspector binds one immutable APK snapshot to the accepted offline lock.
It resolves the four active AVM2 method bodies by their full class/method
identities, so dormant strings or same-named methods in ``RealRemote`` cannot
stand in for the active offline/save/resource implementations.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
ABC_METHODS_PATH = HERE.parent / "dual-form-v1" / "abc_methods.py"
LOCK_DISCOVERY_PATH = HERE / "lock_discovery.py"
TOOLCHAIN_PATH = REPO_ROOT / "mod-tools" / "wf_offline_toolchain.py"

TARGET_SWF = "assets/worldflipper_android_release.swf"
TARGET_PACKAGE = "com.leiting.wf"
TARGET_VERSION_CODE = "1008001"
TARGET_VERSION_NAME = "1.8.1"
MANAGE_EXTERNAL_STORAGE = "android.permission.MANAGE_EXTERNAL_STORAGE"
MAX_LOCK_BYTES = 2 * 1024 * 1024
TOOL_TIMEOUT_SECONDS = 120

OFFLINE_METHOD_IDENTITIES = MappingProxyType(
    {
        "DevConfig_individual/DevConfig_individual": (
            "pinball.config.core:DevConfig_individual/DevConfig_individual"
        ),
        "boot_ffc6#$script364/$init": "boot_ffc6#$script364/$init",
        "InitializeDummyRemote/logicAssetLoadedHandler": (
            "pinball.remote.initialize:InitializeDummyRemote/logicAssetLoadedHandler"
        ),
        "DummyRemote/debugUnlinkTwitter": (
            "pinball.context.remote.dummy:DummyRemote/debugUnlinkTwitter"
        ),
    }
)

_SIGNATURE_EXTENSIONS = (".SF", ".RSA", ".DSA", ".EC")
_DEX_MEMBER = re.compile(r"^classes(?:[2-9][0-9]*)?\.dex$")
_PACKAGE_LINE = re.compile(
    r"^package:\s+name='([^']+)'\s+versionCode='([^']+)'\s+"
    r"versionName='([^']+)'(?:\s|$)",
    re.MULTILINE,
)
_PERMISSION_LINE = re.compile(
    r"^uses-permission(?:-sdk-[0-9]+)?:\s+name='([^']+)'\s*$",
    re.MULTILINE,
)
_LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ApkBuildError(RuntimeError):
    """An APK or accepted baseline failed a release-safety invariant."""


# A narrower descriptive alias is useful to direct callers while the builder
# contract uses ApkBuildError for all Task 11 failures.
ApkBaselineError = ApkBuildError
Runner = Callable[..., Any]


def _load_tracked_module(name: str, path: Path) -> Any:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ApkBuildError(f"cannot load tracked helper: {path.name}")
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    try:
        spec.loader.exec_module(loaded)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return loaded


ABC_METHODS = _load_tracked_module(
    "offline_apk_baseline_abc_methods", ABC_METHODS_PATH
)
LOCK_DISCOVERY = _load_tracked_module(
    "offline_apk_baseline_lock_discovery", LOCK_DISCOVERY_PATH
)
TOOLCHAIN_HELPER = _load_tracked_module(
    "offline_apk_baseline_toolchain", TOOLCHAIN_PATH
)


@dataclass(frozen=True, slots=True)
class ApkBaselineLock(Mapping[str, Any]):
    """The byte-contract fields projected from one canonical accepted lock."""

    source_apk_sha256: str
    source_swf_sha256: str
    manifest_sha256: str
    dex_sha256: Mapping[str, str]
    native_aggregate_sha256: str
    offline_method_sha256: Mapping[str, str]
    document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.document[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.document)

    def __len__(self) -> int:
        return len(self.document)


@dataclass(frozen=True, slots=True)
class ApkBaselineReport:
    apk_sha256: str
    swf_sha256: str
    package_name: str
    version_code: str
    version_name: str
    manifest_sha256: str
    dex_sha256: Mapping[str, str]
    native_aggregate_sha256: str
    offline_method_sha256: Mapping[str, str]
    manage_external_storage_count: int
    target_swf_count: int
    input_certificate_sha256: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ApkBuildError("base lock is not canonical-JSON serializable") from exc
    return (rendered + "\n").encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _is_reparse_point(metadata: os.stat_result) -> bool:
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return bool(attributes & flag)


def _read_regular_snapshot(
    path: Path,
    *,
    label: str,
    maximum_bytes: int | None = None,
    reject_hardlinks: bool = False,
) -> bytes:
    source = Path(path)
    try:
        metadata = source.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or _is_reparse_point(metadata)
            or not stat.S_ISREG(metadata.st_mode)
        ):
            raise ApkBuildError(f"{label} must be a regular non-symlink file")
        if reject_hardlinks and int(getattr(metadata, "st_nlink", 1)) != 1:
            raise ApkBuildError(f"{label} must not have multiple hard links")
        if metadata.st_size <= 0 or (
            maximum_bytes is not None and metadata.st_size > maximum_bytes
        ):
            raise ApkBuildError(f"{label} size is invalid")
        with source.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino)
                != (metadata.st_dev, metadata.st_ino)
            ):
                raise ApkBuildError(f"{label} changed before it was opened")
            raw = handle.read(
                -1 if maximum_bytes is None else maximum_bytes + 1
            )
            finished = os.fstat(handle.fileno())
        if len(raw) != opened.st_size or (
            maximum_bytes is not None and len(raw) > maximum_bytes
        ):
            raise ApkBuildError(f"{label} size changed while reading")
        stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(
            getattr(opened, field) != getattr(finished, field)
            for field in stable
        ):
            raise ApkBuildError(f"{label} changed while reading")
        return raw
    except ApkBuildError:
        raise
    except OSError as exc:
        raise ApkBuildError(f"cannot read {label}") from exc


def _parse_strict_json(raw: bytes) -> Mapping[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ApkBuildError(f"invalid base lock JSON: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ApkBuildError("base lock JSON root must be an object")
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def _lock_from_document(document: Mapping[str, Any]) -> ApkBaselineLock:
    try:
        LOCK_DISCOVERY.validate_lock_document(
            document,
            expected_status="accepted",
            require_extensions=True,
        )
    except LOCK_DISCOVERY.LockDiscoveryError as exc:
        raise ApkBuildError(f"invalid accepted base lock: {exc}") from exc
    frozen = _freeze(document)
    return ApkBaselineLock(
        source_apk_sha256=str(document["source_apk_sha256"]),
        source_swf_sha256=str(document["source_swf_sha256"]),
        manifest_sha256=str(document["manifest_sha256"]),
        dex_sha256=MappingProxyType(dict(document["dex_sha256"])),
        native_aggregate_sha256=str(document["native_aggregate_sha256"]),
        offline_method_sha256=MappingProxyType(
            dict(document["offline_method_sha256"])
        ),
        document=frozen,
    )


def load_base_lock(path: Path | str) -> ApkBaselineLock:
    """Load the one canonical, accepted and extension-complete base lock."""
    raw = _read_regular_snapshot(
        Path(path),
        label="base lock",
        maximum_bytes=MAX_LOCK_BYTES,
        reject_hardlinks=True,
    )
    document = _parse_strict_json(raw)
    if raw != _canonical_json_bytes(document):
        raise ApkBuildError("base lock is not canonical JSON")
    return _lock_from_document(document)


def is_signature_member(name: str) -> bool:
    """Return true only for a top-level APK v1 signer member."""
    parts = str(name).split("/")
    if len(parts) != 2 or parts[0] != "META-INF":
        return False
    filename = parts[1]
    return filename == "MANIFEST.MF" or filename.endswith(_SIGNATURE_EXTENSIONS)


def allowed_to_change(name: str) -> bool:
    return str(name) == TARGET_SWF or is_signature_member(str(name))


def _validate_member_name(name: str) -> None:
    if (
        not name
        or "\x00" in name
        or "\\" in name
        or name.startswith("/")
        or "//" in name
    ):
        raise ApkBuildError("APK contains a non-canonical ZIP member name")
    trimmed = name[:-1] if name.endswith("/") else name
    parts = PurePosixPath(trimmed).parts
    if not trimmed or any(part in ("", ".", "..") for part in parts):
        raise ApkBuildError("APK contains a non-canonical ZIP member name")
    if parts and (":" in parts[0] or PurePosixPath(trimmed).is_absolute()):
        raise ApkBuildError("APK contains a non-canonical ZIP member name")


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (int(info.external_attr) >> 16) & 0xFFFF
    return stat.S_IFMT(mode) == stat.S_IFLNK


def _validated_infos(archive: zipfile.ZipFile) -> tuple[zipfile.ZipInfo, ...]:
    infos = tuple(archive.infolist())
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise ApkBuildError("APK contains duplicate ZIP members")
    casefolded = [name.casefold() for name in names]
    if len(casefolded) != len(set(casefolded)):
        raise ApkBuildError("APK contains a case-insensitive ZIP member collision")
    for info in infos:
        _validate_member_name(info.filename)
        if _is_zip_symlink(info):
            raise ApkBuildError(f"APK contains a symlink member: {info.filename}")
        if info.flag_bits & 0x1:
            raise ApkBuildError("APK contains an encrypted ZIP member")
    return infos


def _hash_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    copy_to: Path | None = None,
) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    output = None
    try:
        if copy_to is not None:
            output = Path(copy_to).open("xb")
        with archive.open(info, "r") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
                if output is not None:
                    output.write(chunk)
        if output is not None:
            output.flush()
            os.fsync(output.fileno())
    finally:
        if output is not None:
            output.close()
    if size != info.file_size:
        raise ApkBuildError(f"APK member size mismatch: {info.filename}")
    return digest.hexdigest(), size


def _native_aggregate(records: Mapping[str, tuple[int, str]]) -> str:
    digest = hashlib.sha256()
    for name in sorted(records):
        size, member_hash = records[name]
        digest.update(f"{name}\0{size}\0{member_hash}\n".encode("utf-8"))
    return digest.hexdigest()


def _copy_apk_snapshot(source: Path, destination: Path) -> str:
    path = Path(source)
    try:
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or _is_reparse_point(metadata)
            or not stat.S_ISREG(metadata.st_mode)
        ):
            raise ApkBuildError("source APK must be a regular non-symlink file")
        if metadata.st_size <= 0:
            raise ApkBuildError("source APK size is invalid")
        digest = hashlib.sha256()
        with path.open("rb") as input_stream, Path(destination).open("xb") as output:
            opened = os.fstat(input_stream.fileno())
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise ApkBuildError("source APK changed before it was opened")
            for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
                digest.update(chunk)
                output.write(chunk)
            finished = os.fstat(input_stream.fileno())
            output.flush()
            os.fsync(output.fileno())
        stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(
            getattr(opened, field) != getattr(finished, field)
            for field in stable
        ):
            raise ApkBuildError("source APK changed while creating inspection snapshot")
        if Path(destination).stat().st_size != opened.st_size:
            raise ApkBuildError("source APK snapshot size mismatch")
        return digest.hexdigest()
    except ApkBuildError:
        raise
    except OSError as exc:
        raise ApkBuildError("cannot create source APK inspection snapshot") from exc


def _decode_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        for encoding in ("utf-8", "utf-16", "gb18030"):
            try:
                return value.decode(encoding)
            except UnicodeError:
                continue
        return value.decode("utf-8", errors="replace")
    return str(value)


def _run_capture(
    argv: list[str],
    *,
    label: str,
    runner: Runner,
) -> str:
    try:
        result = runner(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=False,
            check=False,
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ApkBuildError(f"{label} failed") from exc
    if int(getattr(result, "returncode", 0)) != 0:
        raise ApkBuildError(
            f"{label} failed with exit code {int(result.returncode)}"
        )
    return "\n".join(
        part
        for part in (
            _decode_output(getattr(result, "stdout", "")),
            _decode_output(getattr(result, "stderr", "")),
        )
        if part
    )


def _apksigner_prefix(toolchain: Any) -> list[str]:
    apksigner = Path(toolchain.apksigner).resolve()
    if apksigner.suffix.lower() in (".bat", ".cmd"):
        java = Path(toolchain.java).resolve()
        jar = apksigner.parent / "lib" / "apksigner.jar"
        if not jar.is_file():
            raise ApkBuildError("apksigner launcher jar is missing")
        return [str(java), "-jar", str(jar)]
    return [str(apksigner)]


def _inspect_manifest_and_signer(
    apk: Path,
    toolchain: Any,
    *,
    runner: Runner,
) -> tuple[str, str, str, int, str]:
    aapt = str(Path(toolchain.aapt).resolve())
    badging = _run_capture(
        [aapt, "dump", "badging", str(apk)],
        label="aapt badging inspection",
        runner=runner,
    )
    package_matches = list(_PACKAGE_LINE.finditer(badging))
    if len(package_matches) != 1:
        raise ApkBuildError("aapt package identity is missing or ambiguous")
    package, version_code, version_name = package_matches[0].groups()
    if package != TARGET_PACKAGE:
        raise ApkBuildError("APK package name mismatch")
    if version_code != TARGET_VERSION_CODE:
        raise ApkBuildError("APK versionCode mismatch")
    if version_name != TARGET_VERSION_NAME:
        raise ApkBuildError("APK versionName mismatch")

    permissions = _run_capture(
        [aapt, "dump", "permissions", str(apk)],
        label="aapt permission inspection",
        runner=runner,
    )
    permission_count = sum(
        match.group(1) == MANAGE_EXTERNAL_STORAGE
        for match in _PERMISSION_LINE.finditer(permissions)
    )
    if permission_count != 1:
        raise ApkBuildError(
            "MANAGE_EXTERNAL_STORAGE permission must appear exactly once"
        )

    signer_output = _run_capture(
        [
            *_apksigner_prefix(toolchain),
            "verify",
            "--verbose",
            "--print-certs",
            str(apk),
        ],
        label="apksigner input verification",
        runner=runner,
    )
    try:
        signer = TOOLCHAIN_HELPER.parse_apksigner_verify(signer_output)
    except TOOLCHAIN_HELPER.ToolchainError as exc:
        raise ApkBuildError(f"invalid input APK signature: {exc}") from exc
    return (
        package,
        version_code,
        version_name,
        permission_count,
        str(signer["certificate_sha256"]),
    )


def _inspect_archive(
    apk: Path,
    extracted_swf: Path,
) -> tuple[str, Mapping[str, str], str, str]:
    try:
        with zipfile.ZipFile(apk, "r") as archive:
            infos = _validated_infos(archive)
            swf_infos = [info for info in infos if info.filename == TARGET_SWF]
            if len(swf_infos) != 1:
                raise ApkBuildError(
                    f"expected exactly one main SWF, found {len(swf_infos)}"
                )
            manifests = [
                info for info in infos if info.filename == "AndroidManifest.xml"
            ]
            if len(manifests) != 1:
                raise ApkBuildError("AndroidManifest.xml member count mismatch")
            swf_hash, _ = _hash_member(
                archive, swf_infos[0], copy_to=extracted_swf
            )
            manifest_hash, _ = _hash_member(archive, manifests[0])

            dex_hashes: dict[str, str] = {}
            native_records: dict[str, tuple[int, str]] = {}
            for info in infos:
                if info.is_dir():
                    continue
                if _DEX_MEMBER.fullmatch(info.filename):
                    member_hash, _ = _hash_member(archive, info)
                    dex_hashes[info.filename] = member_hash
                elif info.filename.startswith("lib/"):
                    member_hash, size = _hash_member(archive, info)
                    native_records[info.filename] = (size, member_hash)
            if not dex_hashes:
                raise ApkBuildError("APK contains no DEX members")
            if not native_records:
                raise ApkBuildError("APK contains no native library members")
    except ApkBuildError:
        raise
    except (OSError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ApkBuildError("cannot inspect APK ZIP members") from exc
    return (
        swf_hash,
        MappingProxyType(dict(sorted(dex_hashes.items()))),
        _native_aggregate(native_records),
        manifest_hash,
    )


def _active_offline_method_hashes(swf: Path) -> Mapping[str, str]:
    try:
        index = ABC_METHODS.index_swf_methods(swf)
        hashes: dict[str, str] = {}
        for lock_key, identity in OFFLINE_METHOD_IDENTITIES.items():
            ref = index.require_ref(identity)
            hashes[lock_key] = _sha256_bytes(ref.code)
    except Exception as exc:
        raise ApkBuildError("active offline method identity resolution failed") from exc
    if set(hashes) != set(OFFLINE_METHOD_IDENTITIES):
        raise ApkBuildError("active offline method set mismatch")
    return MappingProxyType(hashes)


def inspect_apk(
    apk: Path | str,
    toolchain: Any,
    *,
    runner: Runner = subprocess.run,
) -> ApkBaselineReport:
    """Inspect one consistent APK snapshot and return its locked byte facts."""
    source = Path(apk)
    with tempfile.TemporaryDirectory(prefix="offline-apk-inspect-") as temporary:
        root = Path(temporary)
        snapshot = root / "input.apk"
        extracted_swf = root / "worldflipper.swf"
        apk_hash = _copy_apk_snapshot(source, snapshot)
        swf_hash, dex_hashes, native_hash, manifest_hash = _inspect_archive(
            snapshot, extracted_swf
        )
        offline_hashes = _active_offline_method_hashes(extracted_swf)
        (
            package,
            version_code,
            version_name,
            permission_count,
            certificate,
        ) = _inspect_manifest_and_signer(snapshot, toolchain, runner=runner)

        # The external path remains only a source.  Re-hashing at the end
        # detects mutation while tools inspected the owned snapshot.
        try:
            if _sha256_file(source) != apk_hash:
                raise ApkBuildError("source APK changed during baseline inspection")
        except OSError as exc:
            raise ApkBuildError("cannot recheck source APK after inspection") from exc

    return ApkBaselineReport(
        apk_sha256=apk_hash,
        swf_sha256=swf_hash,
        package_name=package,
        version_code=version_code,
        version_name=version_name,
        manifest_sha256=manifest_hash,
        dex_sha256=dex_hashes,
        native_aggregate_sha256=native_hash,
        offline_method_sha256=offline_hashes,
        manage_external_storage_count=permission_count,
        target_swf_count=1,
        input_certificate_sha256=certificate,
    )


def _coerce_lock(
    lock: ApkBaselineLock | Mapping[str, Any] | Path | str,
) -> ApkBaselineLock:
    if isinstance(lock, ApkBaselineLock):
        return lock
    if isinstance(lock, Mapping):
        return _lock_from_document(lock)
    return load_base_lock(Path(lock))


def _require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or _LOWER_SHA256.fullmatch(value) is None:
        raise ApkBuildError(f"{label} is not a lowercase SHA-256")
    return value


def assert_locked_baseline(
    report: ApkBaselineReport,
    lock: ApkBaselineLock | Mapping[str, Any] | Path | str,
) -> ApkBaselineReport:
    """Require every immutable base byte and active method to match the lock."""
    accepted = _coerce_lock(lock)
    if report.package_name != TARGET_PACKAGE:
        raise ApkBuildError("APK package name mismatch")
    if report.version_code != TARGET_VERSION_CODE:
        raise ApkBuildError("APK versionCode mismatch")
    if report.version_name != TARGET_VERSION_NAME:
        raise ApkBuildError("APK versionName mismatch")
    if report.manage_external_storage_count != 1:
        raise ApkBuildError(
            "MANAGE_EXTERNAL_STORAGE permission must appear exactly once"
        )
    if report.target_swf_count != 1:
        raise ApkBuildError("main SWF count mismatch")

    scalar_contracts = (
        ("source APK", report.apk_sha256, accepted.source_apk_sha256),
        ("source SWF", report.swf_sha256, accepted.source_swf_sha256),
        ("manifest", report.manifest_sha256, accepted.manifest_sha256),
        (
            "native aggregate",
            report.native_aggregate_sha256,
            accepted.native_aggregate_sha256,
        ),
    )
    for label, actual, expected in scalar_contracts:
        if _require_hash(actual, label) != expected:
            raise ApkBuildError(f"locked {label} hash mismatch")
    if dict(report.dex_sha256) != dict(accepted.dex_sha256):
        raise ApkBuildError("locked DEX hashes mismatch")
    if dict(report.offline_method_sha256) != dict(
        accepted.offline_method_sha256
    ):
        raise ApkBuildError("locked active offline method hashes mismatch")
    _require_hash(report.input_certificate_sha256, "input certificate")
    return report


def _member_content_hashes(
    apk: Path | str,
    *,
    exclude: Callable[[str], bool] | None = None,
) -> Mapping[str, str]:
    try:
        with zipfile.ZipFile(Path(apk), "r") as archive:
            infos = _validated_infos(archive)
            if sum(info.filename == TARGET_SWF for info in infos) != 1:
                raise ApkBuildError("main SWF count mismatch")
            hashes: dict[str, str] = {}
            for info in infos:
                if exclude is not None and exclude(info.filename):
                    continue
                member_hash, _ = _hash_member(archive, info)
                hashes[info.filename] = member_hash
            return MappingProxyType(hashes)
    except ApkBuildError:
        raise
    except (OSError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ApkBuildError("cannot compare APK ZIP members") from exc


def assert_allowed_member_diff(
    base_apk: Path | str,
    output_apk: Path | str,
) -> None:
    """Allow only the main SWF and top-level v1 signer files to differ."""
    base = _member_content_hashes(base_apk, exclude=is_signature_member)
    output = _member_content_hashes(output_apk, exclude=is_signature_member)
    if set(base) != set(output):
        raise ApkBuildError("non-signature APK member set changed")
    for name in base:
        if name != TARGET_SWF and base[name] != output[name]:
            raise ApkBuildError(f"unexpected member drift: {name}")


__all__ = (
    "ApkBaselineError",
    "ApkBaselineLock",
    "ApkBaselineReport",
    "ApkBuildError",
    "OFFLINE_METHOD_IDENTITIES",
    "TARGET_SWF",
    "allowed_to_change",
    "assert_allowed_member_diff",
    "assert_locked_baseline",
    "inspect_apk",
    "is_signature_member",
    "load_base_lock",
)
