# 启动本机 go-local-proxy（默认 127.0.0.1:8794；/ws 为 run 协议，/pty 为嵌入式终端）
# 用法：在项目根目录
#   powershell -ExecutionPolicy Bypass -File .\scripts\run-go-local-proxy.ps1
# 若提示「禁止运行脚本」，可用同目录 run-go-local-proxy.cmd（双击或 cmd 里运行）
# 可选：先编译  .\client_binaries\badcase-local-proxy.exe（见 go-local-proxy 目录注释）

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$exe = Join-Path $root "client_binaries\badcase-local-proxy.exe"
if (-not (Test-Path $exe)) {
    Write-Host "未找到 $exe" -ForegroundColor Yellow
    Write-Host "请先编译: cd go-local-proxy; go build -ldflags=\"-s -w\" -o ..\client_binaries\badcase-local-proxy.exe ." -ForegroundColor Gray
    exit 1
}

Write-Host "启动本地 Go 代理: $exe" -ForegroundColor Cyan
Write-Host "  HTTP /health: http://127.0.0.1:8794/health" -ForegroundColor Gray
Write-Host "  WebSocket run: ws://127.0.0.1:8794/ws  |  pty: ws://127.0.0.1:8794/pty" -ForegroundColor Gray
Write-Host "  修改源码后请先 go build 再运行，否则仍是旧 exe。" -ForegroundColor DarkGray
& $exe
