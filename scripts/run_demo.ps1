param(
    [string]$ReportPath = ".\artifacts\runtime\latest_evaluation.json",
    [string]$RequestReportPath = ".\artifacts\runtime\latest_requests.json",
    [string]$StorePath = ".\artifacts\runtime\memory.sqlite",
    [string]$PythonCommand = "python",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8765,
    [string]$SdkModule = "",
    [switch]$SkipTests,
    [switch]$NoServer
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$env:PYTHONPATH = "$ProjectRoot\src"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$InputPath = ".\data\samples\events.jsonl"
$SuitePath = ".\data\eval\office_memory_eval_v2.json"

function Invoke-PythonStep {
    param([string]$Title, [string[]]$Arguments)
    Write-Host "`n== $Title ==" -ForegroundColor Cyan
    & $PythonCommand -X utf8 @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Title failed with exit code $LASTEXITCODE"
    }
}

$DoctorArguments = @(
    "-m", "os_agent_memory.cli", "doctor",
    "--workspace", ".",
    "--input", $InputPath,
    "--suite", $SuitePath,
    "--host", $HostAddress,
    "--port", "$Port"
)
if ($SdkModule) {
    $DoctorArguments += @("--sdk-module", $SdkModule)
}

Invoke-PythonStep "Preflight" $DoctorArguments
Invoke-PythonStep "Sample memory pipeline" @(
    "-m", "os_agent_memory.cli", "demo", "--input", $InputPath
)
Invoke-PythonStep "Legacy v2 diagnostic (not a release gate)" @(
    "-m", "os_agent_memory.cli", "evaluate",
    "--suite", $SuitePath,
    "--split", "test",
    "--top-k", "3",
    "--summary-only",
    "--output", $ReportPath
)
Invoke-PythonStep "Frozen request quality gate" @(
    "-S", "scripts/evaluate_requests.py",
    "--size", "10000",
    "--require-frozen",
    "--output", $RequestReportPath
)
Invoke-PythonStep "Build SQLite v2 store" @(
    "-m", "os_agent_memory.cli", "build-store",
    "--input", $InputPath,
    "--output", $StorePath
)

if (-not $SkipTests) {
    Invoke-PythonStep "Automated tests" @(
        "-m", "unittest", "discover", "-s", "tests", "-v"
    )
}

Write-Host "`nLocal demo verification finished." -ForegroundColor Green
Write-Host "Report: $ReportPath"
Write-Host "Request metrics: $RequestReportPath"
Write-Host "SQLite store: $StorePath"
if ($NoServer) {
    Write-Host "Dashboard was not started because -NoServer was supplied."
    exit 0
}

Write-Host "Dashboard: http://${HostAddress}:$Port" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the local server."
& $PythonCommand -X utf8 -m os_agent_memory.cli serve `
    --input $InputPath `
    --database $StorePath `
    --host $HostAddress `
    --port $Port
if ($LASTEXITCODE -ne 0) {
    throw "Dashboard failed with exit code $LASTEXITCODE"
}
