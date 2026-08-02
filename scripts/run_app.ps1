# UTF-8 编码启动主应用（虚拟环境）
# 在项目根目录执行: .\scripts\run_app.ps1  或  pwsh -File scripts/run_app.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $root "app.py"))) {
    $root = (Get-Location).Path
}
$venvCandidates = @(
    (Join-Path $root ".venv\Scripts\python.exe"),
    (Join-Path $root "venv\Scripts\python.exe")
)
$venvPython = $venvCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $venvPython) {
    Write-Host "未找到虚拟环境，请先: python -m venv .venv"
    exit 1
}
$env:PYTHONUTF8 = "1"
if (-not $env:FLASK_DEBUG) { $env:FLASK_DEBUG = "0" }
if (-not $env:BADCASE_USE_WAITRESS) { $env:BADCASE_USE_WAITRESS = "1" }
if (-not $env:PAYMENT_PROVIDER) { $env:PAYMENT_PROVIDER = "mock" }
if (-not $env:PAYMENT_MOCK_ENABLED) { $env:PAYMENT_MOCK_ENABLED = "1" }
# Electron 打包客户端（file://）跨域登录联调；纯浏览器同源开发可关掉
if (-not $env:CORS_ALLOW_NULL_ORIGIN) { $env:CORS_ALLOW_NULL_ORIGIN = "1" }
if (-not $env:TRUST_PROXY) { $env:TRUST_PROXY = "1" }
Set-Location $root
Write-Host "启动: $venvPython server_wsgi.py (cwd=$root)"
& $venvPython server_wsgi.py
