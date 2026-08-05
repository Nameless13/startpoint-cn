# -*- coding: utf-8 -*-
"""发布前「键不许消失」闸门。

回归的是两次真事故:
  · 1.4.278 整表发布共享表,顶掉只在设备上的基诺维 169999 -> 进主城 C8601;
  · 杰拉德包的 power_flip_action 只有 7 键而 live 有 10 键,发布即删三个 PF 键。
两次都是「打包前没比过键集合」。
"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wf_mod_tool as core  # noqa: E402
import wf_publish_guard as guard  # noqa: E402


def _orderedmap(rows: dict[str, bytes]) -> bytes:
    """造一个最小 orderedmap,键顺序即插入顺序。"""
    ordered = core.OrderedMap("t", list(rows), list(rows.values()), None)
    return core.build_orderedmap_raw_rows(ordered)


def _zip_with(tmp: Path, name: str, relative: str, payload: bytes) -> Path:
    path = tmp / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("production/upload/" + relative, payload)
    return path


class PublishGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.diff = self.tmp / "archive-common-diff"
        self.full = self.tmp / "archive-common-full"
        self.diff.mkdir()
        self.full.mkdir()
        self.relative = "ab/cdef"
        self.chain = _orderedmap({"a": b"1", "b": b"2", "c": b"3"})
        _zip_with(self.diff, "pinball-1.4.1-1.4.2-1-x.zip", self.relative, self.chain)
        self.patches = [
            mock.patch.object(guard, "CDN_COMMON_DIFF", self.diff),
            mock.patch.object(guard, "CDN_COMMON_FULL", self.full),
            mock.patch.object(guard, "protected_keys", lambda: {}),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self) -> None:
        for patch in self.patches:
            patch.stop()

    def _check(self, payload: bytes) -> list[str]:
        return guard.check([(self.relative, payload)], verbose=False)

    def test_unchanged_passes(self) -> None:
        self.assertEqual(self._check(self.chain), [])

    def test_added_key_passes(self) -> None:
        """新增键正是发布的目的,不能拦。"""
        grown = _orderedmap({"a": b"1", "b": b"2", "c": b"3", "d": b"4"})
        self.assertEqual(self._check(grown), [])

    def test_changed_row_passes(self) -> None:
        """改行内容(键集合不变)放行 —— 暗龙那种改词条就属于这类。"""
        edited = _orderedmap({"a": b"1", "b": b"CHANGED", "c": b"3"})
        self.assertEqual(self._check(edited), [])

    def test_lost_key_blocks(self) -> None:
        """少一个键就必须拦 —— 这就是删角色。"""
        shrunk = _orderedmap({"a": b"1", "c": b"3"})
        problems = self._check(shrunk)
        self.assertTrue(problems, "键消失必须被拦下")
        self.assertIn("丢了 1 个键", problems[0])
        self.assertIn("'b'", problems[0])

    def test_new_file_passes(self) -> None:
        """链上没有的路径 = 纯新增。"""
        self.assertEqual(
            guard.check([("zz/9999", self.chain)], verbose=False), [])

    def test_non_orderedmap_is_skipped(self) -> None:
        """DSL/图片/mp3 解不出键,只能整文件替换,不做键判断。"""
        _zip_with(self.diff, "pinball-1.4.2-1.4.3-1-x.zip", "cd/1234", b"not-a-table")
        self.assertEqual(
            guard.check([("cd/1234", b"still-not-a-table")], verbose=False), [])

    def test_later_edge_wins(self) -> None:
        """同一路径出现在多条边上时,以版本最高的那条为链上现状。"""
        later = _orderedmap({"a": b"1", "b": b"2", "c": b"3", "d": b"4"})
        _zip_with(self.diff, "pinball-1.4.2-1.4.3-1-x.zip", self.relative, later)
        # 回到只有 3 个键 = 相对最新的 1.4.3 丢了 d
        problems = self._check(self.chain)
        self.assertTrue(problems)
        self.assertIn("'d'", problems[0])

    def test_protected_claim_reported(self) -> None:
        """角色包 claims 的行消失时,除了通用报错还要点名。"""
        digest = core.sha1_path("master/skill/power_flip_action.orderedmap")
        relative = f"{digest[:2]}/{digest[2:]}"
        _zip_with(self.diff, "pinball-1.4.3-1.4.4-1-x.zip", relative,
                  _orderedmap({"ginovi_pf": b"1", "special": b"2"}))
        with mock.patch.object(
            guard, "protected_keys",
            lambda: {"master/skill/power_flip_action.orderedmap": {"ginovi_pf"}},
        ):
            problems = guard.check(
                [(relative, _orderedmap({"special": b"2"}))], verbose=False)
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("claims 的行不见了", problems[1])


if __name__ == "__main__":
    unittest.main()
