#!/usr/bin/env python3
"""Apply and verify the nine Seris Phase 4 pure-P-code sites.

This module is deliberately independent from the ignored ``work/`` tree.  It
contains only deterministic method-body transforms; baseline discovery and
lock acceptance live in a separately reviewed tool.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
import json
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
from typing import Any, Callable, Mapping, Sequence


HERE = Path(__file__).resolve().parent
CLIENT_PATCH = HERE.parent
DUAL_FORM = CLIENT_PATCH / "dual-form-v1"
ABYSS_BUILD_PATH = CLIENT_PATCH / "abyss-mode-equipment" / "build_apk.py"
CODE_INDENT = "            "
LABEL_INDENT = "   "
SERIS_ID = "seris_dragon_king"
LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")
OFFSET_LABEL = re.compile(r"\bofs[0-9A-Fa-f]+\b")


class SerisPatchError(RuntimeError):
    pass


def _load_helper(name: str, filename: str):
    path = DUAL_FORM / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SerisPatchError(f"cannot load tracked helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ABC_METHODS = _load_helper("offline_seris_abc_methods", "abc_methods.py")
PCODE_TOOLS = _load_helper("offline_seris_pcode_tools", "pcode_tools.py")


def _load_publish_tools():
    name = "offline_seris_abyss_build_publish_tools"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, ABYSS_BUILD_PATH)
    if spec is None or spec.loader is None:
        raise SerisPatchError(f"cannot load tracked publish helper: {ABYSS_BUILD_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PUBLISH_TOOLS = _load_publish_tools()


@dataclass(frozen=True, slots=True)
class SerisPatch:
    site_id: str
    class_name: str
    method_name: str
    apply: Callable[[str], str]
    verify: Callable[[str], None]


@dataclass(frozen=True, slots=True)
class SerisPatchReport:
    output_path: Path
    input_sha256: str
    output_sha256: str
    site_ids: tuple[str, ...]
    before_hashes: Mapping[str, str]
    after_hashes: Mapping[str, str]
    asset_logicals: tuple[str, ...]
    verified: bool


@dataclass(frozen=True, slots=True)
class _PatchSpec:
    site_id: str
    class_name: str
    method_name: str
    before_anchor: str
    expected_anchor_count: int
    marker: str
    new_labels: tuple[str, ...]
    required_maxstack: int
    required_localcount: int
    transform: Callable[[str], str]
    semantic_tokens: tuple[str, ...]


def _code(*lines: str) -> str:
    return "\n".join(CODE_INDENT + line for line in lines)


def _label(name: str) -> str:
    return LABEL_INDENT + name + ":"


def _instruction_count(text: str, instruction: str) -> int:
    return sum(line.strip() == instruction for line in text.splitlines())


def _require_instruction(text: str, instruction: str, count: int = 1) -> None:
    actual = _instruction_count(text, instruction)
    if actual != count:
        raise SerisPatchError(
            f"instruction {instruction!r} count {actual}; expected {count}"
        )


def _require_order(text: str, tokens: Sequence[str], context: str) -> None:
    cursor = -1
    for token in tokens:
        position = text.find(token, cursor + 1)
        if position < 0:
            raise SerisPatchError(f"{context}: missing semantic token {token!r}")
        if position <= cursor:
            raise SerisPatchError(f"{context}: semantic order changed")
        cursor = position


def canonical_pcode(text: str) -> str:
    """Normalize only FFDec offset-label renumbering, preserving topology."""
    definitions = re.findall(
        r"(?m)^[ \t]*(ofs[0-9A-Fa-f]+):[ \t]*$", text
    )
    normalized = [label.lower() for label in definitions]
    if len(normalized) != len(set(normalized)):
        raise SerisPatchError("P-code contains duplicate offset label definitions")
    labels = {label: f"L{index}" for index, label in enumerate(normalized)}
    referenced = {match.group(0).lower() for match in OFFSET_LABEL.finditer(text)}
    undefined = sorted(referenced - set(labels))
    if undefined:
        raise SerisPatchError(
            f"P-code contains undefined offset label references: {undefined}"
        )
    return OFFSET_LABEL.sub(lambda match: labels[match.group(0).lower()], text)


def _declaration(text: str, name: str) -> int:
    matches = re.findall(rf"(?m)^[ \t]*{name} ([0-9]+)[ \t]*$", text)
    if len(matches) != 1:
        raise SerisPatchError(f"expected one {name} declaration, found {len(matches)}")
    return int(matches[0])


def _raise_declaration(text: str, name: str, required: int) -> str:
    pattern = re.compile(rf"^(?P<indent>[ \t]*){name} (?P<value>[0-9]+)[ \t]*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise SerisPatchError(f"expected one {name} declaration, found {len(matches)}")
    current = int(matches[0].group("value"))
    if current >= required:
        return text
    replacement = f'{matches[0].group("indent")}{name} {required}'
    return text[: matches[0].start()] + replacement + text[matches[0].end() :]


def _dragon_guard(member_lines: tuple[str, ...], fallback: str) -> str:
    member = list(member_lines)
    character = member + [
        'callproperty QName(Namespace("pinball.scene.battle.battle.squad.member:MemberPeek"),"getCharacter"), 0'
    ]
    return _code(
        *(
            character
            + [
                'getproperty QName(PackageNamespace(""),"characterTags")',
                'pushstring "ModDualForm"',
                'callproperty QName(Namespace("http://adobe.com/AS3/2006/builtin"),"indexOf"), 1',
                "convert_i",
                "pushbyte -1",
                f"ifeq {fallback}",
            ]
            + character
            + [
                'getproperty QName(PackageNamespace(""),"mainCharacterStringId")',
                f'pushstring "{SERIS_ID}"',
                f"ifne {fallback}",
            ]
            + member
            + [
                'getlex QName(PackageNamespace("pinball.common.data.character.condition"),"ConditionTargetKind")',
                "pushbyte 22",
                'callproperty QName(PackageNamespace(""),"Unique"), 1',
                'coerce QName(PackageNamespace("pinball.common.data.character.condition"),"ConditionTargetKind")',
                'callproperty QName(PackageNamespace(""),"matchCondition"), 1',
                "convert_b",
                f"iffalse {fallback}",
            ]
        )
    )


PRELOAD_ANCHOR = _code(
    "getscopeobject 1",
    "getslot 9",
    'findpropstrict QName(PackageNamespace(""),"getPixelArtAnimationPath")',
    'callproperty QName(PackageNamespace(""),"getPixelArtAnimationPath"), 0',
    'callpropvoid QName(Namespace("pinball.asset.logic:IAssetPathCollectionBuilder"),"addAnimationLayout"), 1',
)
PRELOAD_MARKER = 'pushstring "character/seris_dragon_king/pixelart/special"'


def _transform_preload(block: str) -> str:
    injection = "\n".join(
        (
            PRELOAD_ANCHOR,
            _code(
                'findpropstrict QName(PackageNamespace(""),"get_stringId")',
                'callproperty QName(PackageNamespace(""),"get_stringId"), 0',
                f'pushstring "{SERIS_ID}"',
                "ifne ofs7a10",
                "getscopeobject 1",
                "getslot 9",
                PRELOAD_MARKER,
                'callpropvoid QName(Namespace("pinball.asset.logic:IAssetPathCollectionBuilder"),"addAnimationLayout"), 1',
                "getscopeobject 1",
                "getslot 9",
                'pushstring "character/seris_dragon_king/ui/skill_cutin_dragon"',
                'callpropvoid QName(Namespace("pinball.asset.logic:IAssetPathCollectionBuilder"),"addImage"), 1',
                "getscopeobject 1",
                "getslot 9",
                'pushstring "character/seris_dragon_king/ui/battle_control_board_dragon"',
                'callpropvoid QName(Namespace("pinball.asset.logic:IAssetPathCollectionBuilder"),"addImage"), 1',
                "getscopeobject 1",
                "getslot 9",
                'pushstring "character/seris_dragon_king/ui/battle_member_status_dragon"',
                'callpropvoid QName(Namespace("pinball.asset.logic:IAssetPathCollectionBuilder"),"addImage"), 1',
            ),
            _label("ofs7a10"),
        )
    )
    return block.replace(PRELOAD_ANCHOR, injection, 1)


SWAP_ANCHOR = _code(
    "pushnull",
    'astype QName(PackageNamespace("pinball.scene.battle.battle.barrier"),"BarrierHpGaugePeek")',
    "setlocal 20",
    'findproperty QName(PackageNamespace(""),"member")',
)
SWAP_MARKER = 'pushstring "ModDualForm"'


def _transform_swap(block: str) -> str:
    replacement = SWAP_ANCHOR.replace(
        CODE_INDENT + 'findproperty QName(PackageNamespace(""),"member")',
        _code(
            "pushnull",
            'astype QName(PackageNamespace(""),"String")',
            "setlocal 23",
            "pushnull",
            'astype QName(PackageNamespace("flatomo.animation"),"Animation")',
            "setlocal 24",
            'findproperty QName(PackageNamespace(""),"member")',
            'getproperty QName(PackageNamespace(""),"member")',
            'callproperty QName(Namespace("pinball.scene.battle.battle.squad.member:MemberPeek"),"getCharacter"), 0',
            'getproperty QName(PackageNamespace(""),"characterTags")',
            SWAP_MARKER,
            'callproperty QName(Namespace("http://adobe.com/AS3/2006/builtin"),"indexOf"), 1',
            "convert_i",
            "pushbyte -1",
            "ifeq ofs7fe0",
            'findproperty QName(PackageNamespace(""),"member")',
            'getproperty QName(PackageNamespace(""),"member")',
            'callproperty QName(Namespace("pinball.scene.battle.battle.squad.member:MemberPeek"),"getCharacter"), 0',
            'getproperty QName(PackageNamespace(""),"mainCharacterStringId")',
            f'pushstring "{SERIS_ID}"',
            "ifne ofs7fe0",
            'findproperty QName(PackageNamespace(""),"member")',
            'getproperty QName(PackageNamespace(""),"member")',
            'getlex QName(PackageNamespace("pinball.common.data.character.condition"),"ConditionTargetKind")',
            "pushbyte 22",
            'callproperty QName(PackageNamespace(""),"Unique"), 1',
            'coerce QName(PackageNamespace("pinball.common.data.character.condition"),"ConditionTargetKind")',
            'callproperty QName(PackageNamespace(""),"matchCondition"), 1',
            "convert_b",
            "iffalse ofs7fc0",
            'pushstring "character/"',
            'findproperty QName(PackageNamespace(""),"member")',
            'getproperty QName(PackageNamespace(""),"member")',
            'callproperty QName(Namespace("pinball.scene.battle.battle.squad.member:MemberPeek"),"getCharacter"), 0',
            'getproperty QName(PackageNamespace(""),"mainCharacterStringId")',
            "add",
            'pushstring "/pixelart/special"',
            "add",
            'coerce QName(PackageNamespace(""),"String")',
            "setlocal 23",
            "jump ofs7fd0",
        )
        + "\n"
        + _label("ofs7fc0")
        + "\n"
        + _code(
            'findproperty QName(PackageNamespace(""),"member")',
            'getproperty QName(PackageNamespace(""),"member")',
            'callproperty QName(Namespace("pinball.scene.battle.battle.squad.member:MemberPeek"),"getCharacterAnimation"), 0',
            'coerce QName(PackageNamespace(""),"String")',
            "setlocal 23",
        )
        + "\n"
        + _label("ofs7fd0")
        + "\n"
        + _code(
            'findproperty QName(PackageNamespace(""),"character")',
            'getproperty QName(PackageNamespace(""),"character")',
            'callproperty QName(PackageNamespace(""),"get_path"), 0',
            'coerce QName(PackageNamespace(""),"String")',
            "getlocal 23",
            "ifeq ofs7fe0",
            'findproperty QName(PackageNamespace(""),"asset")',
            'getproperty QName(PackageNamespace(""),"asset")',
            "getlocal 23",
            'callproperty QName(PackageNamespace(""),"getAnimation"), 1',
            'coerce QName(PackageNamespace("flatomo.animation"),"Animation")',
            "setlocal 24",
            "getlocal 24",
            "iffalse ofs7fe0",
            "getlocal 24",
            "pushbyte 21",
            'initproperty QName(PackageNamespace(""),"zIndex2")',
            "getlocal 24",
            'findproperty QName(PackageNamespace(""),"character")',
            'getproperty QName(PackageNamespace(""),"character")',
            'getproperty QName(PackageNamespace(""),"alpha")',
            'initproperty QName(PackageNamespace(""),"alpha")',
            "getlocal 24",
            'findproperty QName(PackageNamespace(""),"character")',
            'getproperty QName(PackageNamespace(""),"character")',
            'getproperty QName(PackageNamespace(""),"visible")',
            'initproperty QName(PackageNamespace(""),"visible")',
            'findproperty QName(PackageNamespace(""),"characterLayer")',
            'getproperty QName(PackageNamespace(""),"characterLayer")',
            'findproperty QName(PackageNamespace(""),"character")',
            'getproperty QName(PackageNamespace(""),"character")',
            "pushtrue",
            'callpropvoid QName(PackageNamespace(""),"removeChild"), 2',
            'findproperty QName(PackageNamespace(""),"character")',
            "getlocal 24",
            'setproperty QName(PackageNamespace(""),"character")',
            'findproperty QName(PackageNamespace(""),"characterLayer")',
            'getproperty QName(PackageNamespace(""),"characterLayer")',
            'findproperty QName(PackageNamespace(""),"character")',
            'getproperty QName(PackageNamespace(""),"character")',
            'callpropvoid QName(PackageNamespace(""),"addChild"), 1',
        )
        + "\n"
        + _label("ofs7fe0")
        + "\n"
        + CODE_INDENT
        + 'findproperty QName(PackageNamespace(""),"member")',
        1,
    )
    return block.replace(SWAP_ANCHOR, replacement, 1)


PF_ANCHOR = _code(
    'findpropstrict QName(PackageNamespace("pinball.common.data.skill.powerFlip"),"PowerFlipLogic")',
    'getlex QName(PackageNamespace(""),"powerFlipActionId")',
    'findpropstrict QName(PackageNamespace(""),"get_element")',
)
PF_MARKER = 'pushstring "override_seris_human_powerflip"'


def _transform_pf(block: str) -> str:
    replacement = "\n".join(
        (
            _code(
                'findpropstrict QName(PackageNamespace("pinball.common.data.skill.powerFlip"),"PowerFlipLogic")',
                'findpropstrict QName(PackageNamespace(""),"get_stringId")',
                'callproperty QName(PackageNamespace(""),"get_stringId"), 0',
                f'pushstring "{SERIS_ID}"',
                "ifne ofs7a20",
                PF_MARKER,
                "jump ofs7a21",
            ),
            _label("ofs7a20"),
            _code('getlex QName(PackageNamespace(""),"powerFlipActionId")'),
            _label("ofs7a21"),
            _code('findpropstrict QName(PackageNamespace(""),"get_element")'),
        )
    )
    return block.replace(PF_ANCHOR, replacement, 1)


CUTIN_ANCHOR = _code(
    "getlocal2", 'getproperty QName(PackageNamespace(""),"skillCutinImagePath")'
)
CUTIN_INSERT = _code(
    "getlocal2",
    'getproperty QName(PackageNamespace(""),"assistCharacter")',
    "iffalse ofs03b5",
)
CUTIN_MARKER = 'pushstring "character/seris_dragon_king/ui/skill_cutin_dragon"'


def _transform_cutin(block: str) -> str:
    result = block.replace(CUTIN_ANCHOR, _code("getlocal 25"))
    init = "\n".join(
        (
            _code(
                "pushnull",
                'astype QName(PackageNamespace(""),"String")',
                "setlocal 25",
                "getlocal2",
                'getproperty QName(PackageNamespace(""),"skillCutinImagePath")',
                'coerce QName(PackageNamespace(""),"String")',
                "setlocal 25",
            ),
            _dragon_guard(("getlocal0",), "ofs7a30"),
            _code(CUTIN_MARKER, "setlocal 25"),
            _label("ofs7a30"),
            CUTIN_INSERT,
        )
    )
    return result.replace(CUTIN_INSERT, init, 1)


STATUS_GETTER_ANCHOR = _code(
    'findproperty QName(PackageNamespace(""),"character")',
    'getproperty QName(PackageNamespace(""),"character")',
    'getproperty QName(PackageNamespace(""),"memberStatusImagePath")',
    "returnvalue",
)
STATUS_PATH = 'pushstring "character/seris_dragon_king/ui/battle_member_status_dragon"'


def _transform_status_getter(block: str) -> str:
    member = (
        'findproperty QName(PackageNamespace(""),"member")',
        'getproperty QName(PackageNamespace(""),"member")',
    )
    replacement = "\n".join(
        (
            _dragon_guard(member, "ofs7a40"),
            _code(STATUS_PATH, "returnvalue"),
            _label("ofs7a40"),
            STATUS_GETTER_ANCHOR,
        )
    )
    return block.replace(STATUS_GETTER_ANCHOR, replacement, 1)


STATUS_DRAW_ANCHOR = _code(
    "pushnull",
    'astype QName(PackageNamespace("flatomo.animation"),"Animation")',
    "setlocal 11",
    'findproperty QName(PackageNamespace(""),"healthPointGaugeGlow")',
)
STATUS_DRAW_MARKER = 'callproperty QName(Namespace("pinball.scene.battle.battle.hud:HudMemberStatusPeek"),"getCharacterImageAssetPath"), 0'


def _transform_status_draw(block: str) -> str:
    replacement = "\n".join(
        (
            _code(
                "pushnull",
                'astype QName(PackageNamespace("flatomo.animation"),"Animation")',
                "setlocal 11",
                "pushnull",
                'astype QName(PackageNamespace("starling.textures"),"Texture")',
                "setlocal 12",
                'findproperty QName(PackageNamespace(""),"asset")',
                'getproperty QName(PackageNamespace(""),"asset")',
                'findproperty QName(PackageNamespace(""),"status")',
                'getproperty QName(PackageNamespace(""),"status")',
                STATUS_DRAW_MARKER,
                'coerce QName(PackageNamespace(""),"String")',
                'callproperty QName(PackageNamespace(""),"getTexture"), 1',
                'coerce QName(PackageNamespace("starling.textures"),"Texture")',
                "setlocal 12",
                'findproperty QName(PackageNamespace(""),"characterUsual")',
                'getproperty QName(PackageNamespace(""),"characterUsual")',
                'getproperty QName(PackageNamespace(""),"texture")',
                "getlocal 12",
                "ifstricteq ofs7a50",
                'findproperty QName(PackageNamespace(""),"characterUsual")',
                'getproperty QName(PackageNamespace(""),"characterUsual")',
                "getlocal 12",
                'setproperty QName(PackageNamespace(""),"texture")',
            ),
            _label("ofs7a50"),
            _code('findproperty QName(PackageNamespace(""),"healthPointGaugeGlow")'),
        )
    )
    return block.replace(STATUS_DRAW_ANCHOR, replacement, 1)


CONTROL_GETTER_ANCHOR = _code(
    'findproperty QName(PackageNamespace(""),"character")',
    'getproperty QName(PackageNamespace(""),"character")',
    'getproperty QName(PackageNamespace(""),"controlBoardImagePath")',
    "returnvalue",
)
CONTROL_PATH = 'pushstring "character/seris_dragon_king/ui/battle_control_board_dragon"'


def _transform_control_getter(block: str) -> str:
    member = (
        'findproperty QName(PackageNamespace(""),"member")',
        'getproperty QName(PackageNamespace(""),"member")',
    )
    replacement = "\n".join(
        (
            _dragon_guard(member, "ofs7a60"),
            _code(CONTROL_PATH, "returnvalue"),
            _label("ofs7a60"),
            CONTROL_GETTER_ANCHOR,
        )
    )
    return block.replace(CONTROL_GETTER_ANCHOR, replacement, 1)


CONTROL_DRAW_ANCHOR = _code(
    "getlocal0", "pushscope", 'findproperty QName(PackageNamespace(""),"animationAlive")'
)
CONTROL_DRAW_MARKER = 'callproperty QName(Namespace("pinball.scene.battle.viewInput.processor.flipButton:CharacterSpritePeek"),"getCharacterImagePath"), 0'


def _transform_control_draw(block: str) -> str:
    replacement = "\n".join(
        (
            _code(
                "getlocal0",
                "pushscope",
                "pushnull",
                'astype QName(PackageNamespace("starling.textures"),"Texture")',
                "setlocal 10",
                'findproperty QName(PackageNamespace(""),"asset")',
                'getproperty QName(PackageNamespace(""),"asset")',
                'findproperty QName(PackageNamespace(""),"sprite")',
                'getproperty QName(PackageNamespace(""),"sprite")',
                CONTROL_DRAW_MARKER,
                'coerce QName(PackageNamespace(""),"String")',
                'callproperty QName(PackageNamespace(""),"getTexture"), 1',
                'coerce QName(PackageNamespace("starling.textures"),"Texture")',
                "setlocal 10",
                'findproperty QName(PackageNamespace(""),"foregroundImageAlive")',
                'getproperty QName(PackageNamespace(""),"foregroundImageAlive")',
                'getproperty QName(PackageNamespace(""),"texture")',
                "getlocal 10",
                "ifstricteq ofs7a70",
                'findproperty QName(PackageNamespace(""),"foregroundImageAlive")',
                'getproperty QName(PackageNamespace(""),"foregroundImageAlive")',
                "getlocal 10",
                'setproperty QName(PackageNamespace(""),"texture")',
                'findproperty QName(PackageNamespace(""),"foregroundImageDead")',
                'getproperty QName(PackageNamespace(""),"foregroundImageDead")',
                "getlocal 10",
                'setproperty QName(PackageNamespace(""),"texture")',
            ),
            _label("ofs7a70"),
            _code('findproperty QName(PackageNamespace(""),"animationAlive")'),
        )
    )
    return block.replace(CONTROL_DRAW_ANCHOR, replacement, 1)


VOICE_ANCHOR = "\n".join(
    (
        _label("ofs00db"),
        _code(
            "getlocal 6",
            "iffalse ofs00ea",
            "getlocal3",
            'getproperty QName(PackageNamespace(""),"switchedSkillVoicePaths")',
            "jump ofs00ef",
        ),
        _label("ofs00ea"),
        _code("getlocal3", 'getproperty QName(PackageNamespace(""),"skillVoicePaths")'),
        _label("ofs00ef"),
        _code('coerce QName(PackageNamespace(""),"Array")', "setlocal 8"),
    )
)
VOICE_MARKER = 'pushstring "seris_dragon_king"'


def _transform_voice(block: str) -> str:
    replacement = "\n".join(
        (
            _label("ofs00db"),
            _code(
                "getlocal3",
                'getproperty QName(PackageNamespace(""),"characterTags")',
                'pushstring "ModDualForm"',
                'callproperty QName(Namespace("http://adobe.com/AS3/2006/builtin"),"indexOf"), 1',
                "convert_i",
                "pushbyte -1",
                "ifeq ofs7a80",
                "getlocal3",
                'getproperty QName(PackageNamespace(""),"mainCharacterStringId")',
                VOICE_MARKER,
                "ifne ofs7a80",
                "getlocal3",
                'getproperty QName(PackageNamespace(""),"skillVoicePaths")',
                "getlocal 6",
                "convert_i",
                'getproperty MultinameL([PackageNamespace("","1")])',
                'coerce QName(PackageNamespace(""),"String")',
                "newarray 1",
                "jump ofs00ef",
            ),
            _label("ofs7a80"),
            _code(
                "getlocal 6",
                "iffalse ofs00ea",
                "getlocal3",
                'getproperty QName(PackageNamespace(""),"switchedSkillVoicePaths")',
                "jump ofs00ef",
            ),
            _label("ofs00ea"),
            _code("getlocal3", 'getproperty QName(PackageNamespace(""),"skillVoicePaths")'),
            _label("ofs00ef"),
            _code('coerce QName(PackageNamespace(""),"Array")', "setlocal 8"),
        )
    )
    return block.replace(VOICE_ANCHOR, replacement, 1)


def _semantic_specifications() -> tuple[_PatchSpec, ...]:
    return (
        _PatchSpec(
            "preload_seris_dual_form_assets",
            "pinball.common.data.character.BattleCharacterLogic",
            "pinball.common.data.character:BattleCharacterLogic/resolvePathCollection",
            PRELOAD_ANCHOR,
            1,
            PRELOAD_MARKER,
            ("ofs7a10",),
            7,
            8,
            _transform_preload,
            (
                'callproperty QName(PackageNamespace(""),"get_stringId"), 0',
                f'pushstring "{SERIS_ID}"',
                "ifne ofs7a10",
                PRELOAD_MARKER,
                'pushstring "character/seris_dragon_king/ui/skill_cutin_dragon"',
                'pushstring "character/seris_dragon_king/ui/battle_control_board_dragon"',
                'pushstring "character/seris_dragon_king/ui/battle_member_status_dragon"',
                "ofs7a10:",
            ),
        ),
        _PatchSpec(
            "switch_special_pixel_slot_preserve_frame_scale",
            "pinball.scene.battle.battle.squad.member.MemberView",
            "pinball.scene.battle.battle.squad.member:MemberView/draw",
            SWAP_ANCHOR,
            1,
            SWAP_MARKER,
            ("ofs7fc0", "ofs7fd0", "ofs7fe0"),
            4,
            25,
            _transform_swap,
            (
                SWAP_MARKER,
                "ifeq ofs7fe0",
                f'pushstring "{SERIS_ID}"',
                "ifne ofs7fe0",
                "pushbyte 22",
                "iffalse ofs7fc0",
                'pushstring "character/"',
                'pushstring "/pixelart/special"',
                "jump ofs7fd0",
                "ofs7fc0:",
                "ofs7fd0:",
                "ifeq ofs7fe0",
                'callproperty QName(PackageNamespace(""),"getAnimation"), 1',
                "iffalse ofs7fe0",
                "pushbyte 21",
                'callpropvoid QName(PackageNamespace(""),"removeChild"), 2',
                'callpropvoid QName(PackageNamespace(""),"addChild"), 1',
                "ofs7fe0:",
            ),
        ),
        _PatchSpec(
            "default_seris_human_power_flip",
            "pinball.common.data.character.BattleCharacterLogic",
            "pinball.common.data.character:BattleCharacterLogic/getPowerFlipAction",
            PF_ANCHOR,
            1,
            PF_MARKER,
            ("ofs7a20", "ofs7a21"),
            4,
            1,
            _transform_pf,
            (
                'callproperty QName(PackageNamespace(""),"get_stringId"), 0',
                f'pushstring "{SERIS_ID}"',
                "ifne ofs7a20",
                PF_MARKER,
                "jump ofs7a21",
                "ofs7a20:",
                'getlex QName(PackageNamespace(""),"powerFlipActionId")',
                "ofs7a21:",
                'findpropstrict QName(PackageNamespace(""),"get_element")',
            ),
        ),
        _PatchSpec(
            "dynamic_seris_skill_cutin",
            "pinball.scene.battle.battle.squad.member.MemberImpl",
            "pinball.scene.battle.battle.squad.member:MemberImpl/invokeActionSkillIfPossible",
            CUTIN_ANCHOR,
            2,
            CUTIN_MARKER,
            ("ofs7a30",),
            29,
            26,
            _transform_cutin,
            (
                'getproperty QName(PackageNamespace(""),"skillCutinImagePath")',
                'pushstring "ModDualForm"',
                "ifeq ofs7a30",
                f'pushstring "{SERIS_ID}"',
                "ifne ofs7a30",
                "pushbyte 22",
                "iffalse ofs7a30",
                CUTIN_MARKER,
                "setlocal 25",
                "ofs7a30:",
                'getproperty QName(PackageNamespace(""),"assistCharacter")',
                "iffalse ofs03b5",
                "getlocal 25",
                "ofs03b5:",
                "getlocal 25",
            ),
        ),
        _PatchSpec(
            "dynamic_seris_member_status_path",
            "pinball.scene.battle.battle.hud.HudMemberStatus",
            "pinball.scene.battle.battle.hud:HudMemberStatus/getCharacterImageAssetPath",
            STATUS_GETTER_ANCHOR,
            1,
            STATUS_PATH,
            ("ofs7a40",),
            4,
            1,
            _transform_status_getter,
            (
                'pushstring "ModDualForm"',
                "ifeq ofs7a40",
                f'pushstring "{SERIS_ID}"',
                "ifne ofs7a40",
                "pushbyte 22",
                "iffalse ofs7a40",
                STATUS_PATH,
                "returnvalue",
                "ofs7a40:",
                'getproperty QName(PackageNamespace(""),"memberStatusImagePath")',
                "returnvalue",
            ),
        ),
        _PatchSpec(
            "refresh_seris_member_status_texture",
            "pinball.scene.battle.battle.hud.HudMemberStatusView",
            "pinball.scene.battle.battle.hud:HudMemberStatusView/draw",
            STATUS_DRAW_ANCHOR,
            1,
            STATUS_DRAW_MARKER,
            ("ofs7a50",),
            5,
            13,
            _transform_status_draw,
            (
                STATUS_DRAW_MARKER,
                'callproperty QName(PackageNamespace(""),"getTexture"), 1',
                'getproperty QName(PackageNamespace(""),"characterUsual")',
                "ifstricteq ofs7a50",
                'setproperty QName(PackageNamespace(""),"texture")',
                "ofs7a50:",
                'findproperty QName(PackageNamespace(""),"healthPointGaugeGlow")',
            ),
        ),
        _PatchSpec(
            "dynamic_seris_control_board_path",
            "pinball.scene.battle.viewInput.processor.flipButton.CharacterSprite",
            "pinball.scene.battle.viewInput.processor.flipButton:CharacterSprite/getCharacterImagePath",
            CONTROL_GETTER_ANCHOR,
            1,
            CONTROL_PATH,
            ("ofs7a60",),
            4,
            1,
            _transform_control_getter,
            (
                'pushstring "ModDualForm"',
                "ifeq ofs7a60",
                f'pushstring "{SERIS_ID}"',
                "ifne ofs7a60",
                "pushbyte 22",
                "iffalse ofs7a60",
                CONTROL_PATH,
                "returnvalue",
                "ofs7a60:",
                'getproperty QName(PackageNamespace(""),"controlBoardImagePath")',
                "returnvalue",
            ),
        ),
        _PatchSpec(
            "refresh_seris_control_board_texture",
            "pinball.scene.battle.viewInput.processor.flipButton.CharacterSpriteView",
            "pinball.scene.battle.viewInput.processor.flipButton:CharacterSpriteView/draw",
            CONTROL_DRAW_ANCHOR,
            1,
            CONTROL_DRAW_MARKER,
            ("ofs7a70",),
            4,
            11,
            _transform_control_draw,
            (
                CONTROL_DRAW_MARKER,
                'callproperty QName(PackageNamespace(""),"getTexture"), 1',
                'getproperty QName(PackageNamespace(""),"foregroundImageAlive")',
                "ifstricteq ofs7a70",
                'setproperty QName(PackageNamespace(""),"texture")',
                'getproperty QName(PackageNamespace(""),"foregroundImageDead")',
                'setproperty QName(PackageNamespace(""),"texture")',
                "ofs7a70:",
                'findproperty QName(PackageNamespace(""),"animationAlive")',
            ),
        ),
        _PatchSpec(
            "route_seris_skill_voice_by_form",
            "pinball.scene.battle.battle.squad.SquadManagerImpl",
            "pinball.scene.battle.battle.squad:SquadManagerImpl/invokeActionSkill",
            VOICE_ANCHOR,
            1,
            VOICE_MARKER,
            ("ofs7a80",),
            29,
            48,
            _transform_voice,
            (
                'pushstring "ModDualForm"',
                "ifeq ofs7a80",
                VOICE_MARKER,
                "ifne ofs7a80",
                'getproperty QName(PackageNamespace(""),"skillVoicePaths")',
                'getproperty MultinameL([PackageNamespace("","1")])',
                "newarray 1",
                "jump ofs00ef",
                "ofs7a80:",
                "iffalse ofs00ea",
                'getproperty QName(PackageNamespace(""),"switchedSkillVoicePaths")',
                "jump ofs00ef",
                "ofs00ea:",
                'getproperty QName(PackageNamespace(""),"skillVoicePaths")',
                "ofs00ef:",
                "setlocal 8",
            ),
        ),
    )


_PATCH_SPECS = MappingProxyType(
    {spec.site_id: spec for spec in _semantic_specifications()}
)

_CRITICAL_INSTRUCTION_COUNTS = MappingProxyType(
    {
        "preload_seris_dual_form_assets": MappingProxyType(
            {
                PRELOAD_MARKER: 1,
                'pushstring "character/seris_dragon_king/ui/skill_cutin_dragon"': 1,
                'pushstring "character/seris_dragon_king/ui/battle_control_board_dragon"': 1,
                'pushstring "character/seris_dragon_king/ui/battle_member_status_dragon"': 1,
                'callpropvoid QName(Namespace("pinball.asset.logic:IAssetPathCollectionBuilder"),"addImage"), 1': 3,
            }
        ),
        "switch_special_pixel_slot_preserve_frame_scale": MappingProxyType(
            {
                SWAP_MARKER: 1,
                f'pushstring "{SERIS_ID}"': 1,
                "pushbyte 22": 1,
                'pushstring "/pixelart/special"': 1,
                'callproperty QName(PackageNamespace(""),"getAnimation"), 1': 1,
                'callpropvoid QName(PackageNamespace(""),"removeChild"), 2': 1,
                'callpropvoid QName(PackageNamespace(""),"addChild"), 1': 1,
            }
        ),
        "default_seris_human_power_flip": MappingProxyType(
            {
                PF_MARKER: 1,
                f'pushstring "{SERIS_ID}"': 1,
                'getlex QName(PackageNamespace(""),"powerFlipActionId")': 1,
                'findpropstrict QName(PackageNamespace(""),"get_element")': 1,
            }
        ),
        "dynamic_seris_skill_cutin": MappingProxyType(
            {
                CUTIN_MARKER: 1,
                f'pushstring "{SERIS_ID}"': 1,
                "pushbyte 22": 1,
                'getproperty QName(PackageNamespace(""),"assistCharacter")': 1,
                'getproperty QName(PackageNamespace(""),"skillCutinImagePath")': 1,
                "getlocal 25": 2,
            }
        ),
        "dynamic_seris_member_status_path": MappingProxyType(
            {
                STATUS_PATH: 1,
                f'pushstring "{SERIS_ID}"': 1,
                "pushbyte 22": 1,
                'getproperty QName(PackageNamespace(""),"memberStatusImagePath")': 1,
            }
        ),
        "refresh_seris_member_status_texture": MappingProxyType(
            {
                STATUS_DRAW_MARKER: 1,
                'callproperty QName(PackageNamespace(""),"getTexture"), 1': 1,
                'setproperty QName(PackageNamespace(""),"texture")': 1,
            }
        ),
        "dynamic_seris_control_board_path": MappingProxyType(
            {
                CONTROL_PATH: 1,
                f'pushstring "{SERIS_ID}"': 1,
                "pushbyte 22": 1,
                'getproperty QName(PackageNamespace(""),"controlBoardImagePath")': 1,
            }
        ),
        "refresh_seris_control_board_texture": MappingProxyType(
            {
                CONTROL_DRAW_MARKER: 1,
                'callproperty QName(PackageNamespace(""),"getTexture"), 1': 1,
                'getproperty QName(PackageNamespace(""),"foregroundImageDead")': 1,
                'setproperty QName(PackageNamespace(""),"texture")': 2,
            }
        ),
        "route_seris_skill_voice_by_form": MappingProxyType(
            {
                VOICE_MARKER: 1,
                'pushstring "ModDualForm"': 1,
                'getproperty QName(PackageNamespace(""),"switchedSkillVoicePaths")': 1,
                'getproperty QName(PackageNamespace(""),"skillVoicePaths")': 2,
                'getproperty MultinameL([PackageNamespace("","1")])': 1,
            }
        ),
    }
)


def _match_semantic_token(
    actual: str,
    expected: str,
    bindings: Mapping[str, str],
) -> Mapping[str, str] | None:
    expected_labels = list(OFFSET_LABEL.finditer(expected))
    if not expected_labels:
        return {} if actual == expected else None
    pattern_parts = []
    cursor = 0
    symbols = []
    for index, match in enumerate(expected_labels):
        pattern_parts.append(re.escape(expected[cursor : match.start()]))
        pattern_parts.append(rf"(?P<label_{index}>ofs[0-9A-Fa-f]+)")
        symbols.append(match.group(0).lower())
        cursor = match.end()
    pattern_parts.append(re.escape(expected[cursor:]))
    matched = re.fullmatch("".join(pattern_parts), actual)
    if matched is None:
        return None
    updates: dict[str, str] = {}
    for index, symbol in enumerate(symbols):
        actual_label = matched.group(f"label_{index}").lower()
        bound = updates.get(symbol, bindings.get(symbol))
        if bound is not None and bound != actual_label:
            return None
        if any(
            other_symbol != symbol and other_label == actual_label
            for other_symbol, other_label in (*bindings.items(), *updates.items())
        ):
            return None
        updates[symbol] = actual_label
    return updates


def _semantic_region(spec: _PatchSpec, text: str) -> tuple[str, Mapping[str, str]]:
    """Return the exact inserted semantic span, anchored at the unique marker."""
    lines = text.splitlines()
    marker_lines = [
        index for index, line in enumerate(lines) if line.strip() == spec.marker
    ]
    if len(marker_lines) != 1:
        raise SerisPatchError(
            f"{spec.site_id}: semantic marker count {len(marker_lines)}; expected 1"
        )
    marker_tokens = [
        index for index, token in enumerate(spec.semantic_tokens) if token == spec.marker
    ]
    if len(marker_tokens) != 1:
        raise SerisPatchError(f"{spec.site_id}: invalid semantic marker contract")

    selected = [0] * len(spec.semantic_tokens)
    label_bindings: dict[str, str] = {}
    pivot = marker_tokens[0]
    selected[pivot] = marker_lines[0]
    cursor = marker_lines[0]
    for token_index in range(pivot - 1, -1, -1):
        token = spec.semantic_tokens[token_index]
        match = None
        updates: Mapping[str, str] = {}
        for line_index in range(cursor - 1, -1, -1):
            candidate = _match_semantic_token(
                lines[line_index].strip(), token, label_bindings
            )
            if candidate is not None:
                match = line_index
                updates = candidate
                break
        if match is None:
            raise SerisPatchError(
                f"{spec.site_id}: missing semantic instruction {token!r} before marker"
            )
        label_bindings.update(updates)
        selected[token_index] = match
        cursor = match

    cursor = marker_lines[0]
    for token_index in range(pivot + 1, len(spec.semantic_tokens)):
        token = spec.semantic_tokens[token_index]
        match = None
        updates = {}
        for line_index in range(cursor + 1, len(lines)):
            candidate = _match_semantic_token(
                lines[line_index].strip(), token, label_bindings
            )
            if candidate is not None:
                match = line_index
                updates = candidate
                break
        if match is None:
            raise SerisPatchError(
                f"{spec.site_id}: missing semantic instruction {token!r} after marker"
            )
        label_bindings.update(updates)
        selected[token_index] = match
        cursor = match

    return (
        "\n".join(lines[selected[0] : selected[-1] + 1]) + "\n",
        MappingProxyType(dict(label_bindings)),
    )


def _verify_spec(spec: _PatchSpec, text: str) -> None:
    _require_instruction(text, spec.marker)
    if _declaration(text, "maxstack") < spec.required_maxstack:
        raise SerisPatchError(f"{spec.site_id}: maxstack is below required minimum")
    if _declaration(text, "localcount") < spec.required_localcount:
        raise SerisPatchError(f"{spec.site_id}: localcount is below required minimum")
    canonical_pcode(text)
    region, label_bindings = _semantic_region(spec, text)
    for instruction, expected_count in _CRITICAL_INSTRUCTION_COUNTS[
        spec.site_id
    ].items():
        _require_instruction(region, instruction, expected_count)
    for label in spec.new_labels:
        actual_label = label_bindings.get(label.lower())
        if actual_label is None:
            raise SerisPatchError(
                f"{spec.site_id}: semantic label {label} is not bound"
            )
        if len(re.findall(rf"(?m)^\s*{re.escape(actual_label)}:\s*$", text)) != 1:
            raise SerisPatchError(
                f"{spec.site_id}: rebound label {actual_label} is not unique"
            )
    if spec.site_id == "switch_special_pixel_slot_preserve_frame_scale":
        for forbidden in ("SCALE_RENDERER", 'initproperty QName(PackageNamespace(""),"scaleX")', 'initproperty QName(PackageNamespace(""),"scaleY")'):
            if forbidden in text:
                raise SerisPatchError(f"{spec.site_id}: forbidden scale override {forbidden}")
        _require_instruction(region, 'pushstring "seris_dragon_king"')
        _require_instruction(region, "pushbyte 22")
        _require_instruction(region, 'pushstring "/pixelart/special"')
    elif spec.site_id == "dynamic_seris_skill_cutin":
        _require_instruction(region, "getlocal 25", 2)
        _require_instruction(region, 'getproperty QName(PackageNamespace(""),"assistCharacter")')
    elif spec.site_id == "refresh_seris_control_board_texture":
        _require_instruction(region, 'setproperty QName(PackageNamespace(""),"texture")', 2)
    elif spec.site_id == "route_seris_skill_voice_by_form":
        _require_instruction(region, 'getproperty QName(PackageNamespace(""),"switchedSkillVoicePaths")')
        _require_instruction(region, 'getproperty MultinameL([PackageNamespace("","1")])')


def _apply_spec(spec: _PatchSpec, block: str) -> str:
    text = str(block)
    if _instruction_count(text, spec.marker):
        raise SerisPatchError(f"{spec.site_id}: patch marker already present")
    count = text.count(spec.before_anchor)
    if count != spec.expected_anchor_count:
        raise SerisPatchError(
            f"{spec.site_id}: anchor count {count}; expected {spec.expected_anchor_count}"
        )
    for label in spec.new_labels:
        if re.search(rf"\b{re.escape(label)}\b", text):
            raise SerisPatchError(f"{spec.site_id}: new label collision: {label}")
    if spec.site_id == "dynamic_seris_skill_cutin" and text.count(CUTIN_INSERT) != 1:
        raise SerisPatchError("dynamic_seris_skill_cutin: assist insertion anchor count mismatch")
    result = spec.transform(text)
    result = _raise_declaration(result, "maxstack", spec.required_maxstack)
    result = _raise_declaration(result, "localcount", spec.required_localcount)
    if not result.endswith("\n"):
        result += "\n"
    _verify_spec(spec, result)
    return result


def _patch_for(spec: _PatchSpec) -> SerisPatch:
    return SerisPatch(
        site_id=spec.site_id,
        class_name=spec.class_name,
        method_name=spec.method_name,
        apply=lambda block, selected=spec: _apply_spec(selected, block),
        verify=lambda block, selected=spec: _verify_spec(selected, block),
    )


PATCHES = tuple(_patch_for(spec) for spec in _semantic_specifications())
PATCH_BY_ID = MappingProxyType({patch.site_id: patch for patch in PATCHES})

ASSET_LOGICALS = (
    "character/seris_dragon_king/pixelart/special",
    "character/seris_dragon_king/ui/skill_cutin_dragon",
    "character/seris_dragon_king/ui/battle_control_board_dragon",
    "character/seris_dragon_king/ui/battle_member_status_dragon",
)


def extract_asset_logicals(
    patches: Sequence[SerisPatch] = PATCHES,
) -> tuple[str, ...]:
    if tuple(patch.site_id for patch in patches) != tuple(PATCH_BY_ID):
        raise SerisPatchError("Seris patch sequence does not match the release contract")
    return ASSET_LOGICALS


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


def _site_locks(lock: Mapping[str, Any]) -> Mapping[str, Mapping[str, str]]:
    if not isinstance(lock, Mapping):
        raise SerisPatchError("Seris lock must be a mapping")
    if lock.get("schema_version") != 4 or lock.get("status") != "accepted":
        raise SerisPatchError("Seris lock must be accepted schema 4")
    if lock.get("stage") != "post-abyss":
        raise SerisPatchError("Seris lock stage must be post-abyss")
    expected = tuple(patch.site_id for patch in PATCHES)
    if tuple(lock.get("site_ids", ())) != expected:
        raise SerisPatchError("Seris lock site order mismatch")
    sites = lock.get("sites")
    if (
        not isinstance(sites, Mapping)
        or len(sites) != len(expected)
        or set(sites) != set(expected)
    ):
        raise SerisPatchError("Seris lock site mapping mismatch")
    for patch in PATCHES:
        entry = sites.get(patch.site_id)
        if not isinstance(entry, Mapping):
            raise SerisPatchError(f"missing Seris lock site {patch.site_id}")
        if entry.get("class_name") != patch.class_name or entry.get("method_name") != patch.method_name:
            raise SerisPatchError(f"Seris lock identity mismatch for {patch.site_id}")
        for field in (
            "before_pcode_sha256",
            "after_pcode_sha256",
            "before_abc_sha256",
            "after_abc_sha256",
        ):
            if LOWER_SHA256.fullmatch(str(entry.get(field, ""))) is None:
                raise SerisPatchError(f"invalid {field} for {patch.site_id}")
        if entry["before_pcode_sha256"] == entry["after_pcode_sha256"]:
            raise SerisPatchError(f"unchanged Seris lock site {patch.site_id}")
        if entry["before_abc_sha256"] == entry["after_abc_sha256"]:
            raise SerisPatchError(f"unchanged Seris ABC lock site {patch.site_id}")
    return sites


def _subprocess_runner(command, *, cwd: Path, env: Mapping[str, str], timeout: int):
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
        raise SerisPatchError(
            f"FFDec command failed ({completed.returncode}): "
            f"{completed.stderr[-1000:]}"
        )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _run(command, *, cwd: Path, profile_dir: Path, runner, timeout: int) -> None:
    environment = os.environ.copy()
    environment["APPDATA"] = str(profile_dir.resolve())
    result = runner(command, cwd=cwd, env=environment, timeout=timeout)
    if isinstance(result, Mapping) and int(result.get("returncode", 0)) != 0:
        raise SerisPatchError(f"FFDec command failed: {result.get('returncode')}")


def _export_classes(
    swf: Path,
    export_root: Path,
    classes: Sequence[str],
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
            ",".join(dict.fromkeys(classes)),
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


def _read_exported_method(export_root: Path, patch: SerisPatch) -> str:
    source = export_root / "scripts" / Path(*patch.class_name.split(".")).with_suffix(".pcode")
    if not source.is_file():
        raise SerisPatchError(f"missing exported P-code for {patch.class_name}")
    try:
        text = source.read_text(encoding="utf-8")
        return textwrap.dedent(
            PCODE_TOOLS.extract_method_block(
                text,
                trait_kind="method",
                trait_name=patch.method_name.rsplit("/", 1)[-1],
            )
        )
    except (OSError, PCODE_TOOLS.PcodePatchError) as exc:
        raise SerisPatchError(str(exc)) from exc


def _replace_one(
    source: Path,
    destination: Path,
    patch: SerisPatch,
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
            patch.class_name,
            str(replacement),
            str(body_index),
        ],
        cwd=cwd,
        profile_dir=profile_dir,
        runner=runner,
        timeout=timeout,
    )
    if not destination.is_file():
        raise SerisPatchError(f"FFDec did not create stage for {patch.site_id}")


def _verify_methods(
    swf: Path,
    patches: Sequence[SerisPatch],
    sites: Mapping[str, Mapping[str, str]],
    *,
    export_root: Path,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    cwd: Path,
    runner,
    timeout: int,
) -> dict[str, str]:
    index = ABC_METHODS.index_swf_methods(swf)
    refs = {}
    for patch in patches:
        refs[patch.site_id] = index.require_ref(patch.method_name)
    _export_classes(
        swf,
        export_root,
        [patch.class_name for patch in patches],
        ffdec=ffdec,
        java=java,
        profile_dir=profile_dir,
        cwd=cwd,
        runner=runner,
        timeout=timeout,
    )
    hashes: dict[str, str] = {}
    for patch in patches:
        raw_hash = _sha256_abc(refs[patch.site_id].code)
        if raw_hash != sites[patch.site_id]["after_abc_sha256"]:
            raise SerisPatchError(f"reopen ABC hash mismatch for {patch.site_id}")
        block = _read_exported_method(export_root, patch)
        patch.verify(block)
        actual = _sha256_pcode(block)
        expected = sites[patch.site_id]["after_pcode_sha256"]
        if actual != expected:
            raise SerisPatchError(f"reopen hash mismatch for {patch.site_id}")
        hashes[patch.site_id] = actual
    return hashes


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
        raise SerisPatchError("source and output SWF must differ")
    if not source.is_file():
        raise SerisPatchError(f"source SWF is missing: {source}")
    if os.path.lexists(output):
        try:
            if os.path.samefile(source, output):
                raise SerisPatchError("source and output SWF are filesystem aliases")
        except OSError:
            pass
        raise SerisPatchError(f"output SWF already exists: {output}")
    for label, directory in (("work", work), ("profile", profile)):
        try:
            directory.relative_to(output)
        except ValueError:
            continue
        raise SerisPatchError(
            f"output SWF cannot equal or contain the {label} directory"
        )
    for label, path in (("FFDec", ffdec_path), ("Java", java_path)):
        if not path.is_file():
            raise SerisPatchError(f"{label} tool is missing: {path}")
    for label, directory in (("work", work), ("profile", profile)):
        if directory.exists() and not directory.is_dir():
            raise SerisPatchError(f"{label} path is not a directory: {directory}")
    output.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    profile.mkdir(parents=True, exist_ok=True)
    return source, output, ffdec_path, java_path, work, profile


def _copy_snapshot(source: Path, destination: Path) -> None:
    with source.open("rb") as input_handle, destination.open("xb") as output_handle:
        shutil.copyfileobj(input_handle, output_handle, 1024 * 1024)
        output_handle.flush()
        os.fsync(output_handle.fileno())


def _assert_source_hash(source: Path, expected: str) -> None:
    try:
        actual = _sha256_file(source)
    except OSError as exc:
        raise SerisPatchError("source SWF became unreadable during Seris stage") from exc
    if not hmac.compare_digest(actual, expected):
        raise SerisPatchError("source SWF changed during Seris stage")


def _require_handle_bound_publish_support() -> None:
    try:
        PUBLISH_TOOLS._require_handle_bound_publish_support()
    except PUBLISH_TOOLS.BuildError as exc:
        raise SerisPatchError(str(exc)) from exc


def _stage_output_sibling(source: Path, destination: Path, expected_hash: str):
    try:
        return PUBLISH_TOOLS._stage_output_sibling(source, destination, expected_hash)
    except PUBLISH_TOOLS.BuildError as exc:
        raise SerisPatchError(str(exc)) from exc


def _publish_staged_exclusive(staging, destination: Path, expected_hash: str) -> None:
    try:
        PUBLISH_TOOLS._publish_staged_exclusive(staging, destination, expected_hash)
    except PUBLISH_TOOLS.BuildError as exc:
        raise SerisPatchError(str(exc)) from exc


def _cleanup_owned_staging(staging) -> None:
    try:
        PUBLISH_TOOLS._cleanup_owned_staging(staging)
    except PUBLISH_TOOLS.BuildError as exc:
        raise SerisPatchError(str(exc)) from exc


def _clean_transaction_before_publish(transaction: Path) -> None:
    try:
        PUBLISH_TOOLS._clean_transaction_before_publish(transaction)
    except PUBLISH_TOOLS.BuildError as exc:
        raise SerisPatchError(str(exc)) from exc


def apply_seris_phase4(
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
) -> SerisPatchReport:
    _require_handle_bound_publish_support()
    sites = _site_locks(lock)
    source, output, ffdec_path, java_path, work, profile = _validate_stage_paths(
        source_swf, output_swf, ffdec, java, work_dir, profile_dir
    )
    source_sha = _sha256_file(source)
    before_hashes: dict[str, str] = {}
    after_hashes: dict[str, str] = {}
    transaction: Path | None = None
    staged_output = None
    original_error: BaseException | None = None
    try:
        transaction = Path(
            tempfile.mkdtemp(prefix=".seris-phase4-", dir=work)
        ).resolve()
        snapshot = transaction / "source.swf"
        _copy_snapshot(source, snapshot)
        if not hmac.compare_digest(_sha256_file(snapshot), source_sha):
            raise SerisPatchError("source SWF changed while creating stage snapshot")
        _assert_source_hash(source, source_sha)
        current = snapshot
        for sequence, patch in enumerate(PATCHES, start=1):
            index = ABC_METHODS.index_swf_methods(current)
            ref = index.require_ref(patch.method_name)
            before_abc = _sha256_abc(ref.code)
            if before_abc != sites[patch.site_id]["before_abc_sha256"]:
                raise SerisPatchError(f"before ABC hash mismatch for {patch.site_id}")
            export_root = transaction / f"{sequence:02d}-before-export"
            _export_classes(
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
            _assert_source_hash(source, source_sha)
            before = _read_exported_method(export_root, patch)
            before_sha = _sha256_pcode(before)
            if before_sha != sites[patch.site_id]["before_pcode_sha256"]:
                raise SerisPatchError(f"before hash mismatch for {patch.site_id}")
            before_hashes[patch.site_id] = before_sha
            after = patch.apply(before)
            after_sha = _sha256_pcode(after)
            if after_sha != sites[patch.site_id]["after_pcode_sha256"]:
                raise SerisPatchError(f"after hash mismatch for {patch.site_id}")
            replacement = transaction / f"{sequence:02d}-{patch.site_id}.pcode"
            replacement.write_text(after, encoding="utf-8", newline="\n")
            staged = transaction / f"{sequence:02d}-{patch.site_id}.swf"
            _replace_one(
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
            _assert_source_hash(source, source_sha)
            reopened = _verify_methods(
                staged,
                PATCHES[:sequence],
                sites,
                export_root=transaction / f"{sequence:02d}-reopen-export",
                ffdec=ffdec_path,
                java=java_path,
                profile_dir=profile,
                cwd=transaction,
                runner=runner,
                timeout=timeout,
            )
            _assert_source_hash(source, source_sha)
            after_hashes.update(reopened)
            current = staged

        output_sha = _sha256_file(current)
        _assert_source_hash(source, source_sha)
        staged_output = _stage_output_sibling(current, output, output_sha)
        report = SerisPatchReport(
            output_path=output,
            input_sha256=source_sha,
            output_sha256=output_sha,
            site_ids=tuple(patch.site_id for patch in PATCHES),
            before_hashes=MappingProxyType(dict(before_hashes)),
            after_hashes=MappingProxyType(dict(after_hashes)),
            asset_logicals=extract_asset_logicals(),
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
                    raise SerisPatchError(
                        "failed to clean Seris stage transaction"
                    ) from cleanup_error
                original_error.add_note(
                    "failed to clean Seris stage transaction: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )
        if staged_output is not None:
            try:
                _cleanup_owned_staging(staged_output)
            except BaseException as cleanup_error:
                if original_error is None:
                    if isinstance(cleanup_error, SerisPatchError):
                        raise
                    raise SerisPatchError(
                        "failed to clean staged Seris output"
                    ) from cleanup_error
                original_error.add_note(
                    "failed to clean staged Seris output: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )


def verify_seris_phase4(
    output_swf: Path,
    lock: Mapping[str, Any],
    *,
    ffdec: Path,
    java: Path,
    profile_dir: Path,
    work_dir: Path,
    runner=_subprocess_runner,
    timeout: int = 240,
) -> SerisPatchReport:
    sites = _site_locks(lock)
    output = Path(output_swf).resolve()
    ffdec_path = Path(ffdec).resolve()
    java_path = Path(java).resolve()
    work = Path(work_dir).resolve()
    profile = Path(profile_dir).resolve()
    if not output.is_file() or not ffdec_path.is_file() or not java_path.is_file():
        raise SerisPatchError("Seris verification input or tool is missing")
    work.mkdir(parents=True, exist_ok=True)
    profile.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".seris-verify-", dir=work) as temporary:
        after = _verify_methods(
            output,
            PATCHES,
            sites,
            export_root=Path(temporary) / "reopen-export",
            ffdec=ffdec_path,
            java=java_path,
            profile_dir=profile,
            cwd=Path(temporary),
            runner=runner,
            timeout=timeout,
        )
    digest = _sha256_file(output)
    return SerisPatchReport(
        output_path=output,
        input_sha256=digest,
        output_sha256=digest,
        site_ids=tuple(patch.site_id for patch in PATCHES),
        before_hashes=MappingProxyType(
            {site_id: entry["before_pcode_sha256"] for site_id, entry in sites.items()}
        ),
        after_hashes=MappingProxyType(after),
        asset_logicals=extract_asset_logicals(),
        verified=True,
    )


def _load_lock_discovery_module():
    name = "offline_seris_lock_discovery_for_phase4"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = HERE / "lock_discovery.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SerisPatchError(f"cannot load lock discovery module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def discover_lock_candidate(*args, **kwargs):
    return _load_lock_discovery_module().discover_lock_candidate(*args, **kwargs)


def accept_lock_candidate(*args, **kwargs):
    return _load_lock_discovery_module().accept_lock_candidate(*args, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    verify = subparsers.add_parser("verify-lock")
    verify.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        lock_module = _load_lock_discovery_module()
        value = lock_module._load_json_strict(args.lock)
        lock_module.validate_lock_document(value, expected_status="accepted")
        print(
            json.dumps(
                {
                    "asset_logicals": list(extract_asset_logicals()),
                    "site_count": len(PATCHES),
                    "verified": True,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except Exception as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
