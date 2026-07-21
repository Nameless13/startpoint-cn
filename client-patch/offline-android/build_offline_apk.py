#!/usr/bin/env python3
"""Build one locked, patched, aligned and dedicated-signer Android APK.

The builder keeps every external-tool path inside an ASCII-only transaction.
Only the final, already-verified APK and its canonical public report are renamed
into their (possibly non-ASCII) destinations, without replacing existing data.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
import secrets
import stat
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
MOD_TOOLS = REPO_ROOT / "mod-tools"
ABYSS_PATH = REPO_ROOT / "client-patch" / "abyss-mode-equipment" / "build_apk.py"
BASELINE_PATH = HERE / "apk_baseline.py"
SERIS_PATH = HERE / "seris_phase4_pcode.py"
RENDER_PATH = HERE / "render_scale_pcode.py"
RESOURCE_PATH = HERE / "resource_version_pcode.py"
TOOLCHAIN_PATH = MOD_TOOLS / "wf_offline_toolchain.py"

TARGET_SWF = "assets/worldflipper_android_release.swf"
PATCH_ORDER = (
    "abyss-mode-equipment",
    "seris-phase4",
    "render-scale",
    "resource-version",
)
EXPECTED_FULL_RESOURCE_VERSION = "1.4.196"
STAGE_TIMEOUT_SECONDS = 240
PROCESS_TIMEOUT_SECONDS = 240

Runner = Callable[..., Any]
subprocess_runner = subprocess.run


class ApkBuildError(RuntimeError):
    """The offline APK cannot be built and proven without unsafe assumptions."""


def _load_helper(name: str, path: Path):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    if not path.is_file():
        raise ApkBuildError(f"required tracked helper is missing: {path.name}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ApkBuildError(f"cannot load tracked helper: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


TOOLCHAIN = _load_helper("offline_apk_builder_toolchain", TOOLCHAIN_PATH)
ABYSS = _load_helper("offline_apk_builder_abyss", ABYSS_PATH)
SERIS = _load_helper("offline_apk_builder_seris", SERIS_PATH)
RENDER = _load_helper("offline_apk_builder_render", RENDER_PATH)
RESOURCE = _load_helper("offline_apk_builder_resource", RESOURCE_PATH)
BASELINE = (
    _load_helper("offline_apk_builder_baseline", BASELINE_PATH)
    if BASELINE_PATH.is_file()
    else None
)

Toolchain = TOOLCHAIN.Toolchain
SigningConfig = TOOLCHAIN.SigningConfig
ApkBaselineReport = getattr(BASELINE, "ApkBaselineReport", Any)


@dataclass(frozen=True, slots=True)
class OfflineApkBuildConfig:
    source_apk: Path
    baseline_lock: Path
    output_apk: Path
    report_path: Path
    work_dir: Path
    toolchain: Toolchain
    signing: SigningConfig


@dataclass(frozen=True, slots=True)
class ApkBuildReport:
    output_sha256: str
    certificate_sha256: str
    patch_order: tuple[str, ...]
    stage_reports: tuple[Mapping[str, Any], ...]
    full_resource_version: str
    aligned: bool
    signature_schemes: Mapping[str, bool]
    verified: bool


@dataclass(frozen=True, slots=True)
class _StagedPublication:
    path: Path
    identity: tuple[int, int]
    sha256: str
    handle: Any


@dataclass(slots=True)
class _OwnedDirectory:
    path: Path
    handle: int | None
    identity: tuple[int, int]


@dataclass(slots=True)
class _OwnedTransaction:
    path: Path
    directory: _OwnedDirectory


@dataclass(frozen=True, slots=True)
class _ResolvedConfig:
    source_apk: Path
    baseline_lock: Path
    output_apk: Path
    report_path: Path
    work_dir: Path
    toolchain: Toolchain
    signing: SigningConfig
    output_parent: _OwnedDirectory
    report_parent: _OwnedDirectory


@dataclass(frozen=True, slots=True)
class _SourceIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int


def _baseline_module():
    global BASELINE, ApkBaselineReport
    if BASELINE is None:
        BASELINE = _load_helper("offline_apk_builder_baseline", BASELINE_PATH)
        ApkBaselineReport = BASELINE.ApkBaselineReport
    return BASELINE


def load_base_lock(path: Path | str):
    return _baseline_module().load_base_lock(path)


def inspect_apk(apk: Path | str, toolchain: Toolchain, *, runner=subprocess_runner):
    return _baseline_module().inspect_apk(apk, toolchain, runner=runner)


def assert_locked_baseline(report, lock):
    try:
        return _baseline_module().assert_locked_baseline(report, lock)
    except Exception as exc:
        raise ApkBuildError(str(exc)) from None


def assert_allowed_member_diff(base_apk: Path | str, output_apk: Path | str) -> None:
    try:
        _baseline_module().assert_allowed_member_diff(base_apk, output_apk)
    except Exception as exc:
        raise ApkBuildError(str(exc)) from None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def _identity(path: Path) -> tuple[int, int]:
    result = path.lstat()
    if (
        stat.S_ISLNK(result.st_mode)
        or bool(getattr(result, "st_file_attributes", 0) & 0x400)
        or not stat.S_ISREG(result.st_mode)
    ):
        raise ApkBuildError("publication staging path is not a regular file")
    return result.st_dev, result.st_ino


def _same_digest(actual: str, expected: str) -> bool:
    return hmac.compare_digest(str(actual).casefold(), str(expected).casefold())


def _lexical_absolute(path: Path | str) -> Path:
    """Make an input absolute without dereferencing a symlink/reparse point."""
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _directory_handle_info(raw_handle: int) -> tuple[int, tuple[int, int]]:
    import ctypes
    from ctypes import wintypes

    class ByHandleFileInformation(ctypes.Structure):
        _fields_ = (
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        )

    _ctypes, _wintypes, kernel32 = ABYSS._windows_file_api()
    kernel32.GetFileInformationByHandle.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ByHandleFileInformation),
    )
    kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    info = ByHandleFileInformation()
    if not kernel32.GetFileInformationByHandle(raw_handle, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    identity = (
        int(info.dwVolumeSerialNumber),
        (int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow),
    )
    if identity[0] == 0 or identity[1] == 0:
        raise ApkBuildError("directory has no stable nonzero identity")
    return int(info.dwFileAttributes), identity


def _open_raw_directory(
    path: Path, *, deny_delete: bool, request_delete: bool
) -> _OwnedDirectory:
    import ctypes

    if os.name != "nt":
        raise ApkBuildError("offline APK publication requires Windows handles")
    _ctypes, _wintypes, kernel32 = ABYSS._windows_file_api()
    file_list_directory = 0x0001
    file_read_attributes = 0x0080
    delete_access = 0x00010000
    share_read = 0x00000001
    share_write = 0x00000002
    share_delete = 0x00000004
    open_existing = 3
    backup_semantics = 0x02000000
    open_reparse_point = 0x00200000
    access = file_list_directory | file_read_attributes
    if request_delete:
        access |= delete_access
    share = share_read | share_write
    if not deny_delete:
        share |= share_delete
    raw_handle = kernel32.CreateFileW(
        str(path),
        access,
        share,
        None,
        open_existing,
        backup_semantics | open_reparse_point,
        None,
    )
    if raw_handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        attributes, identity = _directory_handle_info(raw_handle)
        if not attributes & 0x10:
            raise ApkBuildError("destination parent is not a directory")
        if attributes & 0x400:
            raise ApkBuildError("destination parent must not be a reparse point")
        return _OwnedDirectory(Path(path), int(raw_handle), identity)
    except BaseException:
        kernel32.CloseHandle(raw_handle)
        raise


def _open_destination_directory(
    path: Path, *, deny_delete: bool = False
) -> _OwnedDirectory:
    try:
        return _open_raw_directory(
            Path(path), deny_delete=deny_delete, request_delete=True
        )
    except ApkBuildError:
        raise
    except OSError as exc:
        raise ApkBuildError(
            f"cannot bind destination parent directory: {type(exc).__name__}"
        ) from None


def _close_owned_directory(directory: _OwnedDirectory) -> None:
    if directory.handle is None:
        return
    _ctypes, _wintypes, kernel32 = ABYSS._windows_file_api()
    raw_handle = directory.handle
    directory.handle = None
    kernel32.CloseHandle(raw_handle)


def _directory_identity_at_path(path: Path) -> tuple[int, int]:
    try:
        opened = _open_raw_directory(
            Path(path), deny_delete=False, request_delete=False
        )
    except (ApkBuildError, OSError) as exc:
        raise ApkBuildError("destination parent identity changed") from exc
    try:
        return opened.identity
    finally:
        _close_owned_directory(opened)


def _require_destination_directory_identity(
    directory: _OwnedDirectory, label: str
) -> None:
    if directory.handle is None:
        raise ApkBuildError(f"{label} directory handle is closed")
    if _directory_identity_at_path(directory.path) != directory.identity:
        raise ApkBuildError("destination parent identity changed")


def _mark_directory_handle_for_delete(directory: _OwnedDirectory) -> None:
    import ctypes
    from ctypes import wintypes

    class FileDispositionInfo(ctypes.Structure):
        _fields_ = (("DeleteFile", wintypes.BOOLEAN),)

    if directory.handle is None:
        raise ApkBuildError("directory handle is closed")
    _ctypes, _wintypes, kernel32 = ABYSS._windows_file_api()
    disposition = FileDispositionInfo(True)
    if not kernel32.SetFileInformationByHandle(
        directory.handle,
        4,
        ctypes.byref(disposition),
        ctypes.sizeof(disposition),
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def _resolve_config(config: OfflineApkBuildConfig) -> _ResolvedConfig:
    # apk_baseline must receive the caller's lexical path so its lstat/fstat
    # gate can reject a symlink or Windows reparse point before dereference.
    source = _lexical_absolute(config.source_apk)
    lock = _lexical_absolute(config.baseline_lock)
    output = _lexical_absolute(config.output_apk)
    report = _lexical_absolute(config.report_path)
    work = Path(config.work_dir).expanduser().resolve()
    if not source.is_file():
        raise ApkBuildError("source APK is not a file")
    if not lock.is_file():
        raise ApkBuildError("baseline lock is not a file")
    if os.path.lexists(output):
        raise ApkBuildError("output APK already exists")
    if os.path.lexists(report):
        raise ApkBuildError("report already exists")
    if _path_key(output) == _path_key(report):
        raise ApkBuildError("output APK and report must be different paths")
    if _path_key(source) in {_path_key(output), _path_key(report)}:
        raise ApkBuildError("source APK cannot be an output path")
    if not str(work).isascii():
        raise ApkBuildError("ASCII work directory is required")
    if work.exists() and not work.is_dir():
        raise ApkBuildError("work path is not a directory")
    for label, path in (
        ("Java executable", Path(config.toolchain.java)),
        ("FFDec jar", Path(config.toolchain.ffdec)),
        ("aapt executable", Path(config.toolchain.aapt)),
        ("zipalign executable", Path(config.toolchain.zipalign)),
        ("apksigner executable", Path(config.toolchain.apksigner)),
        ("stable keystore", Path(config.signing.keystore)),
    ):
        if not path.expanduser().resolve().is_file():
            raise ApkBuildError(f"{label} is not a file")
    password = os.environ.get(config.signing.password_env, "")
    if not isinstance(password, str) or not password:
        raise ApkBuildError(f"{config.signing.password_env} is not set")
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(output):
        raise ApkBuildError("output APK already exists")
    if os.path.lexists(report):
        raise ApkBuildError("report already exists")
    output_parent: _OwnedDirectory | None = None
    report_parent: _OwnedDirectory | None = None
    try:
        # Keep the parent name bound for the entire build.  Omitting
        # FILE_SHARE_DELETE prevents a rename/reparse swap while the staged
        # file handle is committed with an absolute no-replace rename.
        output_parent = _open_destination_directory(
            output.parent, deny_delete=True
        )
        if _path_key(report.parent) == _path_key(output.parent):
            report_parent = output_parent
        else:
            report_parent = _open_destination_directory(
                report.parent, deny_delete=True
            )
        _require_destination_directory_identity(output_parent, "output parent")
        _require_destination_directory_identity(report_parent, "report parent")
        if os.path.lexists(output):
            raise ApkBuildError("output APK already exists")
        if os.path.lexists(report):
            raise ApkBuildError("report already exists")
        return _ResolvedConfig(
            source_apk=source,
            baseline_lock=lock,
            output_apk=output,
            report_path=report,
            work_dir=work,
            toolchain=config.toolchain,
            signing=config.signing,
            output_parent=output_parent,
            report_parent=report_parent,
        )
    except BaseException:
        if report_parent is not None:
            _close_owned_directory(report_parent)
        if output_parent is not None:
            _close_owned_directory(output_parent)
        raise


def _assert_archive_members(archive: zipfile.ZipFile) -> None:
    seen: set[str] = set()
    for info in archive.infolist():
        name = info.filename
        if name in seen:
            raise ApkBuildError("APK contains duplicate ZIP members")
        seen.add(name)
        if not name or "\\" in name or name.startswith("/"):
            raise ApkBuildError("APK contains a non-canonical ZIP member")
        parts = name.split("/")
        if any(part in {"", ".", ".."} for part in parts if part != ""):
            raise ApkBuildError("APK contains a non-canonical ZIP member")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise ApkBuildError("APK contains a symlink member")


def _extract_exactly_one_swf(apk: Path, destination: Path) -> Path:
    if destination.exists():
        raise ApkBuildError("SWF extraction destination already exists")
    try:
        with zipfile.ZipFile(apk, "r") as archive:
            _assert_archive_members(archive)
            matches = [info for info in archive.infolist() if info.filename == TARGET_SWF]
            if len(matches) != 1:
                raise ApkBuildError(
                    f"expected exactly one {TARGET_SWF}, found {len(matches)}"
                )
            payload = archive.read(matches[0])
    except ApkBuildError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ApkBuildError(f"cannot extract locked SWF: {type(exc).__name__}") from None
    destination.write_bytes(payload)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise ApkBuildError("extracted SWF is empty")
    return destination


def _signature_member(name: str) -> bool:
    parts = str(name).split("/")
    if len(parts) != 2 or parts[0] != "META-INF":
        return False
    filename = parts[1]
    return filename == "MANIFEST.MF" or filename.endswith(
        (".SF", ".RSA", ".DSA", ".EC")
    )


def _air_members(apk: Path) -> dict[str, str]:
    with zipfile.ZipFile(apk, "r") as archive:
        _assert_archive_members(archive)
        return {
            info.filename: hashlib.sha256(archive.read(info)).hexdigest()
            for info in archive.infolist()
            if info.filename.startswith("META-INF/AIR/")
        }


def _rewrite_apk_archive(
    base_apk: Path, patched_swf: Path, output_apk: Path
) -> None:
    """Rewrite one private APK with the baseline's strict signer predicate."""
    payload = patched_swf.read_bytes()
    try:
        with zipfile.ZipFile(base_apk, "r") as source:
            _assert_archive_members(source)
            infos = source.infolist()
            target_count = sum(info.filename == TARGET_SWF for info in infos)
            if target_count != 1:
                raise ApkBuildError(
                    f"expected exactly one {TARGET_SWF}, found {target_count}"
                )
            with output_apk.open("xb") as raw_output:
                with zipfile.ZipFile(raw_output, "w", allowZip64=True) as target:
                    target.comment = source.comment
                    for info in infos:
                        if _signature_member(info.filename):
                            continue
                        data = payload if info.filename == TARGET_SWF else source.read(info)
                        target.writestr(info, data)
                raw_output.flush()
                os.fsync(raw_output.fileno())
    except BaseException:
        try:
            output_apk.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def rewrite_apk_once(base_apk: Path, patched_swf: Path, output_apk: Path) -> Path:
    """Perform the sole APK rewrite and prove nested AIR metadata survived."""
    if output_apk.exists():
        raise ApkBuildError("unsigned APK already exists")
    before_air = _air_members(base_apk)
    try:
        _rewrite_apk_archive(base_apk, patched_swf, output_apk)
    except Exception as exc:
        raise ApkBuildError(str(exc)) from None
    if not output_apk.is_file():
        raise ApkBuildError("APK rewrite did not create an output")
    with zipfile.ZipFile(output_apk, "r") as archive:
        _assert_archive_members(archive)
        remaining_signatures = [
            info.filename for info in archive.infolist() if _signature_member(info.filename)
        ]
    if remaining_signatures:
        raise ApkBuildError("top-level APK signatures were not stripped")
    if _air_members(output_apk) != before_air:
        raise ApkBuildError("META-INF/AIR metadata changed during rewrite")
    return output_apk


def _completed_output(completed: Any) -> bytes:
    pieces: list[bytes] = []
    for value in (getattr(completed, "stdout", b""), getattr(completed, "stderr", b"")):
        if isinstance(value, bytes):
            pieces.append(value)
        elif value is not None:
            pieces.append(str(value).encode("utf-8", errors="replace"))
    return b"\n".join(pieces)


def _safe_process_error(error: BaseException, signing: SigningConfig) -> str:
    secret = os.environ.get(signing.password_env, "")
    return TOOLCHAIN.redact_process_error(error, secrets=(secret,) if secret else ())


def _run_checked(
    command: Sequence[Path | str],
    *,
    cwd: Path,
    runner: Runner,
    signing: SigningConfig,
) -> Any:
    argv = [str(part) for part in command]
    try:
        completed = runner(
            argv,
            cwd=cwd,
            capture_output=True,
            text=False,
            check=False,
            timeout=PROCESS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ApkBuildError(_safe_process_error(exc, signing)) from None
    returncode = int(getattr(completed, "returncode", 0))
    if returncode != 0:
        error = subprocess.CalledProcessError(
            returncode,
            argv,
            output=getattr(completed, "stdout", None),
            stderr=getattr(completed, "stderr", None),
        )
        raise ApkBuildError(_safe_process_error(error, signing))
    return completed


def zipalign_once(
    unsigned_apk: Path,
    output_apk: Path,
    toolchain: Toolchain,
    signing: SigningConfig,
    runner: Runner,
) -> Path:
    if output_apk.exists():
        raise ApkBuildError("aligned APK already exists")
    _run_checked(
        (toolchain.zipalign, "-f", "-p", "4", unsigned_apk, output_apk),
        cwd=output_apk.parent,
        runner=runner,
        signing=signing,
    )
    if not output_apk.is_file():
        raise ApkBuildError("zipalign did not create an output")
    return output_apk


def sign_once(
    aligned_apk: Path,
    output_apk: Path,
    toolchain: Toolchain,
    signing: SigningConfig,
    runner: Runner,
) -> Path:
    if output_apk.exists():
        raise ApkBuildError("signed APK already exists")
    try:
        TOOLCHAIN.run_apksigner(
            signing,
            apksigner=toolchain.apksigner,
            java=toolchain.java,
            input_apk=aligned_apk,
            output_apk=output_apk,
            runner=runner,
        )
    except Exception as exc:
        raise ApkBuildError(_safe_process_error(exc, signing)) from None
    if not output_apk.is_file():
        raise ApkBuildError("apksigner did not create an output")
    return output_apk


def _apksigner_prefix(toolchain: Toolchain) -> tuple[str, ...]:
    apksigner = Path(toolchain.apksigner).expanduser().resolve()
    if apksigner.suffix.casefold() in {".bat", ".cmd"}:
        java = Path(toolchain.java).expanduser().resolve()
        jar = apksigner.parent / "lib" / "apksigner.jar"
        if not java.is_file() or not jar.is_file():
            raise ApkBuildError("selected apksigner Java/JAR pair is incomplete")
        return str(java), "-jar", str(jar)
    if not apksigner.is_file():
        raise ApkBuildError("apksigner executable is not a file")
    return (str(apksigner),)


def _verify_alignment_once(
    signed_apk: Path,
    config: _ResolvedConfig,
    transaction: Path,
    runner: Runner,
) -> None:
    _run_checked(
        (config.toolchain.zipalign, "-c", "-p", "-v", "4", signed_apk),
        cwd=transaction,
        runner=runner,
        signing=config.signing,
    )


def _verify_signature_once(
    signed_apk: Path,
    config: _ResolvedConfig,
    transaction: Path,
    runner: Runner,
) -> tuple[Mapping[str, Any], Any]:
    completed = _run_checked(
        (
            *_apksigner_prefix(config.toolchain),
            "verify",
            "--verbose",
            "--print-certs",
            signed_apk,
        ),
        cwd=transaction,
        runner=runner,
        signing=config.signing,
    )
    try:
        parsed = TOOLCHAIN.parse_apksigner_verify(
            _completed_output(completed),
            expected_certificate_sha256=config.signing.expected_certificate_sha256,
        )
    except Exception as exc:
        raise ApkBuildError(_safe_process_error(exc, config.signing)) from None
    return parsed, completed


class _CheckedStageRunner:
    def __init__(self, runner: Runner, signing: SigningConfig) -> None:
        self.runner = runner
        self.signing = signing

    def __call__(self, command, **kwargs):
        try:
            completed = self.runner(command, **kwargs)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ApkBuildError(_safe_process_error(exc, self.signing)) from None
        if int(getattr(completed, "returncode", 0)) != 0:
            error = subprocess.CalledProcessError(
                int(completed.returncode),
                command,
                output=getattr(completed, "stdout", None),
                stderr=getattr(completed, "stderr", None),
            )
            raise ApkBuildError(_safe_process_error(error, self.signing))
        return completed


class _ReplayApksignerVerifyRunner:
    def __init__(self, runner: Runner, verified: Any) -> None:
        self.runner = runner
        self.verified = verified

    def __call__(self, command, **kwargs):
        argv = tuple(str(part) for part in command)
        if "verify" in argv and "--print-certs" in argv:
            return subprocess.CompletedProcess(
                command,
                0,
                getattr(self.verified, "stdout", b""),
                getattr(self.verified, "stderr", b""),
            )
        return self.runner(command, **kwargs)


def _ffdec_args(config: _ResolvedConfig, transaction: Path, runner: Runner):
    return {
        "ffdec": Path(config.toolchain.ffdec),
        "java": Path(config.toolchain.java),
        "profile_dir": transaction / "profile",
        "work_dir": transaction / "stage-work",
        "runner": runner,
    }


def _report_value(value: Any) -> Any:
    if isinstance(value, Path):
        raise ApkBuildError("private path is not allowed in a public report")
    if isinstance(value, Mapping):
        return {str(key): _report_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_report_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ApkBuildError(f"unsupported public report value: {type(value).__name__}")


_SAFE_STAGE_FIELDS = (
    "stage",
    "input_sha256",
    "output_sha256",
    "target_class",
    "before_method_sha256",
    "after_method_sha256",
    "match_count",
    "site_ids",
    "before_hashes",
    "after_hashes",
    "asset_logicals",
    "source_version",
    "output_version",
    "is_full_package",
    "verified",
)


def _sanitize_stage_report(stage: str, report: Any) -> Mapping[str, Any]:
    result: dict[str, Any] = {"stage": stage}
    for name in _SAFE_STAGE_FIELDS:
        if name == "stage":
            continue
        if isinstance(report, Mapping):
            present = name in report
            value = report.get(name)
        else:
            present = hasattr(report, name)
            value = getattr(report, name, None)
        if present:
            result[name] = _report_value(value)
    return MappingProxyType(result)


def _require_stage_output(stage: str, report: Any, expected: Path) -> None:
    output = getattr(report, "output_path", None)
    if output is None or _path_key(Path(output)) != _path_key(expected):
        raise ApkBuildError(f"{stage} returned the wrong output path")
    if not expected.is_file():
        raise ApkBuildError(f"{stage} did not create its output")
    if stage == "abyss-mode-equipment":
        if getattr(report, "match_count", None) != 1:
            raise ApkBuildError("abyss gate match count is not one")
    elif getattr(report, "verified", None) is not True:
        raise ApkBuildError(f"{stage} did not return a verified report")


def verify_abyss_gate(
    output_swf: Path,
    *,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    work_dir: Path,
    runner: Runner,
) -> Mapping[str, Any]:
    """Re-export and markerlessly verify the gated class from the signed SWF."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    export_dir = work_dir / "abyss-final-export"
    environment = dict(os.environ)
    environment["APPDATA"] = str(profile_dir.resolve())
    exported = ABYSS._export_target_class(
        output_swf,
        export_dir,
        ffdec,
        java,
        verify_gate=True,
        runner=runner,
        cwd=work_dir,
        environment=environment,
    )
    return MappingProxyType(
        {
            "stage": "abyss-mode-equipment",
            "target_class": ABYSS.TARGET_CLASS,
            "after_method_sha256": _sha256_file(Path(exported)),
            "verified": True,
        }
    )


def _require_final_patch_invariants(
    abyss_report: Mapping[str, Any],
    seris_report: Any,
    render_report: Any,
    resource_report: Any,
    lock: Mapping[str, Any],
) -> None:
    if abyss_report.get("verified") is not True:
        raise ApkBuildError("final abyss gate verification failed")
    seris_sites = tuple(getattr(seris_report, "site_ids", ()))
    if getattr(seris_report, "verified", None) is not True or len(seris_sites) != 9:
        raise ApkBuildError("final Seris verification did not prove nine sites")
    locked_seris = tuple(lock.get("site_ids", ()))
    if locked_seris and seris_sites != locked_seris:
        raise ApkBuildError("final Seris site identities drifted")
    render_sites = tuple(getattr(render_report, "site_ids", ()))
    if getattr(render_report, "verified", None) is not True or len(render_sites) != 3:
        raise ApkBuildError("final render verification did not prove three sites")
    locked_render = tuple(lock.get("render_site_ids", ()))
    if locked_render and render_sites != locked_render:
        raise ApkBuildError("final render site identities drifted")
    if (
        getattr(resource_report, "verified", None) is not True
        or getattr(resource_report, "output_version", None)
        != EXPECTED_FULL_RESOURCE_VERSION
        or getattr(resource_report, "is_full_package", None) is not True
    ):
        raise ApkBuildError("final full-resource-version invariant failed")


def _assert_final_baseline_invariants(
    baseline: Any,
    final: Any,
    lock: Mapping[str, Any],
) -> None:
    for field_name in (
        "package_name",
        "version_code",
        "version_name",
        "manifest_sha256",
        "native_aggregate_sha256",
        "manage_external_storage_count",
        "target_swf_count",
    ):
        if getattr(final, field_name, None) != getattr(baseline, field_name, None):
            raise ApkBuildError(f"final APK {field_name} drifted")
    if dict(getattr(final, "dex_sha256", {})) != dict(
        getattr(baseline, "dex_sha256", {})
    ):
        raise ApkBuildError("final APK DEX hashes drifted")
    save_hashes = lock.get("save_method_sha256")
    if not isinstance(save_hashes, Mapping) or len(save_hashes) != 2:
        raise ApkBuildError("baseline lock does not contain two save-method hashes")
    final_methods = getattr(final, "offline_method_sha256", {})
    for identity, expected in save_hashes.items():
        if not _same_digest(str(final_methods.get(identity, "")), str(expected)):
            raise ApkBuildError(f"final save method hash drifted: {identity}")
    offline_hashes = lock.get("offline_method_sha256")
    offline_identity = "DevConfig_individual/DevConfig_individual"
    if not isinstance(offline_hashes, Mapping) or not _same_digest(
        str(final_methods.get(offline_identity, "")),
        str(offline_hashes.get(offline_identity, "")),
    ):
        raise ApkBuildError("final active offline method hash drifted")
    resource_lock = lock.get("resource_version")
    resource_identity = "boot_ffc6#$script364/$init"
    if not isinstance(resource_lock, Mapping) or not _same_digest(
        str(final_methods.get(resource_identity, "")),
        str(resource_lock.get("after_abc_sha256", "")),
    ):
        raise ApkBuildError("final active resource method hash drifted")


def verify_signed_apk(
    signed_apk: Path,
    config: _ResolvedConfig,
    baseline: Any,
    lock: Mapping[str, Any],
    transaction: Path,
    final_stage_swf: Path,
    *,
    runner: Runner,
) -> tuple[
    Mapping[str, Any], tuple[Mapping[str, Any], ...], str
]:
    verified_signed_sha256 = _sha256_file(signed_apk)
    assert_allowed_member_diff(transaction / "base.apk", signed_apk)
    _verify_alignment_once(signed_apk, config, transaction, runner)
    signature, verified_process = _verify_signature_once(
        signed_apk, config, transaction, runner
    )
    if not _same_digest(_sha256_file(signed_apk), verified_signed_sha256):
        raise ApkBuildError("signed APK changed after verification")
    final_swf = _extract_exactly_one_swf(signed_apk, transaction / "signed-final.swf")
    if not _same_digest(_sha256_file(final_swf), _sha256_file(final_stage_swf)):
        raise ApkBuildError("signed APK SWF differs from the final patch stage")
    stage_runner = _CheckedStageRunner(runner, config.signing)
    args = _ffdec_args(config, transaction / "final-verify", stage_runner)
    abyss_report = verify_abyss_gate(final_swf, **args)
    seris_report = SERIS.verify_seris_phase4(
        final_swf, lock, timeout=STAGE_TIMEOUT_SECONDS, **args
    )
    render_report = RENDER.verify_render_scale(
        final_swf, lock, timeout=STAGE_TIMEOUT_SECONDS, **args
    )
    resource_report = RESOURCE.verify_resource_version(
        final_swf, lock, timeout=STAGE_TIMEOUT_SECONDS, **args
    )
    _require_final_patch_invariants(
        abyss_report, seris_report, render_report, resource_report, lock
    )
    if not _same_digest(_sha256_file(signed_apk), verified_signed_sha256):
        raise ApkBuildError("signed APK changed after verification")
    replay = _ReplayApksignerVerifyRunner(runner, verified_process)
    final_baseline = inspect_apk(signed_apk, config.toolchain, runner=replay)
    _assert_final_baseline_invariants(baseline, final_baseline, lock)
    if not _same_digest(_sha256_file(signed_apk), verified_signed_sha256):
        raise ApkBuildError("signed APK changed after verification")
    return signature, (
        _sanitize_stage_report(PATCH_ORDER[0], abyss_report),
        _sanitize_stage_report(PATCH_ORDER[1], seris_report),
        _sanitize_stage_report(PATCH_ORDER[2], render_report),
        _sanitize_stage_report(PATCH_ORDER[3], resource_report),
    ), verified_signed_sha256


def _report_payload(report: ApkBuildReport) -> dict[str, Any]:
    return {
        "aligned": report.aligned,
        "certificate_sha256": report.certificate_sha256,
        "full_resource_version": report.full_resource_version,
        "output_sha256": report.output_sha256,
        "patch_order": list(report.patch_order),
        "signature_schemes": dict(report.signature_schemes),
        "stage_reports": [_report_value(item) for item in report.stage_reports],
        "verified": report.verified,
    }


def canonical_json_bytes(report: ApkBuildReport | Mapping[str, Any]) -> bytes:
    if isinstance(report, ApkBuildReport):
        payload = _report_payload(report)
    elif isinstance(report, Mapping):
        payload = _report_value(report)
    elif is_dataclass(report):
        payload = {
            field.name: _report_value(getattr(report, field.name))
            for field in fields(report)
        }
    else:
        raise ApkBuildError("unsupported report type")
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _stage_publication_file(
    source: Path | None,
    payload: bytes | None,
    parent: Path,
    suffix: str,
) -> _StagedPublication:
    path: Path | None = None
    handle: Any | None = None
    staged: _StagedPublication | None = None
    digest = hashlib.sha256()
    try:
        for _attempt in range(128):
            path = parent / f".offline-apk-{secrets.token_hex(16)}{suffix}"
            try:
                handle = ABYSS._create_staging_handle(path)
            except FileExistsError:
                continue
            break
        if path is None or handle is None:
            raise ApkBuildError("cannot allocate publication staging file")
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise ApkBuildError("publication staging handle is not a regular file")
        initial_identity = (int(opened.st_dev), int(opened.st_ino))
        if initial_identity[0] == 0 or initial_identity[1] == 0:
            raise ApkBuildError("publication staging has no stable identity")
        staged = _StagedPublication(path, initial_identity, "", handle)
        if source is not None:
            with source.open("rb") as reader:
                for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                    digest.update(chunk)
                    handle.write(chunk)
        elif payload is not None:
            digest.update(payload)
            handle.write(payload)
        else:
            raise ApkBuildError("publication staging has no content")
        handle.flush()
        os.fsync(handle.fileno())
        finished = os.fstat(handle.fileno())
        if (int(finished.st_dev), int(finished.st_ino)) != initial_identity:
            raise ApkBuildError("publication staging identity changed")
        if _identity(path) != initial_identity:
            raise ApkBuildError("publication staging identity changed")
        staged = _StagedPublication(
            path, initial_identity, digest.hexdigest(), handle
        )
        return staged
    except BaseException as original_error:
        if staged is not None:
            try:
                _cleanup_publication_staging(staged)
            except BaseException as cleanup_error:
                original_error.add_note(
                    "failed to clean handle-bound publication staging: "
                    f"{type(cleanup_error).__name__}"
                )
        elif handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        raise


def _hash_publication_handle(staged: _StagedPublication) -> str:
    if staged.handle.closed:
        raise ApkBuildError("publication staging handle is closed")
    opened = os.fstat(staged.handle.fileno())
    if (int(opened.st_dev), int(opened.st_ino)) != staged.identity:
        raise ApkBuildError("publication staging handle identity changed")
    position = staged.handle.tell()
    staged.handle.seek(0)
    digest = hashlib.sha256()
    for chunk in iter(lambda: staged.handle.read(1024 * 1024), b""):
        digest.update(chunk)
    staged.handle.seek(position)
    return digest.hexdigest()


def _verify_staged_publication(staged: _StagedPublication) -> None:
    if _identity(staged.path) != staged.identity:
        raise ApkBuildError("publication staging identity changed")
    if not _same_digest(_hash_publication_handle(staged), staged.sha256):
        raise ApkBuildError("publication staging bytes changed")


def _cleanup_publication_staging(staged: _StagedPublication) -> None:
    if staged.handle.closed:
        return
    disposition_error: BaseException | None = None
    try:
        ABYSS._mark_staging_handle_for_delete(staged)
    except BaseException as exc:
        disposition_error = exc
    try:
        staged.handle.close()
    except OSError as exc:
        raise ApkBuildError("failed to close publication staging handle") from exc
    if disposition_error is not None:
        raise ApkBuildError("failed to delete publication staging by handle") from (
            disposition_error
        )


def _close_published_staging(staged: _StagedPublication) -> None:
    if not staged.handle.closed:
        try:
            staged.handle.close()
        except OSError:
            pass


def _rename_publication_handle_no_replace(
    staged: _StagedPublication,
    directory: _OwnedDirectory,
    destination_name: str,
) -> None:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    if directory.handle is None:
        raise ApkBuildError("destination parent directory handle is closed")
    if Path(destination_name).name != destination_name:
        raise ApkBuildError("publication destination must be one filename")

    class FileRenameInfo(ctypes.Structure):
        _fields_ = (
            ("ReplaceIfExists", wintypes.BOOLEAN),
            ("RootDirectory", wintypes.HANDLE),
            ("FileNameLength", wintypes.DWORD),
            ("FileName", wintypes.WCHAR * 1),
        )

    _ctypes, _wintypes, kernel32 = ABYSS._windows_file_api()
    # Win32 FILE_RENAME_INFO requires RootDirectory == NULL.  The destination
    # parent is independently held open without FILE_SHARE_DELETE above, so
    # this absolute path cannot be swapped out between identity checks.
    destination = directory.path / destination_name
    file_name = str(destination).encode("utf-16-le")
    buffer_size = FileRenameInfo.FileName.offset + len(file_name)
    buffer = ctypes.create_string_buffer(buffer_size + 2)
    rename = FileRenameInfo.from_buffer(buffer)
    rename.ReplaceIfExists = False
    rename.RootDirectory = None
    rename.FileNameLength = len(file_name)
    ctypes.memmove(
        ctypes.addressof(buffer) + FileRenameInfo.FileName.offset,
        file_name,
        len(file_name),
    )
    raw_handle = msvcrt.get_osfhandle(staged.handle.fileno())
    if not kernel32.SetFileInformationByHandle(
        raw_handle, 3, buffer, buffer_size + 2
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def _require_published_handle_binding(
    staged: _StagedPublication,
    destination: Path,
    expected_sha256: str,
) -> None:
    if _identity(destination) != staged.identity:
        raise ApkBuildError("published file identity changed")
    if not _same_digest(_hash_publication_handle(staged), expected_sha256):
        raise ApkBuildError("published file bytes changed")


def _stage_publication_pair(
    signed_apk: Path,
    report_bytes: bytes,
    config: _ResolvedConfig,
    expected_output_sha256: str,
) -> tuple[_StagedPublication, _StagedPublication]:
    _require_destination_directory_identity(config.output_parent, "output parent")
    _require_destination_directory_identity(config.report_parent, "report parent")
    output_stage = _stage_publication_file(
        signed_apk, None, config.output_parent.path, ".apk.stage"
    )
    report_stage: _StagedPublication | None = None
    try:
        if not _same_digest(output_stage.sha256, expected_output_sha256):
            raise ApkBuildError("verified signed APK bytes changed before publication")
        report_stage = _stage_publication_file(
            None, report_bytes, config.report_parent.path, ".json.stage"
        )
        _verify_staged_publication(output_stage)
        _verify_staged_publication(report_stage)
        return output_stage, report_stage
    except BaseException:
        if report_stage is not None:
            _cleanup_publication_staging(report_stage)
        _cleanup_publication_staging(output_stage)
        raise


def _cleanup_publication_pair(
    pair: tuple[_StagedPublication, _StagedPublication]
) -> None:
    errors: list[BaseException] = []
    for staged in reversed(pair):
        try:
            _cleanup_publication_staging(staged)
        except BaseException as exc:
            errors.append(exc)
    if errors:
        raise ApkBuildError("failed to clean publication staging handles") from errors[0]


def _publish_staged_pair_exclusive(
    pair: tuple[_StagedPublication, _StagedPublication],
    config: _ResolvedConfig,
    report_bytes: bytes,
    expected_output_sha256: str,
) -> None:
    output_stage, report_stage = pair
    try:
        _verify_staged_publication(output_stage)
        _verify_staged_publication(report_stage)
        _require_destination_directory_identity(config.output_parent, "output parent")
        _require_destination_directory_identity(config.report_parent, "report parent")
        try:
            _rename_publication_handle_no_replace(
                output_stage, config.output_parent, config.output_apk.name
            )
        except OSError:
            if os.path.lexists(config.output_apk):
                raise ApkBuildError("output APK already exists") from None
            raise ApkBuildError("failed to publish output APK by handle") from None
        try:
            _rename_publication_handle_no_replace(
                report_stage, config.report_parent, config.report_path.name
            )
        except OSError:
            if os.path.lexists(config.report_path):
                raise ApkBuildError("report already exists") from None
            raise ApkBuildError("failed to publish report by handle") from None
        _require_destination_directory_identity(config.output_parent, "output parent")
        _require_destination_directory_identity(config.report_parent, "report parent")
        _require_published_handle_binding(
            output_stage, config.output_apk, expected_output_sha256
        )
        _require_published_handle_binding(
            report_stage, config.report_path, hashlib.sha256(report_bytes).hexdigest()
        )
    except BaseException:
        _cleanup_publication_pair(pair)
        raise
    _close_published_staging(output_stage)
    _close_published_staging(report_stage)


def _create_owned_transaction(work_dir: Path) -> _OwnedTransaction:
    path = Path(tempfile.mkdtemp(prefix=".offline-apk-", dir=work_dir)).absolute()
    directory: _OwnedDirectory | None = None
    try:
        directory = _open_destination_directory(path, deny_delete=True)
        _require_destination_directory_identity(directory, "transaction")
        return _OwnedTransaction(path, directory)
    except BaseException as original_error:
        if directory is not None:
            try:
                # The just-created directory is still empty.  Delete the exact
                # opened object by handle; never recurse through its pathname.
                _mark_directory_handle_for_delete(directory)
            except BaseException as cleanup_error:
                original_error.add_note(
                    "failed to delete rejected transaction by handle: "
                    f"{type(cleanup_error).__name__}"
                )
            finally:
                _close_owned_directory(directory)
        else:
            # Without a stable handle the name is untrusted and must not be
            # recursively removed.
            original_error.add_note(
                "transaction path preserved because ownership could not be bound"
            )
        raise


def _remove_transaction_entry(path: Path) -> None:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & 0x400
    ):
        path.unlink()
        return
    if stat.S_ISDIR(metadata.st_mode):
        for child in tuple(path.iterdir()):
            _remove_transaction_entry(child)
        path.rmdir()
        return
    if stat.S_ISREG(metadata.st_mode):
        path.unlink()
        return
    raise ApkBuildError("transaction contains an unsupported filesystem object")


def _clean_owned_transaction(transaction: _OwnedTransaction) -> None:
    directory = transaction.directory
    expected_identity = directory.identity
    original_error: BaseException | None = None
    try:
        _require_destination_directory_identity(directory, "transaction")
        for child in tuple(transaction.path.iterdir()):
            _remove_transaction_entry(child)
        _require_destination_directory_identity(directory, "transaction")
        if any(transaction.path.iterdir()):
            raise ApkBuildError("transaction directory is not empty after cleanup")
        _mark_directory_handle_for_delete(directory)
    except BaseException as exc:
        original_error = exc
    finally:
        _close_owned_directory(directory)
    if original_error is not None:
        raise ApkBuildError("failed to clean handle-bound APK transaction") from (
            original_error
        )

    # Never remove the root by path.  A same-name competitor may appear after
    # the delete-on-close handle is released; it must be preserved.
    if os.path.lexists(transaction.path):
        try:
            current = _directory_identity_at_path(transaction.path)
        except ApkBuildError:
            return
        if current == expected_identity:
            raise ApkBuildError("owned APK transaction remains after handle cleanup")


def _source_identity(metadata: os.stat_result) -> _SourceIdentity:
    return _SourceIdentity(
        device=int(metadata.st_dev),
        inode=int(metadata.st_ino),
        size=int(metadata.st_size),
        modified_ns=int(metadata.st_mtime_ns),
    )


def _require_regular_source(metadata: os.stat_result) -> None:
    if (
        stat.S_ISLNK(metadata.st_mode)
        or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)
        or not stat.S_ISREG(metadata.st_mode)
    ):
        raise ApkBuildError("source APK must remain a regular non-symlink file")


def _copy_source_snapshot(
    source: Path, destination: Path, expected_sha256: str
) -> _SourceIdentity:
    digest = hashlib.sha256()
    try:
        before_metadata = source.lstat()
        _require_regular_source(before_metadata)
        before = _source_identity(before_metadata)
        with source.open("rb") as reader, destination.open("xb") as writer:
            opened = _source_identity(os.fstat(reader.fileno()))
            if opened != before:
                raise ApkBuildError("source APK identity changed before snapshot")
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                digest.update(chunk)
                writer.write(chunk)
            finished = _source_identity(os.fstat(reader.fileno()))
            writer.flush()
            os.fsync(writer.fileno())
        if finished != before:
            raise ApkBuildError("source APK identity changed during snapshot")
        after_metadata = source.lstat()
        _require_regular_source(after_metadata)
        if _source_identity(after_metadata) != before:
            raise ApkBuildError("source APK identity changed during snapshot")
        if not _same_digest(digest.hexdigest(), expected_sha256):
            raise ApkBuildError("source APK changed while creating the build snapshot")
        return before
    except BaseException:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _assert_source_unchanged(
    source: Path, expected_identity: _SourceIdentity, expected_sha256: str
) -> None:
    try:
        metadata = source.lstat()
        _require_regular_source(metadata)
    except OSError:
        raise ApkBuildError("source APK identity changed during the build") from None
    if _source_identity(metadata) != expected_identity:
        raise ApkBuildError("source APK identity changed during the build")
    if not _same_digest(_sha256_file(source), expected_sha256):
        raise ApkBuildError("source APK changed during the build")


def _build_offline_apk(
    config: _ResolvedConfig,
    *,
    runner: Runner,
) -> ApkBuildReport:
    baseline_module = _baseline_module()
    typed_lock = baseline_module.load_base_lock(config.baseline_lock)
    # ApkBaselineLock is Mapping-compatible and owns the single canonical,
    # lstat/fstat-verified snapshot.  Never read the path a second time.
    lock = typed_lock
    baseline = baseline_module.inspect_apk(
        config.source_apk, config.toolchain, runner=runner
    )
    baseline_module.assert_locked_baseline(baseline, typed_lock)

    owned_transaction: _OwnedTransaction | None = _create_owned_transaction(
        config.work_dir
    )
    transaction = owned_transaction.path
    publication_pair: tuple[_StagedPublication, _StagedPublication] | None = None
    original_error: BaseException | None = None
    try:
        base_snapshot = transaction / "base.apk"
        source_identity = _copy_source_snapshot(
            config.source_apk, base_snapshot, str(baseline.apk_sha256)
        )
        swf0 = _extract_exactly_one_swf(base_snapshot, transaction / "stage-00.swf")
        stage_runner = _CheckedStageRunner(runner, config.signing)
        args = _ffdec_args(config, transaction, stage_runner)

        stage_paths = [transaction / f"stage-{index:02d}.swf" for index in range(1, 5)]
        stage_reports: list[Any] = []
        abyss_report = ABYSS.apply_gate_to_swf(swf0, stage_paths[0], **args)
        _require_stage_output(PATCH_ORDER[0], abyss_report, stage_paths[0])
        stage_reports.append(abyss_report)
        seris_report = SERIS.apply_seris_phase4(
            stage_paths[0],
            stage_paths[1],
            lock,
            timeout=STAGE_TIMEOUT_SECONDS,
            **args,
        )
        _require_stage_output(PATCH_ORDER[1], seris_report, stage_paths[1])
        stage_reports.append(seris_report)
        render_report = RENDER.apply_render_scale(
            stage_paths[1],
            stage_paths[2],
            lock,
            timeout=STAGE_TIMEOUT_SECONDS,
            **args,
        )
        _require_stage_output(PATCH_ORDER[2], render_report, stage_paths[2])
        stage_reports.append(render_report)
        resource_report = RESOURCE.apply_resource_version(
            stage_paths[2],
            stage_paths[3],
            lock,
            timeout=STAGE_TIMEOUT_SECONDS,
            **args,
        )
        _require_stage_output(PATCH_ORDER[3], resource_report, stage_paths[3])
        if (
            getattr(resource_report, "output_version", None)
            != EXPECTED_FULL_RESOURCE_VERSION
            or getattr(resource_report, "is_full_package", None) is not True
        ):
            raise ApkBuildError("resource-version stage did not produce a full package")
        stage_reports.append(resource_report)

        unsigned = rewrite_apk_once(
            base_snapshot, stage_paths[3], transaction / "unsigned.apk"
        )
        assert_allowed_member_diff(base_snapshot, unsigned)
        aligned = zipalign_once(
            unsigned,
            transaction / "aligned.apk",
            config.toolchain,
            config.signing,
            runner,
        )
        signed = sign_once(
            aligned,
            transaction / "signed.apk",
            config.toolchain,
            config.signing,
            runner,
        )
        signature, _final_verifiers, verified_signed_sha256 = verify_signed_apk(
            signed,
            config,
            baseline,
            lock,
            transaction,
            stage_paths[3],
            runner=runner,
        )
        _assert_source_unchanged(
            config.source_apk, source_identity, str(baseline.apk_sha256)
        )
        public_stages = tuple(
            _sanitize_stage_report(stage, report)
            for stage, report in zip(PATCH_ORDER, stage_reports, strict=True)
        )
        report = ApkBuildReport(
            output_sha256=verified_signed_sha256,
            certificate_sha256=str(signature["certificate_sha256"]),
            patch_order=PATCH_ORDER,
            stage_reports=public_stages,
            full_resource_version=EXPECTED_FULL_RESOURCE_VERSION,
            aligned=True,
            signature_schemes=MappingProxyType(
                dict(signature["signature_schemes"])
            ),
            verified=True,
        )
        report_bytes = canonical_json_bytes(report)
        publication_pair = _stage_publication_pair(
            signed, report_bytes, config, verified_signed_sha256
        )
        _clean_owned_transaction(owned_transaction)
        owned_transaction = None
        _publish_staged_pair_exclusive(
            publication_pair,
            config,
            report_bytes,
            verified_signed_sha256,
        )
        publication_pair = None
        return report
    except BaseException as exc:
        original_error = exc
        raise
    finally:
        if publication_pair is not None:
            try:
                _cleanup_publication_pair(publication_pair)
            except BaseException as cleanup_error:
                if original_error is None:
                    raise
                try:
                    original_error.add_note(
                        "failed to clean publication staging handles"
                    )
                except AttributeError:
                    pass
        if owned_transaction is not None:
            try:
                _clean_owned_transaction(owned_transaction)
            except BaseException as cleanup_error:
                if original_error is None:
                    raise
                try:
                    original_error.add_note(
                        "failed to clean handle-bound APK transaction"
                    )
                except AttributeError:
                    pass


def build_offline_apk(
    config: OfflineApkBuildConfig,
    *,
    runner: Runner = subprocess_runner,
) -> ApkBuildReport:
    """Run the four locked patches and exclusively publish a verified APK/report."""
    resolved = _resolve_config(config)
    try:
        try:
            return _build_offline_apk(resolved, runner=runner)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            safe = _safe_process_error(exc, resolved.signing)
            raise ApkBuildError(safe) from None
    finally:
        _close_owned_directory(resolved.report_parent)
        _close_owned_directory(resolved.output_parent)


__all__ = [
    "ApkBaselineReport",
    "ApkBuildError",
    "ApkBuildReport",
    "EXPECTED_FULL_RESOURCE_VERSION",
    "OfflineApkBuildConfig",
    "PATCH_ORDER",
    "SigningConfig",
    "TARGET_SWF",
    "Toolchain",
    "assert_allowed_member_diff",
    "assert_locked_baseline",
    "build_offline_apk",
    "canonical_json_bytes",
    "inspect_apk",
    "load_base_lock",
    "rewrite_apk_once",
    "sign_once",
    "verify_abyss_gate",
    "verify_signed_apk",
    "zipalign_once",
]
