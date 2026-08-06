#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic ZIP assembly and manifest-last filesystem transaction helpers."""
from __future__ import annotations

import hashlib
import io
import os
import re
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Protocol, Sequence


CI_ZIP_CAP = 5 << 20
ZIP_TIMESTAMP = (2026, 8, 6, 0, 0, 0)
ZIP_MODE = (stat.S_IFREG | 0o644) << 16
CLIENT_ROOTS = ("common", "medium", "android")
ROOT_PREFIXES = {
    "common": "production/upload/",
    "medium": "production/medium_upload/",
    "android": "production/android_upload/",
}
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
TAG_RE = re.compile(r"^[a-z0-9]+$")


class ArchiveError(RuntimeError):
    """The archive plan or filesystem transaction is unsafe."""


class PayloadEntry(Protocol):
    root: str
    member_name: str
    payload: bytes


@dataclass(frozen=True, slots=True)
class ArchivePart:
    root: str
    sequence: int
    name: str
    blob: bytes


def _version(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or VERSION_RE.fullmatch(value) is None:
        raise ArchiveError(f"invalid archive version: {value!r}")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def _is_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        junction = getattr(path, "is_junction", None)
        if junction is not None and junction():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attributes & marker)
    except OSError:
        return False


def _compressed_size(payload: bytes) -> int:
    import zlib

    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return len(compressor.compress(payload) + compressor.flush())


def _entry_cost(entry: PayloadEntry) -> int:
    try:
        name_size = len(entry.member_name.encode("ascii"))
    except UnicodeEncodeError as error:
        raise ArchiveError(f"ZIP member name is not ASCII: {entry.member_name!r}") from error
    # Local header (30), central header (46), and the name in both records.
    return 76 + (2 * name_size) + _compressed_size(entry.payload)


def _archive_blob(entries: Sequence[PayloadEntry]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for entry in entries:
            info = zipfile.ZipInfo(entry.member_name, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = ZIP_MODE
            info.extra = b""
            info.comment = b""
            archive.writestr(
                info,
                entry.payload,
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
    return output.getvalue()


def _verify_blob(
    blob: bytes, entries: Sequence[PayloadEntry], max_zip_bytes: int
) -> None:
    if len(blob) > max_zip_bytes:
        raise ArchiveError(
            f"ZIP hard cap exceeded: actual={len(blob)} cap={max_zip_bytes}"
        )
    expected = [entry.member_name for entry in entries]
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if names != expected or len(names) != len(set(names)):
                raise ArchiveError("ZIP readback member set or order drift")
            for info, entry in zip(infos, entries, strict=True):
                if (
                    info.date_time != ZIP_TIMESTAMP
                    or info.compress_type != zipfile.ZIP_DEFLATED
                    or info.create_system != 3
                    or info.external_attr != ZIP_MODE
                    or info.flag_bits != 0
                    or info.extra != b""
                    or info.comment != b""
                    or info.is_dir()
                    or archive.read(info) != entry.payload
                ):
                    raise ArchiveError(f"ZIP readback drift: {info.filename}")
            if archive.comment != b"":
                raise ArchiveError("ZIP archive comment drift")
            bad = archive.testzip()
            if bad is not None:
                raise ArchiveError(f"ZIP CRC failure: {bad}")
    except ArchiveError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise ArchiveError(f"cannot verify generated ZIP: {error}") from error


def build_parts(
    entries: Iterable[PayloadEntry],
    *,
    roots: tuple[str, ...],
    from_version: str,
    to_version: str,
    tag: str,
    max_zip_bytes: int,
) -> tuple[ArchivePart, ...]:
    if (
        not isinstance(roots, tuple)
        or not roots
        or len(set(roots)) != len(roots)
        or any(root not in CLIENT_ROOTS for root in roots)
        or tuple(root for root in CLIENT_ROOTS if root in roots) != roots
    ):
        raise ArchiveError("roots must be unique client roots in canonical order")
    if _version(to_version) <= _version(from_version):
        raise ArchiveError("archive edge version must increase")
    if not isinstance(tag, str) or TAG_RE.fullmatch(tag) is None:
        raise ArchiveError("archive tag must contain lowercase ASCII letters and digits")
    if type(max_zip_bytes) is not int or max_zip_bytes < 22:
        raise ArchiveError("max_zip_bytes must be an integer of at least 22")
    if max_zip_bytes > CI_ZIP_CAP:
        raise ArchiveError("max_zip_bytes cannot exceed the 5 MiB CI hard cap")

    grouped = {root: [] for root in roots}
    for entry in entries:
        if entry.root not in grouped:
            raise ArchiveError(f"unsupported client root: {entry.root!r}")
        if not isinstance(entry.member_name, str) or not isinstance(entry.payload, bytes):
            raise ArchiveError("archive entry name and payload have invalid types")
        grouped[entry.root].append(entry)

    planned: list[tuple[str, list[PayloadEntry]]] = []
    for root in roots:
        ordered = sorted(grouped[root], key=lambda item: item.member_name)
        if len({entry.member_name for entry in ordered}) != len(ordered):
            raise ArchiveError(f"duplicate ZIP member in {root}")
        current: list[PayloadEntry] = []
        current_size = 22  # empty archive end-of-central-directory record
        for entry in ordered:
            cost = _entry_cost(entry)
            if 22 + cost > max_zip_bytes:
                raise ArchiveError(
                    f"single member exceeds ZIP hard cap: {entry.member_name}"
                )
            if current and current_size + cost > max_zip_bytes:
                planned.append((root, current))
                current = []
                current_size = 22
            current.append(entry)
            current_size += cost
        if current:
            planned.append((root, current))

    parts: list[ArchivePart] = []
    for sequence, (root, part_entries) in enumerate(planned, start=1):
        name = f"pinball-{from_version}-{to_version}-{sequence}-{tag}.zip"
        blob = _archive_blob(part_entries)
        _verify_blob(blob, part_entries, max_zip_bytes)
        parts.append(ArchivePart(root, sequence, name, blob))
    return tuple(parts)


def attest_plan_parts(
    entries: Iterable[PayloadEntry], parts: Iterable[ArchivePart]
) -> None:
    """Fail closed if a plan's ZIPs omit, add, move, or alter any payload."""
    selected = tuple(entries)
    expected = {(entry.root, entry.member_name): entry.payload for entry in selected}
    if len(expected) != len(selected):
        raise ArchiveError("release plan contains duplicate expected entries")
    actual: dict[tuple[str, str], bytes] = {}
    for part in parts:
        if part.root not in ROOT_PREFIXES:
            raise ArchiveError(f"archive part has invalid root: {part.root!r}")
        try:
            with zipfile.ZipFile(io.BytesIO(part.blob)) as zipped:
                infos = zipped.infolist()
                names = [info.filename for info in infos]
                if names != sorted(names):
                    raise ArchiveError(f"archive part member order drift: {part.name}")
                if len(infos) != len(set(names)):
                    raise ArchiveError(f"archive part has duplicate members: {part.name}")
                for info in infos:
                    if (
                        info.date_time != ZIP_TIMESTAMP
                        or info.compress_type != zipfile.ZIP_DEFLATED
                        or info.create_system != 3
                        or info.external_attr != ZIP_MODE
                        or info.flag_bits != 0
                        or info.extra != b""
                        or info.comment != b""
                        or info.is_dir()
                    ):
                        raise ArchiveError(
                            f"archive part metadata drift: {part.name}!{info.filename}"
                        )
                    if not info.filename.startswith(ROOT_PREFIXES[part.root]):
                        raise ArchiveError(
                            f"archive member is in the wrong root: {info.filename}"
                        )
                    key = part.root, info.filename
                    if key in actual:
                        raise ArchiveError(f"archive member repeated across parts: {key}")
                    actual[key] = zipped.read(info)
                if zipped.testzip() is not None:
                    raise ArchiveError(f"archive part failed CRC readback: {part.name}")
                if zipped.comment != b"":
                    raise ArchiveError(f"archive part comment drift: {part.name}")
        except ArchiveError:
            raise
        except (OSError, zipfile.BadZipFile, RuntimeError) as error:
            raise ArchiveError(f"cannot attest archive part {part.name}: {error}") from error
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(key for key in expected.keys() & actual.keys() if expected[key] != actual[key])
    if missing or extra or changed:
        raise ArchiveError(
            "archive plan payload mismatch: "
            f"missing={missing[:3]} extra={extra[:3]} changed={changed[:3]}"
        )


def _parts(plans: Iterable[object]) -> tuple[ArchivePart, ...]:
    flattened: list[ArchivePart] = []
    for plan in plans:
        values = getattr(plan, "parts", None)
        if not isinstance(values, tuple):
            raise ArchiveError("release plan parts must be a tuple")
        if any(not isinstance(part, ArchivePart) for part in values):
            raise ArchiveError("release plan contains an invalid archive part")
        flattened.extend(values)
    if len({part.name for part in flattened}) != len(flattened):
        raise ArchiveError("duplicate archive filename across release plans")
    for part in flattened:
        if Path(part.name).name != part.name or not part.name.endswith(".zip"):
            raise ArchiveError(f"unsafe archive filename: {part.name!r}")
    return tuple(flattened)


def _write_exclusive(path: Path, payload: bytes) -> None:
    created = False
    try:
        with path.open("xb") as stream:
            created = True
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != payload:
            raise ArchiveError(f"write readback drift: {path}")
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
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


def stage_archives(plans: Iterable[object], staging_dir: Path) -> tuple[Path, ...]:
    parts = _parts(plans)
    staging_dir = Path(staging_dir)
    if staging_dir.exists() or staging_dir.is_symlink():
        raise ArchiveError(f"staging directory already exists: {staging_dir}")
    if _is_reparse(staging_dir.parent):
        raise ArchiveError(f"staging parent is a reparse point: {staging_dir.parent}")
    staging_dir.mkdir(parents=True, exist_ok=False)
    if _is_reparse(staging_dir):
        raise ArchiveError(f"staging directory became a reparse point: {staging_dir}")
    created: list[Path] = []
    try:
        for part in parts:
            target = staging_dir / part.name
            _write_exclusive(target, part.blob)
            created.append(target)
        _fsync_directory(staging_dir)
        return tuple(created)
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        try:
            staging_dir.rmdir()
        except OSError:
            pass
        raise


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
    active_dir, manifest_path = Path(active_dir), Path(manifest_path)
    if _is_reparse(active_dir) or not active_dir.is_dir():
        raise ArchiveError(f"active directory is unsafe: {active_dir}")
    if _is_reparse(manifest_path) or not manifest_path.is_file():
        raise ArchiveError(f"manifest path is unsafe: {manifest_path}")
    if _is_reparse(manifest_path.parent):
        raise ArchiveError(f"manifest parent is a reparse point: {manifest_path.parent}")
    if manifest_path.parent.resolve() != active_dir.parent.resolve():
        raise ArchiveError("manifest must be a sibling of the active directory")
    if manifest_path.read_bytes() != manifest_preimage:
        raise ArchiveError("manifest changed before archive publication")

    targets = [active_dir / part.name for part in parts]
    existing = [path for path in targets if path.exists() or path.is_symlink()]
    if existing:
        raise ArchiveError(f"archive target already exists: {existing[0].name}")

    lock_path = manifest_path.parent / ".wf-scoped-release.lock"
    created: list[Path] = []
    temporary: Path | None = None
    committed = False
    lock_created = False
    callback = checkpoint or (lambda _phase: None)
    manifest_mode = stat.S_IMODE(manifest_path.stat().st_mode)
    try:
        _write_exclusive(lock_path, hashlib.sha256(manifest_preimage).digest())
        lock_created = True
        for part, target in zip(parts, targets, strict=True):
            _write_exclusive(target, part.blob)
            created.append(target)
            callback("after_archive")
        _fsync_directory(active_dir)

        if manifest_path.read_bytes() != manifest_preimage:
            raise ArchiveError("manifest changed before commit point")
        callback("before_manifest")
        if manifest_path.read_bytes() != manifest_preimage:
            raise ArchiveError("manifest changed during commit checkpoint")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{manifest_path.name}.", suffix=".tmp", dir=manifest_path.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            os.chmod(temporary, manifest_mode)
            stream.write(manifest_output)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.read_bytes() != manifest_output:
            raise ArchiveError("manifest staging readback drift")
        if manifest_path.read_bytes() != manifest_preimage:
            raise ArchiveError("manifest changed before atomic replace")
        os.replace(temporary, manifest_path)
        temporary = None
        committed = True
        _fsync_directory(manifest_path.parent)
        callback("after_manifest")
        return tuple(targets)
    except BaseException:
        if not committed:
            for path in reversed(created):
                path.unlink(missing_ok=True)
            _fsync_directory(active_dir)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if lock_created:
            lock_path.unlink(missing_ok=True)
