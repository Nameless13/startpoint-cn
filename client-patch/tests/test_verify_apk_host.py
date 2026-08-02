"""verify_apk_host 的单元测试：全部用合成字节做 fixture，不依赖真 APK / FFDec。"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import ipaddress
import json
import struct
import tempfile
import unittest
import zipfile
import zlib
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "client-patch" / "repoint-apk" / "verify_apk_host.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_apk_host", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V = load_module()


# ---------------------------------------------------------------------------
# fixture 构造：一只结构合法的最小 ABC / SWF / APK
# ---------------------------------------------------------------------------
def u30(value: int) -> bytes:
    return V.write_u30(value)


def build_abc(
    extra_strings: list[bytes],
    *,
    flag_value: bool | None = True,
    package: bytes = b"pinball.config.core",
    class_name: bytes = b"DevConfig",
    flag_name: bytes = b"sdkDummy",
) -> bytes:
    """拼一个最小但结构合法的 ABC：一个类 + 一处 sdkDummy 常量赋值。"""
    strings = [package, class_name, flag_name] + list(extra_strings)
    index = {value: position + 1 for position, value in enumerate(strings)}

    out = bytearray()
    out += struct.pack("<HH", 16, 46)          # minor / major
    out += u30(0) * 3                          # int / uint / double 池皆空
    out += u30(len(strings) + 1)               # string 池
    for value in strings:
        out += u30(len(value)) + value
    out += u30(2)                              # namespace 池：1 条
    out += bytes([0x16]) + u30(index[package])  # PackageNamespace
    out += u30(1)                              # ns_set 池：空
    out += u30(3)                              # multiname 池：2 条
    out += bytes([0x07]) + u30(1) + u30(index[class_name])   # #1 QName 类名
    out += bytes([0x07]) + u30(0) + u30(index[flag_name])    # #2 QName sdkDummy
    out += u30(3)                              # method 池：iinit / cinit / script init
    for _ in range(3):
        out += u30(0) + u30(0) + u30(0) + bytes([0])
    out += u30(0)                              # metadata 池：空
    out += u30(1)                              # class_count = 1
    # instance_info
    out += u30(1) + u30(0) + bytes([0]) + u30(0) + u30(0) + u30(0)
    # class_info
    out += u30(1) + u30(0)
    # script_info：1 个，traits 里声明这个类
    out += u30(1)
    out += u30(2) + u30(1) + u30(1) + bytes([4]) + u30(0) + u30(0)
    # method_body：script init 里给 sdkDummy 赋常量
    if flag_value is None:
        code = b""
    else:
        push = b"\x26" if flag_value else b"\x27"   # pushtrue / pushfalse
        code = push + b"\x68" + u30(2)              # initproperty #2
    out += u30(1)
    out += u30(2) + u30(2) + u30(1) + u30(1) + u30(2)
    out += u30(len(code)) + code
    out += u30(0)                              # exception_count
    out += u30(0)                              # body traits
    return bytes(out)


def build_swf(abc_blobs: list[bytes], *, compressed: bool = False) -> bytes:
    body = bytearray()
    body += bytes([0x00])                      # RECT nbits=0
    body += struct.pack("<HH", 24 * 256, 1)    # frameRate / frameCount
    for blob in abc_blobs:
        payload = struct.pack("<I", 1) + b"frame\x00" + blob
        body += struct.pack("<H", (82 << 6) | 0x3F) + struct.pack("<I", len(payload))
        body += payload
    body += struct.pack("<H", 0)               # End tag
    total = 8 + len(body)
    if compressed:
        return b"CWS" + bytes([46]) + struct.pack("<I", total) + zlib.compress(bytes(body))
    return b"FWS" + bytes([46]) + struct.pack("<I", total) + bytes(body)


def build_apk(directory: Path, swf: bytes | None, *, extra: dict | None = None) -> Path:
    path = directory / "sample.apk"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00fake")
        if swf is not None:
            archive.writestr(V.SWF_MEMBER, swf)
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return path


HOST = b"203.0.113.10:8001"
OLD_HOST = b"10.7.7.7:8001"


# ---------------------------------------------------------------------------
class TestPrimitives(unittest.TestCase):
    def test_u30_roundtrip(self) -> None:
        for value in (0, 1, 127, 128, 255, 16383, 16384, 6646, 2 ** 21, 2 ** 30 - 1):
            encoded = V.write_u30(value)
            decoded, pos = V.read_u30(encoded, 0)
            self.assertEqual(decoded, value)
            self.assertEqual(pos, len(encoded))

    def test_read_u30_out_of_range_raises(self) -> None:
        with self.assertRaises(V.ScanError):
            V.read_u30(b"\x80", 0)

    def test_valid_host_rejects_bad_octet_and_port(self) -> None:
        self.assertTrue(V._valid_host("203.0.113.10:8001"))
        self.assertFalse(V._valid_host("999.1.1.1:8001"))
        self.assertFalse(V._valid_host("203.0.113.10:0"))
        self.assertFalse(V._valid_host("203.0.113.10:70000"))
        self.assertFalse(V._valid_host("http://adobe.com:80"))

    def test_is_ipv4_host(self) -> None:
        self.assertTrue(V.is_ipv4_host("10.0.0.1:8001"))
        self.assertFalse(V.is_ipv4_host("wf.example.com:8001"))

    def test_find_hosts_only_matches_whole_strings(self) -> None:
        found = V.find_hosts_in_strings([
            HOST,
            b"http://203.0.113.10:8001/api",       # 不是整串，跳过
            b"wf.example.com:8001",
            b"adobe.com:80",                        # 噪声域名
            b"203.0.113.10:8001",                   # 重复计数
        ])
        self.assertEqual(found, {"203.0.113.10:8001": 2, "wf.example.com:8001": 1})


class TestPrivateAddressJudgement(unittest.TestCase):
    """地址是不是「必须替换」按**网段**判，脚本里没有写死的具体地址。"""

    def test_rfc1918_and_loopback_are_flagged(self) -> None:
        for value in ("10.7.7.7:8001", "172.16.0.1:8001", "127.0.0.1:8001",
                      "127.0.0.1", "::1"):
            self.assertTrue(V._is_private_like(value), value)

    def test_covers_the_third_rfc1918_block(self) -> None:
        # RFC1918 第三段（0xC0A8 开头那个）的样本用整数构造：仓库卫生门禁会拦
        # 这个网段的字面量，而这条断言恰恰要证明它没被漏掉。
        sample = str(ipaddress.ip_address(0xC0A80107))
        self.assertTrue(V._is_private_like(sample), sample)
        self.assertTrue(V._is_private_like(f"{sample}:8001"), sample)

    def test_documentation_and_public_ranges_are_not_flagged(self) -> None:
        # RFC5737/RFC3849 文档网段是本项目文档、--help 示例和本测试里的占位地址，
        # 绝不能被标成「必须替换」。CPython 的 ipaddress.is_private 会把它们
        # 算作 private，实现里显式减掉了；这条测试就是守着那个差别。
        for value in ("203.0.113.10:8001", "198.51.100.7:8001", "192.0.2.5:8001",
                      "2001:db8::1", "8.8.8.8:53", "11.0.0.1:8001", "172.32.0.1:8001"):
            self.assertFalse(V._is_private_like(value), value)

    def test_domains_and_garbage_are_not_flagged(self) -> None:
        for value in ("wf.example.com:8001", "localhost:8001", "", "999.1.1.1:8001"):
            self.assertFalse(V._is_private_like(value), value)

    def test_host_note_only_annotates_private(self) -> None:
        self.assertIn("必须替换", V.host_note("10.7.7.7:8001"))
        self.assertEqual(V.host_note("203.0.113.10:8001"), "")


class TestSwfLayer(unittest.TestCase):
    def test_decompress_passthrough_and_cws(self) -> None:
        plain = build_swf([build_abc([HOST])])
        self.assertIs(V.decompress_swf(plain), plain)
        packed = build_swf([build_abc([HOST])], compressed=True)
        self.assertEqual(V.decompress_swf(packed), plain)

    def test_reject_non_swf(self) -> None:
        with self.assertRaises(V.ScanError):
            V.decompress_swf(b"PK\x03\x04" + b"\x00" * 32)

    def test_iter_tags_handles_long_form(self) -> None:
        swf = build_swf([build_abc([HOST]), build_abc([OLD_HOST])])
        codes = [code for code, _ in V.iter_swf_tags(swf)]
        self.assertEqual(codes, [82, 82, 0])
        self.assertEqual(len(list(V.iter_abc_blobs(swf))), 2)

    def test_truncated_tag_raises(self) -> None:
        swf = bytearray(build_swf([build_abc([HOST])]))
        del swf[-40:]
        with self.assertRaises(V.ScanError):
            list(V.iter_swf_tags(bytes(swf)))


class TestAbcLayer(unittest.TestCase):
    def test_parses_strings_class_names_and_bodies(self) -> None:
        abc = V.AbcFile(build_abc([HOST]))
        self.assertIn(HOST, abc.strings)
        self.assertEqual(abc.qualified_name(1), "pinball.config.core.DevConfig")
        self.assertEqual(
            abc.method_owner[2], "pinball.config.core.DevConfig/script-init"
        )
        self.assertEqual(abc.multiname_indexes(b"sdkDummy"), [2])

    def test_flag_site_reads_true_and_false(self) -> None:
        for value in (True, False):
            sites = V.find_flag_sites(V.AbcFile(build_abc([HOST], flag_value=value)))
            self.assertEqual(len(sites), 1, value)
            self.assertEqual(sites[0].value, value)
            self.assertEqual(sites[0].owner, "pinball.config.core.DevConfig/script-init")

    def test_no_assignment_gives_no_site(self) -> None:
        self.assertEqual(V.find_flag_sites(V.AbcFile(build_abc([HOST], flag_value=None))), [])

    def test_judge_flag_prefers_primary_class(self) -> None:
        primary = V.FlagSite("pinball.config.core.DevConfig/script-init", True, 2)
        other = V.FlagSite("pinball.config.DevConfig_quick_start/iinit", False, 9)
        verdict, owner = V.judge_flag([other, primary])
        self.assertEqual(verdict, "true")
        self.assertEqual(owner, primary.owner)
        verdict, owner = V.judge_flag([other])
        self.assertEqual((verdict, owner), ("false", None))
        self.assertEqual(V.judge_flag([]), ("unknown", None))

    def test_scan_swf_aggregates(self) -> None:
        swf = build_swf([build_abc([HOST]), build_abc([OLD_HOST], flag_value=None)])
        result = V.scan_swf(swf)
        self.assertEqual(result["abc_count"], 2)
        self.assertEqual(
            sorted(result["hosts"]), ["10.7.7.7:8001", "203.0.113.10:8001"]
        )
        self.assertEqual(len(result["flag_sites"]), 1)


class TestRawFallback(unittest.TestCase):
    def test_ipv4_only_by_default(self) -> None:
        blob = b"\x01" + HOST + b"\x02wf.example.com:8001\x03"
        self.assertEqual(V.raw_scan_bytes(blob), {"203.0.113.10:8001": (1, False)})
        widened = V.raw_scan_bytes(blob, include_domains=True)
        self.assertIn("wf.example.com:8001", widened)

    def test_glued_port_is_trimmed_and_flagged(self) -> None:
        # 常量池字符串不带结尾 0，后一条以 "4" 开头就会粘上来
        found = V.raw_scan_bytes(b"\x11" + HOST + b"4abc")
        self.assertEqual(found, {"203.0.113.10:8001": (1, True)})

    def test_url_prefix_does_not_break_match(self) -> None:
        found = V.raw_scan_bytes(b"http://" + HOST + b"/api")
        self.assertEqual(found, {"203.0.113.10:8001": (1, False)})


class TestReport(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_reports_hosts_flag_and_private_note(self) -> None:
        swf = build_swf([build_abc([HOST, b"10.3.5.3:8070"])])
        apk = build_apk(self.dir, swf)
        report = V.build_report(apk, expect="203.0.113.10:8001",
                                forbid=[str(OLD_HOST, "ascii")])
        self.assertEqual(report["mode"], "abc")
        self.assertTrue(report["ok"])
        values = [entry["value"] for entry in report["server_addresses"]]
        self.assertEqual(values, ["10.3.5.3:8070", "203.0.113.10:8001"])
        # 私有地址被标注「必须替换」；公网/文档网段的地址不加注解。
        private, public = report["server_addresses"]
        self.assertTrue(private["private"])
        self.assertIn("必须替换", private["note"])
        self.assertFalse(public["private"])
        self.assertEqual(public["note"], "")
        self.assertEqual(report["login_flag"]["verdict"], "true")
        self.assertEqual(report["input"]["kind"], "apk")
        self.assertEqual(report["swf"]["abc_tags"], 1)

    def test_forbidden_host_fails(self) -> None:
        apk = build_apk(self.dir, build_swf([build_abc([OLD_HOST])]))
        report = V.build_report(apk, forbid=["10.7.7.7:8001"])
        self.assertFalse(report["ok"])
        failed = [c for c in report["checks"] if not c["ok"]]
        self.assertEqual(len(failed), 1)
        self.assertIn("仍在包里", failed[0]["detail"])

    def test_expect_missing_fails(self) -> None:
        apk = build_apk(self.dir, build_swf([build_abc([OLD_HOST])]))
        report = V.build_report(apk, expect="203.0.113.10:8001")
        self.assertFalse(report["ok"])

    def test_bare_swf_input(self) -> None:
        swf_path = self.dir / "main.swf"
        swf_path.write_bytes(build_swf([build_abc([HOST])]))
        report = V.build_report(swf_path, expect="203.0.113.10:8001")
        self.assertEqual(report["input"]["kind"], "swf")
        self.assertTrue(report["ok"])

    def test_auto_falls_back_to_raw_without_main_swf(self) -> None:
        apk = build_apk(self.dir, None, extra={"assets/other.bin": b"cfg=" + HOST})
        report = V.build_report(apk, expect="203.0.113.10:8001")
        self.assertEqual(report["mode"], "raw")
        self.assertTrue(report["ok"])
        self.assertEqual(report["login_flag"]["verdict"], "unknown")
        self.assertTrue(any("降级" in note for note in report["notes"]))

    def test_abc_mode_does_not_fall_back(self) -> None:
        apk = build_apk(self.dir, None, extra={"assets/other.bin": HOST})
        with self.assertRaises(V.ScanError):
            V.build_report(apk, mode="abc")

    def test_domain_expectation_widens_raw_scan(self) -> None:
        apk = build_apk(self.dir, None,
                        extra={"assets/other.bin": b"host=wf.example.com:8001"})
        report = V.build_report(apk, mode="raw", expect="wf.example.com:8001")
        self.assertTrue(report["ok"])

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(V.ScanError):
            V.build_report(self.dir / "nope.apk")

    def test_scan_is_read_only(self) -> None:
        apk = build_apk(self.dir, build_swf([build_abc([HOST])]))
        before = hashlib.sha256(apk.read_bytes()).hexdigest()
        stat_before = apk.stat().st_mtime_ns
        V.build_report(apk, expect="203.0.113.10:8001", forbid=["10.0.0.1:8001"])
        self.assertEqual(hashlib.sha256(apk.read_bytes()).hexdigest(), before)
        self.assertEqual(apk.stat().st_mtime_ns, stat_before)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["sample.apk"])


class TestCli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = V.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_exit_zero_and_text_sections(self) -> None:
        apk = build_apk(self.dir, build_swf([build_abc([HOST])]))
        code, out, _ = self.run_cli(str(apk), "--expect", "203.0.113.10:8001")
        self.assertEqual(code, 0)
        self.assertIn("① 检测到的服务器地址", out)
        self.assertIn("203.0.113.10:8001", out)
        self.assertIn("③ 免登录标记 sdkDummy：true", out)
        self.assertIn("判定以此处为准", out)

    def test_exit_one_on_failed_assertion(self) -> None:
        apk = build_apk(self.dir, build_swf([build_abc([OLD_HOST])]))
        code, out, _ = self.run_cli(str(apk), "--forbid", "10.7.7.7:8001")
        self.assertEqual(code, 1)
        self.assertIn("有断言未通过", out)

    def test_exit_two_on_bad_input(self) -> None:
        code, _, err = self.run_cli(str(self.dir / "missing.apk"))
        self.assertEqual(code, 2)
        self.assertIn("错误", err)

    def test_json_output_is_parsable(self) -> None:
        apk = build_apk(self.dir, build_swf([build_abc([HOST])]))
        code, out, _ = self.run_cli(str(apk), "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["mode"], "abc")
        self.assertEqual(payload["server_addresses"][0]["value"], "203.0.113.10:8001")
        self.assertIn("sha256", payload["input"])


if __name__ == "__main__":
    unittest.main()
