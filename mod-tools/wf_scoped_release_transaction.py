#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fail-closed filesystem transaction for scoped release archives and manifest."""
from __future__ import annotations

import hashlib
import io
import os
import re
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Callable, Iterable

import wf_scoped_release_archive as archive


ARCHIVE_RE = re.compile(
    r"^pinball-(\d+\.\d+\.\d+)-(\d+\.\d+\.\d+)-([1-9]\d*)-([a-z0-9]+)\.zip$"
)
MEMBER_RE = {
    root: re.compile(rf"^{re.escape(prefix)}[0-9a-f]{{2}}/[0-9a-f]{{38}}$")
    for root, prefix in archive.ROOT_PREFIXES.items()
}


class TransactionError(RuntimeError):
    """The filesystem transaction failed closed or retained its recovery lock."""


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _is_reparse(path: Path) -> bool:
    path = Path(path)
    if path.is_symlink():
        return True
    junction = getattr(path, "is_junction", None)
    if junction is not None and junction():
        return True
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & marker)


def _ancestry(path: Path) -> tuple[Path, ...]:
    current = _absolute(path)
    result = [current]
    while current.parent != current:
        current = current.parent
        result.append(current)
    return tuple(reversed(result))


def _assert_plain_ancestry(path: Path, *, leaf: str) -> Path:
    chain = _ancestry(path)
    for index, component in enumerate(chain):
        try:
            metadata = component.lstat()
        except OSError as error:
            raise TransactionError(f"missing or unreadable ancestor: {component}") from error
        if _is_reparse(component):
            raise TransactionError(f"ancestor is a symlink/junction/reparse: {component}")
        expected_leaf = index == len(chain) - 1
        if not expected_leaf and not stat.S_ISDIR(metadata.st_mode):
            raise TransactionError(f"ancestor is not a directory: {component}")
        if expected_leaf and leaf == "directory" and not stat.S_ISDIR(metadata.st_mode):
            raise TransactionError(f"expected directory: {component}")
        if expected_leaf and leaf == "file" and not stat.S_ISREG(metadata.st_mode):
            raise TransactionError(f"expected regular file: {component}")
    return chain[-1]


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def _read_stable(path: Path, label: str) -> tuple[bytes, tuple[int, int, int, int]]:
    target = _assert_plain_ancestry(path, leaf="file")
    before = target.lstat()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise TransactionError(f"{label} opened object is not a regular file")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1 << 20):
            chunks.append(chunk)
        after_open = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = _assert_plain_ancestry(target, leaf="file").lstat()
    identities = {_identity(item) for item in (before, opened, after_open, after)}
    if len(identities) != 1:
        raise TransactionError(f"{label} identity changed during read")
    return b"".join(chunks), _identity(after)


def _parts(plans: Iterable[object]) -> tuple[archive.ArchivePart, ...]:
    flattened: list[archive.ArchivePart] = []
    for plan in plans:
        values = getattr(plan, "parts", None)
        spec = getattr(plan, "spec", None)
        if not isinstance(values, tuple) or any(
            not isinstance(part, archive.ArchivePart) for part in values
        ):
            raise TransactionError("release plan contains invalid archive parts")
        if [part.sequence for part in values] != list(range(1, len(values) + 1)):
            raise TransactionError("release plan archive sequence is not contiguous")
        if any(part.root not in archive.CLIENT_ROOTS for part in values):
            raise TransactionError("release plan archive root is invalid")
        roots = [archive.CLIENT_ROOTS.index(part.root) for part in values]
        if roots != sorted(roots):
            raise TransactionError("release plan archive roots are not canonical")
        for part in values:
            match = ARCHIVE_RE.fullmatch(part.name)
            if match is None or int(match[3]) != part.sequence:
                raise TransactionError(f"non-canonical archive filename: {part.name!r}")
            if spec is not None and (
                match[1] != getattr(spec, "from_version", None)
                or match[2] != getattr(spec, "to_version", None)
                or match[4] != getattr(spec, "tag", None)
            ):
                raise TransactionError(f"archive filename differs from edge spec: {part.name}")
            _validate_blob(part, part.blob)
        flattened.extend(values)
    if len({part.name for part in flattened}) != len(flattened):
        raise TransactionError("duplicate archive filename across release plans")
    return tuple(flattened)


def _validate_blob(part: archive.ArchivePart, blob: bytes) -> None:
    if not isinstance(blob, bytes) or not blob or len(blob) > archive.CI_ZIP_CAP:
        raise TransactionError(
            f"archive exceeds final 5 MiB hard cap or is empty: {part.name}"
        )
    if part.root not in MEMBER_RE:
        raise TransactionError(f"archive has invalid root: {part.root!r}")
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zipped:
            infos = zipped.infolist()
            names = [info.filename for info in infos]
            if not names or names != sorted(names) or len(names) != len(set(names)):
                raise TransactionError(f"archive member set/order is invalid: {part.name}")
            for info in infos:
                if (
                    MEMBER_RE[part.root].fullmatch(info.filename) is None
                    or info.date_time != archive.ZIP_TIMESTAMP
                    or info.compress_type != zipfile.ZIP_DEFLATED
                    or info.create_system != 3
                    or info.external_attr != archive.ZIP_MODE
                    or info.flag_bits != 0
                    or info.extra != b""
                    or info.comment != b""
                    or info.is_dir()
                ):
                    raise TransactionError(
                        f"archive member path/metadata is invalid: {part.name}!{info.filename}"
                    )
            if zipped.comment != b"" or zipped.testzip() is not None:
                raise TransactionError(f"archive CRC/comment validation failed: {part.name}")
    except TransactionError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise TransactionError(f"invalid final archive {part.name}: {error}") from error


def _write_exclusive(path: Path, payload: bytes, owned: list[Path]) -> None:
    _assert_plain_ancestry(path.parent, leaf="directory")
    with path.open("xb") as stream:
        # Record ownership immediately after exclusive creation.  Callers may then
        # retry cleanup without ever deleting a pre-existing foreign path.
        owned.append(path)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    actual, _file_id = _read_stable(path, f"exclusive write {path.name}")
    if actual != payload:
        raise TransactionError(f"exclusive write readback drift: {path}")


def _fsync_directory(path: Path) -> None:
    directory = _assert_plain_ancestry(path, leaf="directory")
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        if os.name == "nt":
            return
        raise
    try:
        os.fsync(descriptor)
    except OSError:
        if os.name != "nt":
            raise
    finally:
        os.close(descriptor)


def _remove(paths: Iterable[Path]) -> list[str]:
    errors: list[str] = []
    for path in reversed(tuple(paths)):
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            errors.append(f"{path}: {error}")
    return errors


def stage_archives(plans: Iterable[object], staging_dir: Path) -> tuple[Path, ...]:
    parts = _parts(plans)
    staging_dir = _absolute(Path(staging_dir))
    if staging_dir.exists() or staging_dir.is_symlink():
        raise TransactionError(f"staging directory already exists: {staging_dir}")
    _assert_plain_ancestry(staging_dir.parent, leaf="directory")
    staging_dir.mkdir(parents=False, exist_ok=False)
    created: list[Path] = []
    try:
        _assert_plain_ancestry(staging_dir, leaf="directory")
        for part in parts:
            target = staging_dir / part.name
            _write_exclusive(target, part.blob, created)
        _fsync_directory(staging_dir)
        return tuple(created)
    except BaseException as error:
        failures = _remove(created)
        try:
            staging_dir.rmdir()
        except OSError as cleanup_error:
            failures.append(f"{staging_dir}: {cleanup_error}")
        if failures:
            raise TransactionError(
                "staging cleanup incomplete: " + "; ".join(failures)
            ) from error
        raise


def _verify_final(
    parts: tuple[archive.ArchivePart, ...],
    targets: tuple[Path, ...],
    identities: dict[Path, tuple[int, int, int, int]] | None = None,
) -> dict[Path, tuple[int, int, int, int]]:
    verified: dict[Path, tuple[int, int, int, int]] = {}
    for part, target in zip(parts, targets, strict=True):
        raw, file_id = _read_stable(target, f"final archive {part.name}")
        if raw != part.blob:
            raise TransactionError(f"final archive bytes changed: {part.name}")
        _validate_blob(part, raw)
        if identities is not None and identities.get(target) != file_id:
            raise TransactionError(f"final archive identity changed: {part.name}")
        verified[target] = file_id
    return verified


def publish_transaction(
    plans: Iterable[object],
    active_dir: Path,
    manifest_path: Path,
    *,
    manifest_preimage: bytes,
    manifest_output: bytes,
    checkpoint: Callable[[str], None] | None = None,
) -> tuple[Path, ...]:
    parts = _parts(plans)
    active = _assert_plain_ancestry(Path(active_dir), leaf="directory")
    manifest = _assert_plain_ancestry(Path(manifest_path), leaf="file")
    if active.parent != manifest.parent:
        raise TransactionError("manifest must be a sibling of the active directory")
    manifest_raw, manifest_id = _read_stable(manifest, "manifest preimage")
    if manifest_raw != manifest_preimage:
        raise TransactionError("manifest changed before archive publication")

    targets = tuple(active / part.name for part in parts)
    if any(path.exists() or path.is_symlink() for path in targets):
        raise TransactionError("one or more archive targets already exist")
    lock = manifest.parent / ".wf-scoped-release.lock"
    token = uuid.uuid4().hex
    private = tuple(
        active / f".wf-scoped-{token}-{index}.pending"
        for index, _part in enumerate(parts, start=1)
    )
    callback = checkpoint or (lambda _phase: None)
    created: list[Path] = []
    private_created: list[Path] = []
    temporary: Path | None = None
    lock_created = False
    committed = False
    lock_owned: list[Path] = []
    try:
        _write_exclusive(
            lock, hashlib.sha256(manifest_preimage).digest(), lock_owned
        )
        lock_created = True
        for part, pending in zip(parts, private, strict=True):
            _write_exclusive(pending, part.blob, private_created)
        _fsync_directory(active)

        for part, pending, target in zip(parts, private, targets, strict=True):
            os.link(pending, target, follow_symlinks=False)
            created.append(target)
            raw, _file_id = _read_stable(target, f"linked archive {part.name}")
            if raw != part.blob:
                raise TransactionError(f"linked archive readback drift: {part.name}")
            pending.unlink()
            private_created.remove(pending)
            callback("after_archive")
        _fsync_directory(active)
        archive_ids = _verify_final(parts, targets)

        current_manifest, current_id = _read_stable(manifest, "manifest commit point")
        if current_manifest != manifest_preimage or current_id != manifest_id:
            raise TransactionError("manifest changed before commit point")
        callback("before_manifest")
        _verify_final(parts, targets, archive_ids)
        current_manifest, current_id = _read_stable(manifest, "manifest checkpoint")
        if current_manifest != manifest_preimage or current_id != manifest_id:
            raise TransactionError("manifest changed during commit checkpoint")

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{manifest.name}.", suffix=".tmp", dir=manifest.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            os.chmod(temporary, stat.S_IMODE(manifest.stat().st_mode))
            stream.write(manifest_output)
            stream.flush()
            os.fsync(stream.fileno())
        staged_manifest, _staged_id = _read_stable(temporary, "staged manifest")
        if staged_manifest != manifest_output:
            raise TransactionError("manifest staging readback drift")
        _verify_final(parts, targets, archive_ids)
        current_manifest, current_id = _read_stable(manifest, "manifest final preimage")
        if current_manifest != manifest_preimage or current_id != manifest_id:
            raise TransactionError("manifest changed before atomic replace")
        os.replace(temporary, manifest)
        temporary = None
        committed = True
        _fsync_directory(manifest.parent)
        callback("after_manifest")
    except BaseException as error:
        lock_created = lock_created or bool(lock_owned)
        cleanup = _remove(([temporary] if temporary is not None else []))
        cleanup.extend(_remove(private_created))
        if committed:
            detail = (
                "; cleanup incomplete: " + "; ".join(cleanup) if cleanup else ""
            )
            raise TransactionError(
                "manifest committed but completion failed; release lock retained"
                + detail
            ) from error
        if not committed:
            cleanup.extend(_remove(created))
            try:
                _fsync_directory(active)
            except OSError as cleanup_error:
                cleanup.append(f"fsync {active}: {cleanup_error}")
        if cleanup:
            raise TransactionError(
                "rollback incomplete; release lock retained: " + "; ".join(cleanup)
            ) from error
        if lock_created:
            try:
                lock.unlink()
                lock_created = False
            except OSError as cleanup_error:
                raise TransactionError(
                    f"release lock retained after failure: {cleanup_error}"
                ) from error
        raise
    if lock_created:
        try:
            lock.unlink()
        except OSError as error:
            raise TransactionError(
                f"manifest committed but release lock cleanup failed: {error}"
            ) from error
    return targets
