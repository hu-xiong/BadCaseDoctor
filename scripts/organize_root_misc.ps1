Param(
    [string]$ProjectRoot = "c:\Users\h2629\PycharmProjects\PythonProject\BadCaseDoctor"
)

Write-Host "=== BadCaseDoctor 根目录杂项归档 ==="
Write-Host "Project root:" $ProjectRoot

Set-Location $ProjectRoot

# 1) 创建目标目录
$dirs = @(
  ".\var",        # 运行产生的日志/备份/本地 DB
  ".\tools",      # 一次性维护脚本 / 小工具
  ".\docs"        # 说明文档（如 SEARCH_TOOL_*.md）
)
foreach ($d in $dirs) {
  if (!(Test-Path $d)) {
    Write-Host "Create directory:" $d
    New-Item -ItemType Directory -Path $d | Out-Null
  }
}

# 2) 运行期生成的文件 → var/
$runtimeFiles = @(
  "backend.log",
  "badcase_backup.txt",
  "badcase_doctor.db",
  "ahareAccessToken.txt",
  "cookies.txt"
)
foreach ($rel in $runtimeFiles) {
  $src = Join-Path "." $rel
  if (Test-Path $src) {
    $dst = Join-Path ".\var" ([IO.Path]::GetFileName($src))
    Write-Host "Move $src -> $dst"
    Move-Item -Path $src -Destination $dst -Force
  } else {
    Write-Host "Skip (not found): $src"
  }
}

# 3) 维护脚本 / 模板 → tools/
$toolFiles = @(
  "create_excel_template.py",
  "badcase_template.xlsx",
  "fix_plan_type.py",
  "fix_status_values.py",
  "permission.py"
)
foreach ($rel in $toolFiles) {
  $src = Join-Path "." $rel
  if (Test-Path $src) {
    $dst = Join-Path ".\tools" ([IO.Path]::GetFileName($src))
    Write-Host "Move $src -> $dst"
    Move-Item -Path $src -Destination $dst -Force
  } else {
    Write-Host "Skip (not found): $src"
  }
}

# 4) 说明文档 → docs/（如果还在根目录）
$docFiles = @(
  "EMAIL_SETUP.md",
  "SEARCH_TOOL_COMPLETION.md",
  "SEARCH_TOOL_IMPLEMENTATION.md",
  "SEARCH_TOOL_QUICK_TEST.md"
)
foreach ($rel in $docFiles) {
  $src = Join-Path "." $rel
  if (Test-Path $src) {
    $dst = Join-Path ".\docs" ([IO.Path]::GetFileName($src))
    Write-Host "Move $src -> $dst"
    Move-Item -Path $src -Destination $dst -Force
  } else {
    Write-Host "Skip (not found): $src"
  }
}

Write-Host "=== 根目录杂项归档完成（代码引用未受影响） ==="

