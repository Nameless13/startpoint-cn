#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给部署者出预签包：把已完成五合一补丁的基座 APK 重指向另一台服务器并重签。

只改 pinball.config.gbits.DevConfig_gf_android 里的 host:port 字符串（②号补丁的
落点），其余补丁字节不动。FFDec 单类 -replace + 复用 abyss 构建器的 rewrite_apk，
全程回读校验：

- DevConfig_gf_android：旧 host 全部出现处恰被替换为新 host，旧值零残留；
- DevConfig(core)：sdkDummy=true 仍在（①免登录未丢）；
- ⑤render-scale 的**三个**站点（pixel-art / member-view / character-cell）：
  用 render_scale_pcode 的权威校验器逐个复核，并比对重指向前后的
  canonical P-code 与原始 ABC 摘要，证明单类替换没有把任何一个站点重序列化坏。

单类 -replace 会让 FFDec 重写整份 ABC，所以“只动了一个类”不等于“别的类没变”；
站点清单必须与 render_scale_pcode.RENDER_SITES 同源，否则以后加了站点这里会漏。

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
RENDER_SCALE = HERE.parent / "offline-android" / "render_scale_pcode.py"


def _load(name: str, path: Path):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载依赖模块: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


abyss = _load("abyss_build_apk_for_repoint", ABYSS)
RENDER = _load("render_scale_pcode_for_repoint", RENDER_SCALE)

GF_CLASS = "pinball.config.gbits.DevConfig_gf_android"
CORE_CLASS = "pinball.config.core.DevConfig"
RENDER_SITE_IDS = RENDER.RENDER_SITE_IDS
HOST_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}\b")


def run(cmd) -> None:
    print(">>", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True)


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def export_scripts(java, ffdec, swf: Path, dest: Path, classes: str) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    run([java, "-Xmx4g", "-jar", ffdec, "-air", "-onerror", "abort",
         "-selectclass", classes, "-export", "script", dest, swf])


def render_fingerprints(java, ffdec, swf: Path, work: Path, profile: Path) -> dict:
    """三个 render-scale 站点的权威复核 + 摘要（校验器在 render_scale_pcode）。"""
    return RENDER.site_fingerprints(
        swf, ffdec=ffdec, java=java, profile_dir=profile, work_dir=work
    )


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

    profile = tx / "ffdec_profile"

    # 1) 基线：host/免登录来自 AS3 导出，render-scale 三站点走权威校验器
    pre = tx / "pre_export"
    export_scripts(a.java, a.ffdec, original, pre, f"{GF_CLASS},{CORE_CLASS}")
    gf_as = find_as(pre, GF_CLASS)
    core_text = read_text(find_as(pre, CORE_CLASS))
    assert "sdkDummy:Boolean = true" in core_text.replace("  ", " "), \
        "基座缺①免登录(sdkDummy=true)"
    base_sites = render_fingerprints(
        a.java, a.ffdec, original, tx / "pre_render", profile
    )
    print(f"[RENDER] 基座站点复核通过: {', '.join(RENDER_SITE_IDS)}")

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
    export_scripts(a.java, a.ffdec, repointed, post, f"{GF_CLASS},{CORE_CLASS}")
    gf_after = read_text(find_as(post, GF_CLASS))
    assert a.host in gf_after, "回读未见新 host"
    assert old_host not in gf_after, "回读仍有旧 host 残留"
    assert "sdkDummy:Boolean = true" in read_text(find_as(post, CORE_CLASS)).replace("  ", " "), \
        "①免登录在替换后丢失"
    post_sites = render_fingerprints(
        a.java, a.ffdec, repointed, tx / "post_render", profile
    )
    RENDER.assert_fingerprints_unchanged(base_sites, post_sites)
    print(f"[RENDER] 重指向后三站点等同: {', '.join(RENDER_SITE_IDS)}")

    # 5) 回封 + 对齐 + 签名 + 验签
    abyss.rewrite_apk(a.base, unsigned, repointed)
    run([a.zipalign, "-p", "-f", "4", unsigned, aligned])
    run([a.apksigner, "sign", "--v4-signing-enabled", "false",
         "--ks", a.ks, "--ks-pass", f"env:{a.ks_pass_env}", "--out", signed, aligned])
    run([a.apksigner, "verify", "--verbose", signed])

    a.out.parent.mkdir(parents=True, exist_ok=True)
    os.replace(signed, a.out)
    report = {
        # v2: 站点 1/2 的启发式探针换成三站点权威指纹（含 character-cell）。
        "schema_version": 2,
        "base_apk": {"path": str(a.base), "sha256": sha(a.base)},
        "output_apk": {"path": str(a.out), "sha256": sha(a.out)},
        "host_old": old_host,
        "host_new": a.host,
        "host_occurrences": n,
        "render_site_ids": list(RENDER_SITE_IDS),
        "render_sites_before": base_sites,
        "render_sites_after": post_sites,
        "checks": ["sdkDummy", "host_swap", *(f"render:{s}" for s in RENDER_SITE_IDS)],
    }
    report_path = a.out.with_suffix(".build-report.json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    print("OK", a.out, "sha256=" + report["output_apk"]["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
