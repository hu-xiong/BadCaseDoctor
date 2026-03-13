Param(
    [string]$ProjectRoot = "c:\Users\h2629\PycharmProjects\PythonProject\BadCaseDoctor"
)

Write-Host "=== BadCaseDoctor 沙箱 utils/tests 搬家 ==="
Write-Host "Project root:" $ProjectRoot

Set-Location $ProjectRoot

# 1) 创建 sandbox 相关目录
$dirs = @(
  ".\sandbox",
  ".\sandbox\utils",
  ".\sandbox\tests"
)
foreach ($d in $dirs) {
  if (!(Test-Path $d)) {
    Write-Host "Create directory:" $d
    New-Item -ItemType Directory -Path $d | Out-Null
  }
}

# 2) 创建 __init__.py（保持为 python 包）
$initFiles = @(
  ".\sandbox\__init__.py",
  ".\sandbox\utils\__init__.py",
  ".\sandbox\tests\__init__.py"
)
foreach ($f in $initFiles) {
  if (!(Test-Path $f)) {
    Write-Host "Create file:" $f
    New-Item -ItemType File -Path $f | Out-Null
  }
}

# 3) 移动 utils 下的沙箱相关实现
$utilsToMove = @(
  "utils\cloud_sandbox_client.py",
  "utils\wsl2_sandbox.py",
  "utils\nsjail_sandbox.py"
)
foreach ($rel in $utilsToMove) {
  $src = Join-Path "." $rel
  if (Test-Path $src) {
    $dst = Join-Path ".\sandbox\utils" ([IO.Path]::GetFileName($src))
    Write-Host "Move $src -> $dst"
    Move-Item -Path $src -Destination $dst -Force
  } else {
    Write-Host "Skip (not found): $src"
  }
}

# 4) 移动沙箱测试脚本到 sandbox/tests
$testSrc = ".\sandbox\test_sandbox.py"
if (Test-Path $testSrc) {
  $testDst = ".\sandbox\tests\test_sandbox.py"
  Write-Host "Move $testSrc -> $testDst"
  Move-Item -Path $testSrc -Destination $testDst -Force
} else {
  Write-Host "Skip (not found): $testSrc"
}

Write-Host "=== 搬家完成：请回到助手，让我帮你改 import 引用 ==="

