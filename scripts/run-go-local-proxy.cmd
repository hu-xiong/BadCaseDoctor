@echo off
chcp 65001 >nul
REM 无需修改 PowerShell 执行策略，直接启动本地 Go 代理
cd /d "%~dp0.."
if not exist "client_binaries\badcase-local-proxy.exe" (
  echo 未找到 client_binaries\badcase-local-proxy.exe
  echo 请在 go-local-proxy 目录执行: go build -ldflags="-s -w" -o ..\client_binaries\badcase-local-proxy.exe .
  exit /b 1
)
echo 启动: http://127.0.0.1:8794/health  ws_run=ws://127.0.0.1:8794/ws  ws_pty=ws://127.0.0.1:8794/pty
echo 修改过 go-local-proxy 源码后请先 go build 再运行本脚本，否则仍是旧 exe。
"client_binaries\badcase-local-proxy.exe"
