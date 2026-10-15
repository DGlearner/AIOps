param(
    [switch]$NoDocker,
    [switch]$NoSimulator,
    [switch]$NoFrontend,
    [switch]$WithDiagnosisWorker,
    [switch]$DryRun,
    [string]$Python = "python",
    [string]$CondaEnv = "crossllm-agent",
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$FrontendDir = Join-Path $RootDir "frontend"
$BackendWindowTitle = "CrossST Backend Stack"
$FrontendWindowTitle = "CrossST Frontend"

function Quote-PSString {
    param([string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function Test-PortInUse {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $connection
}

function Start-NamedPowerShell {
    param(
        [string]$Title,
        [string]$WorkingDirectory,
        [string]$Command
    )

    $shellPath = (Get-Process -Id $PID).Path
    $quotedTitle = Quote-PSString $Title
    $quotedWorkdir = Quote-PSString $WorkingDirectory
    $fullCommand = "`$Host.UI.RawUI.WindowTitle = $quotedTitle; Set-Location -LiteralPath $quotedWorkdir; $Command"

    if ($DryRun) {
        Write-Host "[dry-run] start window: $Title"
        Write-Host "[dry-run] command: $fullCommand"
        return
    }

    Start-Process -FilePath $shellPath -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $fullCommand
    )
}

function Resolve-CondaActivateBat {
    $candidate = Join-Path $env:USERPROFILE "anaconda3\Scripts\activate.bat"
    if (Test-Path $candidate) {
        return $candidate
    }
    return $null
}

function Quote-CmdArgument {
    param([string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

Write-Host "CrossST root: $RootDir"

if (-not $NoDocker) {
    if ($DryRun) {
        Write-Host "[dry-run] docker compose up -d"
    } else {
        Push-Location $RootDir
        docker compose up -d
        Pop-Location
    }
}

$backendArgs = @("scripts\run_dev_stack.py")
if (-not $NoSimulator) {
    $backendArgs += "--simulate"
}
if ($WithDiagnosisWorker) {
    $backendArgs += "--with-diagnosis-worker"
}

$backendCommandArgs = ($backendArgs | ForEach-Object { Quote-PSString $_ }) -join " "
$backendCommand = "& $(Quote-PSString $Python) $backendCommandArgs"
$condaActivate = Resolve-CondaActivateBat
if ($CondaEnv -and $condaActivate) {
    $scriptArgs = if ($backendArgs.Count -gt 1) {
        $backendArgs[1..($backendArgs.Count - 1)] -join " "
    } else {
        ""
    }
    $cmdPayload = "call $(Quote-CmdArgument $condaActivate) $CondaEnv && $Python scripts\run_dev_stack.py $scriptArgs"
    $backendCommand = "& cmd.exe /d /s /c $(Quote-PSString $cmdPayload)"
} elseif ($CondaEnv) {
    Write-Warning "Conda activate.bat not found. Backend window will use Python from PATH."
}
Start-NamedPowerShell -Title $BackendWindowTitle -WorkingDirectory $RootDir -Command $backendCommand

if (-not $NoFrontend) {
    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        throw "frontend\node_modules not found. Run npm install in frontend first."
    }

    if ((-not $DryRun) -and (Test-PortInUse -Port $FrontendPort)) {
        throw "Port $FrontendPort is already in use. Run scripts\stop_all.ps1 first, or close the old Vite server."
    }

    $frontendCommand = "npm run dev -- --port $FrontendPort --strictPort"
    Start-NamedPowerShell -Title $FrontendWindowTitle -WorkingDirectory $FrontendDir -Command $frontendCommand
}

Write-Host ""
Write-Host "CrossST startup requested."
Write-Host "Backend API: http://localhost:8888"
Write-Host "Frontend:    http://localhost:$FrontendPort"
Write-Host "Log ingest:  http://localhost:8100"
Write-Host "Kafka UI:    http://localhost:8080"
