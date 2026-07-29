#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给部署者出预签包：把已完成五合一补丁的基座 APK 重指向另一台服务器并重签。

只改 pinball.config.gbits.DevConfig_gf_android 里的 host:port 字符串（②号补丁的
落点），其余补丁字节不动。FFDec 单类 -replace + 复用 abyss 构建器的 rewrite_apk，
全程回读校验：

- DevConfig_gf_android：旧 host 全部出现处恰被替换为新 host，旧值零残留；
- DevConfig(core)：sdkDummy=true 仍在（①免登录未丢）；
- PixelArtCharacterView：站点 1 缩放标记仍在（⑤render-scale 未丢）；
- MemberView pcode：SCALE_RENDERER 计数与基座一致（⑤站点 2 未被重序列化破坏）。

keystore 口令只经 --ks-pass-env 指定的环境变量传给 apksigner，不落盘不进命令行。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ABYSS = HERE.parent / "abyss-mode-equipment" / "build_apk.py"

_spec = importlib.util.spec_from_file_location("abyss_build_apk_for_repoint", ABYSS)
abyss = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = abyss
_spec.loader.exec_module(abyss)

GF_CLASS = "pinball.config.gbits.DevConfig_gf_android"
CORE_CLASS = "pinball.config.core.DevConfig"
SITE1_CLASS = "pinball.ui.component.pixelArtCharacter.PixelArtCharacterView"
MEMBERVIEW_CLASS = "pinball.scene.battle.battle.squad.member.MemberView"
MEMBERVIEW_PCODE_REL = Path(
    "scripts/pinball/scene/battle/battle/squad/member/MemberView.pcode"
)
HOST_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}\b")
SITE1_MARKERS = ("_loc12_.scale = _loc12_.scale / 6;", "_loc12_.scale /= 6;")


def run(cmd) -> None:
    print(">>", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True)


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def export_scripts(java, ffdec, swf: Path, dest: Path, classes: str) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    run([java, "-Xmx4g", "-jar", ffdec, "-air", "-onerror", "abort",
         "-selectclass", classes, "-export", "script", dest, swf])


def export_pcode(java, ffdec, swf: Path, dest: Path, cls: str) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    run([java, "-Xmx4g", "-jar", ffdec, "-air", "-format", "script:pcode",
         "-selectclass", cls, "-export", "script", dest, swf])
    out = dest / MEMBERVIEW_PCODE_REL
    assert out.is_file(), f"pcode 导出缺文件: {out}"
    return out


def find_as(dest: Path, cls: str) -> Path:
    rel = Path("scripts") / Path(*cls.split(".")).with_suffix(".as")
    out = dest / rel
    assert out.is_file(), f"脚本导出缺文件: {out}"
    return out


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, type=Path,
                    help="五合一基座 APK（真机验证过的那只）")
    ap.add_argument("--host", required=True,
                    help="新服务器 host:port，如 192.168.1.10:8001")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("--ffdec", required=True, type=Path)
    ap.add_argument("--java", required=True, type=Path)
    ap.add_argument("--zipalign", required=True, type=Path)
    ap.add_argument("--apksigner", required=True, type=Path)
    ap.add_argument("--ks", required=True, type=Path)
    ap.add_argument("--ks-pass-env", required=True)
    a = ap.parse_args()

    if not HOST_RE.fullmatch(a.host):
        raise SystemExit(f"--host 不是 ip:port 形式: {a.host}")
    if a.ks_pass_env not in os.environ:
        raise SystemExit(f"{a.ks_pass_env} 未设置")

    a.work.mkdir(parents=True, exist_ok=True)
    tx = Path(tempfile.mkdtemp(prefix=".repoint-", dir=a.work)).resolve()
    original = tx / "original.swf"
    repointed = tx / "repointed.swf"
    unsigned = tx / "unsigned.apk"
    aligned = tx / "aligned.apk"
    signed = tx / "signed.apk"

    abyss._extract_original_swf(a.base, original)

    # 1) 导出三类 + MemberView pcode 基线
    pre = tx / "pre_export"
    export_scripts(a.java, a.ffdec, original, pre,
                   f"{GF_CLASS},{CORE_CLASS},{SITE1_CLASS}")
    gf_as = find_as(pre, GF_CLASS)
    core_text = read_text(find_as(pre, CORE_CLASS))
    site1_text = read_text(find_as(pre, SITE1_CLASS))
    assert "sdkDummy:Boolean = true" in core_text.replace("  ", " "), \
        "基座缺①免登录(sdkDummy=true)"
    assert any(m in site1_text for m in SITE1_MARKERS), "基座缺⑤站点1标记"
    base_pcode = export_pcode(a.java, a.ffdec, original, tx / "pre_pcode",
                              MEMBERVIEW_CLASS)
    base_sr_count = read_text(base_pcode).count("SCALE_RENDERER")

    # 2) 改 host（要求基座内恰一个既有 host 值，全部出现处统一替换）
    gf_text = read_text(gf_as)
    hosts = sorted(set(HOST_RE.findall(gf_text)))
    if len(hosts) != 1:
        raise SystemExit(f"基座 DevConfig_gf_android 内 host 值不唯一: {hosts}")
    old_host = hosts[0]
    n = gf_text.count(old_host)
    new_text = gf_text.replace(old_host, a.host)
    edited = tx / "DevConfig_gf_android.repointed.as"
    edited.write_text(new_text, encoding="utf-8")
    print(f"[HOST] {old_host} -> {a.host} ({n} 处)")

    # 3) 单类替换回 SWF
    run([a.java, "-Xmx4g", "-jar", a.ffdec, "-air", "-onerror", "abort",
         "-replace", original, repointed, GF_CLASS, edited])
    assert repointed.is_file(), "repointed swf 未生成"

    # 4) 回读校验
    post = tx / "post_export"
    export_scripts(a.java, a.ffdec, repointed, post,
                   f"{GF_CLASS},{CORE_CLASS},{SITE1_CLASS}")
    gf_after = read_text(find_as(post, GF_CLASS))
    assert a.host in gf_after, "回读未见新 host"
    assert old_host not in gf_after, "回读仍有旧 host 残留"
    assert "sdkDummy:Boolean = true" in read_text(find_as(post, CORE_CLASS)).replace("  ", " "), \
        "①免登录在替换后丢失"
    assert any(m in read_text(find_as(post, SITE1_CLASS)) for m in SITE1_MARKERS), \
        "⑤站点1标记在替换后丢失"
    post_pcode = export_pcode(a.java, a.ffdec, repointed, tx / "post_pcode",
                              MEMBERVIEW_CLASS)
    post_sr_count = read_text(post_pcode).count("SCALE_RENDERER")
    assert post_sr_count == base_sr_count, \
        f"⑤站点2疑似被破坏: SCALE_RENDERER {base_sr_count} -> {post_sr_count}"

    # 5) 回封 + 对齐 + 签名 + 验签
    abyss.rewrite_apk(a.base, unsigned, repointed)
    run([a.zipalign, "-p", "-f", "4", unsigned, aligned])
    run([a.apksigner, "sign", "--v4-signing-enabled", "false",
         "--ks", a.ks, "--ks-pass", f"env:{a.ks_pass_env}", "--out", signed, aligned])
    run([a.apksigner, "verify", "--verbose", signed])

    a.out.parent.mkdir(parents=True, exist_ok=True)
    os.replace(signed, a.out)
    report = {
        "schema_version": 1,
        "base_apk": {"path": str(a.base), "sha256": sha(a.base)},
        "output_apk": {"path": str(a.out), "sha256": sha(a.out)},
        "host_old": old_host,
        "host_new": a.host,
        "host_occurrences": n,
        "memberview_scale_renderer_count": post_sr_count,
        "checks": ["sdkDummy", "site1_marker", "site2_count", "host_swap"],
    }
    report_path = a.out.with_suffix(".build-report.json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    print("OK", a.out, "sha256=" + report["output_apk"]["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
