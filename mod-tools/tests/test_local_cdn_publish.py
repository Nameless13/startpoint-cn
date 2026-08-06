# -*- coding: utf-8 -*-
"""Temporary-root tests for stopped-server multi-root local CDN publication."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from release_inventory_support import InventoryCase

import wf_local_cdn_publish as publisher
import wf_local_scoped_release as adapter
import wf_scoped_release as scoped


class LocalCdnPublishTest(InventoryCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cdn = self.root / ".cdn" / "cn"
        self.directories = {
            root: self.cdn / f"archive-{root}-diff"
            for root in ("common", "medium", "android")
        }
        for directory in self.directories.values():
            directory.mkdir(parents=True)
        self.edge = self.plan()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def plan(self) -> scoped.EdgePlan:
        raw_by_key = {
            (root, f"fixture/{root}.bin"): f"payload-{root}".encode()
            for root in ("common", "medium", "android")
        }
        members = [
            {
                "owner": f"owner-{root}",
                "kind": "file",
                "root": root,
                "logical_path": logical,
                "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            for (root, logical), raw in raw_by_key.items()
        ]
        contract = self.parse(self.payload(members))
        return scoped.build_edge_plan(
            contract,
            {key: None for key in raw_by_key},
            lambda member: raw_by_key[member.key],
            adapter.COMPATIBILITY_SPEC,
        )

    def publish(self, **kwargs):
        return publisher.publish_local_311_edge(
            self.edge,
            self.cdn,
            confirmation=publisher.CONFIRMATION,
            server_probe=lambda: False,
            **kwargs,
        )

    def test_global_sequences_are_not_renumbered_and_parts_use_declared_roots(self):
        result = self.publish()
        self.assertEqual([1, 2, 3], [part.sequence for part in self.edge.parts])
        self.assertEqual(
            [part.name for part in self.edge.parts],
            [path.name for path in result.paths],
        )
        for part, path in zip(self.edge.parts, result.paths, strict=True):
            self.assertEqual(self.directories[part.root], path.parent)
            self.assertEqual(part.blob, path.read_bytes())
        self.assertFalse((self.cdn / publisher.LOCK_NAME).exists())
        self.assertEqual([], list(self.cdn.rglob("*.pending")))

    def test_failure_after_first_visible_archive_rolls_back_every_root(self):
        count = 0

        def fail(phase: str) -> None:
            nonlocal count
            if phase == "after_archive":
                count += 1
                if count == 1:
                    raise RuntimeError("injected multi-root failure")

        with self.assertRaisesRegex(
            publisher.LocalCdnPublishError, "injected multi-root"
        ):
            self.publish(checkpoint=fail)
        self.assertEqual([], list(self.cdn.rglob("*.zip")))
        self.assertEqual([], list(self.cdn.rglob("*.pending")))
        self.assertFalse((self.cdn / publisher.LOCK_NAME).exists())

    def test_same_edge_name_in_the_wrong_root_is_a_hard_collision(self):
        foreign = self.directories["medium"] / self.edge.parts[0].name
        foreign.write_bytes(b"foreign")
        with self.assertRaisesRegex(
            publisher.LocalCdnPublishError, "already exists|collision"
        ):
            self.publish()
        self.assertEqual(b"foreign", foreign.read_bytes())
        self.assertEqual([foreign], list(self.cdn.rglob("*.zip")))
        self.assertFalse((self.cdn / publisher.LOCK_NAME).exists())

    def test_foreign_replacement_before_commit_is_left_with_recovery_lock(self):
        foreign = b"foreign replacement"

        def replace(phase: str) -> None:
            if phase == "before_commit":
                target = self.directories["common"] / self.edge.parts[0].name
                target.unlink()
                target.write_bytes(foreign)

        with self.assertRaisesRegex(
            publisher.LocalCdnPublishError, "identity|rollback|lock"
        ):
            self.publish(checkpoint=replace)
        target = self.directories["common"] / self.edge.parts[0].name
        self.assertEqual(foreign, target.read_bytes())
        self.assertTrue((self.cdn / publisher.LOCK_NAME).is_file())
        target.unlink()
        (self.cdn / publisher.LOCK_NAME).unlink()

    def test_confirmation_and_stopped_server_are_mandatory(self):
        with self.assertRaisesRegex(publisher.LocalCdnPublishError, "requires"):
            publisher.publish_local_311_edge(
                self.edge,
                self.cdn,
                confirmation="NO",
                server_probe=lambda: False,
            )
        with self.assertRaisesRegex(publisher.LocalCdnPublishError, "stopped"):
            publisher.publish_local_311_edge(
                self.edge,
                self.cdn,
                confirmation=publisher.CONFIRMATION,
                server_probe=lambda: True,
            )
        self.assertEqual([], list(self.cdn.rglob("*.zip")))


if __name__ == "__main__":
    unittest.main()
