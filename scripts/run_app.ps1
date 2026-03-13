# UTF-8 编码启动主应用（虚拟环境）
# 在项目根目录执行: .\scripts\run_app.ps1  或  pwsh -File scripts/run_app.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path $root)) { $root = (Get-Location).Path }
$venvPython = Join-Path $root "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "未找到 venv，请先创建虚拟环境: python -m venv venv"
    exit 1
}
$env:PYTHONUTF8 = "1"
Set-Location $root
& $venvPython app.py
