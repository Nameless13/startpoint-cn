#!/usr/bin/env python3
"""Controlled discovery and explicit acceptance for the offline Seris base lock."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
SERIS_PATH = HERE / "seris_phase4_pcode.py"
TARGET_SWF = "assets/worldflipper_android_release.swf"
EXPECTED_BASE_APK_SHA256 = "4f6884f33641788108c0522c7c70036c63ba530e1fdb183105b3cd395bdd66f6"
EXPECTED_SWF_SHA256 = "08187f538703aecadce264b7bd5e085411f8e3aedb5f48adf2cf035a100f550d"
EXPECTED_MANIFEST_SHA256 = "2823fbfad46bfcdc34c8df77b3f2ed2acf9f5812b8b61644304cc6d11109d6f9"
EXPECTED_DEX_SHA256 = {
    "classes.dex": "c12d119d425f0e8f35623dbac07296e00a8b9e60620c4f371b307121b389c043",
    "classes2.dex": "b310c77febb7da0d2908b32274391ae39226a9df334e0d7d7f51b5a081bc539b",
}
EXPECTED_NATIVE_AGGREGATE_SHA256 = "a42f92e417199a9ac99ca4f63efa0db487019bdf1220a86301fcfa0a4118f995"
EXPECTED_NATIVE_MEMBERS = {
    "lib/arm64-v8a/libCore.so": {"size": 20348224, "sha256": "41b50823cbada646ced0999a724a5886fe2f48fc2f71a8ef26266064db3b0dfe"},
    "lib/arm64-v8a/libSocketHelper.so": {"size": 317784, "sha256": "92bdc44a7316917e42c030003948da635ae71735d62654fb70f6ca60a7f1441d"},
    "lib/arm64-v8a/libc++_shared.so": {"size": 1058904, "sha256": "218ecc677aa79e1974f3968d2e0ecd0172c4f517188d04ebd7d45cbb285b5d03"},
    "lib/arm64-v8a/libentryexpro.so": {"size": 177624, "sha256": "368e1420d00d53be8901eb7c7bafad8f6c8d584cc4ca48eab17a26a5253f3074"},
    "lib/arm64-v8a/libgetuiext3.so": {"size": 55152, "sha256": "bb3a923d724ba6e6346d8825d5cc1571665645b4afff04d6a63fd975331aba5c"},
    "lib/arm64-v8a/libsecsdk.so": {"size": 349040, "sha256": "16a59fe3f40137ac3aa2cbb532e9fa1caa2ad153f9f4c016c6dbbbfb201eb200"},
    "lib/arm64-v8a/libsobot.so": {"size": 14080, "sha256": "2be4c71c78a5c45f759c127815aa2fd52b55adaf4163efec0da8f165d5a560ee"},
    "lib/arm64-v8a/libtracepath.so": {"size": 94560, "sha256": "8efcf10665b7d2305ef58e5fa028e8c40e73b7e6490afe71372414907a0b4208"},
    "lib/arm64-v8a/libuptsmaddon.so": {"size": 776992, "sha256": "e1417fb3446cc42c017ff66354e8655d5d7072b7f682f915a5f08bfabf089557"},
    "lib/arm64-v8a/libuptsmaddonmi.so": {"size": 776992, "sha256": "78ee11a083ccd6dee10ef7ab4f7d14cc35add70d4442fe9e6accea20245f41fa"},
    "lib/arm64-v8a/libwordfilter.so": {"size": 1038544, "sha256": "199ffdc9c2fb6fee78ef4404cd4e4fee02a192716ede1408abeac333ab644384"},
    "lib/arm64-v8a/libysshared.so": {"size": 333656, "sha256": "abf21718bfcd5cbba28a7f129378865a5cd39d2cb835e42eac30a7c47c411a20"},
}
EXPECTED_OFFLINE_METHOD_SHA256 = {
    "DevConfig_individual/DevConfig_individual": "ac87a4744507d4fa47fa46af99290a1aec0c230a5338e317cbeeb7c80badc139",
    "boot_ffc6#$script364/$init": "afcb8c8602158db0a64ba1560f36875166004283bfe6a04ad9eeaf49ee3714b2",
    "InitializeDummyRemote/logicAssetLoadedHandler": "d17591dc3c793faaa02c1080968b0bb30384b968f70dbe9363d8860fa30fcd3c",
    "DummyRemote/debugUnlinkTwitter": "45bc87da473d018f700f349fda2c743a6d11509cc236390584dccf2ac7d75a38",
}
EXPECTED_SAVE_METHOD_SHA256 = {
    "InitializeDummyRemote/logicAssetLoadedHandler": EXPECTED_OFFLINE_METHOD_SHA256[
        "InitializeDummyRemote/logicAssetLoadedHandler"
    ],
    "DummyRemote/debugUnlinkTwitter": EXPECTED_OFFLINE_METHOD_SHA256["DummyRemote/debugUnlinkTwitter"],
}
SAVE_METHOD_CONTRACTS = (
    (
        "InitializeDummyRemote/logicAssetLoadedHandler",
        "pinball.remote.initialize:InitializeDummyRemote/logicAssetLoadedHandler",
        "pinball.remote.initialize.InitializeDummyRemote",
        "logicAssetLoadedHandler",
        "READ",
        "readUTFBytes",
    ),
    (
        "DummyRemote/debugUnlinkTwitter",
        "pinball.context.remote.dummy:DummyRemote/debugUnlinkTwitter",
        "pinball.context.remote.dummy.DummyRemote",
        "debugUnlinkTwitter",
        "WRITE",
        "writeUTFBytes",
    ),
)
CONFIRMATION = "ACCEPT_OFFLINE_BASE_4F6884F3"
MAX_LOCK_BYTES = 2 * 1024 * 1024
LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")
ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/)")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}")
PRIVATE_KEY = re.compile(
    r"^(?:timestamp|created_at|updated_at|command|commands|argv|refresh|refresh_instruction)$|(?:^|_)(?:password|secret|token|keystore|key_path)(?:$|_)",
    re.IGNORECASE,
)


class LockDiscoveryError(RuntimeError):
    pass


def _load_seris_module():
    name = "offline_seris_phase4_for_lock_discovery"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, SERIS_PATH)
    if spec is None or spec.loader is None:
        raise LockDiscoveryError(f"cannot load Seris module: {SERIS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SERIS = _load_seris_module()
EXPECTED_SITES = tuple(patch.site_id for patch in SERIS.PATCHES)
EXPECTED_ASSETS = tuple(SERIS.extract_asset_logicals())
NATIVE_COMPATIBILITY_METHODS = (
    "pinball.scene.battle.battle.squad.member:MemberImpl/startPowerFlip",
    "pinball.scene.battle.battle.squad.member:MemberImpl/resolveConditionalKind",
    "pinball.ui.component.pixelArtCharacter:PixelArtCharacterView/spriteSheetLoadCompleted",
    "pinball.scene.battle.battle.squad.member:MemberView/MemberView",
)
NATIVE_COMPATIBILITY_HASHES = {
    NATIVE_COMPATIBILITY_METHODS[0]: "675b4a9e5874e5bba8502ea998963a20ab198d3553e0159a5f8422b7c9987f51",
    NATIVE_COMPATIBILITY_METHODS[1]: "eb0b16be3b9503e5604c97b5f8866cdc7754b6cf43a88d376b92ed0ef3ce00b0",
    NATIVE_COMPATIBILITY_METHODS[2]: "9475368c4dd326f0d8230ba724d96a60af5d30dba37ac5d43d5bdd04a85b038b",
    NATIVE_COMPATIBILITY_METHODS[3]: "0ca2af059a85e432c9c6dc991126d0eeba57acaa5ecc152aee83e36ed19a9d77",
}
MERGE_CONTRACTS = {
    "preload_seris_dual_form_assets": (
        "4c17b898e702b11092ee4d8ec148b18b3550900475f3b0e14a1ef725062f84fd",
        ("offline_base_path", "abyss_equipment_gate", "seris_dual_form_preload"),
    ),
    "default_seris_human_power_flip": (
        "fe609f8079a69de8b6276a10f166676e232a917aedf03c1702314dbcd96ac4c9",
        ("offline_base_power_flip", "seris_human_dragon_selection"),
    ),
}
TOP_LEVEL_KEYS = {
    "schema_version",
    "status",
    "stage",
    "site_count",
    "verified",
    "source_apk_sha256",
    "source_swf_sha256",
    "post_abyss_swf_sha256",
    "abyss_stage",
    "manifest_sha256",
    "dex_sha256",
    "native_aggregate_sha256",
    "native_members",
    "offline_method_sha256",
    "save_method_sha256",
    "site_ids",
    "asset_logicals",
    "sites",
    "native_compatibility",
    "three_way_merges",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _copy_regular_file_snapshot(source: Path, destination: Path) -> None:
    """Copy one stable regular-file view into an exclusive transaction file."""
    try:
        source = Path(source)
        metadata = source.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise LockDiscoveryError("source APK must be a regular non-symlink file")
        with source.open("rb") as input_handle, Path(destination).open("xb") as output_handle:
            opened = os.fstat(input_handle.fileno())
            if not stat.S_ISREG(opened.st_mode) or (
                opened.st_dev,
                opened.st_ino,
            ) != (metadata.st_dev, metadata.st_ino):
                raise LockDiscoveryError("source APK changed before it was opened")
            copied = 0
            for chunk in iter(lambda: input_handle.read(1024 * 1024), b""):
                output_handle.write(chunk)
                copied += len(chunk)
            output_handle.flush()
            os.fsync(output_handle.fileno())
            finished = os.fstat(input_handle.fileno())
        stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if copied != opened.st_size or any(
            getattr(opened, field) != getattr(finished, field) for field in stable_fields
        ):
            raise LockDiscoveryError("source APK changed while creating the snapshot")
    except LockDiscoveryError:
        raise
    except OSError as exc:
        raise LockDiscoveryError(f"cannot snapshot source APK: {exc}") from exc


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise LockDiscoveryError(f"lock is not canonical-JSON serializable: {exc}") from exc
    return (text + "\n").encode("utf-8")


def _reject_constant(value: str):
    raise ValueError(f"non-standard JSON constant: {value}")


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_regular_file_snapshot(path: Path) -> bytes:
    try:
        source = Path(path)
        metadata = source.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise LockDiscoveryError("lock candidate must be a regular non-symlink file")
        if metadata.st_size <= 0 or metadata.st_size > MAX_LOCK_BYTES:
            raise LockDiscoveryError("lock candidate size is invalid")
        with source.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode) or (
                opened.st_dev,
                opened.st_ino,
            ) != (metadata.st_dev, metadata.st_ino):
                raise LockDiscoveryError("lock candidate changed before it was opened")
            raw = handle.read(MAX_LOCK_BYTES + 1)
            finished = os.fstat(handle.fileno())
        if len(raw) > MAX_LOCK_BYTES or len(raw) != opened.st_size:
            raise LockDiscoveryError("lock candidate size changed while reading")
        stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(opened, field) != getattr(finished, field) for field in stable_fields):
            raise LockDiscoveryError("lock candidate changed while reading")
        return raw
    except LockDiscoveryError:
        raise
    except OSError as exc:
        raise LockDiscoveryError(f"cannot read lock candidate: {exc}") from exc


def _parse_json_strict_bytes(raw: bytes) -> Mapping[str, Any]:
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except LockDiscoveryError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise LockDiscoveryError(f"invalid lock JSON: {exc}") from exc
    if not isinstance(value, Mapping):
        raise LockDiscoveryError("lock JSON root must be an object")
    return value


def _load_json_strict(path: Path) -> Mapping[str, Any]:
    return _parse_json_strict_bytes(_read_regular_file_snapshot(path))


def _privacy_scan(value: Any, location: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise LockDiscoveryError(f"non-string key at {location}")
            if PRIVATE_KEY.search(key):
                raise LockDiscoveryError(f"private operational key at {location}.{key}")
            _privacy_scan(child, f"{location}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _privacy_scan(child, f"{location}[{index}]")
    elif isinstance(value, str):
        if ABSOLUTE_PATH.match(value):
            raise LockDiscoveryError(f"absolute path at {location}")
        if TIMESTAMP.match(value):
            raise LockDiscoveryError(f"timestamp at {location}")


def _require_hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or LOWER_SHA256.fullmatch(value) is None:
        raise LockDiscoveryError(f"invalid SHA-256 at {field}")
    return value


def _require_hash_mapping(value: Any, field: str, *, nonempty: bool = True) -> Mapping[str, str]:
    if not isinstance(value, Mapping) or (nonempty and not value):
        raise LockDiscoveryError(f"{field} must be a nonempty mapping")
    for key, digest in value.items():
        if not isinstance(key, str) or not key:
            raise LockDiscoveryError(f"invalid key in {field}")
        _require_hash(digest, f"{field}.{key}")
    return value


def validate_lock_document(value: Mapping[str, Any], *, expected_status: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != TOP_LEVEL_KEYS:
        raise LockDiscoveryError("lock top-level schema mismatch")
    _privacy_scan(value)
    if value.get("schema_version") != 4 or value.get("status") != expected_status:
        raise LockDiscoveryError("lock schema/status mismatch")
    if value.get("stage") != "post-abyss" or value.get("site_count") != 9:
        raise LockDiscoveryError("lock stage/site count mismatch")
    if value.get("verified") is not True:
        raise LockDiscoveryError("lock is not verified")
    expected_scalars = {
        "source_apk_sha256": EXPECTED_BASE_APK_SHA256,
        "source_swf_sha256": EXPECTED_SWF_SHA256,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "native_aggregate_sha256": EXPECTED_NATIVE_AGGREGATE_SHA256,
    }
    for field, expected in expected_scalars.items():
        if value.get(field) != expected:
            raise LockDiscoveryError(f"locked baseline mismatch at {field}")
    post_abyss_hash = _require_hash(
        value.get("post_abyss_swf_sha256"), "post_abyss_swf_sha256"
    )
    if post_abyss_hash == EXPECTED_SWF_SHA256:
        raise LockDiscoveryError("post-abyss SWF is unchanged")
    abyss = value.get("abyss_stage")
    if not isinstance(abyss, Mapping) or set(abyss) != {
        "stage", "input_sha256", "output_sha256", "target_class",
        "before_method_sha256", "after_method_sha256", "match_count",
    }:
        raise LockDiscoveryError("abyss stage evidence schema mismatch")
    if (
        abyss["stage"] != "abyss-mode-equipment"
        or abyss["input_sha256"] != EXPECTED_SWF_SHA256
        or abyss["output_sha256"] != post_abyss_hash
        or abyss["target_class"] != "pinball.common.data.character.BattleCharacterLogic"
        or type(abyss["match_count"]) is not int
        or abyss["match_count"] != 1
    ):
        raise LockDiscoveryError("abyss stage evidence mismatch")
    before_abyss = _require_hash(abyss["before_method_sha256"], "abyss before method")
    after_abyss = _require_hash(abyss["after_method_sha256"], "abyss after method")
    if before_abyss == after_abyss:
        raise LockDiscoveryError("abyss method evidence is unchanged")
    if value.get("dex_sha256") != EXPECTED_DEX_SHA256:
        raise LockDiscoveryError("locked DEX hashes mismatch")
    if value.get("offline_method_sha256") != EXPECTED_OFFLINE_METHOD_SHA256:
        raise LockDiscoveryError("locked offline method hashes mismatch")
    if value.get("save_method_sha256") != EXPECTED_SAVE_METHOD_SHA256:
        raise LockDiscoveryError("locked save method hashes mismatch")
    native_members = value.get("native_members")
    if native_members != EXPECTED_NATIVE_MEMBERS:
        raise LockDiscoveryError("native member detail lock mismatch")
    native_records = {}
    for name, entry in native_members.items():
        if not isinstance(entry, Mapping) or set(entry) != {"size", "sha256"}:
            raise LockDiscoveryError(f"native member schema mismatch for {name}")
        if not isinstance(entry["size"], int) or entry["size"] <= 0:
            raise LockDiscoveryError(f"native member size mismatch for {name}")
        _require_hash(entry["sha256"], f"native member {name}")
        native_records[name] = (entry["size"], entry["sha256"])
    if _native_aggregate(native_records) != EXPECTED_NATIVE_AGGREGATE_SHA256:
        raise LockDiscoveryError("native member aggregate proof mismatch")
    if tuple(value.get("site_ids", ())) != EXPECTED_SITES:
        raise LockDiscoveryError("lock site order mismatch")
    if tuple(value.get("asset_logicals", ())) != EXPECTED_ASSETS:
        raise LockDiscoveryError("lock asset logicals mismatch")

    sites = value.get("sites")
    if not isinstance(sites, Mapping) or len(sites) != 9 or set(sites) != set(EXPECTED_SITES):
        raise LockDiscoveryError("lock site mapping mismatch")
    for patch in SERIS.PATCHES:
        entry = sites[patch.site_id]
        if not isinstance(entry, Mapping) or set(entry) != {
            "class_name", "method_name", "before_pcode_sha256", "after_pcode_sha256",
            "before_abc_sha256", "after_abc_sha256",
        }:
            raise LockDiscoveryError(f"site schema mismatch for {patch.site_id}")
        if entry["class_name"] != patch.class_name or entry["method_name"] != patch.method_name:
            raise LockDiscoveryError(f"site identity mismatch for {patch.site_id}")
        for field in ("before_pcode_sha256", "after_pcode_sha256", "before_abc_sha256", "after_abc_sha256"):
            _require_hash(entry[field], f"sites.{patch.site_id}.{field}")
        if entry["before_pcode_sha256"] == entry["after_pcode_sha256"] or entry["before_abc_sha256"] == entry["after_abc_sha256"]:
            raise LockDiscoveryError(f"unchanged site lock for {patch.site_id}")

    native = value.get("native_compatibility")
    if not isinstance(native, Mapping) or set(native) != set(NATIVE_COMPATIBILITY_METHODS):
        raise LockDiscoveryError("native compatibility method set mismatch")
    for method, entry in native.items():
        if not isinstance(entry, Mapping) or set(entry) != {"abc_sha256", "semantic_verified"}:
            raise LockDiscoveryError(f"native compatibility schema mismatch for {method}")
        _require_hash(entry["abc_sha256"], f"native_compatibility.{method}")
        if entry["abc_sha256"] != NATIVE_COMPATIBILITY_HASHES[method]:
            raise LockDiscoveryError(f"native compatibility identity mismatch for {method}")
        if entry["semantic_verified"] is not True:
            raise LockDiscoveryError(f"native compatibility is not verified for {method}")

    merges = value.get("three_way_merges")
    if not isinstance(merges, Mapping) or set(merges) != set(MERGE_CONTRACTS):
        raise LockDiscoveryError("three-way merge set mismatch")
    for site_id, (base_hash, semantics) in MERGE_CONTRACTS.items():
        entry = merges[site_id]
        if not isinstance(entry, Mapping) or set(entry) != {
            "base_method_abc_sha256", "post_abyss_before_abc_sha256",
            "preserved_semantics", "verified",
        }:
            raise LockDiscoveryError(f"three-way merge schema mismatch for {site_id}")
        if entry["base_method_abc_sha256"] != base_hash:
            raise LockDiscoveryError(f"three-way base identity mismatch for {site_id}")
        if entry["post_abyss_before_abc_sha256"] != sites[site_id]["before_abc_sha256"]:
            raise LockDiscoveryError(f"three-way post-abyss identity mismatch for {site_id}")
        if tuple(entry["preserved_semantics"]) != semantics or entry["verified"] is not True:
            raise LockDiscoveryError(f"three-way semantic proof mismatch for {site_id}")
    return value


def _native_aggregate(records: Mapping[str, tuple[int, str]]) -> str:
    digest = hashlib.sha256()
    for name in sorted(records):
        size, member_hash = records[name]
        _require_hash(member_hash, f"native member {name}")
        digest.update(f"{name}\0{int(size)}\0{member_hash}\n".encode("utf-8"))
    return digest.hexdigest()


def _inspect_base_apk(source_apk: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(source_apk, "r") as archive:
            names = [info.filename for info in archive.infolist()]
            if len(names) != len(set(names)):
                raise LockDiscoveryError("APK contains duplicate ZIP members")
            required = (TARGET_SWF, "AndroidManifest.xml", "classes.dex", "classes2.dex")
            for name in required:
                if names.count(name) != 1:
                    raise LockDiscoveryError(f"APK member count mismatch for {name}")
            swf = archive.read(TARGET_SWF)
            manifest = archive.read("AndroidManifest.xml")
            dex = {name: _sha256_bytes(archive.read(name)) for name in ("classes.dex", "classes2.dex")}
            native_records = {}
            native_members = {}
            for info in archive.infolist():
                if info.filename.startswith("lib/") and not info.is_dir():
                    data = archive.read(info)
                    member_hash = _sha256_bytes(data)
                    native_records[info.filename] = (len(data), member_hash)
                    native_members[info.filename] = {
                        "size": len(data),
                        "sha256": member_hash,
                    }
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise LockDiscoveryError(f"cannot inspect base APK: {exc}") from exc
    return {
        "source_swf_sha256": _sha256_bytes(swf),
        "manifest_sha256": _sha256_bytes(manifest),
        "dex_sha256": dex,
        "native_aggregate_sha256": _native_aggregate(native_records),
        "native_members": native_members,
    }


def _stage_output_sibling(source: Path, destination: Path, expected_hash: str):
    try:
        return SERIS._stage_output_sibling(source, destination, expected_hash)
    except SERIS.SerisPatchError as exc:
        raise LockDiscoveryError(str(exc)) from exc


def _publish_staged_exclusive(staging, destination: Path, expected_hash: str) -> None:
    try:
        SERIS._publish_staged_exclusive(staging, destination, expected_hash)
    except SERIS.SerisPatchError as exc:
        raise LockDiscoveryError(str(exc)) from exc


def _cleanup_owned_staging(staging) -> None:
    try:
        SERIS._cleanup_owned_staging(staging)
    except SERIS.SerisPatchError as exc:
        raise LockDiscoveryError(str(exc)) from exc


def _write_exclusive_canonical(value: Mapping[str, Any], output: Path) -> None:
    output = Path(output).resolve()
    if os.path.lexists(output):
        raise LockDiscoveryError(f"lock output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_json_bytes(value)
    transaction: Path | None = None
    staging = None
    original_error: BaseException | None = None
    try:
        transaction = Path(tempfile.mkdtemp(prefix=".offline-lock-", dir=output.parent)).resolve()
        source = transaction / "canonical.json"
        with source.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        expected_hash = _sha256_bytes(payload)
        staging = _stage_output_sibling(source, output, expected_hash)
        shutil.rmtree(transaction)
        transaction = None
        _publish_staged_exclusive(staging, output, expected_hash)
        staging = None
    except BaseException as error:
        original_error = error
        raise
    finally:
        if transaction is not None:
            try:
                shutil.rmtree(transaction)
            except BaseException as cleanup_error:
                if original_error is None:
                    raise LockDiscoveryError("failed to clean lock transaction") from cleanup_error
                original_error.add_note(f"failed to clean lock transaction: {cleanup_error}")
        if staging is not None:
            try:
                _cleanup_owned_staging(staging)
            except BaseException as cleanup_error:
                if original_error is None:
                    raise
                original_error.add_note(f"failed to clean staged lock: {cleanup_error}")


EvidenceProvider = Callable[..., Mapping[str, Any]]


def _require_suffix_ref(index, suffix: str):
    matches = []
    for ref in index.refs:
        if any(alias == suffix or alias.endswith("/" + suffix) or alias.endswith(suffix) for alias in ref.aliases):
            if ref not in matches:
                matches.append(ref)
    if len(matches) != 1:
        raise LockDiscoveryError(
            f"expected exactly one method ending in {suffix!r}, found {len(matches)}"
        )
    return matches[0]


def _assert_unchanged(path: Path, expected_hash: str, label: str) -> None:
    if _sha256_file(path) != expected_hash:
        raise LockDiscoveryError(f"{label} changed during discovery")


def _discover_seris_sites(
    post_abyss_swf: Path,
    *,
    transaction_dir: Path,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    runner=SERIS._subprocess_runner,
    timeout: int = 240,
) -> tuple[dict[str, dict[str, str]], Path]:
    """Apply the nine transforms without a lock and derive reviewed lock evidence."""
    current = Path(post_abyss_swf).resolve()
    transaction = Path(transaction_dir).resolve()
    profile = Path(profile_dir).resolve()
    ffdec_path = Path(ffdec).resolve()
    java_path = Path(java).resolve()
    records: dict[str, dict[str, str]] = {}
    for sequence, patch in enumerate(SERIS.PATCHES, start=1):
        input_hash = _sha256_file(current)
        index = SERIS.ABC_METHODS.index_swf_methods(current)
        ref = index.require_ref(patch.method_name)
        export_root = transaction / f"discover-{sequence:02d}-before"
        SERIS._export_classes(
            current,
            export_root,
            [patch.class_name],
            ffdec=ffdec_path,
            java=java_path,
            profile_dir=profile,
            cwd=transaction,
            runner=runner,
            timeout=timeout,
        )
        _assert_unchanged(current, input_hash, f"Seris stage {sequence} input")
        before = SERIS._read_exported_method(export_root, patch)
        after = patch.apply(before)
        entry = {
            "class_name": patch.class_name,
            "method_name": patch.method_name,
            "before_pcode_sha256": SERIS._sha256_pcode(before),
            "after_pcode_sha256": SERIS._sha256_pcode(after),
            "before_abc_sha256": SERIS._sha256_abc(ref.code),
            "after_abc_sha256": "",
        }
        replacement = transaction / f"discover-{sequence:02d}-{patch.site_id}.pcode"
        replacement.write_text(after, encoding="utf-8", newline="\n")
        staged = transaction / f"discover-{sequence:02d}-{patch.site_id}.swf"
        SERIS._replace_one(
            current,
            staged,
            patch,
            replacement,
            ref.body_index,
            ffdec=ffdec_path,
            java=java_path,
            profile_dir=profile,
            cwd=transaction,
            runner=runner,
            timeout=timeout,
        )
        _assert_unchanged(current, input_hash, f"Seris stage {sequence} input")
        records[patch.site_id] = entry

        reopened_index = SERIS.ABC_METHODS.index_swf_methods(staged)
        applied = SERIS.PATCHES[:sequence]
        for applied_patch in applied:
            applied_ref = reopened_index.require_ref(applied_patch.method_name)
            raw_hash = SERIS._sha256_abc(applied_ref.code)
            expected_raw = records[applied_patch.site_id]["after_abc_sha256"]
            if expected_raw and raw_hash != expected_raw:
                raise LockDiscoveryError(
                    f"cumulative raw ABC drift for {applied_patch.site_id}"
                )
            records[applied_patch.site_id]["after_abc_sha256"] = raw_hash
        reopen_root = transaction / f"discover-{sequence:02d}-reopen"
        SERIS._export_classes(
            staged,
            reopen_root,
            [item.class_name for item in applied],
            ffdec=ffdec_path,
            java=java_path,
            profile_dir=profile,
            cwd=transaction,
            runner=runner,
            timeout=timeout,
        )
        _assert_unchanged(current, input_hash, f"Seris stage {sequence} input")
        for applied_patch in applied:
            reopened = SERIS._read_exported_method(reopen_root, applied_patch)
            applied_patch.verify(reopened)
            if SERIS._sha256_pcode(reopened) != records[applied_patch.site_id]["after_pcode_sha256"]:
                raise LockDiscoveryError(
                    f"cumulative P-code drift for {applied_patch.site_id}"
                )
        current = staged
    return records, current


def _offline_method_evidence(source_swf: Path) -> dict[str, str]:
    index = SERIS.ABC_METHODS.index_swf_methods(source_swf)
    result = {}
    for suffix, expected in EXPECTED_OFFLINE_METHOD_SHA256.items():
        ref = _require_suffix_ref(index, suffix)
        actual = _sha256_bytes(ref.code)
        if actual != expected:
            raise LockDiscoveryError(f"offline method hash mismatch for {suffix}")
        result[suffix] = actual
    return result


def _verify_save_haxe_pcode(
    source_swf: Path,
    *,
    export_root: Path,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    runner,
    timeout: int,
) -> None:
    # Verify the literal and operation inside each exact read/write body, not
    # merely elsewhere in the selected classes or SWF constant pool.
    index = SERIS.ABC_METHODS.index_swf_methods(source_swf)
    classes = []
    for suffix, identity, class_name, _method_name, _mode, _operation in SAVE_METHOD_CONTRACTS:
        ref = _require_suffix_ref(index, suffix)
        if identity not in ref.aliases:
            raise LockDiscoveryError(f"save method identity mismatch for {suffix}")
        classes.append(class_name)
    SERIS._export_classes(
        source_swf,
        export_root,
        tuple(dict.fromkeys(classes)),
        ffdec=ffdec,
        java=java,
        profile_dir=profile_dir,
        cwd=export_root.parent,
        runner=runner,
        timeout=timeout,
    )
    for suffix, _identity, class_name, method_name, mode, operation in SAVE_METHOD_CONTRACTS:
        source = (
            export_root
            / "scripts"
            / Path(*class_name.split(".")).with_suffix(".pcode")
        )
        try:
            text = source.read_text(encoding="utf-8")
            block = SERIS.PCODE_TOOLS.extract_method_block(
                text,
                trait_kind="method",
                trait_name=method_name,
            )
        except (OSError, SERIS.PCODE_TOOLS.PcodePatchError) as exc:
            raise LockDiscoveryError(
                f"cannot read exact save method P-code for {suffix}: {exc}"
            ) from exc
        ordered = (
            'getproperty QName(PackageNamespace(""),"userDirectory")',
            'pushstring "WorldFlipper/save_haxe"',
            'callproperty QName(PackageNamespace(""),"resolvePath"), 1',
            f'getproperty QName(PackageNamespace(""),"{mode}")',
            f'QName(PackageNamespace(""),"{operation}"), 1',
        )
        positions = [block.find(token) for token in ordered]
        if (
            block.count('pushstring "WorldFlipper/save_haxe"') != 1
            or any(position < 0 for position in positions)
            or positions != sorted(positions)
        ):
            raise LockDiscoveryError(
                f"save_haxe {mode.lower()} semantics mismatch for {suffix}"
            )


def build_reviewed_evidence_provider(
    *,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    runner=SERIS._subprocess_runner,
    timeout: int = 240,
) -> EvidenceProvider:
    """Compose Task 8 and unlocked Task 9 stages for explicit discovery."""
    ffdec_path = Path(ffdec).resolve()
    java_path = Path(java).resolve()
    profile = Path(profile_dir).resolve()

    def provider(*, source_swf: Path, transaction_dir: Path) -> Mapping[str, Any]:
        transaction = Path(transaction_dir).resolve()
        base_index = SERIS.ABC_METHODS.index_swf_methods(source_swf)
        for site_id, (base_hash, _semantics) in MERGE_CONTRACTS.items():
            patch = SERIS.PATCH_BY_ID[site_id]
            if _sha256_bytes(base_index.require_ref(patch.method_name).code) != base_hash:
                raise LockDiscoveryError(f"base three-way identity mismatch for {site_id}")
        offline = _offline_method_evidence(source_swf)
        _verify_save_haxe_pcode(
            source_swf,
            export_root=transaction / "save-haxe-export",
            ffdec=ffdec_path,
            java=java_path,
            profile_dir=profile,
            runner=runner,
            timeout=timeout,
        )

        post_abyss = transaction / "post-abyss.swf"
        def abyss_runner(command, *, check, cwd, env):
            del check
            return runner(command, cwd=Path(cwd), env=dict(env), timeout=timeout)

        try:
            abyss_report = SERIS.PUBLISH_TOOLS.apply_gate_to_swf(
                source_swf,
                post_abyss,
                ffdec=ffdec_path,
                java=java_path,
                profile_dir=profile,
                work_dir=transaction / "abyss-work",
                runner=abyss_runner,
            )
        except SERIS.PUBLISH_TOOLS.BuildError as exc:
            raise LockDiscoveryError(f"abyss discovery stage failed: {exc}") from exc
        if abyss_report.match_count != 1:
            raise LockDiscoveryError("abyss discovery proof is not singular")

        post_index = SERIS.ABC_METHODS.index_swf_methods(post_abyss)
        native = {}
        for method in NATIVE_COMPATIBILITY_METHODS:
            ref = post_index.require_ref(method)
            actual = _sha256_bytes(ref.code)
            if actual != NATIVE_COMPATIBILITY_HASHES[method]:
                raise LockDiscoveryError(
                    f"post-abyss native compatibility mismatch for {method}"
                )
            native[method] = {
                "abc_sha256": actual,
                "semantic_verified": True,
            }
        sites, final_swf = _discover_seris_sites(
            post_abyss,
            transaction_dir=transaction,
            ffdec=ffdec_path,
            java=java_path,
            profile_dir=profile,
            runner=runner,
            timeout=timeout,
        )
        final_index = SERIS.ABC_METHODS.index_swf_methods(final_swf)
        for method, entry in native.items():
            final_hash = _sha256_bytes(final_index.require_ref(method).code)
            if final_hash != NATIVE_COMPATIBILITY_HASHES[method] or final_hash != entry["abc_sha256"]:
                raise LockDiscoveryError(f"native compatibility drift for {method}")
        try:
            SERIS.PUBLISH_TOOLS._export_target_class(
                final_swf,
                transaction / "final-abyss-gate-reopen",
                ffdec_path,
                java_path,
                verify_gate=True,
                runner=abyss_runner,
                cwd=transaction,
                environment={**os.environ, "APPDATA": str(profile)},
            )
        except SERIS.PUBLISH_TOOLS.BuildError as exc:
            raise LockDiscoveryError(
                f"final post-Seris abyss gate verification failed: {exc}"
            ) from exc
        merges = {}
        for site_id, (base_hash, semantics) in MERGE_CONTRACTS.items():
            merges[site_id] = {
                "base_method_abc_sha256": base_hash,
                "post_abyss_before_abc_sha256": sites[site_id]["before_abc_sha256"],
                "preserved_semantics": list(semantics),
                "verified": True,
            }
        return {
            "post_abyss_swf_sha256": abyss_report.output_sha256,
            "abyss_stage": {
                "stage": abyss_report.stage,
                "input_sha256": abyss_report.input_sha256,
                "output_sha256": abyss_report.output_sha256,
                "target_class": abyss_report.target_class,
                "before_method_sha256": abyss_report.before_method_sha256,
                "after_method_sha256": abyss_report.after_method_sha256,
                "match_count": abyss_report.match_count,
            },
            "offline_method_sha256": offline,
            "save_method_sha256": dict(EXPECTED_SAVE_METHOD_SHA256),
            "sites": sites,
            "native_compatibility": native,
            "three_way_merges": merges,
        }

    return provider


def discover_lock_candidate(
    source_apk: Path,
    output: Path,
    *,
    work_dir: Path,
    evidence_provider: EvidenceProvider,
    expected_apk_sha256: str = EXPECTED_BASE_APK_SHA256,
    after_stage: str = "abyss",
) -> Mapping[str, Any]:
    source = Path(source_apk).resolve()
    destination = Path(output).resolve()
    work = Path(work_dir).resolve()
    if expected_apk_sha256 != EXPECTED_BASE_APK_SHA256:
        raise LockDiscoveryError("expected APK hash must equal the reviewed offline base")
    if after_stage != "abyss":
        raise LockDiscoveryError("lock discovery must compose the abyss stage")
    if not source.is_file() or os.path.lexists(destination):
        raise LockDiscoveryError("discovery source is missing or candidate output exists")
    try:
        work.relative_to(destination)
    except ValueError:
        pass
    else:
        raise LockDiscoveryError("candidate output cannot equal or contain work directory")
    work.mkdir(parents=True, exist_ok=True)
    transaction: Path | None = Path(tempfile.mkdtemp(prefix=".seris-lock-discovery-", dir=work)).resolve()
    try:
        source_snapshot = transaction / "source.apk"
        _copy_regular_file_snapshot(source, source_snapshot)
        if _sha256_file(source_snapshot) != EXPECTED_BASE_APK_SHA256:
            raise LockDiscoveryError("source APK hash mismatch")
        baseline = _inspect_base_apk(source_snapshot)
        expected_baseline = {
            "source_swf_sha256": EXPECTED_SWF_SHA256,
            "manifest_sha256": EXPECTED_MANIFEST_SHA256,
            "dex_sha256": EXPECTED_DEX_SHA256,
            "native_aggregate_sha256": EXPECTED_NATIVE_AGGREGATE_SHA256,
        }
        for field, expected in expected_baseline.items():
            if baseline.get(field) != expected:
                raise LockDiscoveryError(f"base APK member mismatch at {field}")
        if len(baseline.get("native_members", {})) != 12:
            raise LockDiscoveryError("base APK must contain exactly 12 native members")
        swf = transaction / "source.swf"
        with zipfile.ZipFile(source_snapshot, "r") as archive:
            infos = [info for info in archive.infolist() if info.filename == TARGET_SWF]
            if len(infos) != 1:
                raise LockDiscoveryError("expected exactly one main SWF member")
            with swf.open("xb") as handle:
                handle.write(archive.read(infos[0]))
                handle.flush()
                os.fsync(handle.fileno())
        extracted_swf_sha256 = _sha256_file(swf)
        if (
            extracted_swf_sha256 != EXPECTED_SWF_SHA256
            or extracted_swf_sha256 != baseline["source_swf_sha256"]
        ):
            raise LockDiscoveryError("extracted SWF differs from the inspected baseline")
        evidence = evidence_provider(source_swf=swf, transaction_dir=transaction)
        if not isinstance(evidence, Mapping):
            raise LockDiscoveryError("evidence provider must return a mapping")
        candidate = {
            "schema_version": 4,
            "status": "candidate",
            "stage": "post-abyss",
            "site_count": 9,
            "verified": True,
            "source_apk_sha256": EXPECTED_BASE_APK_SHA256,
            **baseline,
            "site_ids": list(EXPECTED_SITES),
            "asset_logicals": list(EXPECTED_ASSETS),
            **dict(evidence),
        }
        validate_lock_document(candidate, expected_status="candidate")
        if _sha256_file(source) != EXPECTED_BASE_APK_SHA256:
            raise LockDiscoveryError("source APK changed during discovery")
        shutil.rmtree(transaction)
        transaction = None
        _write_exclusive_canonical(candidate, destination)
        return candidate
    finally:
        if transaction is not None:
            shutil.rmtree(transaction)


def accept_lock_candidate(
    candidate: Path,
    output: Path,
    *,
    confirmation: str,
    expected_candidate_sha256: str,
) -> Mapping[str, Any]:
    if confirmation != CONFIRMATION:
        raise LockDiscoveryError("lock acceptance confirmation mismatch")
    expected_digest = _require_hash(
        expected_candidate_sha256,
        "expected_candidate_sha256",
    )
    raw_candidate = _read_regular_file_snapshot(candidate)
    actual_digest = _sha256_bytes(raw_candidate)
    if not hmac.compare_digest(actual_digest, expected_digest):
        raise LockDiscoveryError("reviewed lock candidate SHA-256 mismatch")
    value = dict(_parse_json_strict_bytes(raw_candidate))
    validate_lock_document(value, expected_status="candidate")
    if raw_candidate != _canonical_json_bytes(value):
        raise LockDiscoveryError("candidate JSON is not canonical UTF-8/LF")
    accepted = dict(value)
    accepted["status"] = "accepted"
    validate_lock_document(accepted, expected_status="accepted")
    _write_exclusive_canonical(accepted, output)
    return accepted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    discover = subparsers.add_parser("discover")
    discover.add_argument("--source-apk", type=Path, required=True)
    discover.add_argument("--expected-apk-sha256", required=True)
    discover.add_argument("--after-stage", required=True)
    discover.add_argument("--output", type=Path, required=True)
    discover.add_argument("--java", type=Path)
    discover.add_argument("--ffdec", type=Path)
    discover.add_argument("--work-dir", type=Path)
    discover.add_argument("--profile-dir", type=Path)
    accept = subparsers.add_parser("accept")
    accept.add_argument("--candidate", type=Path, required=True)
    accept.add_argument("--output", type=Path, required=True)
    accept.add_argument("--confirm", required=True)
    accept.add_argument("--expected-candidate-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "accept":
            accepted = accept_lock_candidate(
                args.candidate,
                args.output,
                confirmation=args.confirm,
                expected_candidate_sha256=args.expected_candidate_sha256,
            )
            print(json.dumps({"status": accepted["status"], "site_count": accepted["site_count"]}, sort_keys=True))
            return 0
        repo_root = HERE.parents[1]
        java_value = args.java or shutil.which("java")
        ffdec_value = args.ffdec or (repo_root / "ffdec_26.2.1" / "ffdec.jar")
        work_value = args.work_dir or (repo_root / "work" / "offline-lock-discovery")
        profile_value = args.profile_dir or (work_value / "ffdec-profile")
        if java_value is None:
            raise LockDiscoveryError("Java was not found; pass --java")
        java_path = Path(java_value).resolve()
        ffdec_path = Path(ffdec_value).resolve()
        if not java_path.is_file() or not ffdec_path.is_file():
            raise LockDiscoveryError("Java or FFDec is missing; pass explicit tool paths")
        provider = build_reviewed_evidence_provider(
            ffdec=ffdec_path,
            java=java_path,
            profile_dir=Path(profile_value),
        )
        candidate = discover_lock_candidate(
            args.source_apk,
            args.output,
            work_dir=Path(work_value),
            evidence_provider=provider,
            expected_apk_sha256=args.expected_apk_sha256,
            after_stage=args.after_stage,
        )
        print(json.dumps({"status": candidate["status"], "site_count": candidate["site_count"]}, sort_keys=True))
        return 0
    except LockDiscoveryError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
