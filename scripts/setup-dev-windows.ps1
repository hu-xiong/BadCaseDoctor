# BadCase Doctor — Windows 开发环境一键准备（Python 虚拟环境 + 前端依赖 + 可选 Go 本地代理）
# 在项目根目录执行:  powershell -ExecutionPolicy Bypass -File .\scripts\setup-dev-windows.ps1
# 或:  cd 到项目根后  .\scripts\setup-dev-windows.ps1

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# winget/MSI 安装 Go 后，已打开的终端往往仍无 PATH；本会话内补全，避免找不到 go
foreach ($dir in @("C:\Program Files\Go\bin", (Join-Path $env:LOCALAPPDATA "Programs\Go\bin"))) {
    if (Test-Path (Join-Path $dir "go.exe")) {
        if ($env:Path -notlike "*$dir*") {
            $env:Path = "$dir;$env:Path"
        }
        break
    }
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Test-Cmd($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

Write-Host ""
Write-Host "=== BadCase Doctor / 工作环境准备 (Windows) ===" -ForegroundColor Cyan
Write-Host "项目目录: $ProjectRoot"
Write-Host ""

# ---------- Python ----------
Write-Host "[1/4] Python" -ForegroundColor Yellow
$py = $null
if (Test-Cmd "py") {
    $py = "py"
} elseif (Test-Cmd "python") {
    $py = "python"
}
if (-not $py) {
    Write-Host "  未检测到 Python。请安装 3.10+： https://www.python.org/downloads/  （勾选 Add python.exe to PATH）" -ForegroundColor Red
    exit 1
}
$ver = & $py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "  当前: $py -> $ver"
$venvPy = Join-Path $ProjectRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "  创建虚拟环境 venv ..."
    & $py -m venv venv
}
Write-Host "  安装 Python 依赖 (requirements.txt) ..."
& (Join-Path $ProjectRoot "venv\Scripts\python.exe") -m pip install -U pip wheel
& (Join-Path $ProjectRoot "venv\Scripts\python.exe") -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
Write-Host "  Python 依赖完成。" -ForegroundColor Green

# ---------- Node (Vue / Vite) ----------
Write-Host ""
Write-Host "[2/4] Node.js（electron-vue3）" -ForegroundColor Yellow
if (-not (Test-Cmd "node")) {
    Write-Host "  未检测到 Node.js。请安装 LTS： https://nodejs.org/  或使用: winget install OpenJS.NodeJS.LTS" -ForegroundColor Red
    exit 1
}
Write-Host "  node: $(node -v)  npm: $(npm -v)"
Push-Location (Join-Path $ProjectRoot "electron-vue3")
npm install
Pop-Location
Write-Host "  前端依赖完成。" -ForegroundColor Green

# ---------- Go（可选：本地代理 badcase-local-proxy） ----------
Write-Host ""
Write-Host "[3/4] Go（可选，用于 go-local-proxy）" -ForegroundColor Yellow
$goExe = $null
if (Test-Cmd "go") {
    $goExe = "go"
} elseif (Test-Path "C:\Program Files\Go\bin\go.exe") {
    $goExe = "C:\Program Files\Go\bin\go.exe"
}
if ($goExe) {
    Write-Host "  $($goExe): $(& $goExe version)"
    $gp = Join-Path $ProjectRoot "go-local-proxy"
    $outDir = Join-Path $ProjectRoot "client_binaries"
    if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }
    Push-Location $gp
    & $goExe mod tidy
    $winOut = Join-Path $outDir "badcase-local-proxy.exe"
    Write-Host "  编译 Windows 本地代理 -> $winOut"
    & $goExe build -ldflags="-s -w" -o $winOut .
    Pop-Location
    Write-Host "  badcase-local-proxy.exe 已生成（Web 下载用）。" -ForegroundColor Green
} else {
    Write-Host "  未安装 Go，已跳过。需要时安装: https://go.dev/dl/  或 winget install GoLang.Go" -ForegroundColor DarkGray
    Write-Host "  安装后可在 go-local-proxy 目录执行 go build -o ..\client_binaries\badcase-local-proxy.exe ." -ForegroundColor DarkGray
}

# ---------- 提示 ----------
Write-Host ""
Write-Host "[4/4] 后续手动项" -ForegroundColor Yellow
Write-Host "  - 配置项目根目录 .env（至少 DATABASE_URL、Redis、大模型 Key 等，见 config.py）" -ForegroundColor White
Write-Host "  - 启动 Redis（默认 127.0.0.1:6379）" -ForegroundColor White
Write-Host "  - 启动后端:  .\venv\Scripts\python.exe app.py   或  .\scripts\run_app.ps1" -ForegroundColor White
Write-Host "  - 启动 Web 前端:  cd electron-vue3 && npm run dev  （默认 http://localhost:5173 代理到 Flask :5000）" -ForegroundColor White
Write-Host "  - 本机 Go 命令代理（可选）:  scripts\run-go-local-proxy.cmd  或  powershell -ExecutionPolicy Bypass -File .\scripts\run-go-local-proxy.ps1" -ForegroundColor White
Write-Host ""
Write-Host "=== 完成 ===" -ForegroundColor Cyan
