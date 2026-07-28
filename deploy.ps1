<#
.SYNOPSIS
  startpoint-cn(release/modes-20260714 分支)一键部署脚本。

.DESCRIPTION
  在一台"什么都没有"的 Windows 电脑上,自动完成:
    装 Git/Node → clone 本仓库 → npm ci + 构建 → 生成 .env →
    校验/布局基础 CDN → 启动服务端 → currentTime 自检。

  唯一无法自动化的环节:基础 CDN(~11GB)须自备(官方源已停服,
  本仓库不分发版权资产)。放置位置见脚本输出指引。

.USAGE
  # 方式一:还没 clone,任意目录运行(需先下载本脚本):
  powershell -ExecutionPolicy Bypass -File deploy.ps1

  # 方式二:已在仓库根目录:
  powershell -ExecutionPolicy Bypass -File deploy.ps1 -Here

  # 自备 CDN 压缩包(zip,内含 cn/ 目录或其内容)一并布局:
  powershell -ExecutionPolicy Bypass -File deploy.ps1 -Here -CdnArchive D:\wf-base-cdn.zip
#>
param(
    [string]$InstallDir = (Join-Path (Get-Location) "startpoint-cn"),
    [string]$CdnArchive = "",
    [switch]$Here
)

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/kuronzzhan-droid/startpoint-cn.git"
$Branch  = "release/modes-20260714"

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

function Ensure-Tool($cmd, $wingetId, $name) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) { Ok "$name 已安装: $($found.Source)"; return }
    Step "安装 $name (winget)"
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "未找到 winget,请手动安装 $name 后重跑(Git: git-scm.com / Node LTS: nodejs.org)"
    }
    & winget install --id $wingetId -e --accept-source-agreements --accept-package-agreements
    # winget 装完后当前会话 PATH 不含新目录,补常见安装位
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "$name 安装后仍不可用,请开新终端重跑本脚本"
    }
}

# ---------- 1. 工具链 ----------
Step "检查工具链"
Ensure-Tool "git"  "Git.Git"        "Git"
Ensure-Tool "node" "OpenJS.NodeJS.LTS" "Node.js LTS"
$nodeVer = (& node --version).TrimStart("v")
if ([version]$nodeVer -lt [version]"20.19.0") {
    throw "Node $nodeVer 过旧,需要 >= 20.19.0(winget install OpenJS.NodeJS.LTS)"
}
Ok "Node $nodeVer"

# ---------- 2. 仓库 ----------
if ($Here -or (Test-Path ".git")) {
    $root = (Get-Location).Path
    Step "使用当前仓库: $root"
} else {
    Step "clone 仓库 → $InstallDir"
    if (-not (Test-Path $InstallDir)) {
        & git clone --branch $Branch --single-branch $RepoUrl $InstallDir
    } else {
        Warn "$InstallDir 已存在,跳过 clone(如需更新请自行 git pull)"
    }
    Set-Location $InstallDir
    $root = $InstallDir
}

# ---------- 3. 依赖与构建 ----------
Step "npm ci(首次数分钟)"
& npm ci
if ($LASTEXITCODE -ne 0) { throw "npm ci 失败" }
Step "构建服务端"
& npm run build:server
if ($LASTEXITCODE -ne 0) { throw "构建失败" }
Ok "构建完成"

# ---------- 4. .env ----------
if (-not (Test-Path ".env")) {
    Step "生成 .env(基于 .env.example)"
    Copy-Item ".env.example" ".env"
    Ok ".env 已生成:默认仅监听 127.0.0.1:8001"
    Warn "客户端在同一台电脑的模拟器里 → 保持默认即可(配合 adb reverse)"
    Warn "客户端在局域网其他设备 → 编辑 .env 把 CN_LISTEN_HOST 改为本机 LAN IP,并按注释配置管理令牌"
} else {
    Ok ".env 已存在,不覆盖"
}

# ---------- 5. 基础 CDN ----------
$cdnDir = Join-Path $root ".cdn\cn"
if (-not (Test-Path $cdnDir)) {
    if ($CdnArchive -ne "" -and (Test-Path $CdnArchive)) {
        Step "解压基础 CDN → .cdn\"
        Expand-Archive -Path $CdnArchive -DestinationPath (Join-Path $root ".cdn") -Force
        if (-not (Test-Path $cdnDir)) {
            # 压缩包也许直接是 cn 的内容而非 cn/ 目录
            $inner = Get-ChildItem (Join-Path $root ".cdn") -Directory | Select-Object -First 1
            if ($inner -and (Test-Path (Join-Path $inner.FullName "archive-common-diff"))) {
                Rename-Item $inner.FullName "cn"
            }
        }
    }
}
if (-not (Test-Path $cdnDir)) {
    Warn "缺少基础 CDN(~11GB,版权原因须自备,官方源已停服)"
    Warn "获取途径:WF 私服圈资源;放置到 $cdnDir"
    Warn "就绪后重跑: powershell -ExecutionPolicy Bypass -File deploy.ps1 -Here"
    Warn "(mod 增量内容已随仓库自带 assets/asset-patch/active/,无需另取)"
    exit 1
}
Ok "基础 CDN 就绪: $cdnDir"

# ---------- 6. 启动 + 自检 ----------
Step "启动服务端(start-cn.bat)"
Start-Process -FilePath (Join-Path $root "start-cn.bat") -WorkingDirectory $root
$baseUrl = "http://127.0.0.1:8001"
$okFlag = $false
foreach ($i in 1..30) {
    Start-Sleep -Seconds 2
    try {
        $resp = Invoke-RestMethod -Uri "$baseUrl/api/server/currentTime" -TimeoutSec 3
        $okFlag = $true; break
    } catch { }
}
if (-not $okFlag) { throw "60 秒内未通过 currentTime 自检,请看服务端窗口日志" }
Ok "服务端在线: $baseUrl"

# ---------- 7. 下一步指引 ----------
Step "部署完成,下一步"
Write-Host @"
  1) 客户端:照 docs/部署攻略.md 重打指向你服务器的 APK
     (通用 selfhost 包发布后可跳过重打:装包 + adb reverse tcp:8001 tcp:8001 即可)
  2) 模拟器(MuMu 12)装 APK,启动游戏自动增量更新到 mod 内容
  3) 管理后台: $baseUrl (邮件发放三位自制角色)
"@
