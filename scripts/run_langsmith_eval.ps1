# 定时/本地跑 LangSmith 金路径评测
# 用法:
#   .\scripts\run_langsmith_eval.ps1              # dry-run
#   .\scripts\run_langsmith_eval.ps1 -Upload      # 上传 LangSmith（需 LANGSMITH_API_KEY）
param(
    [switch]$Upload,
    [string]$Prefix = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $root "app.py"))) { $root = (Get-Location).Path }
Set-Location $root
$py = @(
    (Join-Path $root ".venv\Scripts\python.exe"),
    (Join-Path $root "venv\Scripts\python.exe"),
    "python"
) | Where-Object { $_ -eq "python" -or (Test-Path $_) } | Select-Object -First 1

$env:PYTHONPATH = $root
$env:LANGGRAPH_CHECKPOINTER = "memory"
$argsList = @("-m", "evals.langsmith.run_eval")
if ($Upload) { $argsList += "--upload" } else { $argsList += "--dry-run" }
if ($Prefix) { $argsList += @("--prefix", $Prefix) }
& $py @argsList
exit $LASTEXITCODE
