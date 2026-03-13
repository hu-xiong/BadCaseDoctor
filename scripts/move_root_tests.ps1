Param(
    [string]$ProjectRoot = "c:\Users\h2629\PycharmProjects\PythonProject\BadCaseDoctor"
)

Write-Host "=== BadCaseDoctor 根目录 test*.py 归档 ==="
Write-Host "Project root:" $ProjectRoot

Set-Location $ProjectRoot

# 1) 创建 tests 目录（根目录下，与 sandbox/tests 区分：这里是根级手动测试脚本）
$testDir = ".\tests"
if (!(Test-Path $testDir)) {
    Write-Host "Create directory:" $testDir
    New-Item -ItemType Directory -Path $testDir | Out-Null
}

# 2) 根目录三个 test 开头的 py 移到 tests/
$filesToMove = @(
    "test.py",
    "test_search_tool.py",
    "test_smart_search.py"
)
foreach ($f in $filesToMove) {
    $src = Join-Path "." $f
    if (Test-Path $src) {
        $dst = Join-Path $testDir $f
        Write-Host "Move $src -> $dst"
        Move-Item -Path $src -Destination $dst -Force
    } else {
        Write-Host "Skip (not found): $src"
    }
}

Write-Host "=== 完成。运行方式: python tests/test_search_tool.py 等 ==="
