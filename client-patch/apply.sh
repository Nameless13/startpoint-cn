#!/usr/bin/env bash
# 最小客户端补丁:免登录 + API 重定向
# 用法: bash apply.sh <AS3_EXPORT_DIR> <host:port>
# 说明: 作用于 FFDec 反编译出的 AS3 导出目录;用 perl 做语义字符串替换,
#       规避 macOS/Linux sed -i 差异。原创实现,不含 starview 代码。
set -euo pipefail

EXPORT_DIR="${1:?用法: apply.sh <AS3_EXPORT_DIR> <host:port>}"
API_HOST="${2:?用法: apply.sh <AS3_EXPORT_DIR> <host:port>}"

dev=$(find "$EXPORT_DIR" -name DevConfig.as -path '*/core/*' | head -1)
gf=$(find "$EXPORT_DIR" -name DevConfig_gf_android.as | head -1)
[ -n "$dev" ] || { echo "未找到 DevConfig.as"; exit 1; }
[ -n "$gf" ]  || { echo "未找到 DevConfig_gf_android.as"; exit 1; }

perl -pi -e 's/public static var sdkDummy:Boolean = false;/public static var sdkDummy:Boolean = true;/' "$dev"
perl -pi -e 's/shijtswygamegf\.leiting\.com/'"$API_HOST"'/g; s/"https"/"http"/' "$gf"

echo "[OK] 免登录: $dev"
echo "[OK] 重定向→$API_HOST: $gf"
