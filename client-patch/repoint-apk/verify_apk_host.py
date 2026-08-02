#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读校验：一只 WF 客户端 APK 到底指向哪台服务器。

给一个 APK（或已解出来的主 SWF）路径，报告三件事：

1. **检测到的服务器地址** —— 主 SWF（`assets/worldflipper_android_release.swf`）
   AS3 常量池里所有形如 `host:port` 的字符串；
2. **是否残留旧地址** —— `--forbid` 指定的地址是否还在；另外内置一张已知地址表，
   命中会附注来源（官方开发基线 / 作者内网默认值）；
3. **免登录标记 sdkDummy** —— 常量池里叫 `sdkDummy` 的属性在哪些方法里被赋成
   `true` / `false`（读的是 `pushtrue|pushfalse` + `initproperty|setproperty`
   指令序列，不是字符串是否出现）。

全程 **只读**：所有文件都以 "rb" 打开，不写、不改、不重打包 APK。
纯标准库，不需要 FFDec / Java。

## 能力边界（别夸大）

- 只解析 **DoABC 标签里的 ABC 常量池与方法体字节**，不做完整反编译；
  能看到「哪个字符串在」「某属性被赋成 true 还是 false」，看不到控制流，
  因此**不能证明一段补丁逻辑运行时真的生效**。想要那种保证请上真机。
- `sdkDummy` 这个**字符串在官方原版 APK 里本来就有**（它是字段名）。所以只有
  「赋值指令」这一层的结论有意义，脚本报的就是这一层；若某个 APK 里该属性是
  运行时算出来的（而不是常量赋值），脚本会报 `unknown`，那不是"没打补丁"的证据。
- `--mode raw` 是降级模式：直接在 APK 全部成员的原始字节里搜 host 模式。
  ABC 常量池的字符串是**长度前缀、不带结尾 0**，相邻字符串会粘在一起，
  所以 raw 模式可能把下一个字符串的开头数字算进端口（例：`...:8001` 后面跟着
  一个 `4` 会被读成 `:80014`）。脚本会把端口 > 65535 的匹配截回合法值并标
  `ambiguous: true`。默认 `--mode auto` 先走 ABC，失败才降级。
- 只认主 SWF 里的地址。若某个包把地址塞在别处（原生 so、资源文件），
  ABC 模式看不见；`--mode raw` 会扫到所有成员，可作交叉验证。

## 用法

```
python -X utf8 verify_apk_host.py WorldFlipper-xxx.apk
python -X utf8 verify_apk_host.py out.apk --expect 192.168.1.10:8001 \
    --forbid 192.168.0.130:8001 --json
```

退出码：0 = 所有断言通过；1 = 有断言不通过；2 = 用法/解析错误。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
import zlib
from pathlib import Path
from typing import Iterable, Iterator, NamedTuple

SWF_MEMBER = "assets/worldflipper_android_release.swf"
LOGIN_FLAG_NAME = b"sdkDummy"
#: ①免登录补丁的落点类；同名属性在别的配置类里也有，判定以这个类为准。
PRIMARY_FLAG_CLASS = "pinball.config.core.DevConfig"

#: 完整匹配一条 host:port 字符串（常量池里是整串，所以这里用 fullmatch）。
HOST_RE = re.compile(
    rb"(?:\d{1,3}(?:\.\d{1,3}){3}"
    rb"|[A-Za-z0-9][A-Za-z0-9\-]{0,62}(?:\.[A-Za-z0-9][A-Za-z0-9\-]{0,62})+)"
    rb":\d{1,5}"
)
#: raw 降级模式：默认只认 IPv4:port。域名形态在原始字节里噪声极大
#: （XMP 元数据的 `xmp.did:...`、AS3 里的 `e.nodeType:9` 之类全会命中），
#: 要扫域名得显式打开 include_domains。
RAW_IPV4_RE = re.compile(rb"(?<![0-9A-Za-z.\-])\d{1,3}(?:\.\d{1,3}){3}:\d{1,6}")
RAW_HOST_RE = re.compile(
    rb"(?<![0-9A-Za-z.\-])"
    rb"(?:\d{1,3}(?:\.\d{1,3}){3}"
    rb"|[A-Za-z0-9][A-Za-z0-9\-]{0,62}(?:\.[A-Za-z0-9][A-Za-z0-9\-]{0,62})+)"
    rb":\d{1,6}"
)

#: 已知地址注解表。命中只是加一句说明，不改变通过/失败判定。
KNOWN_HOSTS = {
    "10.3.5.3:8070": "官方开发基线残留：官方未改动的原版包里就有这一条，与私服无关",
    "192.168.0.130:8001": "作者内网默认值：v2.0-threechar 发行包的出厂指向，重指向后不应再出现",
}

#: 明显不是服务器地址的域名噪声（AS3 命名空间 URI 之类）。
NOISE_HOSTS = ("adobe.com", "w3.org", "purl.org", "google.com", "robvanderwoude.com")


class ScanError(Exception):
    """输入不是能解析的 APK / SWF。"""


class HostHit(NamedTuple):
    value: str
    occurrences: int
    ambiguous: bool
    where: str


class FlagSite(NamedTuple):
    owner: str
    value: bool
    method: int


# --------------------------------------------------------------------------
# 基础字节读写
# --------------------------------------------------------------------------
def read_u30(data: bytes, pos: int) -> tuple[int, int]:
    """读一个 ABC 变长 u30，返回 (值, 新位置)。"""
    result = 0
    for shift in range(5):
        if pos >= len(data):
            raise ScanError("u30 读越界")
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << (7 * shift)
        if not byte & 0x80:
            break
    return result & 0xFFFFFFFF, pos


def write_u30(value: int) -> bytes:
    """把整数编成 ABC 变长 u30（构造指令匹配模式时用）。"""
    if value < 0:
        raise ValueError("u30 不能为负")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def read_u16(data: bytes, pos: int) -> int:
    if pos + 2 > len(data):
        raise ScanError("u16 读越界")
    return data[pos] | (data[pos + 1] << 8)


def read_u32(data: bytes, pos: int) -> int:
    if pos + 4 > len(data):
        raise ScanError("u32 读越界")
    return int.from_bytes(data[pos:pos + 4], "little")


# --------------------------------------------------------------------------
# SWF
# --------------------------------------------------------------------------
def decompress_swf(data: bytes) -> bytes:
    """把 SWF 规范化成未压缩形式（FWS 原样返回；CWS=zlib；ZWS=LZMA）。"""
    if len(data) < 8:
        raise ScanError("SWF 太短")
    signature = data[:3]
    if signature == b"FWS":
        return data
    if signature == b"CWS":
        try:
            body = zlib.decompress(data[8:])
        except zlib.error as exc:  # pragma: no cover - 依赖具体样本
            raise ScanError(f"CWS 解压失败: {exc}") from exc
        return b"FWS" + data[3:8] + body
    if signature == b"ZWS":
        import lzma

        declared = read_u32(data, 4)
        props = data[12:17]
        payload = data[17:]
        size = max(declared - 8, 0)
        header = props + size.to_bytes(8, "little")
        try:
            body = lzma.decompress(header + payload, format=lzma.FORMAT_ALONE)
        except lzma.LZMAError as exc:  # pragma: no cover - 依赖具体样本
            raise ScanError(f"ZWS 解压失败: {exc}") from exc
        return b"FWS" + data[3:8] + body
    raise ScanError(f"不是 SWF：签名 {signature!r}")


def iter_swf_tags(swf: bytes) -> Iterator[tuple[int, bytes]]:
    """遍历未压缩 SWF 的标签，产出 (tag_code, payload)。"""
    body = swf[8:]
    if not body:
        raise ScanError("SWF 没有内容")
    nbits = body[0] >> 3
    pos = (5 + 4 * nbits + 7) // 8 + 4  # RECT + frameRate(u16) + frameCount(u16)
    while pos + 2 <= len(body):
        header = read_u16(body, pos)
        pos += 2
        code = header >> 6
        length = header & 0x3F
        if length == 0x3F:
            length = read_u32(body, pos)
            pos += 4
        if pos + length > len(body):
            raise ScanError(f"标签 {code} 长度越界")
        yield code, body[pos:pos + length]
        pos += length
        if code == 0:  # End
            return


def iter_abc_blobs(swf: bytes) -> Iterator[bytes]:
    """产出 SWF 里每个 DoABC(72) / DoABC2(82) 标签中的 ABC 字节。"""
    for code, payload in iter_swf_tags(swf):
        if code == 72:
            yield payload
        elif code == 82:
            end = payload.find(b"\x00", 4)
            if end < 0:
                raise ScanError("DoABC2 缺少名字结束符")
            yield payload[end + 1:]


# --------------------------------------------------------------------------
# ABC
# --------------------------------------------------------------------------
class AbcFile:
    """够用即可的 ABC 解析：常量池 + 类名 + 方法体字节。"""

    def __init__(self, data: bytes) -> None:
        self.strings: list[bytes] = [b""]
        self.multinames: list[tuple[str, int, int] | None] = [None]
        self.namespaces: list[int] = [0]
        self.method_owner: dict[int, str] = {}
        self.bodies: dict[int, bytes] = {}
        self._parse(data)

    # -- 内部 ------------------------------------------------------------
    def _parse(self, data: bytes) -> None:
        pos = 4  # minor + major
        pos = self._skip_pool(data, pos, self._skip_u30)          # int
        pos = self._skip_pool(data, pos, self._skip_u30)          # uint
        count, pos = read_u30(data, pos)                          # double
        pos += 8 * max(0, count - 1)
        pos = self._read_strings(data, pos)
        pos = self._read_namespaces(data, pos)
        pos = self._skip_ns_sets(data, pos)
        pos = self._read_multinames(data, pos)
        pos = self._skip_methods(data, pos)
        pos = self._skip_metadata(data, pos)
        pos = self._read_classes(data, pos)
        pos = self._read_scripts(data, pos)
        self._read_bodies(data, pos)

    @staticmethod
    def _skip_u30(data: bytes, pos: int) -> int:
        _, pos = read_u30(data, pos)
        return pos

    def _skip_pool(self, data: bytes, pos: int, step) -> int:
        count, pos = read_u30(data, pos)
        for _ in range(max(0, count - 1)):
            pos = step(data, pos)
        return pos

    def _read_strings(self, data: bytes, pos: int) -> int:
        count, pos = read_u30(data, pos)
        for _ in range(max(0, count - 1)):
            length, pos = read_u30(data, pos)
            if pos + length > len(data):
                raise ScanError("字符串常量越界")
            self.strings.append(data[pos:pos + length])
            pos += length
        return pos

    def _read_namespaces(self, data: bytes, pos: int) -> int:
        count, pos = read_u30(data, pos)
        for _ in range(max(0, count - 1)):
            pos += 1  # kind
            name, pos = read_u30(data, pos)
            self.namespaces.append(name)
        return pos

    def _skip_ns_sets(self, data: bytes, pos: int) -> int:
        count, pos = read_u30(data, pos)
        for _ in range(max(0, count - 1)):
            inner, pos = read_u30(data, pos)
            for _ in range(inner):
                _, pos = read_u30(data, pos)
        return pos

    def _read_multinames(self, data: bytes, pos: int) -> int:
        count, pos = read_u30(data, pos)
        for _ in range(max(0, count - 1)):
            kind = data[pos]
            pos += 1
            if kind in (0x07, 0x0D):          # QName / QNameA
                ns, pos = read_u30(data, pos)
                name, pos = read_u30(data, pos)
                self.multinames.append(("Q", ns, name))
            elif kind in (0x0F, 0x10):        # RTQName / RTQNameA
                name, pos = read_u30(data, pos)
                self.multinames.append(("RTQ", 0, name))
            elif kind in (0x11, 0x12):        # RTQNameL / RTQNameLA
                self.multinames.append(("RTQL", 0, 0))
            elif kind in (0x09, 0x0E):        # Multiname / MultinameA
                name, pos = read_u30(data, pos)
                _, pos = read_u30(data, pos)
                self.multinames.append(("M", 0, name))
            elif kind in (0x1B, 0x1C):        # MultinameL / MultinameLA
                _, pos = read_u30(data, pos)
                self.multinames.append(("ML", 0, 0))
            elif kind == 0x1D:                # TypeName
                name, pos = read_u30(data, pos)
                params, pos = read_u30(data, pos)
                for _ in range(params):
                    _, pos = read_u30(data, pos)
                self.multinames.append(("T", 0, name))
            else:
                raise ScanError(f"未知 multiname kind {kind:#x}")
        return pos

    def _skip_methods(self, data: bytes, pos: int) -> int:
        count, pos = read_u30(data, pos)
        for _ in range(count):
            params, pos = read_u30(data, pos)
            _, pos = read_u30(data, pos)
            for _ in range(params):
                _, pos = read_u30(data, pos)
            _, pos = read_u30(data, pos)
            flags = data[pos]
            pos += 1
            if flags & 0x08:  # HAS_OPTIONAL
                optional, pos = read_u30(data, pos)
                for _ in range(optional):
                    _, pos = read_u30(data, pos)
                    pos += 1
            if flags & 0x80:  # HAS_PARAM_NAMES
                for _ in range(params):
                    _, pos = read_u30(data, pos)
        return pos

    def _skip_metadata(self, data: bytes, pos: int) -> int:
        count, pos = read_u30(data, pos)
        for _ in range(count):
            _, pos = read_u30(data, pos)
            items, pos = read_u30(data, pos)
            for _ in range(items):
                _, pos = read_u30(data, pos)
                _, pos = read_u30(data, pos)
        return pos

    def _read_traits(self, data: bytes, pos: int) -> tuple[int, list[tuple[int, int]]]:
        """跳过一段 traits，顺带回收 (name_index, kind) 供命名用。"""
        collected: list[tuple[int, int]] = []
        count, pos = read_u30(data, pos)
        for _ in range(count):
            name, pos = read_u30(data, pos)
            byte = data[pos]
            pos += 1
            kind = byte & 0x0F
            attrs = byte >> 4
            if kind in (0, 6):                    # Slot / Const
                _, pos = read_u30(data, pos)
                _, pos = read_u30(data, pos)
                vindex, pos = read_u30(data, pos)
                if vindex:
                    pos += 1
            elif kind in (1, 2, 3, 4, 5):         # Method/Getter/Setter/Class/Function
                _, pos = read_u30(data, pos)
                _, pos = read_u30(data, pos)
            else:
                raise ScanError(f"未知 trait kind {kind}")
            if attrs & 0x04:                      # ATTR_Metadata
                metas, pos = read_u30(data, pos)
                for _ in range(metas):
                    _, pos = read_u30(data, pos)
            collected.append((name, kind))
        return pos, collected

    def _read_classes(self, data: bytes, pos: int) -> int:
        count, pos = read_u30(data, pos)
        names: list[str] = []
        for _ in range(count):
            name, pos = read_u30(data, pos)
            _, pos = read_u30(data, pos)          # super_name
            flags = data[pos]
            pos += 1
            if flags & 0x08:                      # ClassProtectedNs
                _, pos = read_u30(data, pos)
            interfaces, pos = read_u30(data, pos)
            for _ in range(interfaces):
                _, pos = read_u30(data, pos)
            iinit, pos = read_u30(data, pos)
            label = self.qualified_name(name)
            names.append(label)
            self.method_owner.setdefault(iinit, f"{label}/iinit")
            pos, _ = self._read_traits(data, pos)
        for index in range(count):
            cinit, pos = read_u30(data, pos)
            self.method_owner.setdefault(cinit, f"{names[index]}/cinit")
            pos, _ = self._read_traits(data, pos)
        return pos

    def _read_scripts(self, data: bytes, pos: int) -> int:
        count, pos = read_u30(data, pos)
        for index in range(count):
            init, pos = read_u30(data, pos)
            pos, traits = self._read_traits(data, pos)
            defined = [self.qualified_name(name) for name, kind in traits if kind == 4]
            label = defined[0] if defined else f"script#{index}"
            self.method_owner.setdefault(init, f"{label}/script-init")
        return pos

    def _read_bodies(self, data: bytes, pos: int) -> None:
        count, pos = read_u30(data, pos)
        for _ in range(count):
            method, pos = read_u30(data, pos)
            for _ in range(4):                    # max_stack/local/init_scope/max_scope
                _, pos = read_u30(data, pos)
            length, pos = read_u30(data, pos)
            if pos + length > len(data):
                raise ScanError("方法体越界")
            self.bodies[method] = data[pos:pos + length]
            pos += length
            handlers, pos = read_u30(data, pos)
            for _ in range(handlers):
                for _ in range(5):
                    _, pos = read_u30(data, pos)
            pos, _ = self._read_traits(data, pos)

    # -- 对外 ------------------------------------------------------------
    def string(self, index: int) -> bytes:
        return self.strings[index] if 0 <= index < len(self.strings) else b""

    def qualified_name(self, index: int) -> str:
        entry = self.multinames[index] if 0 <= index < len(self.multinames) else None
        if entry is None:
            return f"multiname#{index}"
        kind, ns, name = entry
        local = self.string(name).decode("utf-8", "replace")
        if kind == "Q" and 0 < ns < len(self.namespaces):
            package = self.string(self.namespaces[ns]).decode("utf-8", "replace")
            if package:
                return f"{package}.{local}"
        return local or f"multiname#{index}"

    def multiname_indexes(self, name: bytes) -> list[int]:
        out = []
        for index, entry in enumerate(self.multinames):
            if entry is None:
                continue
            if self.string(entry[2]) == name:
                out.append(index)
        return out


# --------------------------------------------------------------------------
# 扫描
# --------------------------------------------------------------------------
def _valid_host(text: str) -> bool:
    host, _, port_text = text.rpartition(":")
    if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
        return False
    if any(noise in host for noise in NOISE_HOSTS):
        return False
    parts = host.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return all(len(p) <= 3 and int(p) <= 255 for p in parts)
    return True


def _trim_port(text: str) -> tuple[str, bool]:
    """raw 模式下端口可能粘上了后一个字符串的数字，截回合法端口。"""
    host, _, port_text = text.rpartition(":")
    trimmed = False
    while port_text and (not port_text.isdigit() or int(port_text) > 65535):
        port_text = port_text[:-1]
        trimmed = True
    if not port_text:
        return "", True
    return f"{host}:{port_text}", trimmed


def find_hosts_in_strings(strings: Iterable[bytes]) -> dict[str, int]:
    """从常量池字符串里挑出整串就是 host:port 的那些。"""
    found: dict[str, int] = {}
    for raw in strings:
        if not HOST_RE.fullmatch(raw):
            continue
        text = raw.decode("ascii", "replace")
        if not _valid_host(text):
            continue
        found[text] = found.get(text, 0) + 1
    return found


def find_flag_sites(abc: AbcFile, name: bytes = LOGIN_FLAG_NAME) -> list[FlagSite]:
    """找 `pushtrue|pushfalse` 紧跟 `initproperty|setproperty <name>` 的赋值点。"""
    sites: list[FlagSite] = []
    targets = abc.multiname_indexes(name)
    if not targets:
        return sites
    patterns = []
    for index in targets:
        operand = write_u30(index)
        for opcode in (b"\x68", b"\x61"):  # initproperty / setproperty
            patterns.append((True, b"\x26" + opcode + operand))   # pushtrue
            patterns.append((False, b"\x27" + opcode + operand))  # pushfalse
    for method, code in abc.bodies.items():
        for value, pattern in patterns:
            hits = code.count(pattern)
            if hits:
                owner = abc.method_owner.get(method, f"method#{method}")
                sites.extend([FlagSite(owner, value, method)] * hits)
    return sites


def judge_flag(sites: list[FlagSite]) -> tuple[str, str | None]:
    """给出 sdkDummy 结论：优先看 ①补丁落点类，没有才合并全部赋值点。"""
    if not sites:
        return "unknown", None
    primary = [s for s in sites if s.owner.startswith(PRIMARY_FLAG_CLASS + "/")]
    chosen = primary or sites
    values = {site.value for site in chosen}
    if values == {True}:
        verdict = "true"
    elif values == {False}:
        verdict = "false"
    else:
        verdict = "mixed"
    return verdict, (chosen[0].owner if primary else None)


def scan_swf(swf_bytes: bytes) -> dict:
    """解析 SWF，返回 {hosts, flag_sites, abc_count, string_count}。"""
    swf = decompress_swf(swf_bytes)
    hosts: dict[str, int] = {}
    sites: list[FlagSite] = []
    abc_count = 0
    string_count = 0
    for blob in iter_abc_blobs(swf):
        abc = AbcFile(blob)
        abc_count += 1
        string_count += len(abc.strings) - 1
        for host, count in find_hosts_in_strings(abc.strings).items():
            hosts[host] = hosts.get(host, 0) + count
        sites.extend(find_flag_sites(abc))
    if not abc_count:
        raise ScanError("SWF 里没有 DoABC 标签")
    return {
        "hosts": hosts,
        "flag_sites": sites,
        "abc_count": abc_count,
        "string_count": string_count,
    }


def raw_scan_bytes(data: bytes, include_domains: bool = False) -> dict[str, tuple[int, bool]]:
    """降级模式：在原始字节里搜 host 模式，返回 {host: (次数, 是否被截断)}。"""
    found: dict[str, tuple[int, bool]] = {}
    pattern = RAW_HOST_RE if include_domains else RAW_IPV4_RE
    for match in pattern.finditer(data):
        text = match.group().decode("ascii", "replace")
        text, trimmed = _trim_port(text)
        if not text or not _valid_host(text):
            continue
        count, was = found.get(text, (0, False))
        found[text] = (count + 1, was or trimmed)
    return found


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_swf_from_apk(path: Path, member: str = SWF_MEMBER) -> bytes:
    with zipfile.ZipFile(path) as archive:
        names = [info.filename for info in archive.infolist()]
        if member not in names:
            raise ScanError(f"APK 内没有 {member}")
        return archive.read(member)


def scan_apk_raw(path: Path, include_domains: bool = False) -> dict[str, tuple[int, bool]]:
    found: dict[str, tuple[int, bool]] = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            try:
                data = archive.read(info)
            except (RuntimeError, zipfile.BadZipFile):
                continue
            for host, (count, trimmed) in raw_scan_bytes(data, include_domains).items():
                prev, was = found.get(host, (0, False))
                found[host] = (prev + count, was or trimmed)
    return found


def is_ipv4_host(text: str) -> bool:
    host, _, port = text.rpartition(":")
    parts = host.split(".")
    return (
        port.isdigit()
        and len(parts) == 4
        and all(p.isdigit() and len(p) <= 3 and int(p) <= 255 for p in parts)
    )


def build_report(
    path: Path,
    *,
    mode: str = "auto",
    member: str = SWF_MEMBER,
    expect: str | None = None,
    forbid: Iterable[str] = (),
    raw_domains: bool = False,
) -> dict:
    """扫描一个 APK/SWF 并组装报告（只读）。"""
    path = Path(path)
    forbid = list(forbid)
    wanted = [h for h in ([expect] if expect else []) + forbid]
    if any(not is_ipv4_host(h) for h in wanted):
        raw_domains = True  # 断言里出现了域名，raw 模式必须放宽才可能命中
    if not path.is_file():
        raise ScanError(f"文件不存在: {path}")
    is_apk = zipfile.is_zipfile(path)
    report: dict = {
        "schema_version": 1,
        "input": {
            "path": str(path),
            "kind": "apk" if is_apk else "swf",
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        },
        "mode": mode,
        "server_addresses": [],
        "login_flag": {"name": LOGIN_FLAG_NAME.decode(), "sites": [], "verdict": "unknown"},
        "checks": [],
        "notes": [],
    }

    hits: list[HostHit] = []
    used_mode = mode
    if mode in ("auto", "abc"):
        try:
            swf_bytes = load_swf_from_apk(path, member) if is_apk else path.read_bytes()
            result = scan_swf(swf_bytes)
        except ScanError as exc:
            if mode == "abc":
                raise
            report["notes"].append(f"ABC 模式失败，降级为 raw：{exc}")
            used_mode = "raw"
        else:
            used_mode = "abc"
            report["swf"] = {
                "member": member if is_apk else None,
                "size": len(swf_bytes),
                "sha256": hashlib.sha256(swf_bytes).hexdigest(),
                "abc_tags": result["abc_count"],
                "constant_strings": result["string_count"],
            }
            hits = [
                HostHit(host, count, False, "abc-constant-pool")
                for host, count in sorted(result["hosts"].items())
            ]
            sites = result["flag_sites"]
            report["login_flag"]["sites"] = [
                {"owner": site.owner, "value": site.value, "method": site.method}
                for site in sorted(sites, key=lambda s: (s.owner, s.method))
            ]
            verdict, primary = judge_flag(sites)
            report["login_flag"]["verdict"] = verdict
            report["login_flag"]["primary_owner"] = primary
            if sites and primary is None:
                report["notes"].append(
                    f"没找到 {PRIMARY_FLAG_CLASS} 的 {LOGIN_FLAG_NAME.decode()} 赋值点，"
                    "③ 的结论是全部赋值点的合并，参考价值下降"
                )
    if used_mode == "raw":
        raw = (
            scan_apk_raw(path, raw_domains)
            if is_apk
            else raw_scan_bytes(path.read_bytes(), raw_domains)
        )
        hits = [
            HostHit(host, count, trimmed, "raw-bytes")
            for host, (count, trimmed) in sorted(raw.items())
        ]
        report["notes"].append("raw 模式不解析 ABC，sdkDummy 判定不可用")
        report["notes"].append(
            "raw 模式" + ("含域名形态，命中里会混进大量非服务器字符串"
                         if raw_domains else "只扫 IPv4:port，域名形态的地址扫不到")
        )
    report["mode"] = used_mode

    report["server_addresses"] = [
        {
            "value": hit.value,
            "occurrences": hit.occurrences,
            "ambiguous": hit.ambiguous,
            "where": hit.where,
            "note": KNOWN_HOSTS.get(hit.value, ""),
        }
        for hit in hits
    ]

    values = {hit.value for hit in hits}
    checks: list[dict] = []
    if expect:
        checks.append({
            "name": "expect-host",
            "ok": expect in values,
            "detail": f"期望指向 {expect}；实测 {sorted(values) or '无'}",
        })
    for host in forbid:
        checks.append({
            "name": f"forbid-host:{host}",
            "ok": host not in values,
            "detail": f"{host} " + ("仍在包里" if host in values else "已清除"),
        })
    report["checks"] = checks
    report["ok"] = all(check["ok"] for check in checks)
    return report


def format_report(report: dict) -> str:
    lines = [
        f"文件      : {report['input']['path']}",
        f"类型/大小 : {report['input']['kind']}  {report['input']['size']} B",
        f"sha256    : {report['input']['sha256']}",
        f"扫描模式  : {report['mode']}",
    ]
    swf = report.get("swf")
    if swf:
        lines.append(
            f"主 SWF    : {swf['size']} B  sha256={swf['sha256'][:16]}…  "
            f"DoABC×{swf['abc_tags']}  字符串×{swf['constant_strings']}"
        )
    lines.append("")
    lines.append("① 检测到的服务器地址：")
    if not report["server_addresses"]:
        lines.append("   （没扫到任何 host:port —— 这只包很可能不是 WF 客户端）")
    for entry in report["server_addresses"]:
        flag = "  ⚠端口可能粘连" if entry["ambiguous"] else ""
        note = f"   ← {entry['note']}" if entry["note"] else ""
        lines.append(f"   - {entry['value']}  ×{entry['occurrences']}{flag}{note}")
    lines.append("")
    lines.append("② 旧地址残留检查：")
    forbid_checks = [c for c in report["checks"] if c["name"].startswith("forbid-host:")]
    if not forbid_checks:
        lines.append("   （未指定 --forbid，跳过）")
    for check in forbid_checks:
        lines.append(f"   [{'OK' if check['ok'] else '失败'}] {check['detail']}")
    lines.append("")
    flag = report["login_flag"]
    lines.append(f"③ 免登录标记 {flag['name']}：{flag['verdict']}")
    primary = flag.get("primary_owner")
    for site in flag["sites"]:
        mark = "  ← 判定以此处为准" if site["owner"] == primary else ""
        lines.append(f"   - {site['owner']} → {str(site['value']).lower()}{mark}")
    if flag["verdict"] == "unknown":
        lines.append("   （没找到常量赋值指令；raw 模式下本项本来就不可用）")
    expect_checks = [c for c in report["checks"] if c["name"] == "expect-host"]
    if expect_checks:
        lines.append("")
        for check in expect_checks:
            lines.append(f"[{'OK' if check['ok'] else '失败'}] {check['detail']}")
    for note in report["notes"]:
        lines.append(f"注: {note}")
    lines.append("")
    lines.append("结论: " + ("全部断言通过" if report["ok"] else "有断言未通过"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="只读检查 WF 客户端 APK 指向哪台服务器（不修改任何文件）",
    )
    parser.add_argument("target", type=Path, help="APK 路径，或已解出的主 SWF")
    parser.add_argument("--expect", help="断言包内存在这个 host:port")
    parser.add_argument("--forbid", action="append", default=[],
                        help="断言包内不存在这个 host:port（可重复）")
    parser.add_argument("--mode", choices=("auto", "abc", "raw"), default="auto",
                        help="auto=先 ABC 失败再降级；raw=只搜原始字节")
    parser.add_argument("--swf-member", default=SWF_MEMBER, help="APK 内主 SWF 成员名")
    parser.add_argument("--raw-domains", action="store_true",
                        help="raw 模式下也扫域名形态（噪声很大，默认只扫 IPv4:port）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    try:
        report = build_report(
            args.target,
            mode=args.mode,
            member=args.swf_member,
            expect=args.expect,
            forbid=args.forbid,
            raw_domains=args.raw_domains,
        )
    except ScanError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
