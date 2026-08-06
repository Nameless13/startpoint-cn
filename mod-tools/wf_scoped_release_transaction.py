#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fail-closed filesystem transaction for scoped release archives and manifest."""
from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import wf_scoped_release_archive as archive
from wf_scoped_release_validation import (
    TransactionError,
    parts as _parts,
    validate_blob as _validate_blob,
)


class _UncertainLinkError(TransactionError):
    """A link result cannot be attributed safely; retain the recovery lock."""


@dataclass(frozen=True, slots=True)
class _OwnedPath:
    path: Path
    object_id: tuple[int, int]


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


def _object_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


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


def _write_exclusive(
    path: Path, payload: bytes, owned: list[_OwnedPath]
) -> None:
    _assert_plain_ancestry(path.parent, leaf="directory")
    with path.open("xb") as stream:
        # Record ownership immediately after exclusive creation.  Callers may then
        # retry cleanup without ever deleting a pre-existing foreign path.
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise TransactionError(f"exclusive output is not a regular file: {path}")
        owned.append(_OwnedPath(path, _object_identity(metadata)))
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


def _remove_owned(paths: Iterable[_OwnedPath]) -> list[str]:
    errors: list[str] = []
    for owned in reversed(tuple(paths)):
        path = owned.path
        try:
            _assert_plain_ancestry(path.parent, leaf="directory")
            try:
                metadata = path.lstat()
            except FileNotFoundError:
                continue
            if (
                _is_reparse(path)
                or not stat.S_ISREG(metadata.st_mode)
                or _object_identity(metadata) != owned.object_id
            ):
                errors.append(f"{path}: owned identity changed; left untouched")
                continue
            path.unlink()
        except (OSError, TransactionError) as error:
            errors.append(f"{path}: {error}")
    return errors


def _remove_owned_directory(owned: _OwnedPath) -> list[str]:
    path = owned.path
    try:
        _assert_plain_ancestry(path.parent, leaf="directory")
        metadata = path.lstat()
        if (
            _is_reparse(path)
            or not stat.S_ISDIR(metadata.st_mode)
            or _object_identity(metadata) != owned.object_id
        ):
            return [f"{path}: owned directory identity changed; left untouched"]
        path.rmdir()
        return []
    except (OSError, TransactionError) as error:
        return [f"{path}: {error}"]


def _probe_owned_at(path: Path, *, label: str) -> _OwnedPath | None:
    target = _absolute(path)
    _assert_plain_ancestry(target.parent, leaf="directory")
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        return None
    if _is_reparse(target) or not stat.S_ISREG(metadata.st_mode):
        raise TransactionError(f"{label} is not a plain regular file")
    return _OwnedPath(target, _object_identity(metadata))


def _owned_at(path: Path, *, label: str) -> _OwnedPath:
    owned = _probe_owned_at(path, label=label)
    if owned is None:
        raise TransactionError(f"{label} is missing: {path}")
    return owned


def _link_owned(
    source: _OwnedPath, target: Path, created: list[_OwnedPath]
) -> None:
    try:
        os.link(source.path, target, follow_symlinks=False)
    except BaseException as error:
        try:
            linked = _probe_owned_at(target, label="ambiguous link target")
        except (OSError, TransactionError) as probe_error:
            raise _UncertainLinkError(
                f"cannot prove ambiguous link outcome for {target}: {probe_error}"
            ) from error
        if linked is None:
            raise
        if linked.object_id != source.object_id:
            raise _UncertainLinkError(
                f"ambiguous link target identity changed; left untouched: {target}"
            ) from error
        created.append(linked)
        raise
    linked = _owned_at(target, label="linked archive")
    if linked.object_id != source.object_id:
        raise _UncertainLinkError(
            f"linked archive identity differs from pending source: {target}"
        )
    created.append(linked)


def stage_archives(plans: Iterable[object], staging_dir: Path) -> tuple[Path, ...]:
    parts = _parts(plans)
    staging_dir = _absolute(Path(staging_dir))
    if staging_dir.exists() or staging_dir.is_symlink():
        raise TransactionError(f"staging directory already exists: {staging_dir}")
    _assert_plain_ancestry(staging_dir.parent, leaf="directory")
    staging_dir.mkdir(parents=False, exist_ok=False)
    staging_owned = _OwnedPath(
        staging_dir, _object_identity(staging_dir.lstat())
    )
    created: list[_OwnedPath] = []
    try:
        _assert_plain_ancestry(staging_dir, leaf="directory")
        for part in parts:
            target = staging_dir / part.name
            _write_exclusive(target, part.blob, created)
        _fsync_directory(staging_dir)
        return tuple(item.path for item in created)
    except BaseException as error:
        failures = _remove_owned(created)
        failures.extend(_remove_owned_directory(staging_owned))
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
    created: list[_OwnedPath] = []
    private_created: list[_OwnedPath] = []
    temporary: _OwnedPath | None = None
    lock_created = False
    committed = False
    lock_owned: list[_OwnedPath] = []
    try:
        _write_exclusive(
            lock, hashlib.sha256(manifest_preimage).digest(), lock_owned
        )
        lock_created = True
        for part, pending in zip(parts, private, strict=True):
            _write_exclusive(pending, part.blob, private_created)
        _fsync_directory(active)

        for part, pending, target in zip(parts, private, targets, strict=True):
            pending_owned = next(
                item for item in private_created if item.path == pending
            )
            _link_owned(pending_owned, target, created)
            raw, _file_id = _read_stable(target, f"linked archive {part.name}")
            if raw != part.blob:
                raise TransactionError(f"linked archive readback drift: {part.name}")
            pending_cleanup = _remove_owned((pending_owned,))
            if pending_cleanup:
                raise TransactionError(
                    "pending archive cleanup incomplete: "
                    + "; ".join(pending_cleanup)
                )
            private_created.remove(pending_owned)
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
        temporary_path = Path(temporary_name)
        temporary = _OwnedPath(
            temporary_path, _object_identity(os.fstat(descriptor))
        )
        with os.fdopen(descriptor, "wb") as stream:
            os.chmod(temporary_path, stat.S_IMODE(manifest.stat().st_mode))
            stream.write(manifest_output)
            stream.flush()
            os.fsync(stream.fileno())
        staged_manifest, _staged_id = _read_stable(
            temporary_path, "staged manifest"
        )
        if staged_manifest != manifest_output:
            raise TransactionError("manifest staging readback drift")
        _verify_final(parts, targets, archive_ids)
        current_manifest, current_id = _read_stable(manifest, "manifest final preimage")
        if current_manifest != manifest_preimage or current_id != manifest_id:
            raise TransactionError("manifest changed before atomic replace")
        os.replace(temporary_path, manifest)
        temporary = None
        committed = True
        _fsync_directory(manifest.parent)
        callback("after_manifest")
    except BaseException as error:
        lock_created = lock_created or bool(lock_owned)
        cleanup = _remove_owned(
            ([temporary] if temporary is not None else [])
        )
        cleanup.extend(_remove_owned(private_created))
        if isinstance(error, _UncertainLinkError):
            cleanup.append(str(error))
        if committed:
            detail = (
                "; cleanup incomplete: " + "; ".join(cleanup) if cleanup else ""
            )
            raise TransactionError(
                "manifest committed but completion failed; release lock retained"
                + detail
            ) from error
        if not committed:
            cleanup.extend(_remove_owned(created))
            try:
                _fsync_directory(active)
            except OSError as cleanup_error:
                cleanup.append(f"fsync {active}: {cleanup_error}")
        if cleanup:
            raise TransactionError(
                "rollback incomplete; release lock retained: " + "; ".join(cleanup)
            ) from error
        if lock_created:
            lock_cleanup = _remove_owned(lock_owned)
            if lock_cleanup:
                raise TransactionError(
                    "release lock retained after failure: "
                    + "; ".join(lock_cleanup)
                ) from error
            lock_created = False
        raise
    if lock_created:
        lock_cleanup = _remove_owned(lock_owned)
        if lock_cleanup:
            raise TransactionError(
                "manifest committed but release lock cleanup failed: "
                + "; ".join(lock_cleanup)
            )
    return targets
