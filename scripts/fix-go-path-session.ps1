# 安装 Go 后若当前终端仍报「找不到 go」，用本脚本把 Go 的 bin 加入「本窗口」的 PATH。
# 用法（注意开头的点与空格，会改当前 PowerShell 会话）：
#   cd 项目根目录
#   . .\scripts\fix-go-path-session.ps1
# 然后执行： go version

$candidates = @(
    "C:\Program Files\Go\bin",
    (Join-Path $env:LOCALAPPDATA "Programs\Go\bin")
)
foreach ($dir in $candidates) {
    $exe = Join-Path $dir "go.exe"
    if (Test-Path $exe) {
        if ($env:Path -notlike "*$dir*") {
            $env:Path = "$dir;$env:Path"
        }
        Write-Host "已在本会话加入 PATH: $dir" -ForegroundColor Green
        & $exe version
        return
    }
}
Write-Host "未找到 go.exe。若已安装，请完全退出并重新打开 Cursor/终端，或检查「系统环境变量」Path 是否包含 Go 的 bin。" -ForegroundColor Red
