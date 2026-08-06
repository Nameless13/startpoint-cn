# -*- coding: utf-8 -*-
"""Strict offline receipt coverage for the frozen local-live release."""
from __future__ import annotations

import hashlib
import io
import json
import stat
import sys
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path


MOD_TOOLS = Path(__file__).resolve().parent.parent
CONTRACTS = MOD_TOOLS / "release-contracts"
sys.path.insert(0, str(MOD_TOOLS))

import wf_local_release_receipt as receipt  # noqa: E402
import wf_local_server_contract as server_contract  # noqa: E402
import wf_character_pack as character_pack  # noqa: E402
import wf_mod_tool as core  # noqa: E402
from wf_release_inventory_contract import (  # noqa: E402
    InventoryContract,
    InventoryMember,
    projection_sha256,
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def manifest_blob(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def zip_blob(member_payloads: list[tuple[str, bytes]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, payload in member_payloads:
            info = zipfile.ZipInfo(name, (2026, 8, 6, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


class ReceiptFixture:
    def __init__(self):
        self.old_a, self.old_b = b"old-a", b"old-b"
        self.new_a, self.new_b = b"new-a", b"new-b"
        self.key_a = ("common", "fixture/a.bin")
        self.key_b = ("common", "fixture/b.bin")
        self.key_table = ("common", "fixture/table.orderedmap")
        self.table_claim = character_pack.TableClaim(
            "common", self.key_table[1], "flat", ("owned",)
        )

        def table(sentinel: bytes, owned: bytes) -> bytes:
            return core.build_orderedmap(core.OrderedMap(
                "fixture", ["sentinel", "owned"], [sentinel, owned], Path("<fixture>"),
            ))

        self.table_terminal = table(b"terminal-wip", b"terminal-owned")
        self.table_277 = table(b"baseline-277", b"old-owned")
        self.table_311 = table(b"baseline-311", b"terminal-owned")
        self.table_output_277 = table(b"baseline-277", b"terminal-owned")
        terminal = InventoryContract(
            "terminal-fixture",
            (
                InventoryMember("owner-a", "file", *self.key_a, len(self.new_a), sha(self.new_a)),
                InventoryMember("owner-b", "file", *self.key_b, len(self.new_b), sha(self.new_b)),
                InventoryMember(
                    "owner-table", "table", *self.key_table,
                    claim=self.table_claim,
                    projection_sha256=projection_sha256(
                        self.table_terminal, self.table_claim
                    ),
                    source_size=len(self.table_terminal),
                    source_sha256=sha(self.table_terminal),
                ),
            ),
        )
        baselines = {
            "1.4.277": InventoryContract(
                "baseline-277",
                (
                    InventoryMember("owner-a", "file", *self.key_a, len(self.old_a), sha(self.old_a)),
                    InventoryMember(
                        "owner-table", "table", *self.key_table,
                        claim=self.table_claim,
                        projection_sha256=projection_sha256(
                            self.table_277, self.table_claim
                        ),
                        source_size=len(self.table_277),
                        source_sha256=sha(self.table_277),
                    ),
                ),
            ),
            "1.4.311": InventoryContract(
                "baseline-311",
                (
                    InventoryMember("owner-a", "file", *self.key_a, len(self.new_a), sha(self.new_a)),
                    InventoryMember("owner-b", "file", *self.key_b, len(self.old_b), sha(self.old_b)),
                    InventoryMember(
                        "owner-table", "table", *self.key_table,
                        claim=self.table_claim,
                        projection_sha256=projection_sha256(
                            self.table_311, self.table_claim
                        ),
                        source_size=len(self.table_311),
                        source_sha256=sha(self.table_311),
                    ),
                ),
            ),
        }
        projected = {"hero": {"name": "terminal"}}
        selector = server_contract.ServerSelector("object_keys", (), ("hero",))
        server_member = server_contract.ServerMember(
            "server-owner",
            "server.json",
            selector,
            sha(canonical({"hero": {"name": "preimage"}})),
            sha(canonical(projected)),
            {"hero": {"name": "preimage"}},
            projected,
        )
        migration = server_contract.MigrationContract(
            "migration-fixture", terminal.contract_id, (), (server_member,)
        )
        bindings = (
            receipt.ContractBinding("terminal", "contracts/terminal.json", terminal.contract_id, b"terminal"),
            receipt.ContractBinding("baseline_1_4_277", "contracts/277.json", baselines["1.4.277"].contract_id, b"277"),
            receipt.ContractBinding("baseline_1_4_311", "contracts/311.json", baselines["1.4.311"].contract_id, b"311"),
            receipt.ContractBinding("provenance", "contracts/provenance.json", "provenance-fixture", b"provenance"),
            receipt.ContractBinding("migration", "contracts/migration.json", migration.contract_id, b"migration"),
        )
        descriptors = {
            "1.4.277": {
                self.key_a: receipt.BaselineDescriptor(True, len(self.old_a), sha(self.old_a), "archive/277.zip", receipt.archive_member_name(*self.key_a)),
                self.key_b: receipt.BaselineDescriptor(False, None, None, None, None),
                self.key_table: receipt.BaselineDescriptor(
                    True, len(self.table_277), sha(self.table_277),
                    "archive/277.zip", receipt.archive_member_name(*self.key_table),
                ),
            },
            "1.4.311": {
                self.key_a: receipt.BaselineDescriptor(True, len(self.new_a), sha(self.new_a), "archive/311.zip", receipt.archive_member_name(*self.key_a)),
                self.key_b: receipt.BaselineDescriptor(True, len(self.old_b), sha(self.old_b), "archive/311.zip", receipt.archive_member_name(*self.key_b)),
                self.key_table: receipt.BaselineDescriptor(
                    True, len(self.table_311), sha(self.table_311),
                    "archive/311.zip", receipt.archive_member_name(*self.key_table),
                ),
            },
        }
        self.context = receipt.ReleaseContext(terminal, baselines, descriptors, migration, bindings)
        self.policy = receipt.ReleasePolicy(
            release_id="local-live-1-4-312",
            terminal_contract_id=terminal.contract_id,
            baseline_versions=("1.4.277", "1.4.311"),
            terminal_member_count=3,
            unique_path_count=3,
            server_member_count=1,
            client_migration_count=0,
            contract_ids={binding.role: binding.contract_id for binding in bindings},
        )
        name277 = "pinball-1.4.277-1.4.312-1-fixture277.zip"
        name311 = "pinball-1.4.311-1.4.312-1-fixture311.zip"
        blob277 = zip_blob([
            (receipt.archive_member_name(*self.key_a), self.new_a),
            (receipt.archive_member_name(*self.key_b), self.new_b),
            (receipt.archive_member_name(*self.key_table), self.table_output_277),
        ])
        blob311 = zip_blob([(receipt.archive_member_name(*self.key_b), self.new_b)])
        self.edges = (
            receipt.EdgeEvidence(
                "1.4.277", "1.4.312", "fixture-277", "fixture277",
                {self.key_a: self.old_a, self.key_b: None, self.key_table: self.table_277},
                {
                    self.key_a: self.new_a, self.key_b: self.new_b,
                    self.key_table: self.table_output_277,
                },
                (receipt.ArchiveEvidence("common", name277, blob277),),
            ),
            receipt.EdgeEvidence(
                "1.4.311", "1.4.312", "fixture-311", "fixture311",
                {
                    self.key_a: self.new_a, self.key_b: self.old_b,
                    self.key_table: self.table_311,
                },
                {
                    self.key_a: self.new_a, self.key_b: self.new_b,
                    self.key_table: self.table_311,
                },
                (receipt.ArchiveEvidence("common", name311, blob311),),
            ),
        )
        self.preimage = manifest_blob({"cdn_version": "1.4.54", "patches": []})
        patches = []
        for edge in self.edges:
            patches.append({
                "id": edge.patch_id,
                "type": "patch",
                "name": edge.patch_id,
                "description": "fixture edge",
                "version": edge.to_version,
                "depends_on": edge.from_version,
                "enabled": True,
                "chain": [part.name for part in edge.archives],
                "created_at": "2026-08-06",
            })
        self.manifest = manifest_blob({"cdn_version": "1.4.54", "patches": patches})
        self.server_files = {"server.json": canonical(projected)}
        self.terminal_sources = {
            self.key_a: self.new_a,
            self.key_b: self.new_b,
            self.key_table: self.table_terminal,
        }

    def build(self) -> bytes:
        return receipt.build_receipt(
            self.context,
            self.policy,
            terminal_sources=self.terminal_sources,
            edges=self.edges,
            manifest_preimage=self.preimage,
            manifest_output=self.manifest,
            server_files=self.server_files,
        )

    def archive_blobs(self) -> dict[str, bytes]:
        return {
            f"active/{part.name}": part.blob
            for edge in self.edges for part in edge.archives
        }


class LocalReleaseReceiptTest(unittest.TestCase):
    def test_writer_and_offline_verifier_cover_both_edges_and_noop_omission(self):
        fx = ReceiptFixture()
        raw = fx.build()
        value = receipt.parse_receipt(raw)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(["1.4.277", "1.4.311"], [edge["from_version"] for edge in value["edges"]])
        edge311 = value["edges"][1]
        path_a = next(item for item in edge311["paths"] if item["logical_path"] == "fixture/a.bin")
        self.assertEqual("omitted_equal", path_a["disposition"])
        self.assertIsNone(path_a["archive"])
        edge277 = value["edges"][0]
        table277 = next(
            item for item in edge277["paths"]
            if item["logical_path"] == fx.key_table[1]
        )
        self.assertEqual("included", table277["disposition"])
        self.assertEqual(
            projection_sha256(fx.table_terminal, fx.table_claim),
            table277["claims"][0]["projection_sha256"],
        )
        self.assertEqual(
            table277["unclaimed_before_sha256"],
            table277["unclaimed_after_sha256"],
        )
        table311 = next(
            item for item in edge311["paths"]
            if item["logical_path"] == fx.key_table[1]
        )
        self.assertEqual("omitted_equal", table311["disposition"])
        report = receipt.verify_receipt(
            fx.context,
            fx.policy,
            raw,
            archive_blobs=fx.archive_blobs(),
            manifest_raw=fx.manifest,
            server_files=fx.server_files,
        )
        self.assertEqual((2, 3, 3), (report.edge_count, report.path_count_per_edge, report.claim_count_per_edge))

    def test_writer_rejects_table_output_that_overwrites_unclaimed_rows(self):
        fx = ReceiptFixture()
        bad_edge = replace(
            fx.edges[0],
            output={**fx.edges[0].output, fx.key_table: fx.table_terminal},
        )
        with self.assertRaisesRegex(receipt.ReceiptError, "unclaimed|output"):
            receipt.build_receipt(
                fx.context,
                fx.policy,
                terminal_sources=fx.terminal_sources,
                edges=(bad_edge, fx.edges[1]),
                manifest_preimage=fx.preimage,
                manifest_output=fx.manifest,
                server_files=fx.server_files,
            )

    def test_strict_json_rejects_duplicate_nan_absolute_and_runtime_paths(self):
        bad = (
            b'{"schema":"wf-local-release-receipt/v1",'
            b'"schema":"wf-local-release-receipt/v1"}'
        )
        with self.assertRaisesRegex(receipt.ReceiptError, "duplicate"):
            receipt.parse_receipt(bad)
        with self.assertRaisesRegex(receipt.ReceiptError, "non-JSON"):
            receipt.parse_receipt(b'{"value":NaN}')
        with self.assertRaisesRegex(receipt.ReceiptError, "absolute|runtime"):
            receipt.parse_receipt(b'{"path":"C:\\\\Temp\\\\leak"}')
        with self.assertRaisesRegex(receipt.ReceiptError, "runtime"):
            receipt.parse_receipt(b'{"mtime_ns":123}')

    def test_verifier_rejects_zip_manifest_and_path_coverage_tamper(self):
        fx = ReceiptFixture()
        raw = fx.build()
        archives = fx.archive_blobs()
        first = next(iter(archives))
        broken = dict(archives)
        broken[first] += b"tamper"
        with self.assertRaisesRegex(receipt.ReceiptError, "archive.*sha256|size"):
            receipt.verify_receipt(
                fx.context, fx.policy, raw, archive_blobs=broken,
                manifest_raw=fx.manifest, server_files=fx.server_files,
            )
        value = receipt.parse_receipt(raw)
        archive_record = value["edges"][0]["archives"][0]
        junk = archives[first] + b"JUNK"
        archive_record["size"] = len(junk)
        archive_record["sha256"] = sha(junk)
        value.pop("receipt_sha256")
        value["receipt_sha256"] = sha(receipt.canonical_receipt(value))
        with self.assertRaisesRegex(receipt.ReceiptError, "canonical byte-for-byte"):
            receipt.verify_receipt(
                fx.context, fx.policy, receipt.canonical_receipt(value),
                archive_blobs={**archives, first: junk},
                manifest_raw=fx.manifest, server_files=fx.server_files,
            )
        with self.assertRaisesRegex(receipt.ReceiptError, "manifest"):
            receipt.verify_receipt(
                fx.context, fx.policy, raw, archive_blobs=archives,
                manifest_raw=fx.manifest + b" ", server_files=fx.server_files,
            )
        value = receipt.parse_receipt(raw)
        value["manifest"]["preimage_sha256"] = "0" * 64
        value.pop("receipt_sha256")
        value["receipt_sha256"] = sha(receipt.canonical_receipt(value))
        with self.assertRaisesRegex(receipt.ReceiptError, "preimage sha256"):
            receipt.verify_receipt(
                fx.context, fx.policy, receipt.canonical_receipt(value),
                archive_blobs=archives, manifest_raw=fx.manifest,
                server_files=fx.server_files,
            )
        value = receipt.parse_receipt(raw)
        value["edges"][0]["paths"].pop()
        value.pop("receipt_sha256")
        value["receipt_sha256"] = sha(receipt.canonical_receipt(value))
        missing = receipt.canonical_receipt(value)
        with self.assertRaisesRegex(receipt.ReceiptError, "path coverage"):
            receipt.verify_receipt(
                fx.context, fx.policy, missing, archive_blobs=archives,
                manifest_raw=fx.manifest, server_files=fx.server_files,
            )

    def test_local_context_binds_exact_task3a_contracts(self):
        context = receipt.load_local_context(CONTRACTS)
        self.assertEqual(receipt.LOCAL_POLICY.terminal_contract_id, context.terminal.contract_id)
        self.assertEqual(257, len(context.terminal.members))
        self.assertEqual(233, len({member.key for member in context.terminal.members}))
        self.assertEqual(5, len(context.contract_bindings))


if __name__ == "__main__":
    unittest.main()
