param(
    [switch]$KeepDocker,
    [switch]$DryRun,
    [int[]]$Ports = @(5173, 5174, 8888, 8100)
)

$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendWindowTitle = "CrossST Backend Stack"
$FrontendWindowTitle = "CrossST Frontend"

function Stop-ProcessTree {
    param([int]$ProcessId)

    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId ([int]$child.ProcessId)
    }

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return
    }

    if ($DryRun) {
        Write-Host "[dry-run] stop process tree pid=$ProcessId name=$($process.ProcessName)"
        return
    }

    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-WindowByTitle {
    param([string]$Title)

    $processes = Get-Process | Where-Object { $_.MainWindowTitle -like "$Title*" }
    foreach ($process in $processes) {
        Stop-ProcessTree -ProcessId $process.Id
    }
}

function Stop-PortOwners {
    param([int[]]$TargetPorts)

    foreach ($port in $TargetPorts) {
        $owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($owner in $owners) {
            if ($owner -and $owner -ne 0) {
                Write-Host "Stopping process listening on port $port pid=$owner"
                Stop-ProcessTree -ProcessId ([int]$owner)
            }
        }
    }
}

function Stop-ProjectProcesses {
    $rootText = [string]$RootDir
    $patterns = @(
        "scripts\run_dev_stack.py",
        "crossst.main",
        "crossst.workers.",
        "log_ingest.main",
        "scripts.simulate_log_clients",
        "vite"
    )

    $processes = Get-CimInstance Win32_Process | Where-Object {
        $commandLine = $_.CommandLine
        if ([string]::IsNullOrWhiteSpace($commandLine)) {
            return $false
        }
        if ($commandLine -notlike "*$rootText*") {
            return $false
        }
        foreach ($pattern in $patterns) {
            if ($commandLine -like "*$pattern*") {
                return $true
            }
        }
        return $false
    }

    foreach ($process in $processes) {
        Stop-ProcessTree -ProcessId ([int]$process.ProcessId)
    }
}

Write-Host "Stopping CrossST app processes..."
Stop-WindowByTitle -Title $BackendWindowTitle
Stop-WindowByTitle -Title $FrontendWindowTitle
Stop-PortOwners -TargetPorts $Ports
Stop-ProjectProcesses

if (-not $KeepDocker) {
    if ($DryRun) {
        Write-Host "[dry-run] docker compose down"
    } else {
        Push-Location $RootDir
        docker compose down
        Pop-Location
    }
}

Write-Host "CrossST stop requested."
