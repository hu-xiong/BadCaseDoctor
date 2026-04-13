# 可选：将 badcase-local-proxy 加入用户登录启动（快捷方式方式，非协议注册）
# 用法（需自行改 $ExePath）：
#   powershell -ExecutionPolicy Bypass -File .\scripts\protocol\windows-autostart-shortcut.ps1
param(
  [string] $ExePath = ""
)
if (-not $ExePath -or -not (Test-Path -LiteralPath $ExePath)) {
  Write-Host "请编辑本脚本或传入 -ExePath 指向 badcase-local-proxy.exe" -ForegroundColor Yellow
  exit 1
}
$startup = [Environment]::GetFolderPath('Startup')
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut((Join-Path $startup "BadCase Local Proxy.lnk"))
$shortcut.TargetPath = $ExePath
$shortcut.WorkingDirectory = (Split-Path -Parent $ExePath)
$shortcut.Save()
Write-Host "已写入启动文件夹: $startup" -ForegroundColor Green
