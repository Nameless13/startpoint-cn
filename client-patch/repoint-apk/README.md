# repoint-apk — 五合一 APK 重指向重签

给部署者出预签包：在**真机验证过的五合一基座 APK** 上只改服务器指向
（`pinball/config/gbits/DevConfig_gf_android` 的 `host:port` 字符串，即②号补丁落点），
其余补丁字节不动，重签后交付。适用场景：别的服主要一只指向他自己服务器的现成客户端，
但没有 FFDec/keystore 流水线。

## 用法

```powershell
$env:WF_APK_KS_PASS = "<keystore 口令>"   # 只走环境变量，不落盘不进命令行
python -X utf8 client-patch/repoint-apk/repoint_build.py `
  --base <五合一基座.apk> `
  --host 192.168.1.10:8001 `
  --out out/repoint-deployer/WorldFlipper-5in1-<host>.apk `
  --work out/repoint-deployer/work `
  --ffdec ffdec_26.2.1/ffdec.jar --java <java8> `
  --zipalign <zipalign> --apksigner <apksigner> `
  --ks <wf_new.keystore> --ks-pass-env WF_APK_KS_PASS
```

## 校验（构建内置，任一失败即中止）

- 基座与产物都要有：①`sdkDummy=true`、⑤站点1缩放标记；
- `DevConfig_gf_android` 内既有 host 值必须唯一，全部出现处统一替换、旧值零残留；
- MemberView pcode 的 `SCALE_RENDERER` 计数替换前后一致（⑤站点2未被重序列化破坏）；
- `apksigner verify` 通过后才落 `--out`，并写 `.build-report.json`。

## 注意

- 签名用 `wf_new.keystore`：与对方设备上旧包**同签名可覆盖安装保身份**；不同签名须
  卸载重装（本地身份被抹掉，存档在服务端 DB，服主按 device_id 重绑，见 self-host 指南）。
- 本工具只换指向，不打补丁；基座必须已是五合一成品（构建见
  `render-scale-v1/build_render_scale_apk.py` 链）。
