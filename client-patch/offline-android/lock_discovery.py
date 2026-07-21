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
import secrets
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
SERIS_PATH = HERE / "seris_phase4_pcode.py"
RENDER_SCALE_PATH = HERE / "render_scale_pcode.py"
RESOURCE_VERSION_PATH = HERE / "resource_version_pcode.py"
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
BASE_TOP_LEVEL_KEYS = {
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
EXTENSION_KEYS = {
    "render_site_ids",
    "render_sites",
    "resource_version",
}
EXTENDED_TOP_LEVEL_KEYS = BASE_TOP_LEVEL_KEYS | EXTENSION_KEYS
# Backwards-compatible public name for Task 9 callers and tests.
TOP_LEVEL_KEYS = BASE_TOP_LEVEL_KEYS
RENDER_SITE_IDS = ("pixel-art", "member-view", "character-cell")
RENDER_SITE_IDENTITIES = {
    "pixel-art": (
        "pinball.ui.component.pixelArtCharacter.PixelArtCharacterView",
        "pinball.ui.component.pixelArtCharacter:PixelArtCharacterView/spriteSheetLoadCompleted",
        "9475368c4dd326f0d8230ba724d96a60af5d30dba37ac5d43d5bdd04a85b038b",
    ),
    "member-view": (
        "pinball.scene.battle.battle.squad.member.MemberView",
        "pinball.scene.battle.battle.squad.member:MemberView/MemberView",
        "0ca2af059a85e432c9c6dc991126d0eeba57acaa5ecc152aee83e36ed19a9d77",
    ),
    "character-cell": (
        "pinball.scene.character.cell.CharacterCellView",
        "pinball.scene.character.cell:CharacterCellView/drawWithAdvanceFlag",
        "cc64eafcb0bbaeb4f1ae705944da569cc1d59bf9dc7636b1bbfe64342175e3a7",
    ),
}
RENDER_SITE_KEYS = {
    "class_name",
    "method_name",
    "before_pcode_sha256",
    "after_pcode_sha256",
    "before_abc_sha256",
    "after_abc_sha256",
}
RESOURCE_VERSION_KEYS = {
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
RESOURCE_VERSION_IDENTITY = {
    "site_id": "full-resource-version",
    "class_name": "pinball.config.core.DevConfig",
    "method_name": "boot_ffc6#$script364/$init",
    "source_version": "1.4.54",
    "target_version": "1.4.196",
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


def _validate_lock_extensions(value: Mapping[str, Any]) -> None:
    if tuple(value.get("render_site_ids", ())) != RENDER_SITE_IDS:
        raise LockDiscoveryError("render site order mismatch")
    sites = value.get("render_sites")
    if (
        not isinstance(sites, Mapping)
        or len(sites) != len(RENDER_SITE_IDS)
        or set(sites) != set(RENDER_SITE_IDS)
    ):
        raise LockDiscoveryError("render site mapping mismatch")
    for site_id in RENDER_SITE_IDS:
        entry = sites[site_id]
        if not isinstance(entry, Mapping) or set(entry) != RENDER_SITE_KEYS:
            raise LockDiscoveryError(f"render site schema mismatch for {site_id}")
        class_name, method_name, before_abc = RENDER_SITE_IDENTITIES[site_id]
        if (
            entry["class_name"] != class_name
            or entry["method_name"] != method_name
            or entry["before_abc_sha256"] != before_abc
        ):
            raise LockDiscoveryError(f"render site identity mismatch for {site_id}")
        for field in (
            "before_pcode_sha256",
            "after_pcode_sha256",
            "before_abc_sha256",
            "after_abc_sha256",
        ):
            _require_hash(entry[field], f"render_sites.{site_id}.{field}")
        if (
            entry["before_pcode_sha256"] == entry["after_pcode_sha256"]
            or entry["before_abc_sha256"] == entry["after_abc_sha256"]
        ):
            raise LockDiscoveryError(f"unchanged render site lock for {site_id}")

    resource = value.get("resource_version")
    if not isinstance(resource, Mapping) or set(resource) != RESOURCE_VERSION_KEYS:
        raise LockDiscoveryError("resource-version schema mismatch")
    for field, expected in RESOURCE_VERSION_IDENTITY.items():
        if resource[field] != expected:
            raise LockDiscoveryError(f"resource-version identity mismatch at {field}")
    for field in (
        "before_pcode_sha256",
        "after_pcode_sha256",
        "before_abc_sha256",
        "after_abc_sha256",
    ):
        _require_hash(resource[field], f"resource_version.{field}")
    if resource["before_abc_sha256"] != value["offline_method_sha256"][
        "boot_ffc6#$script364/$init"
    ]:
        raise LockDiscoveryError("resource-version baseline identity mismatch")
    if (
        resource["before_pcode_sha256"] == resource["after_pcode_sha256"]
        or resource["before_abc_sha256"] == resource["after_abc_sha256"]
    ):
        raise LockDiscoveryError("unchanged resource-version lock")


def validate_lock_document(
    value: Mapping[str, Any],
    *,
    expected_status: str,
    require_extensions: bool = False,
) -> Mapping[str, Any]:
    keys = set(value) if isinstance(value, Mapping) else set()
    has_extensions = keys == EXTENDED_TOP_LEVEL_KEYS
    if not isinstance(value, Mapping) or keys not in (
        BASE_TOP_LEVEL_KEYS,
        EXTENDED_TOP_LEVEL_KEYS,
    ):
        raise LockDiscoveryError("lock top-level schema mismatch")
    if require_extensions and not has_extensions:
        raise LockDiscoveryError("lock extensions are required")
    if has_extensions and expected_status != "accepted":
        raise LockDiscoveryError("lock extensions require accepted status")
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
    if has_extensions:
        _validate_lock_extensions(value)
    return value


def validate_extension_candidate(
    value: Mapping[str, Any],
    accepted_base: Mapping[str, Any],
) -> Mapping[str, Any]:
    validate_lock_document(accepted_base, expected_status="accepted")
    if set(accepted_base) != BASE_TOP_LEVEL_KEYS:
        raise LockDiscoveryError("extension base must be an unextended accepted lock")
    validate_lock_document(
        value,
        expected_status="accepted",
        require_extensions=True,
    )
    for key in BASE_TOP_LEVEL_KEYS:
        if value[key] != accepted_base[key]:
            raise LockDiscoveryError(f"extension candidate changed Task 9 field {key}")
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


class _CasOwnedFile:
    """Mutable path ownership for one handle-bound accepted-lock CAS."""

    __slots__ = (
        "path",
        "identity",
        "handle",
        "pending_paths",
        "pending_label",
    )

    def __init__(self, path: Path, identity, handle) -> None:
        self.path = Path(path)
        self.identity = identity
        self.handle = handle
        self.pending_paths = None
        self.pending_label = None


def _reconcile_cas_owner_path(owned, first: Path, second: Path, label: str) -> Path:
    candidates = []
    seen = set()
    for value in (first, second):
        path = Path(value)
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            candidates.append(path)
    matches = []
    try:
        for path in candidates:
            actual = SERIS.PUBLISH_TOOLS._file_identity(
                path,
                f"{label} path",
                missing_ok=True,
            )
            if actual == owned.identity:
                matches.append(path)
    except SERIS.PUBLISH_TOOLS.BuildError as exc:
        raise LockDiscoveryError(
            f"cannot reconcile accepted-lock owner after {label}"
        ) from exc
    if len(matches) != 1:
        raise LockDiscoveryError(
            f"accepted-lock owner is ambiguous after {label}: {len(matches)} matches"
        )
    owned.path = matches[0]
    owned.pending_paths = None
    owned.pending_label = None
    return matches[0]


def _settle_pending_cas_owner(
    owned,
    original_error: BaseException | None,
    *,
    context: str,
) -> bool:
    """Retry one unresolved handle rename, or close and report both candidates."""
    if owned.pending_paths is None:
        return True
    pending_paths = tuple(owned.pending_paths)
    pending_label = owned.pending_label or "accepted-lock cleanup"
    try:
        _reconcile_cas_owner_path(
            owned,
            pending_paths[0],
            pending_paths[1],
            pending_label,
        )
    except BaseException as reconcile_error:
        existing_candidates = [
            path for path in pending_paths if os.path.lexists(path)
        ]
        close_failed = False
        try:
            _close_owned_existing(owned)
        except BaseException as close_error:
            close_failed = True
            reconcile_error.add_note(
                "failed to close unreconciled accepted-lock handle: "
                f"{type(close_error).__name__}: {close_error}"
            )
        close_status = "handle close failed" if close_failed else "handle closed"
        existing_text = ", ".join(str(path) for path in existing_candidates)
        detail = (
            f"{context}; {close_status}; existing pending paths="
            f"[{existing_text}]; error={type(reconcile_error).__name__}: "
            f"{reconcile_error}"
        )
        if original_error is None:
            reconcile_error.add_note(detail)
            raise
        original_error.add_note(detail)
        return False
    return True


def _rename_cas_owner_no_replace(owned, destination: Path, label: str) -> None:
    if owned.pending_paths is not None:
        raise LockDiscoveryError(
            "accepted-lock owner has an unresolved handle rename"
        )
    previous = Path(owned.path)
    target = Path(destination)
    owned.pending_paths = (previous, target)
    owned.pending_label = label
    try:
        SERIS.PUBLISH_TOOLS._rename_staging_handle_no_replace(owned, target)
    except BaseException as error:
        try:
            _reconcile_cas_owner_path(owned, previous, target, label)
        except BaseException as reconcile_error:
            error.add_note(
                f"failed to reconcile accepted-lock owner after {label}: "
                f"{type(reconcile_error).__name__}: {reconcile_error}"
            )
        raise
    actual = _reconcile_cas_owner_path(owned, previous, target, label)
    if os.path.normcase(str(actual)) != os.path.normcase(str(target)):
        raise LockDiscoveryError(
            f"accepted-lock handle rename did not reach target during {label}"
        )


def _publish_candidate_owner_no_replace(owned, destination: Path) -> None:
    try:
        _rename_cas_owner_no_replace(owned, destination, "candidate publication")
    except OSError as exc:
        raise LockDiscoveryError(
            "failed to publish extension candidate for CAS"
        ) from exc


def _open_existing_for_cas(path: Path):
    """Open and freeze one existing Windows file for an identity-bound rename."""
    if os.name != "nt":
        raise LockDiscoveryError("lock compare-and-swap requires Windows")
    import msvcrt

    handle = None
    try:
        ctypes, _wintypes, kernel32 = SERIS.PUBLISH_TOOLS._windows_file_api()
        generic_read = 0x80000000
        delete_access = 0x00010000
        share_read = 0x00000001
        open_existing = 3
        normal_attribute = 0x00000080
        raw_handle = kernel32.CreateFileW(
            str(path),
            generic_read | delete_access,
            share_read,
            None,
            open_existing,
            normal_attribute,
            None,
        )
        if raw_handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            descriptor = msvcrt.open_osfhandle(raw_handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            kernel32.CloseHandle(raw_handle)
            raise
        try:
            handle = os.fdopen(descriptor, "rb")
        except BaseException as error:
            try:
                os.close(descriptor)
            except BaseException as close_error:
                error.add_note(
                    "failed to close accepted-lock descriptor after fdopen "
                    f"failure: {type(close_error).__name__}: {close_error}"
                )
            raise
        owned = _CasOwnedFile(
            Path(path),
            SERIS.PUBLISH_TOOLS._identity_from_stat(
                os.fstat(handle.fileno()), "accepted lock handle"
            ),
            handle,
        )
        SERIS.PUBLISH_TOOLS._require_file_identity(
            owned.path, owned.identity, "accepted lock"
        )
        return owned
    except LockDiscoveryError:
        if handle is not None:
            handle.close()
        raise
    except (OSError, SERIS.PUBLISH_TOOLS.BuildError) as exc:
        if handle is not None:
            try:
                handle.close()
            except OSError as close_error:
                exc.add_note(f"failed to close rejected CAS handle: {close_error}")
        raise LockDiscoveryError(f"cannot freeze accepted lock for CAS: {exc}") from exc
    except BaseException:
        if handle is not None:
            handle.close()
        raise


def _read_owned_existing(owned) -> bytes:
    try:
        SERIS.PUBLISH_TOOLS._require_file_identity(
            owned.path, owned.identity, "accepted lock"
        )
        opened = os.fstat(owned.handle.fileno())
        if opened.st_size <= 0 or opened.st_size > MAX_LOCK_BYTES:
            raise LockDiscoveryError("accepted lock size is invalid")
        owned.handle.seek(0)
        raw = owned.handle.read(MAX_LOCK_BYTES + 1)
        finished = os.fstat(owned.handle.fileno())
        if len(raw) != opened.st_size or len(raw) > MAX_LOCK_BYTES:
            raise LockDiscoveryError("accepted lock size changed while reading")
        stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(opened, field) != getattr(finished, field) for field in stable_fields):
            raise LockDiscoveryError("accepted lock changed while reading")
        SERIS.PUBLISH_TOOLS._require_file_identity(
            owned.path, owned.identity, "accepted lock"
        )
        return raw
    except LockDiscoveryError:
        raise
    except (OSError, SERIS.PUBLISH_TOOLS.BuildError) as exc:
        raise LockDiscoveryError(f"cannot read accepted lock for CAS: {exc}") from exc


def _retire_existing_no_replace(owned, destination: Path):
    """Move the exact opened old lock to a unique recovery name."""
    for _attempt in range(128):
        recovery = destination.parent / (
            f".{destination.name}.{secrets.token_hex(16)}.cas-old"
        )
        try:
            _rename_cas_owner_no_replace(
                owned,
                recovery,
                "accepted-lock retirement",
            )
        except FileExistsError:
            continue
        except OSError as exc:
            raise LockDiscoveryError("failed to retire accepted lock for CAS") from exc
        try:
            SERIS.PUBLISH_TOOLS._require_file_identity(
                owned.path, owned.identity, "retired accepted lock"
            )
        except SERIS.PUBLISH_TOOLS.BuildError as exc:
            raise LockDiscoveryError("retired accepted lock identity changed") from exc
        return owned
    raise LockDiscoveryError("cannot allocate a unique accepted-lock recovery path")


def _restore_retired_no_replace(retired, destination: Path):
    try:
        _rename_cas_owner_no_replace(
            retired,
            destination,
            "accepted-lock restoration",
        )
    except OSError as exc:
        raise LockDiscoveryError("failed to restore retired accepted lock") from exc
    try:
        SERIS.PUBLISH_TOOLS._require_file_identity(
            retired.path, retired.identity, "restored accepted lock"
        )
    except SERIS.PUBLISH_TOOLS.BuildError as exc:
        raise LockDiscoveryError(
            "restored accepted lock identity changed at accepted path"
        ) from exc
    return retired


def _close_owned_existing(owned) -> None:
    try:
        owned.handle.close()
    except OSError as exc:
        raise LockDiscoveryError("failed to close accepted lock handle") from exc


def _delete_retired_existing(retired) -> None:
    try:
        SERIS.PUBLISH_TOOLS._cleanup_owned_staging(retired)
    except SERIS.PUBLISH_TOOLS.BuildError as exc:
        raise LockDiscoveryError("failed to delete retired accepted lock") from exc


EvidenceProvider = Callable[..., Mapping[str, Any]]
ExtensionStage = Callable[..., tuple[Path, Mapping[str, Any]]]
ExtensionVerifier = Callable[..., None]


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


def _load_extension_module(name: str, path: Path):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise LockDiscoveryError(f"cannot load Task 10 stage module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _load_extension_modules():
    return (
        _load_extension_module(
            "offline_lock_discovery_render_scale", RENDER_SCALE_PATH
        ),
        _load_extension_module(
            "offline_lock_discovery_resource_version", RESOURCE_VERSION_PATH
        ),
    )


def _apply_locked_abyss_stage(
    *,
    source_swf: Path,
    accepted_lock: Mapping[str, Any],
    transaction_dir: Path,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    runner,
    timeout: int,
) -> tuple[Path, Mapping[str, Any]]:
    source = Path(source_swf).resolve()
    transaction = Path(transaction_dir).resolve()
    source_sha256 = _sha256_file(source)
    if source_sha256 != accepted_lock["source_swf_sha256"]:
        raise LockDiscoveryError("abyss extension input disagrees with the base lock")
    output = transaction / "post-abyss-extension.swf"

    def abyss_runner(command, *, check, cwd, env):
        del check
        return runner(
            command,
            cwd=Path(cwd),
            env=dict(env),
            timeout=timeout,
        )

    try:
        report = SERIS.PUBLISH_TOOLS.apply_gate_to_swf(
            source,
            output,
            ffdec=Path(ffdec),
            java=Path(java),
            profile_dir=Path(profile_dir),
            work_dir=transaction / "extension-abyss-work",
            runner=abyss_runner,
        )
    except SERIS.PUBLISH_TOOLS.BuildError as exc:
        raise LockDiscoveryError(f"locked abyss extension stage failed: {exc}") from exc
    _assert_unchanged(source, source_sha256, "abyss extension input")
    expected = accepted_lock["abyss_stage"]
    observed = {
        "stage": report.stage,
        "input_sha256": report.input_sha256,
        "output_sha256": report.output_sha256,
        "target_class": report.target_class,
        "before_method_sha256": report.before_method_sha256,
        "after_method_sha256": report.after_method_sha256,
        "match_count": report.match_count,
    }
    if observed != expected:
        raise LockDiscoveryError("locked abyss extension evidence drifted")
    if (
        not output.is_file()
        or Path(report.output_path).resolve() != output.resolve()
        or _sha256_file(output) != accepted_lock["post_abyss_swf_sha256"]
    ):
        raise LockDiscoveryError("locked abyss extension output drifted")
    return output, {}


def _apply_locked_seris_stage(
    *,
    source_swf: Path,
    accepted_lock: Mapping[str, Any],
    transaction_dir: Path,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    runner,
    timeout: int,
) -> tuple[Path, Mapping[str, Any]]:
    source = Path(source_swf).resolve()
    transaction = Path(transaction_dir).resolve()
    source_sha256 = _sha256_file(source)
    if source_sha256 != accepted_lock["post_abyss_swf_sha256"]:
        raise LockDiscoveryError("Seris extension input disagrees with the base lock")
    output = transaction / "post-seris-extension.swf"
    try:
        report = SERIS.apply_seris_phase4(
            source,
            output,
            accepted_lock,
            ffdec=Path(ffdec),
            java=Path(java),
            profile_dir=Path(profile_dir),
            work_dir=transaction / "extension-seris-work",
            runner=runner,
            timeout=timeout,
        )
    except SERIS.SerisPatchError as exc:
        raise LockDiscoveryError(f"locked Seris extension stage failed: {exc}") from exc
    _assert_unchanged(source, source_sha256, "Seris extension input")
    if (
        not report.verified
        or Path(report.output_path).resolve() != output.resolve()
        or report.input_sha256 != source_sha256
        or tuple(report.site_ids) != tuple(accepted_lock["site_ids"])
    ):
        raise LockDiscoveryError("locked Seris extension report drifted")
    for site_id in accepted_lock["site_ids"]:
        entry = accepted_lock["sites"][site_id]
        if (
            report.before_hashes.get(site_id) != entry["before_pcode_sha256"]
            or report.after_hashes.get(site_id) != entry["after_pcode_sha256"]
        ):
            raise LockDiscoveryError(
                f"locked Seris extension evidence drifted at {site_id}"
            )
    if not output.is_file() or _sha256_file(output) != report.output_sha256:
        raise LockDiscoveryError("locked Seris extension output drifted")
    return output, {}


def _discover_render_extension_stage(
    *,
    source_swf: Path,
    accepted_lock: Mapping[str, Any],
    transaction_dir: Path,
    render_module,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    runner,
    timeout: int,
) -> tuple[Path, Mapping[str, Any]]:
    source = Path(source_swf).resolve()
    transaction = Path(transaction_dir).resolve()
    source_sha256 = _sha256_file(source)
    sites = tuple(render_module.RENDER_SITES)
    if tuple(site.site_id for site in sites) != RENDER_SITE_IDS:
        raise LockDiscoveryError("render discovery module site order mismatch")
    locks: dict[str, dict[str, str]] = {}
    current = source
    try:
        for sequence, site in enumerate(sites, start=1):
            expected_class, expected_method, expected_before_abc = (
                RENDER_SITE_IDENTITIES[site.site_id]
            )
            if (
                site.class_name != expected_class
                or site.method_name != expected_method
            ):
                raise LockDiscoveryError(
                    f"render discovery identity mismatch for {site.site_id}"
                )
            index = render_module.ABC_METHODS.index_swf_methods(current)
            ref = index.require_ref(site.method_name)
            before_abc = render_module._sha256_abc(ref.code)
            if before_abc != expected_before_abc:
                raise LockDiscoveryError(
                    f"render discovery before ABC mismatch for {site.site_id}"
                )
            export_root = transaction / f"render-{sequence:02d}-before-export"
            render_module._export_classes(
                current,
                export_root,
                (site.class_name,),
                ffdec=Path(ffdec),
                java=Path(java),
                profile_dir=Path(profile_dir),
                cwd=transaction,
                runner=runner,
                timeout=timeout,
            )
            _assert_unchanged(source, source_sha256, "render discovery input")
            before = render_module._read_exported_method(export_root, site)
            before_pcode = render_module._sha256_pcode(before)
            after = site.patch(before)
            site.verify(after)
            after_pcode = render_module._sha256_pcode(after)
            replacement = transaction / f"render-{sequence:02d}-{site.site_id}.pcode"
            with replacement.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(after)
            staged = transaction / f"render-{sequence:02d}-{site.site_id}.swf"
            render_module._replace_one(
                current,
                staged,
                site,
                replacement,
                ref.body_index,
                ffdec=Path(ffdec),
                java=Path(java),
                profile_dir=Path(profile_dir),
                cwd=transaction,
                runner=runner,
                timeout=timeout,
            )
            _assert_unchanged(source, source_sha256, "render discovery input")
            reopened_ref = (
                render_module.ABC_METHODS.index_swf_methods(staged).require_ref(
                    site.method_name
                )
            )
            after_abc = render_module._sha256_abc(reopened_ref.code)
            locks[site.site_id] = {
                "class_name": site.class_name,
                "method_name": site.method_name,
                "before_pcode_sha256": before_pcode,
                "after_pcode_sha256": after_pcode,
                "before_abc_sha256": before_abc,
                "after_abc_sha256": after_abc,
            }
            reopened = render_module._verify_methods(
                staged,
                sites[:sequence],
                locks,
                export_root=transaction / f"render-{sequence:02d}-reopen-export",
                ffdec=Path(ffdec),
                java=Path(java),
                profile_dir=Path(profile_dir),
                cwd=transaction,
                runner=runner,
                timeout=timeout,
            )
            expected_reopened = {
                prior.site_id: locks[prior.site_id]["after_pcode_sha256"]
                for prior in sites[:sequence]
            }
            if dict(reopened) != expected_reopened:
                raise LockDiscoveryError(
                    f"render cumulative reopen drifted after {site.site_id}"
                )
            current = staged
    except LockDiscoveryError:
        raise
    except (OSError, render_module.RenderScaleError) as exc:
        raise LockDiscoveryError(f"render extension discovery failed: {exc}") from exc
    return current, {
        "render_site_ids": list(RENDER_SITE_IDS),
        "render_sites": locks,
    }


def _discover_resource_extension_stage(
    *,
    source_swf: Path,
    accepted_lock: Mapping[str, Any],
    transaction_dir: Path,
    resource_module,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    runner,
    timeout: int,
) -> tuple[Path, Mapping[str, Any]]:
    source = Path(source_swf).resolve()
    transaction = Path(transaction_dir).resolve()
    source_sha256 = _sha256_file(source)
    identity = {
        "site_id": resource_module.RESOURCE_SITE_ID,
        "class_name": resource_module.RESOURCE_CLASS,
        "method_name": resource_module.RESOURCE_METHOD,
        "source_version": resource_module.SOURCE_VERSION,
        "target_version": resource_module.TARGET_VERSION,
    }
    if identity != RESOURCE_VERSION_IDENTITY:
        raise LockDiscoveryError("resource-version discovery module identity mismatch")
    try:
        resource_ref, dummy_ref = resource_module._method_refs(source)
        before_abc = resource_module._sha256_abc(resource_ref.code)
        dummy_abc = resource_module._sha256_abc(dummy_ref.code)
        if before_abc != accepted_lock["offline_method_sha256"][
            identity["method_name"]
        ]:
            raise LockDiscoveryError("resource-version before ABC baseline drifted")
        if dummy_abc != accepted_lock["offline_method_sha256"][
            "DummyRemote/debugUnlinkTwitter"
        ]:
            raise LockDiscoveryError("resource-version DummyRemote baseline drifted")
        export_root = transaction / "resource-before-export"
        resource_module._export_resource_class(
            source,
            export_root,
            ffdec=Path(ffdec),
            java=Path(java),
            profile_dir=Path(profile_dir),
            cwd=transaction,
            runner=runner,
            timeout=timeout,
        )
        _assert_unchanged(source, source_sha256, "resource-version discovery input")
        before = resource_module._read_exported_resource(export_root)
        before_pcode = resource_module._sha256_pcode(before)
        after = resource_module.patch_resource_version(before)
        after_pcode = resource_module._sha256_pcode(after)
        replacement = transaction / "resource-version.pcode"
        with replacement.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(after)
        output = transaction / "post-resource-version.swf"
        resource_module._replace_one(
            source,
            output,
            replacement,
            resource_ref.body_index,
            ffdec=Path(ffdec),
            java=Path(java),
            profile_dir=Path(profile_dir),
            cwd=transaction,
            runner=runner,
            timeout=timeout,
        )
        _assert_unchanged(source, source_sha256, "resource-version discovery input")
        reopened_resource, reopened_dummy = resource_module._method_refs(output)
        after_abc = resource_module._sha256_abc(reopened_resource.code)
        if resource_module._sha256_abc(reopened_dummy.code) != dummy_abc:
            raise LockDiscoveryError("resource-version changed DummyRemote raw ABC")
        entry = {
            **identity,
            "before_pcode_sha256": before_pcode,
            "after_pcode_sha256": after_pcode,
            "before_abc_sha256": before_abc,
            "after_abc_sha256": after_abc,
        }
        resource_module._verify_reopened_swf(
            output,
            entry,
            dummy_abc,
            export_root=transaction / "resource-reopen-export",
            ffdec=Path(ffdec),
            java=Path(java),
            profile_dir=Path(profile_dir),
            cwd=transaction,
            runner=runner,
            timeout=timeout,
        )
        _assert_unchanged(source, source_sha256, "resource-version discovery input")
    except LockDiscoveryError:
        raise
    except (OSError, resource_module.ResourceVersionError) as exc:
        raise LockDiscoveryError(
            f"resource-version extension discovery failed: {exc}"
        ) from exc
    return output, {"resource_version": entry}


def _verify_extension_cumulative(
    *,
    source_swf: Path,
    extended_lock: Mapping[str, Any],
    transaction_dir: Path,
    render_module,
    resource_module,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    runner,
    timeout: int,
) -> None:
    validate_lock_document(
        extended_lock,
        expected_status="accepted",
        require_extensions=True,
    )
    source = Path(source_swf).resolve()
    transaction = Path(transaction_dir).resolve()
    source_sha256 = _sha256_file(source)

    def abyss_runner(command, *, check, cwd, env):
        del check
        return runner(
            command,
            cwd=Path(cwd),
            env=dict(env),
            timeout=timeout,
        )

    try:
        SERIS.PUBLISH_TOOLS._export_target_class(
            source,
            transaction / "extension-final-abyss-reopen",
            Path(ffdec),
            Path(java),
            verify_gate=True,
            runner=abyss_runner,
            cwd=transaction,
            environment={**os.environ, "APPDATA": str(Path(profile_dir))},
        )
        _assert_unchanged(source, source_sha256, "final extension SWF")
        seris_report = SERIS.verify_seris_phase4(
            source,
            extended_lock,
            ffdec=Path(ffdec),
            java=Path(java),
            profile_dir=Path(profile_dir),
            work_dir=transaction / "extension-final-seris-work",
            runner=runner,
            timeout=timeout,
        )
        if not seris_report.verified or tuple(seris_report.site_ids) != tuple(
            extended_lock["site_ids"]
        ):
            raise LockDiscoveryError("final cumulative Seris verification drifted")
        _assert_unchanged(source, source_sha256, "final extension SWF")
        render_report = render_module.verify_render_scale(
            source,
            extended_lock,
            ffdec=Path(ffdec),
            java=Path(java),
            profile_dir=Path(profile_dir),
            work_dir=transaction / "extension-final-render-work",
            runner=runner,
            timeout=timeout,
        )
        if not render_report.verified or tuple(render_report.site_ids) != RENDER_SITE_IDS:
            raise LockDiscoveryError("final cumulative render verification drifted")
        _assert_unchanged(source, source_sha256, "final extension SWF")
        resource_report = resource_module.verify_resource_version(
            source,
            extended_lock,
            ffdec=Path(ffdec),
            java=Path(java),
            profile_dir=Path(profile_dir),
            work_dir=transaction / "extension-final-resource-work",
            runner=runner,
            timeout=timeout,
        )
        if (
            not resource_report.verified
            or resource_report.output_version
            != RESOURCE_VERSION_IDENTITY["target_version"]
            or not resource_report.is_full_package
        ):
            raise LockDiscoveryError(
                "final cumulative resource-version verification drifted"
            )
        _assert_unchanged(source, source_sha256, "final extension SWF")
    except LockDiscoveryError:
        raise
    except (
        SERIS.PUBLISH_TOOLS.BuildError,
        SERIS.SerisPatchError,
        render_module.RenderScaleError,
        resource_module.ResourceVersionError,
    ) as exc:
        raise LockDiscoveryError(f"final cumulative extension verification failed: {exc}") from exc

    final_index = SERIS.ABC_METHODS.index_swf_methods(source)
    resource_method = RESOURCE_VERSION_IDENTITY["method_name"]
    for suffix, before_hash in extended_lock["offline_method_sha256"].items():
        expected = (
            extended_lock["resource_version"]["after_abc_sha256"]
            if suffix == resource_method
            else before_hash
        )
        if _sha256_bytes(_require_suffix_ref(final_index, suffix).code) != expected:
            raise LockDiscoveryError(
                f"final cumulative offline method drifted for {suffix}"
            )
    render_after_by_method = {
        entry["method_name"]: entry["after_abc_sha256"]
        for entry in extended_lock["render_sites"].values()
    }
    for method in NATIVE_COMPATIBILITY_METHODS:
        expected = render_after_by_method.get(
            method,
            extended_lock["native_compatibility"][method]["abc_sha256"],
        )
        if _sha256_bytes(final_index.require_ref(method).code) != expected:
            raise LockDiscoveryError(
                f"final cumulative native compatibility drifted for {method}"
            )
    _verify_save_haxe_pcode(
        source,
        export_root=transaction / "extension-final-save-haxe-export",
        ffdec=Path(ffdec),
        java=Path(java),
        profile_dir=Path(profile_dir),
        runner=runner,
        timeout=timeout,
    )
    _assert_unchanged(source, source_sha256, "final extension SWF")


def _run_extension_stage(
    name: str,
    stage: ExtensionStage,
    *,
    source_swf: Path,
    accepted_lock: Mapping[str, Any],
    transaction_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    input_path = Path(source_swf).resolve()
    input_sha256 = _sha256_file(input_path)
    result = stage(
        source_swf=input_path,
        accepted_lock=accepted_lock,
        transaction_dir=transaction_dir,
    )
    if not isinstance(result, tuple) or len(result) != 2:
        raise LockDiscoveryError(
            f"{name} extension stage must return (output_swf, evidence)"
        )
    output_value, evidence = result
    if not isinstance(output_value, (str, os.PathLike)):
        raise LockDiscoveryError(f"{name} extension stage output path is invalid")
    output = Path(output_value).resolve()
    try:
        output.relative_to(transaction_dir)
    except ValueError as exc:
        raise LockDiscoveryError(
            f"{name} extension stage output must stay inside the transaction"
        ) from exc
    if output == input_path or not output.is_file():
        raise LockDiscoveryError(
            f"{name} extension stage must create a distinct output SWF"
        )
    if _sha256_file(input_path) != input_sha256:
        raise LockDiscoveryError(f"{name} extension stage mutated its input SWF")
    if not isinstance(evidence, Mapping):
        raise LockDiscoveryError(f"{name} extension stage evidence is invalid")
    return output, dict(evidence)


def compose_extension_evidence_provider(
    *,
    abyss_stage: ExtensionStage,
    seris_stage: ExtensionStage,
    render_stage: ExtensionStage,
    resource_stage: ExtensionStage,
    final_verifier: ExtensionVerifier,
) -> EvidenceProvider:
    """Compose the frozen Task 10 discovery order without inventing evidence."""

    def provider(
        *,
        source_swf: Path,
        accepted_lock: Mapping[str, Any],
        transaction_dir: Path,
    ) -> Mapping[str, Any]:
        if set(accepted_lock) != BASE_TOP_LEVEL_KEYS:
            raise LockDiscoveryError(
                "extension provider requires the frozen Task 9 base lock"
            )
        validate_lock_document(accepted_lock, expected_status="accepted")
        transaction = Path(transaction_dir).resolve()
        if not transaction.is_dir():
            raise LockDiscoveryError("extension transaction directory is missing")

        current, abyss_evidence = _run_extension_stage(
            "abyss",
            abyss_stage,
            source_swf=Path(source_swf),
            accepted_lock=accepted_lock,
            transaction_dir=transaction,
        )
        if abyss_evidence:
            raise LockDiscoveryError("abyss extension stage returned unexpected evidence")
        current, seris_evidence = _run_extension_stage(
            "Seris",
            seris_stage,
            source_swf=current,
            accepted_lock=accepted_lock,
            transaction_dir=transaction,
        )
        if seris_evidence:
            raise LockDiscoveryError("Seris extension stage returned unexpected evidence")
        current, render_evidence = _run_extension_stage(
            "render",
            render_stage,
            source_swf=current,
            accepted_lock=accepted_lock,
            transaction_dir=transaction,
        )
        if set(render_evidence) != {"render_site_ids", "render_sites"}:
            raise LockDiscoveryError("render extension evidence schema mismatch")
        current, resource_evidence = _run_extension_stage(
            "resource-version",
            resource_stage,
            source_swf=current,
            accepted_lock=accepted_lock,
            transaction_dir=transaction,
        )
        if set(resource_evidence) != {"resource_version"}:
            raise LockDiscoveryError("resource-version extension evidence schema mismatch")

        evidence = {**render_evidence, **resource_evidence}
        candidate = dict(accepted_lock)
        candidate.update(evidence)
        validate_extension_candidate(candidate, accepted_lock)
        final_verifier(
            source_swf=current,
            extended_lock=candidate,
            transaction_dir=transaction,
        )
        return evidence

    return provider


def build_extension_evidence_provider(
    *,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    runner=SERIS._subprocess_runner,
    timeout: int = 240,
) -> EvidenceProvider:
    """Build the real base -> Abyss -> Seris -> render -> resource discovery."""
    ffdec_path = Path(ffdec).resolve()
    java_path = Path(java).resolve()
    profile = Path(profile_dir).resolve()
    if not ffdec_path.is_file() or not java_path.is_file():
        raise LockDiscoveryError("Task 10 discovery Java or FFDec tool is missing")
    if profile.exists() and not profile.is_dir():
        raise LockDiscoveryError("Task 10 discovery profile path is not a directory")
    render_module, resource_module = _load_extension_modules()
    common = {
        "ffdec": ffdec_path,
        "java": java_path,
        "profile_dir": profile,
        "runner": runner,
        "timeout": timeout,
    }

    def abyss_stage(**stage):
        return _apply_locked_abyss_stage(**stage, **common)

    def seris_stage(**stage):
        return _apply_locked_seris_stage(**stage, **common)

    def render_stage(**stage):
        return _discover_render_extension_stage(
            **stage,
            render_module=render_module,
            **common,
        )

    def resource_stage(**stage):
        return _discover_resource_extension_stage(
            **stage,
            resource_module=resource_module,
            **common,
        )

    def final_verifier(**stage):
        return _verify_extension_cumulative(
            **stage,
            render_module=render_module,
            resource_module=resource_module,
            **common,
        )

    return compose_extension_evidence_provider(
        abyss_stage=abyss_stage,
        seris_stage=seris_stage,
        render_stage=render_stage,
        resource_stage=resource_stage,
        final_verifier=final_verifier,
    )


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


def _read_canonical_document_with_digest(
    path: Path,
    *,
    expected_sha256: str,
    label: str,
) -> tuple[bytes, Mapping[str, Any]]:
    expected = _require_hash(expected_sha256, f"expected_{label}_sha256")
    raw = _read_regular_file_snapshot(path)
    actual = _sha256_bytes(raw)
    if not hmac.compare_digest(actual, expected):
        raise LockDiscoveryError(f"{label} SHA-256 mismatch")
    value = _parse_json_strict_bytes(raw)
    if raw != _canonical_json_bytes(value):
        raise LockDiscoveryError(f"{label} JSON is not canonical UTF-8/LF")
    return raw, value


def discover_extension_candidate(
    source_apk: Path,
    base_lock: Path,
    output: Path,
    *,
    work_dir: Path,
    evidence_provider: EvidenceProvider,
    expected_old_lock_sha256: str,
    expected_apk_sha256: str = EXPECTED_BASE_APK_SHA256,
) -> Mapping[str, Any]:
    """Create a new reviewed Task 10 candidate without editing the accepted lock."""
    source = Path(source_apk).resolve()
    lock_path = Path(base_lock).resolve()
    destination = Path(output).resolve()
    work = Path(work_dir).resolve()
    if expected_apk_sha256 != EXPECTED_BASE_APK_SHA256:
        raise LockDiscoveryError("expected APK hash must equal the reviewed offline base")
    if not source.is_file() or os.path.lexists(destination):
        raise LockDiscoveryError("extension source is missing or candidate output exists")
    if os.path.normcase(str(lock_path)) == os.path.normcase(str(destination)):
        raise LockDiscoveryError("extension candidate must not overwrite the accepted lock")
    try:
        work.relative_to(destination)
    except ValueError:
        pass
    else:
        raise LockDiscoveryError("candidate output cannot equal or contain work directory")

    old_raw, old_value = _read_canonical_document_with_digest(
        lock_path,
        expected_sha256=expected_old_lock_sha256,
        label="old_lock",
    )
    validate_lock_document(old_value, expected_status="accepted")
    if set(old_value) != BASE_TOP_LEVEL_KEYS:
        raise LockDiscoveryError("extension discovery requires an unextended accepted lock")

    work.mkdir(parents=True, exist_ok=True)
    transaction: Path | None = Path(
        tempfile.mkdtemp(prefix=".offline-lock-extension-", dir=work)
    ).resolve()
    try:
        source_snapshot = transaction / "source.apk"
        _copy_regular_file_snapshot(source, source_snapshot)
        if _sha256_file(source_snapshot) != EXPECTED_BASE_APK_SHA256:
            raise LockDiscoveryError("source APK hash mismatch")
        baseline = _inspect_base_apk(source_snapshot)
        for field in (
            "source_swf_sha256",
            "manifest_sha256",
            "dex_sha256",
            "native_aggregate_sha256",
            "native_members",
        ):
            if baseline.get(field) != old_value[field]:
                raise LockDiscoveryError(f"accepted lock baseline mismatch at {field}")

        swf = transaction / "source.swf"
        try:
            with zipfile.ZipFile(source_snapshot, "r") as archive:
                infos = [
                    info
                    for info in archive.infolist()
                    if info.filename == TARGET_SWF
                ]
                if len(infos) != 1:
                    raise LockDiscoveryError("expected exactly one main SWF member")
                with swf.open("xb") as handle:
                    handle.write(archive.read(infos[0]))
                    handle.flush()
                    os.fsync(handle.fileno())
        except (OSError, zipfile.BadZipFile, KeyError) as exc:
            raise LockDiscoveryError(f"cannot extract extension source SWF: {exc}") from exc
        extracted_hash = _sha256_file(swf)
        if (
            extracted_hash != EXPECTED_SWF_SHA256
            or extracted_hash != old_value["source_swf_sha256"]
        ):
            raise LockDiscoveryError("extension source SWF baseline mismatch")

        evidence = evidence_provider(
            source_swf=swf,
            accepted_lock=old_value,
            transaction_dir=transaction,
        )
        if not isinstance(evidence, Mapping) or set(evidence) != EXTENSION_KEYS:
            raise LockDiscoveryError("extension evidence schema mismatch")
        candidate = dict(old_value)
        candidate.update(dict(evidence))
        validate_extension_candidate(candidate, old_value)

        if _sha256_file(source) != EXPECTED_BASE_APK_SHA256:
            raise LockDiscoveryError("source APK changed during extension discovery")
        if _read_regular_file_snapshot(lock_path) != old_raw:
            raise LockDiscoveryError("accepted lock changed during extension discovery")
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


def accept_extension_candidate(
    candidate: Path,
    output: Path,
    *,
    confirmation: str,
    expected_old_lock_sha256: str,
    expected_candidate_sha256: str,
) -> Mapping[str, Any]:
    """CAS an accepted extension candidate into the existing lock path."""
    if confirmation != CONFIRMATION:
        raise LockDiscoveryError("lock acceptance confirmation mismatch")
    expected_old = _require_hash(
        expected_old_lock_sha256, "expected_old_lock_sha256"
    )
    expected_candidate = _require_hash(
        expected_candidate_sha256, "expected_candidate_sha256"
    )
    candidate_path = Path(candidate).resolve()
    destination = Path(output).resolve()
    if os.path.normcase(str(candidate_path)) == os.path.normcase(str(destination)):
        raise LockDiscoveryError("extension candidate and accepted lock must differ")
    try:
        if os.path.samefile(candidate_path, destination):
            raise LockDiscoveryError(
                "extension candidate and accepted lock are filesystem aliases"
            )
    except FileNotFoundError:
        raise LockDiscoveryError("extension candidate or accepted lock is missing") from None
    except OSError as exc:
        raise LockDiscoveryError("cannot compare extension candidate paths") from exc

    candidate_raw, candidate_value = _read_canonical_document_with_digest(
        candidate_path,
        expected_sha256=expected_candidate,
        label="candidate",
    )
    old_owned = None
    staged = None
    candidate_owned = None
    published_owned = None
    committed = False
    original_error: BaseException | None = None
    try:
        old_owned = _open_existing_for_cas(destination)
        old_raw = _read_owned_existing(old_owned)
        if not hmac.compare_digest(_sha256_bytes(old_raw), expected_old):
            raise LockDiscoveryError("old lock SHA-256 mismatch")
        old_value = _parse_json_strict_bytes(old_raw)
        if old_raw != _canonical_json_bytes(old_value):
            raise LockDiscoveryError("old lock JSON is not canonical UTF-8/LF")
        validate_extension_candidate(candidate_value, old_value)

        staged = _stage_output_sibling(
            candidate_path,
            destination,
            expected_candidate,
        )
        candidate_owned = _CasOwnedFile(
            staged.path,
            staged.identity,
            staged.handle,
        )
        staged = None
        _retire_existing_no_replace(old_owned, destination)
        _publish_candidate_owner_no_replace(candidate_owned, destination)
        published_raw = _read_owned_existing(candidate_owned)
        if not hmac.compare_digest(
            _sha256_bytes(published_raw), expected_candidate
        ):
            raise LockDiscoveryError(
                "published extension candidate handle SHA-256 mismatch"
            )
        _close_owned_existing(candidate_owned)
        candidate_owned = None
        published_owned = _open_existing_for_cas(destination)
        frozen_raw = _read_owned_existing(published_owned)
        if not hmac.compare_digest(_sha256_bytes(frozen_raw), expected_candidate):
            raise LockDiscoveryError(
                "frozen extension candidate SHA-256 mismatch"
            )
        committed = True
        _delete_retired_existing(old_owned)
        old_owned = None
        final_raw = _read_owned_existing(published_owned)
        if not hmac.compare_digest(_sha256_bytes(final_raw), expected_candidate):
            raise LockDiscoveryError(
                "frozen extension candidate changed during old-lock cleanup"
            )
        _close_owned_existing(published_owned)
        published_owned = None
        return candidate_value
    except BaseException as error:
        original_error = error
        raise
    finally:
        if committed and original_error is not None:
            original_error.add_note(
                "candidate commit is retained; "
                f"destination={destination}; sha256={expected_candidate}"
            )
        if candidate_owned is not None and candidate_owned.pending_paths is not None:
            if not _settle_pending_cas_owner(
                candidate_owned,
                original_error,
                context="failed candidate publication owner reconciliation",
            ):
                candidate_owned = None
        if candidate_owned is not None:
            candidate_path_now = Path(candidate_owned.path)
            candidate_at_destination = os.path.normcase(
                str(candidate_path_now)
            ) == os.path.normcase(str(destination))
            try:
                if candidate_at_destination:
                    _close_owned_existing(candidate_owned)
                else:
                    _cleanup_owned_staging(candidate_owned)
            except BaseException as cleanup_error:
                if original_error is None:
                    raise
                original_error.add_note(
                    "failed to settle candidate publication owner: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}; "
                    f"path={candidate_path_now}"
                )
            candidate_owned = None
        if published_owned is not None:
            try:
                _close_owned_existing(published_owned)
            except BaseException as close_error:
                if original_error is None:
                    raise
                original_error.add_note(
                    "failed to close frozen extension candidate: "
                    f"{type(close_error).__name__}: {close_error}"
                )
            published_owned = None
        if old_owned is not None and old_owned.pending_paths is not None:
            if not _settle_pending_cas_owner(
                old_owned,
                original_error,
                context="failed secondary accepted-lock owner reconciliation",
            ):
                old_owned = None
        if old_owned is not None and not committed:
            owner_at_destination = os.path.normcase(str(old_owned.path)) == os.path.normcase(
                str(destination)
            )
            if not owner_at_destination and not os.path.lexists(destination):
                try:
                    _restore_retired_no_replace(old_owned, destination)
                except BaseException as recovery_error:
                    if old_owned.pending_paths is not None and not (
                        _settle_pending_cas_owner(
                            old_owned,
                            original_error,
                            context=(
                                "failed to settle accepted-lock owner after restore "
                                f"failure ({type(recovery_error).__name__}: "
                                f"{recovery_error})"
                            ),
                        )
                    ):
                        old_owned = None
                    if old_owned is not None:
                        actual_path = Path(old_owned.path)
                        try:
                            _close_owned_existing(old_owned)
                        except BaseException as close_error:
                            recovery_error.add_note(
                                "failed to close old accepted-lock handle after restore "
                                f"failure: {type(close_error).__name__}: {close_error}"
                            )
                        old_owned = None
                        if original_error is None:
                            raise recovery_error
                        if os.path.normcase(str(actual_path)) == os.path.normcase(
                            str(destination)
                        ):
                            original_error.add_note(
                                "old accepted lock moved back to accepted path but "
                                "post-restore verification failed; handle closed; "
                                f"path={actual_path}; error={type(recovery_error).__name__}: "
                                f"{recovery_error}"
                            )
                        elif os.path.lexists(actual_path):
                            original_error.add_note(
                                "failed to restore retired accepted lock; handle closed; "
                                f"recovery preserved at {actual_path}; "
                                f"error={type(recovery_error).__name__}: {recovery_error}"
                            )
                        else:
                            original_error.add_note(
                                "failed to restore retired accepted lock; handle closed; "
                                f"last known path={actual_path}; "
                                f"error={type(recovery_error).__name__}: {recovery_error}"
                            )
                else:
                    try:
                        _close_owned_existing(old_owned)
                    except BaseException as close_error:
                        if original_error is None:
                            raise
                        original_error.add_note(
                            "failed to close restored accepted lock: "
                            f"{type(close_error).__name__}: {close_error}"
                        )
                    old_owned = None
            else:
                owned_path = Path(old_owned.path)
                try:
                    _close_owned_existing(old_owned)
                except BaseException as close_error:
                    if original_error is None:
                        raise
                    original_error.add_note(
                        "failed to close old accepted lock: "
                        f"{type(close_error).__name__}: {close_error}"
                    )
                old_owned = None
                if original_error is not None and not owner_at_destination:
                    original_error.add_note(
                        f"accepted lock recovery preserved at {owned_path}"
                    )
        if old_owned is not None and committed:
            recovery_path = Path(old_owned.path)
            try:
                _close_owned_existing(old_owned)
            except BaseException as close_error:
                if original_error is None:
                    raise
                original_error.add_note(
                    "failed to close committed recovery handle: "
                    f"{type(close_error).__name__}: {close_error}"
                )
            old_owned = None
            if original_error is not None and os.path.lexists(recovery_path):
                original_error.add_note(
                    f"old accepted lock recovery preserved at {recovery_path}"
                )
        if staged is not None:
            try:
                _cleanup_owned_staging(staged)
            except BaseException as cleanup_error:
                if original_error is None:
                    raise
                original_error.add_note(
                    "failed to clean staged extension candidate: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )


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
    discover_extension = subparsers.add_parser("discover-extension")
    discover_extension.add_argument("--source-apk", type=Path, required=True)
    discover_extension.add_argument("--base-lock", type=Path, required=True)
    discover_extension.add_argument("--expected-apk-sha256", required=True)
    discover_extension.add_argument("--expected-old-lock-sha256", required=True)
    discover_extension.add_argument("--output", type=Path, required=True)
    discover_extension.add_argument("--java", type=Path)
    discover_extension.add_argument("--ffdec", type=Path)
    discover_extension.add_argument("--work-dir", type=Path)
    discover_extension.add_argument("--profile-dir", type=Path)
    accept = subparsers.add_parser("accept")
    accept.add_argument("--candidate", type=Path, required=True)
    accept.add_argument("--output", type=Path, required=True)
    accept.add_argument("--confirm", required=True)
    accept.add_argument("--expected-candidate-sha256", required=True)
    accept_extension = subparsers.add_parser("accept-extension")
    accept_extension.add_argument("--candidate", type=Path, required=True)
    accept_extension.add_argument("--output", type=Path, required=True)
    accept_extension.add_argument("--confirm", required=True)
    accept_extension.add_argument("--expected-old-lock-sha256", required=True)
    accept_extension.add_argument("--expected-candidate-sha256", required=True)
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
        if args.action == "accept-extension":
            accepted = accept_extension_candidate(
                args.candidate,
                args.output,
                confirmation=args.confirm,
                expected_old_lock_sha256=args.expected_old_lock_sha256,
                expected_candidate_sha256=args.expected_candidate_sha256,
            )
            print(
                json.dumps(
                    {
                        "status": accepted["status"],
                        "final_sha256": args.expected_candidate_sha256,
                        "render_site_count": len(accepted["render_site_ids"]),
                        "resource_version": accepted["resource_version"][
                            "target_version"
                        ],
                    },
                    sort_keys=True,
                )
            )
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
        provider_builder = (
            build_extension_evidence_provider
            if args.action == "discover-extension"
            else build_reviewed_evidence_provider
        )
        provider = provider_builder(
            ffdec=ffdec_path,
            java=java_path,
            profile_dir=Path(profile_value),
        )
        if args.action == "discover-extension":
            candidate = discover_extension_candidate(
                args.source_apk,
                args.base_lock,
                args.output,
                work_dir=Path(work_value),
                evidence_provider=provider,
                expected_old_lock_sha256=args.expected_old_lock_sha256,
                expected_apk_sha256=args.expected_apk_sha256,
            )
            print(
                json.dumps(
                    {
                        "status": "extension-candidate",
                        "base_lock_sha256": args.expected_old_lock_sha256,
                        "candidate_sha256": _sha256_bytes(
                            _canonical_json_bytes(candidate)
                        ),
                        "render_site_count": len(candidate["render_site_ids"]),
                        "resource_version": candidate["resource_version"][
                            "target_version"
                        ],
                    },
                    sort_keys=True,
                )
            )
            return 0
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
