# ============================================
# knowledge_base 定时扫描 — Windows 计划任务安装脚本
# ============================================
# 以管理员身份运行此脚本，创建每小时自动扫描的任务
#
# 用法:
#   PowerShell (管理员):  .\install_scheduled_task.ps1
#   PowerShell (管理员):  .\install_scheduled_task.ps1 -IntervalMinutes 30
#   PowerShell (管理员):  .\install_scheduled_task.ps1 -Remove   (卸载任务)
# ============================================

param(
    [int]$IntervalMinutes = 60,
    [switch]$Remove
)

$TaskName = "PPT_Master_KnowledgeBase_Watcher"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WatcherScript = Join-Path $ScriptDir "file_watcher.py"
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source

if (-not $PythonExe) {
    Write-Host "[错误] 找不到 Python，请确认已安装并添加到 PATH" -ForegroundColor Red
    exit 1
}

# ── 卸载任务 ────────────────────────────
if ($Remove) {
    Write-Host "正在卸载计划任务: $TaskName ..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    if ($?) {
        Write-Host "✓ 任务已卸载" -ForegroundColor Green
    } else {
        Write-Host "任务不存在或已卸载" -ForegroundColor Gray
    }
    exit 0
}

# ── 创建任务 ────────────────────────────
Write-Host "====================================" -ForegroundColor Cyan
Write-Host "  安装 PPT Master 知识库定时扫描任务" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  任务名称:   $TaskName"
Write-Host "  扫描间隔:   ${IntervalMinutes}分钟"
Write-Host "  Python:     $PythonExe"
Write-Host "  监控脚本:   $WatcherScript"
Write-Host "  工作目录:   $ScriptDir"
Write-Host ""

# 先移除旧任务（如果存在）
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# 任务操作：运行 python file_watcher.py --once
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$WatcherScript`" --once" `
    -WorkingDirectory $ScriptDir

# 触发器：每 IntervalMinutes 分钟执行一次
$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration ([TimeSpan]::MaxValue)

# 任务配置
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false `
    -MultipleInstances IgnoreNew

# 创建任务（以当前用户身份运行）
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "PPT Master: 每小时扫描 knowledge_base，检测新文件并自动触发全量流水线" `
        -Force

    Write-Host "✓ 计划任务已创建成功!" -ForegroundColor Green
    Write-Host ""
    Write-Host "  管理方式:" -ForegroundColor Yellow
    Write-Host "    1. 打开 Windows 任务计划程序 (taskschd.msc)" -ForegroundColor White
    Write-Host "    2. 查找任务: $TaskName"
    Write-Host "    3. 可手动运行、禁用或修改触发器"
    Write-Host ""
    Write-Host "  手动触发一次:" -ForegroundColor Yellow
    Write-Host "    Start-ScheduledTask -TaskName '$TaskName'"
    Write-Host ""
    Write-Host "  卸载任务:" -ForegroundColor Yellow
    Write-Host "    .\install_scheduled_task.ps1 -Remove"
} catch {
    Write-Host "✗ 创建任务失败: $_" -ForegroundColor Red
    Write-Host "  请以管理员身份运行 PowerShell 后重试" -ForegroundColor Yellow
}
