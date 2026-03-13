Param(
    [string]$ProjectRoot = "c:\Users\h2629\PycharmProjects\PythonProject\BadCaseDoctor"
)

Write-Host "=== BadCaseDoctor 沙箱脚本搬家 ==="
Write-Host "Project root:" $ProjectRoot

Set-Location $ProjectRoot

# 1) 创建 sandbox 目录
if (!(Test-Path ".\sandbox")) {
  Write-Host "Create directory: .\sandbox"
  New-Item -ItemType Directory -Path ".\sandbox" | Out-Null
}

# 2) 创建 __init__.py（如果还没有）
if (!(Test-Path ".\sandbox\__init__.py")) {
  Write-Host "Create file: .\sandbox\__init__.py"
  New-Item -ItemType File -Path ".\sandbox\__init__.py" | Out-Null
}

# 3) 定义要移动的沙箱相关脚本
$filesToMove = @(
  "server_sandbox.py",
  "scripts\run_local_sandbox.py",
  "scripts\sandbox_cleanup.py",
  "scripts\sandbox_oneclick.py",
  "scripts\test_sandbox.py"
)

foreach ($rel in $filesToMove) {
  $src = Join-Path "." $rel
  if (Test-Path $src) {
    $dst = Join-Path ".\sandbox" ([IO.Path]::GetFileName($src))
    Write-Host "Move $src -> $dst"
    Move-Item -Path $src -Destination $dst -Force
  } else {
    Write-Host "Skip (not found): $src"
  }
}

Write-Host "=== 搬家完成：请回到助手，让我帮你改 import 引用 ==="

